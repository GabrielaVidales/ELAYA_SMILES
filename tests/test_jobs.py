import os
import sys
import time

import pytest

import elaya_jobs as ej

FAKE = os.path.join(os.path.dirname(__file__), "fake_worker.py")


def manager(tmp_path, mode="ok", **kw):
    os.environ["FAKE_MODE"] = mode
    return ej.JobManager(base_dir=str(tmp_path), worker_cmd=lambda wd, m: [sys.executable, "-u", FAKE, wd], **kw)


def submit(m, **over):
    p = ej.clamp_params({"preset": "fast", **over})
    return m.submit("2\nx\nH 0 0 0\nH 0 0 .7\n", {"bonds": [], "rotors": []}, p, "ANI1ccx", {"smiles": "[H][H]"})


def wait(m, jid, status=None, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        out = m.poll(jid)
        if (status and out["status"] == status) or (not status and out["done"]):
            return out
        time.sleep(0.05)
    raise AssertionError("timeout waiting for job: %s" % m.poll(jid))


def test_clamp_params_limits_and_validation():
    p = ej.clamp_params({"initpop": 10 ** 6, "generations": -5, "energy_cutoff": "7.5", "preset": "standard"})
    assert p["initpop"] == ej.LIMITS["initpop"][1] and p["generations"] == 0 and p["energy_cutoff"] == 7.5
    assert p["max_minutes"] <= ej.max_minutes_limit()
    with pytest.raises(ValueError):
        ej.clamp_params({"initpop": "abc"})
    with pytest.raises(ValueError):
        ej.clamp_params({"ani_model": "ANI9000"})
    assert ej.clamp_params({})["preset"] == "fast"


def test_input_file_written(tmp_path):
    m = manager(tmp_path)
    jid = submit(m)
    txt = open(os.path.join(m.get(jid).workdir, "INPUT.txt")).read()
    assert "nof_initpop" in txt and "calculator          ANI1ccx" in txt and "problem_file" in txt
    wait(m, jid)
    m.shutdown()


def test_job_completes_and_poll_cursor(tmp_path):
    m = manager(tmp_path)
    jid = submit(m)
    out = wait(m, jid)
    assert out["status"] == "done"
    assert m.get(jid).result["conformers"][0]["name"] == "c1"
    first = m.poll(jid, 0)
    again = m.poll(jid, first["cursor"])
    assert first["events"] and again["events"] == []
    assert any(e["type"] == "start" for e in first["events"])
    m.shutdown()


def test_crash_is_reported_as_error(tmp_path):
    m = manager(tmp_path, "crash")
    out = wait(m, submit(m))
    assert out["status"] == "error" and "code 3" in out["error"]
    m.shutdown()


def test_cancel_running_returns_partial(tmp_path):
    m = manager(tmp_path, "slow")
    jid = submit(m)
    wait(m, jid, "running")
    time.sleep(0.3)
    assert m.cancel(jid)
    out = wait(m, jid)
    assert out["status"] == "cancelled" and m.get(jid).result["conformers"]
    m.shutdown()


def test_queue_runs_one_at_a_time_and_cancel_queued(tmp_path):
    m = manager(tmp_path, "slow", max_concurrent=1)
    j1, j2 = submit(m), submit(m)
    wait(m, j1, "running")
    assert m.poll(j2)["status"] == "queued" and m.poll(j2)["queue_position"] == 1
    assert m.cancel(j2) and m.poll(j2)["status"] == "cancelled"
    m.cancel(j1); wait(m, j1)
    m.shutdown()


def test_watchdog_kills_deaf_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(ej, "KILL_GRACE_S", 1.0)
    m = manager(tmp_path, "deaf")
    jid = submit(m)
    wait(m, jid, "running"); time.sleep(0.5)
    m.cancel(jid)
    out = wait(m, jid, timeout=20)
    assert out["done"] and out["status"] == "error"          # killed before writing a result
    m.shutdown()


def test_unknown_job(tmp_path):
    m = manager(tmp_path)
    assert m.poll("nope") is None and m.cancel("nope") is False
    m.shutdown()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX signals")
def test_worker_killed_is_reported_as_memory_problem(tmp_path):
    m = manager(tmp_path, mode="oom")
    jid = submit(m)
    out = wait(m, jid)
    assert out["status"] == "error" and "killed by signal 9" in out["error"] and "memory" in out["error"]
    m.shutdown()


def test_worker_error_event_is_not_duplicated(tmp_path):
    m = manager(tmp_path, mode="error_event")
    jid = submit(m)
    out = wait(m, jid)
    assert out["status"] == "error" and out["error"] == "ModelLoadError: boom"
    errors = [e for e in m.poll(jid)["events"] if e["type"] == "error"]
    assert len(errors) == 1
    m.shutdown()
