from flask import Flask, Response, request, jsonify, send_from_directory
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
        data = request.json
        smiles = data['smiles']
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES"}), 400

        drawer = rdMolDraw2D.MolDraw2DSVG(300, 300)
        drawer.drawOptions().useSvgStyles = False
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()

        return Response(svg, mimetype='image/svg+xml')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
