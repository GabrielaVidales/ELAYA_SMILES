"""
glomos_worker.py — runs one GLOMOS job in its own process.

    python glomos_worker.py <workdir> [--deadline-minutes M]

<workdir> must contain INPUT.txt (+ rotamer.xyz and problem.json).
Progress is emitted on stdout as ``@@ELAYA@@ {json}`` lines (see glomos.libreport);
cancellation is requested by creating <workdir>/CANCEL.
Exit codes: 0 ok (or partial result), 2 error.
"""
import os
import sys
import time
import traceback


def main(argv):
    if len(argv) < 2:
        print("usage: glomos_worker.py <workdir> [--deadline-minutes M]", file=sys.stderr)
        return 2
    workdir = os.path.abspath(argv[1])
    deadline = None
    if "--deadline-minutes" in argv:
        deadline = time.time() + 60.0 * float(argv[argv.index("--deadline-minutes") + 1])
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    os.chdir(workdir)

    from glomos.libreport import Reporter
    rep = Reporter(deadline=deadline, cancel_file=os.path.join(workdir, "CANCEL"), echo=True)
    try:
        from glomos.heuristic_ga_rotamers import conformational
        result = conformational("INPUT.txt", reporter=rep)
        rep.event("done", n_conformers=len(result["conformers"]),
                  stop_reason=result["meta"].get("stop_reason"))
        return 0
    except BaseException as exc:                      # noqa: BLE001 - report everything
        rep.event("error", message="%s: %s" % (type(exc).__name__, exc),
                  trace=traceback.format_exc()[-2000:])
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
