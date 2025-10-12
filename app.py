from flask import Flask, Response, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D
import os
from elaya_smiles import MolecularTools

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

tool = MolecularTools()

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_file(path):
    return send_from_directory('.', path)

@app.route('/api')
def api_base():
    return jsonify({
        "status": "API ready",
        "endpoints": {
            "convert": "/api/convert [POST]",
            "compare": "/api/compare [POST]",
            "similarity": "/api/similarity [POST]",
            "connectivity": "/api/connectivity [POST]"
        }
    })

@app.route('/api/convert', methods=['POST'])
def convert():
    try:
        data = request.json
        print("Datos recibidos:", data)
        
        smiles = data['smiles']
        identifier = data['identifier']
        method = data.get('method', 'rdkit')
        force_field = data.get('force_field', 'uff')
        
        print(f"Convirtiendo {smiles} con {method}")
        
        if method == 'rdkit':
            result = tool.rdkit_conversion(smiles, identifier, force_field)
        elif method == 'openbabel':
            result = {"xyz": tool.openbabel_conversion(smiles, identifier, force_field)}
        elif method == 'networkx':
            result = {"xyz": tool.networkx_conversion(smiles, identifier)}
        else:
            return jsonify({"error": "Método no soportado"}), 400

        return jsonify(result)
    
    except Exception as e:
        print("Error en la conversión:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/compare', methods=['POST'])
def compare():
    try:
        data = request.json
        smiles = data['smiles']
        identifier = data['identifier']
        
        rdkit_xyz = tool.rdkit_conversion(smiles, f"{identifier}_rdkit")
        obabel_xyz = tool.openbabel_conversion(smiles, f"{identifier}_openbabel")
        networkx_xyz = tool.networkx_conversion(smiles, f"{identifier}_networkx")
        
        return jsonify({
            "rdkit": rdkit_xyz,
            "openbabel": obabel_xyz,
            "networkx": networkx_xyz
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/draw2d', methods=['POST'])
def draw_2d():
    try:
        # Asegura parseo de JSON aunque falte el header en algunos clientes
        data = request.get_json(force=True) or {}
        smiles = (data.get('smiles') or '').strip()

        if not smiles:
            return jsonify({"error": "Missing 'smiles'"}), 400

        # Construye molécula y valida
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES"}), 400

        # --- Preparación robusta para dibujo 2D ---
        from rdkit.Chem import rdDepictor
        from rdkit.Chem.Draw import rdMolDraw2D

        # En algunos SMILES complejos, kekulize puede fallar; probamos y si falla, sin kekulize
        try:
            # (opcional) sanitiza si vienes de fuentes dudosas
            Chem.SanitizeMol(mol)
            # Calcula coords 2D de forma explícita (evita rarezas de PrepareAndDraw en ciertos RDKit)
            rdDepictor.Compute2DCoords(mol)
            # Algunas versiones requieren preparar la mol para dibujo
            rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=True)
        except Exception:
            # Fallback sin kekulize
            try:
                rdDepictor.Compute2DCoords(mol)
                rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=False)
            except Exception as e2:
                print("[/api/draw2d] PrepareMolForDrawing fallback error:", repr(e2))
                return jsonify({"error": "Failed to prepare molecule for drawing", "detail": str(e2)}), 500

        # Dibujo SVG
        width, height = 320, 320
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        # Opciones de dibujo: evita estilos CSS si algún visor los bloquea
        try:
            drawer.drawOptions().useSvgStyles = False
        except Exception:
            pass

        # Dibujo (usando la mol ya preparada)
        try:
            # Si tu RDKit no admite PrepareAndDrawMolecule con mol ya preparado, usa DrawMolecule
            rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        except Exception:
            from rdkit.Chem import AllChem
            # Asegura coords por si el Prepare no las dejó
            rdDepictor.Compute2DCoords(mol)
            drawer.DrawMolecule(mol)

        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()

        # Algunos RDKit devuelven encabezado xml con entities; lo dejamos tal cual
        return Response(svg, mimetype='image/svg+xml')

    except Exception as e:
        import traceback
        print("[/api/draw2d] ERROR:", repr(e))
        traceback.print_exc()
        return jsonify({"error": "Draw2D server failure", "detail": str(e)}), 500

@app.route('/files/<filename>')
def serve_file(filename):
    directories = [
        "output_xyz_rdkit",
        "output_xyz_openbabel"
    ]
    for directory in directories:
        file_path = os.path.join(directory, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
    return "Archivo no encontrado", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

