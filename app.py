# -*- coding: utf-8 -*-
"""
ELAYA SMILES — Flask backend.

Endpoints
    GET  /api                    index of endpoints
    GET  /api/health[?deep=1]    which libraries import, job queue; deep=1 runs a tiny ANI calculation
    GET  /api/version
    POST /api/analyze            {smiles}                      -> descriptors, stereo, warnings
    POST /api/convert            {smiles, method, force_field} -> xyz, mol, rotational constants, QA
    POST /api/export             {smiles, xyz, format}         -> file download (xyz/mol/sdf/pdb/mol2/cml)
    POST /api/draw2d             {smiles}                      -> SVG
    POST /api/glomos/start       {smiles, glomos_params}       -> {job_id}
    GET  /api/glomos/poll/<id>?cursor=n
    POST /api/glomos/cancel/<id>
    GET  /api/glomos/result/<id>[?format=json|xyz]

Heavy libraries (RDKit, torch, ASE) are imported lazily; the GA runs in a subprocess.
"""
import importlib.util
import json
import os
import sys
import time

from flask import Flask, Response, jsonify, request, send_from_directory

VERSION = "2.4.0"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


@app.after_request
def add_cors(resp):
    """Minimal CORS for /api/* (replaces flask-cors, one dependency less)."""
    if request.path == "/api" or request.path.startswith("/api/"):
        resp.headers["Access-Control-Allow-Origin"] = os.environ.get("ELAYA_CORS_ORIGINS", "*")
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/api/<path:subpath>", methods=["OPTIONS"])
def api_options(subpath):
    return Response("", 204)

app.url_map.strict_slashes = False

STATIC_FILES = {"index.html", "app.js", "glomos_progress.js", "structure_panel.js", "ux_extras.js", "learn.js", "guide.js", "styles.css"}
STATIC_DIRS = {"pictures"}

_tool = None
_jobs = None


def tool():
    global _tool
    if _tool is None:
        from elaya_smiles import MolecularTools
        _tool = MolecularTools()
    return _tool


def jobs():
    global _jobs
    if _jobs is None:
        from elaya_jobs import JobManager
        _jobs = JobManager()
    return _jobs


def err(message, code=400, **extra):
    out = {"error": message}
    out.update(extra)
    return jsonify(out), code


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def smiles_from(data):
    s = (data.get("smiles") or "").strip()
    if not s:
        raise ValueError("Missing 'smiles'")
    return s


@app.errorhandler(413)
def too_big(_):
    return err("Request too large", 413)


# ------------------------------------------------------------------------------------------
# Static
# ------------------------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/<path:path>")
def static_file(path):
    if path.startswith("api/"):
        return err("Route /%s not found or method not allowed" % path, 404)
    top = path.split("/")[0]
    if path in STATIC_FILES or top in STATIC_DIRS:
        return send_from_directory(HERE, path)
    return err("Not found", 404)


