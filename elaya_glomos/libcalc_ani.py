"""
libcalc_ani.py — ANI (TorchANI) local optimisation for GLOMOS.

Changes with respect to the original version
--------------------------------------------
* torch/torchani are imported lazily (the module is importable without them, so
  health checks and unit tests do not pay for / depend on them).
* Models run in **float64** by default. The original float32 calculator has force
  noise of the order of 1e-4 eV/A at ~1e3 eV total energies, so a BFGS run asked
  for fmax = 1e-3 eV/A routinely exhausted its 200 steps (that is what the
  temporary "[diag]" print was chasing). Override with ELAYA_ANI_DTYPE=float32.
* LBFGS instead of BFGS (fewer steps for the same tolerance), with a per-structure
  convergence flag instead of silently accepting non-converged geometries.
* No ``multiprocessing.Process`` per generation: forking a process that already
  initialised OpenMP/torch can deadlock. Optimisation is sequential and in-process;
  torch parallelises each evaluation internally (ELAYA_TORCH_THREADS).
* A failure in one structure no longer aborts the generation.
* After relaxation each structure is re-validated (connectivity, stereocentres,
  E/Z): ANI starting from a strained geometry can open rings or transfer protons.
* Cooperative cancellation: ``Reporter.check()`` is polled from inside the
  optimiser so a timeout/cancel takes effect within a few steps.
"""
import os
import sys
import time
import contextlib
import warnings

from elaya_glomos.libreport import Stopped

warnings.filterwarnings("ignore", message="cuaev not installed")
# torchani 2.2.4 imports pkg_resources (deprecated) and warns about its optional data module;
# without these filters the warnings end up in the job log shown to the user.
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", message="Dependency not satisfied, torchani.data")
os.environ.setdefault("TORCHANI_NO_WARN_EXTENSIONS", "1")

ANI_INFO_FILES = {"ANI1x": "ani-1x_8x.info", "ANI1ccx": "ani-1ccx_8x.info", "ANI2x": "ani-2x_8x.info"}


class ModelLoadError(RuntimeError):
    """The ANI model could not be built (missing dependency or parameters). Fatal for a job."""


def ani_weights_status():
    """Which ANI parameter sets are already on disk (no torch import).

    torchani 2.2.4 ships *empty* placeholder files and downloads the real parameters from
    GitHub the first time a model is built.  The Dockerfile does that at build time; this
    check lets /api/health tell whether it happened.
    """
    import importlib.util
    spec = importlib.util.find_spec("torchani")
    if spec is None or not spec.origin:
        return {m: False for m in ANI_INFO_FILES}
    res_dirs = [os.path.join(os.path.dirname(spec.origin), "resources"),
                os.path.expanduser("~/.local/torchani")]
    out = {}
    for model, info in ANI_INFO_FILES.items():
        out[model] = any(os.path.isfile(os.path.join(d, info)) and os.path.getsize(os.path.join(d, info)) > 0
                         for d in res_dirs)
    return out


def _explain_model_error(opt, exc):
    """Turn the typical torchani failures into an actionable message."""
    text = "%s: %s" % (type(exc).__name__, exc)
    if isinstance(exc, ModuleNotFoundError) and "pkg_resources" in str(exc):
        hint = ("torchani 2.2.4 needs pkg_resources, removed in setuptools>=81. "
                "Install 'setuptools<81' (it is pinned in requirements.txt).")
    elif type(exc).__name__ == "BadZipFile" or "requests" in text.lower() or "connection" in text.lower():
        hint = ("The ANI parameters are not installed and could not be downloaded from GitHub. "
                "Build the Docker image again (it downloads them at build time) or run once with internet: "
                "python -c \"import torchani; torchani.models.%s()\"" % opt)
    else:
        hint = "Could not build the ANI model."
    return "%s (%s)" % (hint, text)

eVtokcalpermol = 23.060548012069496

# Calculators already built, by model name. Tests (or callers) may pre-populate it
# with any ASE calculator; real models are built on first use.
_MODEL_CACHE = {}
_TORCH_READY = False


@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w") as devnull:
        old = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old


