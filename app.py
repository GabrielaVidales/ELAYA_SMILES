from flask import Flask, Response, request, jsonify, send_from_directory, stream_with_context
from flask_cors import CORS
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D
import os
import json
import uuid
import threading
import time
from elaya_smiles import MolecularTools

app = Flask(__name__, static_folder=None)  # static files served manually below — avoids route conflicts with /api/*
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"]}})
app.url_map.strict_slashes = False  # prevent 301 redirects that turn POST into GET

tool = MolecularTools()

# ── Job store for GLOMOS polling ─────────────────────────────────────────────
# { job_id: { 'events': [...], 'done': bool, 'created': float } }
_jobs: dict = {}
_jobs_lock = threading.Lock()

def _cleanup_old_jobs():
    """Remove jobs older than 30 minutes to avoid memory leaks."""
    cutoff = time.time() - 1800
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if j['created'] < cutoff]
        for jid in stale:
            del _jobs[jid]

def _run_glomos_job(job_id: str, smiles: str, glomos_params: dict):
    """Worker thread: runs GLOMOS and pushes events into the job store."""
    def push(event: dict):
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]['events'].append(event)

    push({'type': 'loading', 'message': 'Preparando semilla 3D...'})

    try:
        seed_xyz, workdir, params = tool.prepare_glomos_seed(smiles, glomos_params)
    except Exception as exc:
        push({'type': 'error', 'message': str(exc)})
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]['done'] = True
        return

    push({'type': 'start', 'generations': params['generations']})

    try:
        for event in tool.run_glomos_streaming(seed_xyz, workdir, **params):
            if event.get('type') == 'loading':
                continue  # already sent above
            push(event)
    except Exception as exc:
        push({'type': 'error', 'message': str(exc)})

    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]['done'] = True

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    base = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base, 'index.html')

@app.route('/api', strict_slashes=False)
def api_base():
    return jsonify({
        "status": "API ready",
        "endpoints": {
            "convert":      "/api/convert [POST]",
            "glomos_start": "/api/glomos/start [POST]",
            "glomos_poll":  "/api/glomos/poll/<job_id> [GET]",
            "draw2d":       "/api/draw2d [POST]"
        }
    })

@app.route('/api/convert', methods=['POST'], strict_slashes=False)
def convert():
    try:
        data = request.json
        print("Datos recibidos:", data)

        smiles = data['smiles']
        identifier = data.get('identifier', 'mol1')
        method = data.get('method', 'rdkit')
        force_field = data.get('force_field', 'uff')

        post_opt = data.get('post_opt')
        glomos_params = data.get('glomos_params', {})

        print(f"Convirtiendo {smiles} | método={method} | post_opt={post_opt}")

        if post_opt == 'glomos':
            print("→ Ejecutando GLOMOS (ANI Rotamers)")
            result = tool.run_glomos_from_smiles(smiles, glomos_params)
        else:
            if method == 'rdkit':
                result = tool.rdkit_conversion(
                    smiles,
                    identifier,
                    force_field=force_field
                )
            elif method == 'openbabel':
                ob_res = tool.openbabel_conversion(
                    smiles,
                    identifier,
                    force_field=force_field
                )
                result = {"xyz": ob_res["xyz"], "mol": ob_res["mol"]}
            elif method == 'networkx':
                xyz = tool.networkx_conversion(smiles, identifier)
                result = {"xyz": xyz}
            else:
                return jsonify({"error": "Método no soportado"}), 400

        return jsonify(result)

    except Exception as e:
        print("Error en la conversión:", str(e))
        return jsonify({"error": str(e)}), 500


# ── GLOMOS job-based endpoints (replaces SSE /api/convert/stream) ─────────────