# ------------------------------------------------------------------------------------------
# Meta
# ------------------------------------------------------------------------------------------
def _have(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:                                           # noqa: BLE001
        return False


@app.route("/api")
def api_base():
    return jsonify({"status": "API ready", "version": VERSION, "endpoints": {
        "health": "GET /api/health[?deep=1]", "analyze": "POST /api/analyze",
        "convert": "POST /api/convert", "export": "POST /api/export",
        "draw2d": "POST /api/draw2d", "glomos_start": "POST /api/glomos/start",
        "glomos_poll": "GET /api/glomos/poll/<job_id>?cursor=n",
        "glomos_cancel": "POST /api/glomos/cancel/<job_id>",
        "glomos_result": "GET /api/glomos/result/<job_id>[?format=xyz]"}})


@app.route("/api/version")
def version():
    return jsonify({"version": VERSION, "python": sys.version.split()[0]})


_SELFTEST_CODE = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
t0 = time.time()
from ase import Atoms
from elaya_glomos.libcalc_ani import ANI_single, torchani_versions
water = Atoms("OHH", positions=[[0, 0, 0], [0.96, 0, 0], [-0.24, 0.93, 0]])
res = ANI_single(water, "ANI1ccx")
print("@@SELFTEST@@" + json.dumps({"ok": True, "energy_kcal": res.info["e"], "converged": res.info["converged"],
      "seconds": round(time.time() - t0, 1), "versions": torchani_versions()}))
"""


def selftest_ani(timeout=300):
    """Real ANI calculation on water. Used by /api/health?deep=1.

    Runs in a separate process: importing torch inside the web server would keep ~250 MB
    resident for the life of the process (and can get the whole service OOM-killed on 512 MB)."""
    import subprocess
    try:
        proc = subprocess.run([sys.executable, "-W", "ignore", "-c", _SELFTEST_CODE, HERE],
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ANI self-test did not finish in %d s (server too slow?)" % timeout}
    for line in proc.stdout.splitlines():
        if line.startswith("@@SELFTEST@@"):
            return json.loads(line[len("@@SELFTEST@@"):])
    if proc.returncode is not None and proc.returncode < 0:
        return {"ok": False, "error": "self-test killed by signal %d (out of memory?)" % -proc.returncode}
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return {"ok": False, "error": " | ".join(tail) or "exit code %s" % proc.returncode}


def memory_limit_mb():
    """cgroup memory limit of the container in MB (None if unlimited / unknown)."""
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path) as fh:
                raw = fh.read().strip()
            if raw and raw != "max":
                v = int(raw)
                if v < (1 << 50):                               # v1 reports a huge number when unlimited
                    return v // (1024 * 1024)
        except (OSError, ValueError):
            continue
    return None


@app.route("/api/health")
def health():
    libs = {m: _have(m) for m in ("rdkit", "openbabel", "networkx", "torch", "torchani", "ase", "scipy")}
    from importlib import metadata
    versions = {}
    for dist in ("rdkit", "openbabel-wheel", "networkx", "torch", "torchani", "ase", "scipy", "numpy", "flask"):
        try:
            versions[dist] = metadata.version(dist)
        except Exception:                                       # noqa: BLE001
            versions[dist] = None
    out = {"status": "ok", "version": VERSION, "python": sys.version.split()[0], "versions": versions,
           "libraries": libs,
           "glomos_ready": all(libs[m] for m in ("rdkit", "torch", "torchani", "ase", "scipy")),
           "max_minutes": float(os.environ.get("ELAYA_MAX_MINUTES", "20")),
           "max_concurrent_jobs": int(os.environ.get("ELAYA_MAX_JOBS", "1"))}
    if not out["glomos_ready"]:
        out["missing_for_glomos"] = [m for m in ("rdkit", "torch", "torchani", "ase", "scipy") if not libs[m]]
    try:
        import elaya_glomos
        import elaya_glomos.libreport                           # noqa: F401
        out["glomos_package"] = {"ok": True, "path": os.path.dirname(elaya_glomos.__file__)}
    except Exception as exc:                                    # noqa: BLE001
        out["glomos_package"] = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        out["glomos_ready"] = False
        out["status"] = "degraded"
    if libs["torchani"]:
        try:
            from elaya_glomos.libcalc_ani import ani_weights_status
            out["ani_weights"] = ani_weights_status()
        except Exception as exc:                                # noqa: BLE001
            out["ani_weights"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
    out["memory_limit_mb"] = memory_limit_mb()
    try:
        from elaya_glomos.libcalc_ani import cpu_quota, torch_threads
        out["cpus"] = round(cpu_quota(), 2)
        out["torch_threads"] = torch_threads()
    except Exception:                                           # noqa: BLE001
        pass
    if out["memory_limit_mb"] and out["memory_limit_mb"] < 1000:
        out["memory_warning"] = ("Container memory limit is %d MB: GLOMOS (torch + ANI) needs ~1 GB; "
                                 "jobs may be killed." % out["memory_limit_mb"])
    if request.args.get("deep") and out["glomos_ready"]:
        try:
            out["ani_selftest"] = selftest_ani()
            if not out["ani_selftest"].get("ok"):
                out["status"] = "degraded"
        except Exception as exc:                                # noqa: BLE001
            out["status"] = "degraded"
            out["ani_selftest"] = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return jsonify(out)


# ------------------------------------------------------------------------------------------
# Chemistry
# ------------------------------------------------------------------------------------------
@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        import elaya_chem as ec
        return jsonify(ec.mol_report(smiles_from(body())))
    except ValueError as exc:                                   # includes ChemError
        return err(str(exc))
    except Exception as exc:                                    # noqa: BLE001
        return err("Analysis failed: %s" % exc, 500)


@app.route("/api/validate", methods=["POST"])
def validate():
    """Quick check of many SMILES at once (file preview): {smiles: [..]} -> {results: [{ok, formula|error}]}."""
    items = body().get("smiles")
    if not isinstance(items, list):
        return err("Expected {'smiles': [list of strings]}")
    if len(items) > 2000:
        return err("At most 2000 SMILES per request")
    try:
        import elaya_chem as ec
        from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    except Exception as exc:                                    # noqa: BLE001
        return err("Validation unavailable: %s" % exc, 503)
    out = []
    for s in items:
        s = str(s or "").strip()
        try:
            if not s:
                raise ValueError("empty")
            out.append({"ok": True, "formula": CalcMolFormula(ec.parse_smiles(s))})
        except Exception as exc:                                # noqa: BLE001
            out.append({"ok": False, "error": str(exc)[:160]})
    return jsonify({"results": out})


@app.route("/api/convert", methods=["POST"])
def convert():
    data = body()
    try:
        smiles = smiles_from(data)
        if data.get("post_opt") == "glomos":
            return err("GLOMOS runs as a background job: use POST /api/glomos/start.", 400)
        res = tool().convert(smiles, data.get("method", "rdkit"),
                             data.get("force_field", "mmff"), str(data.get("identifier", "mol1"))[:60])
        return jsonify(res)
    except ValueError as exc:
        return err(str(exc))
    except Exception as exc:                                    # noqa: BLE001
        return err("Conversion failed: %s" % exc, 500)


MIME = {"xyz": "chemical/x-xyz", "mol": "chemical/x-mdl-molfile", "sdf": "chemical/x-mdl-sdfile",
        "pdb": "chemical/x-pdb", "mol2": "chemical/x-mol2", "cml": "chemical/x-cml"}


@app.route("/api/export", methods=["POST"])
def export():
    data = body()
    try:
        fmt = (data.get("format") or "xyz").lower()
        if fmt not in MIME:
            return err("Unsupported format")
        raw_name = str(data.get("name", "elaya"))
        # record title inside the file (MOL/SDF header line, PDB COMPND...): readable, one line, <= 80 chars
        title = "".join(c if (c.isprintable() and c not in "\r\n\t$") else " " for c in raw_name).strip()[:80] or "elaya"
        fname = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_name)[:50] or "elaya"
        text = tool().export(smiles_from(data), data.get("xyz", ""), fmt, title, data.get("properties"))
        return Response(text, mimetype=MIME[fmt], headers={
            "Content-Disposition": 'attachment; filename="%s.%s"' % (fname, fmt)})
    except ValueError as exc:
        return err(str(exc))
    except Exception as exc:                                    # noqa: BLE001
        return err("Export failed: %s" % exc, 500)


@app.route("/api/draw2d", methods=["POST"])
def draw_2d():
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDepictor
        from rdkit.Chem.Draw import rdMolDraw2D
        import elaya_chem as ec
        mol = ec.parse_smiles(smiles_from(body()))
        rdDepictor.SetPreferCoordGen(True)
        rdDepictor.Compute2DCoords(mol)
        drawer = rdMolDraw2D.MolDraw2DSVG(340, 340)
        drawer.drawOptions().addStereoAnnotation = True
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        drawer.FinishDrawing()
        return Response(drawer.GetDrawingText(), mimetype="image/svg+xml")
    except ValueError as exc:
        return err(str(exc))
    except Exception as exc:                                    # noqa: BLE001
        return err("Draw2D failed: %s" % exc, 500)


# ------------------------------------------------------------------------------------------
# GLOMOS
# ------------------------------------------------------------------------------------------
def _finalize(result, smiles=None):
    """Add rotational constants and a MOL block (bond orders, for the 3D viewer) to each conformer."""
    import elaya_chem as ec
    for c in result["conformers"]:
        syms, pos = ec.parse_xyz(c["xyz"])
        c["rotational_constants"] = ec.rotational_constants(syms, pos)
        if smiles:
            try:
                from rdkit import Chem
                c["mol"] = Chem.MolToMolBlock(ec.mol_with_coords(smiles, c["xyz"]))
            except Exception:                                   # noqa: BLE001
                c["mol"] = None
    return result


@app.route("/api/glomos/start", methods=["POST"])
def glomos_start():
    data = body()
    try:
        smiles = smiles_from(data)
        from elaya_jobs import clamp_params
        from elaya_glomos.ani_domain import resolve_model, DomainError
        import elaya_chem as ec
        params = clamp_params(data.get("glomos_params"))
        molh, seed_xyz, problem, info = ec.glomos_seed_pool(smiles, params["n_seeds"], 665)
        syms = [a.GetSymbol() for a in molh.GetAtoms()]
        try:
            dom = resolve_model(syms, params["ani_model"], problem["charge"])
        except DomainError as exc:
            return err(str(exc), 422, kind="ani_domain")
        meta = {"smiles": smiles, "n_rotors": len(problem["rotors"]), "n_atoms": len(syms),
                "seed_info": info, "ani_notes": dom["notes"], "ani_warnings": dom["warnings"],
                "formula": ec.mol_report(smiles)["formula"]}
        job_id = jobs().submit(seed_xyz, problem, params, dom["model"], meta,
                               finalize=lambda res: _finalize(res, smiles))
        return jsonify({"job_id": job_id, "model": dom["model"], "notes": dom["notes"],
                        "warnings": dom["warnings"], "n_rotors": meta["n_rotors"], "params": params})
    except ValueError as exc:
        return err(str(exc))
    except Exception as exc:                                    # noqa: BLE001
        return err("Could not start GLOMOS: %s" % exc, 500)


@app.route("/api/glomos/poll/<job_id>")
def glomos_poll(job_id):
    try:
        cursor = int(request.args.get("cursor", 0))
    except ValueError:
        cursor = 0
    try:
        out = jobs().poll(job_id, cursor)
        if out is None:
            return err("Job not found (it expired or the server restarted)", 404)
        return jsonify(out)
    except Exception as exc:                                    # noqa: BLE001
        import traceback
        traceback.print_exc()
        return err("Poll failed: %s: %s" % (type(exc).__name__, exc), 500)


@app.route("/api/glomos/cancel/<job_id>", methods=["POST"])
def glomos_cancel(job_id):
    if not jobs().cancel(job_id):
        return err("Job not found", 404)
    return jsonify({"ok": True})


@app.route("/api/glomos/result/<job_id>")
def glomos_result(job_id):
    job = jobs().get(job_id)
    if job is None:
        return err("Job not found", 404)
    if not job.done:
        return err("Job is still running", 409, status=job.status)
    if not job.result:
        return err(job.error or "No result", 404)
    if request.args.get("format") == "xyz":
        text = "".join(c["xyz"] for c in job.result["conformers"])
        return Response(text, mimetype="chemical/x-xyz", headers={
            "Content-Disposition": 'attachment; filename="elaya_conformers.xyz"'})
    out = dict(job.result)
    out["status"] = job.status
    out["job"] = job.meta
    return jsonify(out)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    try:
        from waitress import serve
        print("ELAYA %s on http://0.0.0.0:%d" % (VERSION, port))
        serve(app, host="0.0.0.0", port=port, threads=int(os.environ.get("ELAYA_THREADS", "4")),
              channel_timeout=600)
    except ImportError:
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)
