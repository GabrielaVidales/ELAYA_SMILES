"""Stand-in for glomos_worker.py used by the job-manager tests: python fake_worker.py <workdir> [--deadline-minutes M]"""
import json, os, sys, time
wd = sys.argv[1]
mode = os.environ.get("FAKE_MODE", "ok")
P = "@@ELAYA@@"
def ev(**d):
    print(P + json.dumps(d), flush=True)
def write(reason, partial):
    conf = [{"name": "c1", "energy_kcal": -10.0, "rel_kcal": 0.0, "boltzmann_298": 1.0, "converged": True,
             "xyz": "2\n-10 c1\nH 0 0 0\nH 0 0 0.74\n"}]
    json.dump({"partial": partial, "meta": {"stop_reason": reason}, "conformers": conf}, open(os.path.join(wd, "result.json"), "w"))
ev(type="start", generations=2)
if mode == "oom":                         # killed by the kernel OOM killer
    import signal; os.kill(os.getpid(), signal.SIGKILL)
if mode == "error_event":                 # worker reports its own error, then exits 2
    ev(type="error", message="ModelLoadError: boom"); sys.exit(2)
if mode == "crash":
    print("Traceback: boom", flush=True); sys.exit(3)
if mode == "ok":
    ev(type="progress", gen=1, total=2); write("completed", False); ev(type="done"); sys.exit(0)
if mode == "slow":
    write("running", True)
    for _ in range(300):
        if os.path.exists(os.path.join(wd, "CANCEL")):
            write("cancelled", True); sys.exit(0)
        time.sleep(0.05)
    write("completed", False); sys.exit(0)
if mode == "deaf":                       # ignores cancel: must be killed by the watchdog
    time.sleep(60)
