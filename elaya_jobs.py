"""
elaya_jobs.py — in-memory manager for GLOMOS jobs.

Why this replaces the original file-per-job store + threads:

* One job = one **subprocess** (glomos_worker.py): torch/ASE memory is returned to the OS when
  the job ends, a crash cannot take the web server down, and a job can really be killed.
* Structured events (``@@ELAYA@@{json}``) instead of regex scraping of stdout.
* Cancel (``CANCEL`` file + kill after a grace period) and wall-clock limit per job.
* A bounded queue (``ELAYA_MAX_JOBS`` concurrent, default 1) so a 512 MB - 2 GB instance is not
  overrun by several simultaneous ANI runs.
* Everything lives in the process: with a single waitress process there is nothing to persist.
  Jobs that finished are kept for ``ELAYA_JOB_TTL_MIN`` minutes (default 120).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from elaya_glomos.libreport import EVENT_PREFIX

HERE = os.path.dirname(os.path.abspath(__file__))

MAX_EVENTS = 4000
KILL_GRACE_S = 25.0

# ---- parameter handling -------------------------------------------------------------------
PRESETS = {
    "fast":     {"initpop": 6,  "matings": 4,  "mutants": 4,  "generations": 4,  "energy_cutoff": 6.0,  "cutoff_population": 6},
    "standard": {"initpop": 12, "matings": 8,  "mutants": 8,  "generations": 8,  "energy_cutoff": 8.0,  "cutoff_population": 10},
    "thorough": {"initpop": 30, "matings": 16, "mutants": 16, "generations": 20, "energy_cutoff": 10.0, "cutoff_population": 20},
}
LIMITS = {
    "initpop": (1, 60), "matings": (0, 40), "mutants": (0, 40), "generations": (0, 60),
    "energy_cutoff": (0.5, 40.0), "cutoff_population": (1, 40), "n_seeds": (1, 12),
    "random_seed": (0, 2147483646),
}
ANI_CHOICES = ("auto", "ANI1x", "ANI1ccx", "ANI2x")


def max_minutes_limit():
    try:
        return float(os.environ.get("ELAYA_MAX_MINUTES", "20"))
    except ValueError:
        return 20.0


def clamp_params(raw):
    """Validate / clamp the user parameters (never trust the browser)."""
    raw = dict(raw or {})
    preset = raw.get("preset")
    p = dict(PRESETS.get(preset, PRESETS["fast"]))
    p["preset"] = preset if preset in PRESETS else "custom" if raw else "fast"
    for key, (lo, hi) in LIMITS.items():
        if key in raw and raw[key] not in (None, ""):
            try:
                v = float(raw[key])
            except (TypeError, ValueError):
                raise ValueError("Parameter %s must be a number" % key)
            if v != v:                                      # NaN
                raise ValueError("Parameter %s is not a number" % key)
            v = max(lo, min(hi, v))
            p[key] = int(round(v)) if key != "energy_cutoff" else float(v)
    p.setdefault("n_seeds", 4)
    p.setdefault("random_seed", 0)
    model = raw.get("ani_model", "auto")
    if model not in ANI_CHOICES:
        raise ValueError("ani_model must be one of %s" % ", ".join(ANI_CHOICES))
    p["ani_model"] = model
    try:
        mm = float(raw.get("max_minutes", max_minutes_limit()))
    except (TypeError, ValueError):
        mm = max_minutes_limit()
    p["max_minutes"] = max(1.0, min(mm, max_minutes_limit()))
    return p


def write_input_txt(workdir, p, model):
    """INPUT.txt for elaya_glomos.heuristic_ga_rotamers."""
    txt = (
        "rotamer_seed        seed.xyz\n"
        "problem_file        problem.json\n\n"
        "# evolutive parameters\n"
        "nof_initpop         %(initpop)d\n"
        "nof_matings         %(matings)d\n"
        "nof_mutants         %(mutants)d\n\n"
        "# discrimination\n"
        "tol_similarity      0.95\n"
        "tol_energy          0.1\n"
        "cutoff_energy       %(energy_cutoff).3f\n"
        "cutoff_population   %(cutoff_population)d\n\n"
        "# stop criteria\n"
        "nof_generations     %(generations)d\n"
        "nof_repeats         2\n"
        "nof_stagnant        3\n"
        "max_minutes         %(max_minutes).2f\n\n"
        "# theory level\n"
        "calculator          %(model)s\n"
        "prec                2E-02 5E-03\n"
        "polish_prec         1E-03\n"
        "random_seed         %(random_seed)d\n"
    ) % dict(p, model=model)
    with open(os.path.join(workdir, "INPUT.txt"), "w") as fh:
        fh.write(txt)


# ---- job object ----------------------------------------------------------------------------
class Job:
    def __init__(self, job_id, workdir, meta):
        self.id = job_id
        self.workdir = workdir
        self.meta = meta                       # smiles, params, notes ... (sent to the client)
        self.events = []
        self.status = "queued"                 # queued | running | done | error | cancelled | timeout
        self.result = None
        self.error = None
        self.proc = None
        self.created = time.time()
        self.started = None
        self.finished = None
        self.cancel_requested = None
        self.finalize = None
        self.lock = threading.Lock()

    @property
    def done(self):
        return self.status in ("done", "error", "cancelled", "timeout")

    def push(self, evt):
        with self.lock:
            if len(self.events) >= MAX_EVENTS:
                # keep structure: drop oldest log lines first
                for k, e in enumerate(self.events):
                    if e.get("type") == "log":
                        del self.events[k]
                        break
                else:
                    del self.events[0]
                self.dropped = getattr(self, "dropped", 0) + 1
            self.events.append(evt)


class JobManager:
    def __init__(self, max_concurrent=None, ttl_minutes=None, base_dir=None, worker_cmd=None):
        self.max_concurrent = max_concurrent or int(os.environ.get("ELAYA_MAX_JOBS", "1"))
        self.ttl = 60.0 * (ttl_minutes or float(os.environ.get("ELAYA_JOB_TTL_MIN", "120")))
        self.base_dir = base_dir or tempfile.mkdtemp(prefix="elaya_jobs_")
        os.makedirs(self.base_dir, exist_ok=True)
        # worker_cmd(workdir, deadline_minutes) -> argv ; overridable for tests
        self.worker_cmd = worker_cmd or self._default_worker_cmd
        self.jobs = {}
        self.queue = []
        self.lock = threading.RLock()
        self._stop = False
        self._reaper = threading.Thread(target=self._reap_loop, daemon=True)
        self._reaper.start()

    # ---- public API ----
    @staticmethod
    def _default_worker_cmd(workdir, deadline_minutes):
        return [sys.executable, "-u", os.path.join(HERE, "glomos_worker.py"), workdir,
                "--deadline-minutes", "%.3f" % deadline_minutes]

    def submit(self, seed_xyz, problem, params, model, meta=None, finalize=None):
        """Create a job. Returns job id. ``problem`` is the JSON-serialisable Problem dict."""
        self._cleanup()
        job_id = uuid.uuid4().hex[:16]
        workdir = os.path.join(self.base_dir, job_id)
        os.makedirs(workdir)
        with open(os.path.join(workdir, "seed.xyz"), "w") as fh:
            fh.write(seed_xyz)
        with open(os.path.join(workdir, "problem.json"), "w") as fh:
            json.dump(problem, fh)
        write_input_txt(workdir, params, model)
        meta = dict(meta or {})
        meta.update({"params": params, "model": model})
        job = Job(job_id, workdir, meta)
        job.finalize = finalize
        with self.lock:
            self.jobs[job_id] = job
            self.queue.append(job_id)
        self._dispatch()
        return job_id

    def get(self, job_id):
        return self.jobs.get(job_id)

    def poll(self, job_id, cursor=0):
        job = self.jobs.get(job_id)
        if job is None:
            return None
        with job.lock:
            cursor = max(0, min(int(cursor), len(job.events)))
            events = job.events[cursor:]
            new_cursor = cursor + len(events)
        out = {"events": events, "cursor": new_cursor, "status": job.status, "done": job.done,
               "elapsed": round((job.finished or time.time()) - (job.started or job.created), 1)}
        if job.status == "queued":
            with self.lock:
                out["queue_position"] = self.queue.index(job_id) + 1 if job_id in self.queue else 0
        if job.error:
            out["error"] = job.error
        return out

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job is None:
            return False
        with self.lock:
            if job.status == "queued":
                if job_id in self.queue:
                    self.queue.remove(job_id)
                job.status = "cancelled"
                job.finished = time.time()
                job.push({"type": "log", "line": "Cancelled before start."})
                return True
        if job.status == "running":
            job.cancel_requested = time.time()
            with open(os.path.join(job.workdir, "CANCEL"), "w") as fh:
                fh.write("1")
            job.push({"type": "log", "line": "Cancel requested; stopping after the current step..."})
        return True

    def shutdown(self):
        self._stop = True
        for job in list(self.jobs.values()):
            if job.proc is not None and job.proc.poll() is None:
                job.proc.kill()

    # ---- internals ----
    def _dispatch(self):
        with self.lock:
            running = sum(1 for j in self.jobs.values() if j.status == "running")
            while self.queue and running < self.max_concurrent:
                jid = self.queue.pop(0)
                job = self.jobs.get(jid)
                if job is None or job.status != "queued":
                    continue
                job.status = "running"
                job.started = time.time()
                running += 1
                threading.Thread(target=self._run, args=(job,), daemon=True).start()

    def _run(self, job):
        minutes = job.meta["params"]["max_minutes"]
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        env["PYTHONPATH"] = HERE + os.pathsep + env.get("PYTHONPATH", "")
        cmd = self.worker_cmd(job.workdir, minutes)
        tail = []
        try:
            job.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                        encoding="utf-8", errors="replace", bufsize=1, env=env, cwd=job.workdir)
            killer = threading.Thread(target=self._watchdog, args=(job, minutes), daemon=True)
            killer.start()
            for raw in job.proc.stdout:
                line = raw.rstrip("\n")
                if line.startswith(EVENT_PREFIX):
                    try:
                        job.push(json.loads(line[len(EVENT_PREFIX):]))
                    except ValueError:
                        job.push({"type": "log", "line": line})
                elif line.strip():
                    tail.append(line)
                    tail = tail[-30:]
                    job.push({"type": "log", "line": line})
            job.proc.wait()
            self._finish(job, job.proc.returncode, tail)
        except Exception as exc:                                # noqa: BLE001
            job.error = "%s: %s" % (type(exc).__name__, exc)
            job.status = "error"
            job.finished = time.time()
            job.push({"type": "error", "message": job.error})
        finally:
            self._dispatch()

    def _watchdog(self, job, minutes):
        """Hard kill if the worker ignores the cooperative cancel / deadline."""
        while job.proc is not None and job.proc.poll() is None:
            time.sleep(1.0)
            now = time.time()
            over_deadline = now - job.started > 60.0 * minutes + KILL_GRACE_S
            over_cancel = job.cancel_requested and now - job.cancel_requested > KILL_GRACE_S
            if over_deadline or over_cancel:
                job.push({"type": "log", "line": "Worker did not stop in time: terminating it."})
                job.proc.kill()
                return

    def _finish(self, job, returncode, tail):
        path = os.path.join(job.workdir, "result.json")
        result = None
        if os.path.isfile(path):
            try:
                with open(path) as fh:
                    result = json.load(fh)
            except ValueError:
                result = None
        err_evt = next((e for e in reversed(job.events) if e.get("type") == "error"), None)
        reason = (result or {}).get("meta", {}).get("stop_reason")
        if result and job.finalize:
            try:
                result = job.finalize(result)
            except Exception as exc:                            # noqa: BLE001
                job.push({"type": "log", "line": "Post-processing failed: %s" % exc})
        if returncode == 0 and result and result["conformers"]:
            job.status = {"cancelled": "cancelled", "timeout": "timeout"}.get(reason, "done")
        elif result and result.get("conformers") and job.cancel_requested:
            job.status = "cancelled"
        else:
            job.status = "error"
            if err_evt:
                job.error = err_evt.get("message")       # already in the event stream: do not repeat it
            else:
                if returncode is not None and returncode < 0:
                    why = ("the worker was killed by signal %d (out of memory? GLOMOS needs ~1 GB of RAM)"
                           % -returncode)
                else:
                    why = "GLOMOS worker exited with code %s." % returncode
                job.error = ("%s %s" % (why, " | ".join(tail[-3:]))).strip()
                job.push({"type": "error", "message": job.error})
        job.result = result
        job.finished = time.time()
        job.push({"type": "end", "status": job.status})

    def _cleanup(self):
        now = time.time()
        with self.lock:
            for jid, job in list(self.jobs.items()):
                if job.done and job.finished and now - job.finished > self.ttl:
                    shutil.rmtree(job.workdir, ignore_errors=True)
                    del self.jobs[jid]

    def _reap_loop(self):
        while not self._stop:
            time.sleep(60)
            try:
                self._cleanup()
            except Exception:                                   # noqa: BLE001
                pass