def cpu_quota():
    """CPUs available to this container (cgroup quota; e.g. 0.1 on a Render free instance)."""
    try:
        with open("/sys/fs/cgroup/cpu.max") as fh:                       # cgroup v2: "quota period"
            quota, period = fh.read().split()[:2]
        if quota != "max":
            return float(quota) / float(period)
    except (OSError, ValueError):
        pass
    try:                                                                  # cgroup v1
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as fq, open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as fp:
            q, per = int(fq.read()), int(fp.read())
        if q > 0:
            return q / per
    except (OSError, ValueError):
        pass
    try:
        return float(len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return float(os.cpu_count() or 1)


def torch_threads():
    """ELAYA_TORCH_THREADS (int or 'auto'). auto = whole CPUs of the container, 1..4.

    More threads than CPUs only adds contention: on a 0.1-CPU instance torch must use 1."""
    env = os.environ.get("ELAYA_TORCH_THREADS", "auto").strip().lower()
    if env and env != "auto":
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return max(1, min(4, int(cpu_quota())))


def _prepare_torch():
    """Import torch once and apply thread / compatibility settings."""
    global _TORCH_READY
    import torch
    if not _TORCH_READY:
        try:
            torch.set_num_threads(torch_threads())
        except Exception:
            pass
        # torchani >= 2.7 calls torch.compiler.is_compiling(); absent in torch < 2.3
        try:
            if not hasattr(torch.compiler, "is_compiling"):
                torch.compiler.is_compiling = lambda: False
        except Exception:
            pass
        _TORCH_READY = True
    return torch


def get_calculator(opt="ANI1ccx"):
    """ASE calculator for an ANI model, built once per process and reused."""
    if opt in _MODEL_CACHE:
        return _MODEL_CACHE[opt]
    if opt not in ANI_INFO_FILES:
        raise ValueError("Unknown ANI model %r (valid: %s)" % (opt, ", ".join(ANI_INFO_FILES)))
    try:
        torch = _prepare_torch()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import torchani
        builders = {
            "ANI1x": torchani.models.ANI1x,
            "ANI1ccx": torchani.models.ANI1ccx,
            "ANI2x": torchani.models.ANI2x,
        }
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        with suppress_stdout():
            model = builders[opt]()
            if os.environ.get("ELAYA_ANI_DTYPE", "float64").lower() in ("float64", "double", "fp64"):
                model = model.double()
            model = model.to(device)
            _MODEL_CACHE[opt] = model.ase()
    except Exception as exc:                            # noqa: BLE001
        raise ModelLoadError(_explain_model_error(opt, exc)) from exc
    return _MODEL_CACHE[opt]


def torchani_versions():
    """Versions for provenance (does not import torch if it is not installed)."""
    out = {}
    for mod in ("torch", "torchani", "ase"):
        try:
            m = __import__(mod)
            out[mod] = getattr(m, "__version__", "unknown")
        except Exception:
            out[mod] = None
    return out


def relax(atoms, calculator, fmax_stages=(2e-2, 5e-3), max_steps=400, reporter=None):
    """Relax ``atoms`` (copy) with LBFGS through successive force thresholds (eV/A).

    out: (relaxed_atoms, info) with info = dict(converged, steps, seconds)
    raises Stopped if the reporter requests a stop.
    """
    from ase.optimize import LBFGS
    mol = atoms.copy()
    mol.info = dict(atoms.info)
    mol.calc = calculator
    t0 = time.time()
    steps, converged = 0, False
    for fmax in fmax_stages:
        dyn = LBFGS(mol, logfile=None, maxstep=0.15)
        if reporter is not None:
            dyn.attach(reporter.check, interval=3)
        converged = bool(dyn.run(fmax=fmax, steps=max_steps))
        steps += int(getattr(dyn, "nsteps", 0))
        if not converged:
            break
    return mol, {"converged": converged, "steps": steps, "seconds": time.time() - t0}


def ANI_single(atoms, opt="ANI1ccx", preclist=(2e-2, 5e-3), max_steps=400, reporter=None):
    """Relax one structure and store the ANI energy (kcal/mol) in info['e']."""
    calculator = get_calculator(opt)
    mol, info = relax(atoms, calculator, preclist, max_steps, reporter)
    mol.info["e"] = float(mol.get_potential_energy()) * eVtokcalpermol
    mol.info["converged"] = info["converged"]
    mol.info["steps"] = info["steps"]
    mol.info["seconds"] = info["seconds"]
    mol.calc = None
    return mol


def ANI(moleculelist, n_jobs=1, opt="ANI1ccx", preclist=(2e-2, 5e-3), problem=None,
        reporter=None, max_steps=400, keep_unconverged=False, sink=None, screening="ensemble"):
    """Relax a list of conformers of one molecule (batched, see libbatch.relax_many).

    in:
        n_jobs  accepted for backward compatibility (unused)
        problem optional Problem for post-relaxation validation
        keep_unconverged  if False, structures that did not reach the force threshold are discarded
        sink    optional list: each valid structure is appended as soon as it finishes, so a
                cancellation/timeout in the middle of a batch keeps what was already relaxed
        screening  "ensemble" (all networks) or "single" (first network only; faster, used to
                screen candidates; the final polish always uses the ensemble)
    out:
        list of relaxed ase.Atoms in input order (info: e, i, converged, steps, seconds)
    """
    from elaya_glomos.libbatch import make_evaluator, relax_many
    mols = list(moleculelist)
    if not mols:
        return []
    calculator = get_calculator(opt)
    total = len(mols)
    accepted = {}
    finished = set()

    def on_done(k, mol, info):
        finished.add(k)
        name = mols[k].info.get("i", "mol%d" % k)
        mol.info["e"] = info["energy_eV"] * eVtokcalpermol
        mol.info["converged"] = info["converged"]
        mol.info["steps"] = info["steps"]
        mol.info["seconds"] = info["seconds"]
        mol.calc = None
        reason = problem.why_invalid(mol, check_clash=False) if problem is not None else None
        if reason is None and not keep_unconverged and not info["converged"]:
            reason = "not converged in %d steps" % info["steps"]
        if reason is not None:
            msg = "%s: discarded after ANI relaxation (%s)" % (name, reason)
            if reporter is not None:
                reporter.log(msg)
                reporter.event("discard", name=name, reason=reason)
            else:
                print(msg)
            return
        accepted[k] = mol
        if sink is not None:
            sink.append(mol)
        if reporter is not None:
            reporter.event("optimized", name=name, index=len(accepted), total=total,
                           energy=mol.info["e"], steps=info["steps"], seconds=round(info["seconds"], 2))
            reporter.log("%s  E = %.4f kcal/mol  (%d steps, %.1f s)"
                         % (name, mol.info["e"], info["steps"], info["seconds"]))
        else:
            print("%s  E = %.4f kcal/mol  (%d steps)" % (name, mol.info["e"], info["steps"]))

    check = reporter.check if reporter is not None else None
    try:
        evaluator = make_evaluator(calculator, mols[0], screening)
        relax_many(mols, evaluator, preclist, max_steps, check=check, on_done=on_done)
    except (Stopped, ModelLoadError):
        raise
    except Exception as exc:                           # noqa: BLE001
        # isolate the failing structure(s): retry one by one with whatever did not finish
        msg = "batch relaxation failed (%s: %s); retrying one by one" % (type(exc).__name__, exc)
        if reporter is not None:
            reporter.log(msg)
        else:
            print(msg)
        for k in [k for k in range(total) if k not in finished]:
            name = mols[k].info.get("i", "mol%d" % k)
            try:
                ev = make_evaluator(calculator, mols[k], screening)
                relax_many([mols[k]], ev, preclist, max_steps, check=check,
                           on_done=lambda _i, mol, info, k=k: on_done(k, mol, info))
            except (Stopped, ModelLoadError):
                raise
            except Exception as exc2:                  # noqa: BLE001
                msg = "%s: optimisation failed (%s: %s)" % (name, type(exc2).__name__, exc2)
                if reporter is not None:
                    reporter.log(msg)
                else:
                    print(msg)
    return [accepted[k] for k in sorted(accepted)]
