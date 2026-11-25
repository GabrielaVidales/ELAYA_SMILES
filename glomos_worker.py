"""
glomos_worker.py — runs one GLOMOS job in its own process.

    python glomos_worker.py <workdir> [--deadline-minutes M]

<workdir> must contain INPUT.txt (+ rotamer.xyz and problem.json).
Progress is emitted on stdout as ``@@ELAYA@@ {json}`` lines (see elaya_glomos.libreport);
cancellation is requested by creating <workdir>/CANCEL.
Exit codes: 0 ok (or partial result), 2 error.
"""
import json
import os
import sys
import time
import traceback


def build_seeds(rep):
    """seed_request.json -> seed.xyz + problem.json (RDKit ETKDGv3 + MMFF94 starting structures)."""
    if not os.path.isfile("seed_request.json") or os.path.isfile("seed.xyz"):
        return
    with open("seed_request.json") as fh:
        req = json.load(fh)
    rep.event("phase", name="seeds")
    rep.log("Building %d starting structure(s) with RDKit (ETKDGv3 + MMFF94)..." % int(req.get("n_seeds", 4)))
    t0 = time.time()
    import elaya_chem as ec
    from rdkit import Chem
    molh, xyz, problem, info = ec.glomos_seed_pool(req["smiles"], int(req.get("n_seeds", 4)),
                                                   int(req.get("seed", 665)))
    problem["molblock"] = Chem.MolToMolBlock(molh)
    with open("seed.xyz", "w") as fh:
        fh.write(xyz)
    with open("problem.json", "w") as fh:
        json.dump(problem, fh)
    rep.log("Starting structures ready: %d (%.1f s)" % (info.get("n_seeds", 0), time.time() - t0))


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

    from elaya_glomos.libreport import Reporter
    rep = Reporter(deadline=deadline, cancel_file=os.path.join(workdir, "CANCEL"), echo=True)
    try:
        build_seeds(rep)
        from elaya_glomos.heuristic_ga_rotamers import conformational
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