@app.route('/api/glomos/start', methods=['POST'], strict_slashes=False)
def glomos_start():
    """
    Inicia un job GLOMOS en un thread separado.
    Body: { "smiles": "...", "glomos_params": {...} }
    Returns: { "job_id": "..." }
    """
    data = request.get_json(force=True) or {}
    smiles = data.get('smiles', '').strip()
    glomos_params = data.get('glomos_params', {})

    if not smiles:
        return jsonify({"error": "Missing smiles"}), 400

    _cleanup_old_jobs()

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            'events':  [],
            'done':    False,
            'created': time.time(),
        }

    t = threading.Thread(
        target=_run_glomos_job,
        args=(job_id, smiles, glomos_params),
        daemon=True
    )
    t.start()

    return jsonify({"job_id": job_id})


@app.route('/api/glomos/poll/<job_id>', methods=['GET'], strict_slashes=False)
def glomos_poll(job_id):
    """
    Devuelve los eventos nuevos desde el cursor indicado.
    Query param: ?cursor=<int>  (default 0)
    Returns: { "events": [...], "cursor": <int>, "done": bool }
    """
    cursor = int(request.args.get('cursor', 0))

    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        return jsonify({"error": "Job not found"}), 404

    events    = job['events']
    new_events = events[cursor:]
    new_cursor = cursor + len(new_events)

    return jsonify({
        "events": new_events,
        "cursor": new_cursor,
        "done":   job['done'],
    })


# Keep /api/convert/stream alive so old JS doesn't crash, just returns a clean error
@app.route('/api/convert/stream', methods=['POST'], strict_slashes=False)
def convert_stream_legacy():
    return jsonify({
        "error": "SSE not supported on Waitress. Use /api/glomos/start + /api/glomos/poll."
    }), 410


@app.route('/api/draw2d', methods=['POST'], strict_slashes=False)
def draw_2d():
    try:
        data = request.get_json(force=True) or {}
        smiles = (data.get('smiles') or '').strip()

        if not smiles:
            return jsonify({"error": "Missing 'smiles'"}), 400

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES"}), 400

        from rdkit.Chem import rdDepictor
        from rdkit.Chem.Draw import rdMolDraw2D

        try:
            Chem.SanitizeMol(mol)
            rdDepictor.Compute2DCoords(mol)
            rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=True)
        except Exception:
            try:
                rdDepictor.Compute2DCoords(mol)
                rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=False)
            except Exception as e2:
                print("[/api/draw2d] PrepareMolForDrawing fallback error:", repr(e2))
                return jsonify({"error": "Failed to prepare molecule for drawing", "detail": str(e2)}), 500

        width, height = 320, 320
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        try:
            drawer.drawOptions().useSvgStyles = False
        except Exception:
            pass

        try:
            rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        except Exception:
            from rdkit.Chem import AllChem
            rdDepictor.Compute2DCoords(mol)
            drawer.DrawMolecule(mol)

        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()

        return Response(svg, mimetype='image/svg+xml')

    except Exception as e:
        import traceback
        print("[/api/draw2d] ERROR:", repr(e))
        traceback.print_exc()
        return jsonify({"error": "Draw2D server failure", "detail": str(e)}), 500



# ── OPTIONS preflight handler for all /api/* routes ──────────────────────────
@app.route('/api/<path:subpath>', methods=['OPTIONS'])
def api_options(subpath):
    """Respond to CORS preflight requests for any /api/* path."""
    response = app.make_default_options_response()
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# NOTE: this catch-all is intentionally AFTER all /api routes.
# Flask matches routes in definition order, so /api/* routes above take priority.
@app.route('/<path:path>')
def static_file(path):
    # Return a clear JSON 405 for any api path that slips through (should not happen normally)
    if path.startswith('api/'):
        return jsonify({"error": f"Route /{path} not found or method not allowed"}), 405
    base = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base, path)


if __name__ == '__main__':
    try:
        from waitress import serve
        print("Servidor iniciado con Waitress en http://localhost:5000")
        serve(app, host='0.0.0.0', port=5000, threads=8, channel_timeout=600)
    except ImportError:
        print("AVISO: instala waitress con:  pip install waitress")
        app.run(port=5000, debug=False, threaded=True, use_reloader=False)