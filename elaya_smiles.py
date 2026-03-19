# -*- coding: utf-8 -*-
"""                                ELAYA SMILES
                 Molecular Conversion and Analysis Tool
        "Energy-minimized Linear-to-structure Atom Yielding Algorithm"
Elaborado por Gabriela Vidales, Luis Gonzalez, Filiberto Ortiz, and Gabriel Merino.

Funcionalidades principales
- Conversión SMILES a 3D (RDKit, OpenBabel, NetworkX, Auto3D)
- Visualización 3D (py3Dmol)
- Generación de matrices de conectividad
- Carga individual o por archivo.
- Exportación de estructuras en formato .xyz.
- Interfaz moderna y amigable.
"""

import os
import shutil
import contextlib
import numpy as np
from scipy.spatial.distance import pdist, squareform
import networkx as nx

# RDKit and cheminformatics
from rdkit import Chem
from rdkit.Chem import AllChem, rdmolops, Draw
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem import MolToMolBlock
from rdkit.Geometry import Point3D

# 3D visualization
import py3Dmol

# Molecular dynamics and descriptors
from ase.io import read, write
from dscribe.descriptors import SOAP, ValleOganov
from dscribe.kernels import AverageKernel

# OpenBabel
from openbabel import openbabel as ob, pybel
from openbabel.pybel import readstring

# Auto3D for AI-based optimization
import Auto3D
from Auto3D.auto3D import options, main

# Genetic algorithm for rotamer optimization (bundled as /app/glomos local package)
from glomos.heuristic_ga_rotamers import conformational

class MolecularTools:
    def __init__(self):
        """Initialize with ASCII art and setup"""
        os.environ['BABEL_DATADIR'] = os.path.abspath('openbabel_data')
        self.print_banner()
        self.setup_directories()

    def print_banner(self):
        """Display program banner"""
        print("""
                              ELAYA SMILES
                 Molecular Conversion and Analysis Tool
        "Energy-minimized Linear-to-structure Atom Yielding Algorithm"
        """)

    def setup_directories(self):
        """Create necessary directories"""
        self.dirs = {
            'smi': 'output_smi_individuales',
            'xyz_rdkit': 'output_xyz_rdkit',
            'xyz_openbabel': 'output_xyz_openbabel',
            'xyz_networkx': 'output_xyz_networkx',
            'xyz_auto3d': 'output_xyz_auto3d',
            'similarity': 'similarity_analysis'
        }

        for dir_name, dir_path in self.dirs.items():
            os.makedirs(dir_path, exist_ok=True)
            self.dirs[dir_name] = os.path.abspath(dir_path)
            print(f"Directorio {dir_name}: {self.dirs[dir_name]}")

    # SMILES Processing Methods
    def load_smiles(self, input_type=1, file_path=None):
        """Load SMILES either from single input or file"""
        if input_type == 1:
            self.smiles_list = [input("Enter SMILES: ")]
            self.identifiers = ["mol1"]
        else:
            if not file_path:
                raise ValueError("No file path provided")
                
            self.smiles_list = []
            self.identifiers = []
            with open(file_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        self.smiles_list.append(parts[0])
                        self.identifiers.append(parts[1])

    # 3D Conversion Methods
    def rdkit_conversion(self, smiles, identifier, force_field='uff', optimize=True):
        """Convert SMILES to 3D using RDKit"""
        try:
            print(f"Intentando convertir SMILES: {smiles}")
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ValueError(f"RDKit no pudo parsear el SMILES: {smiles}")
            
            mol = Chem.AddHs(mol)

            # Generate 3D coordinates
            params = AllChem.ETKDGv3()
            params.randomSeed = 665
            status = AllChem.EmbedMolecule(mol, params=params)
            if status == -1:
                raise ValueError("Embedding failed - could not generate 3D coordinates")
            print("Coordenadas 3D generadas")

            # Optimization
            if optimize:
                if force_field.lower() == 'uff':
                    print("Optimizando con UFF...")
                    status = AllChem.UFFOptimizeMolecule(mol, maxIters=2000)
                    if status == -1:
                        print(f"Warning: UFF optimization failed for {identifier}")
                else:  # MMFF94
                    print("Optimizando con MMFF94...")
                    mmff_props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94")
                    if mmff_props is None:
                        print(f"Warning: MMFF94 not available for {identifier}, using UFF instead")
                        AllChem.UFFOptimizeMolecule(mol, maxIters=2000)
                    else:
                        ff = AllChem.MMFFGetMoleculeForceField(mol, mmff_props)
                        ff.Minimize(maxIts=2000)

            # Save XYZ file
            xyz_content = f"{mol.GetNumAtoms()}\n0  0   {smiles}\n"
            conf = mol.GetConformer()
            for atom in mol.GetAtoms():
                pos = conf.GetAtomPosition(atom.GetIdx())
                xyz_content += f"{atom.GetSymbol()} {pos.x:.4f} {pos.y:.4f} {pos.z:.4f}\n"

            safe_name = smiles.translate(str.maketrans({
                '\\': '_', '/': '_', ':': '_', '*': '_', '?': '_', '"': '_', '<': '_', '>': '_', '|': '_'
            }))
            output_path = os.path.join(self.dirs['xyz_rdkit'], f"{safe_name}.xyz")
            with open(output_path, 'w') as f:
                f.write(xyz_content)
            
            mol_block = MolToMolBlock(mol)

            print(f"Conversión exitosa para {identifier}")
            return {"xyz": xyz_content, "mol": mol_block}

        except Exception as e:
            print(f"Error converting {smiles}: {str(e)}")
            raise


    def openbabel_conversion(self, smiles, identifier, force_field='uff'):
        """Convert SMILES to 3D using OpenBabel with enhanced bond detection and warm-up"""
        try:
            print(f"Convirtiendo {smiles} con OpenBabel...")

            # --- Warm-up opcional: evita fallos internos en primeras llamadas a make3D ---
            try:
                warm_conv = ob.OBConversion()
                warm_conv.SetInAndOutFormats("smi", "mol")
                warm_mol = ob.OBMol()
                warm_conv.ReadString(warm_mol, '[O]')
                warm_pybel = pybel.readstring("mol", warm_conv.WriteString(warm_mol))
                warm_pybel.make3D(forcefield=force_field, steps=1)
                print("Warm-up de OpenBabel completado")
            except Exception as warm_error:
                print("Warm-up fallido o innecesario:", warm_error)

            # --- Conversión principal ---
            conv = ob.OBConversion()
            conv.SetInAndOutFormats("smi", "mol")

            mol = ob.OBMol()
            if not conv.ReadString(mol, smiles):
                raise ValueError(f"OpenBabel no pudo interpretar el SMILES: {smiles}")

            mol.AddHydrogens()
            mol.PerceiveBondOrders()

            # Generar coordenadas y optimizar
            builder = ob.OBBuilder()
            builder.Build(mol)

            if force_field.lower() not in ('none', ''):
                ff = ob.OBForceField.FindForceField(force_field.upper())
                if ff is None:
                    print(f"Warning: force field '{force_field}' no encontrado, omitiendo optimización")
                else:
                    ff.Setup(mol)
                    ff.ConjugateGradients(2000)
                    ff.GetCoordinates(mol)

            # SDF preserva órdenes de enlace (dobles/triples) para el viewer 3D
            conv_mol = ob.OBConversion()
            conv_mol.SetOutFormat("sdf")
            mol.PerceiveBondOrders()
            mol_block = conv_mol.WriteString(mol)

            # Generar archivo XYZ
            xyz_content = f"{mol.NumAtoms()}\n0  0   {smiles}\n"
            for atom in ob.OBMolAtomIter(mol):
                x, y, z = atom.GetX(), atom.GetY(), atom.GetZ()
                xyz_content += f"{atom.GetType()[0]} {x:.4f} {y:.4f} {z:.4f}\n"

            # Guardar XYZ
            safe_name = smiles.translate(str.maketrans('\\/:*?"<>|', '_________'))
            output_path = os.path.join(self.dirs['xyz_openbabel'], f"{safe_name}.xyz")
            with open(output_path, 'w') as f:
                f.write(xyz_content)

            print(f"Conversión exitosa para {identifier}")
            return {"xyz": xyz_content, "mol": mol_block}

        except Exception as e:
            print(f"Error en OpenBabel: {str(e)}")
            raise

    def networkx_conversion(self, smiles, identifier):
        """Generar coordenadas aproximadas en 3D usando NetworkX a partir del SMILES"""
        try:
            print(f"Generando coordenadas aproximadas para {smiles}")

            # Convertir SMILES a Mol y añadir hidrógenos
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ValueError(f"SMILES inválido: {smiles}")
            mol = Chem.AddHs(mol)

            # Construcción de nodos y enlaces para el grafo molecular
            self.atoms = [(atom.GetIdx(), atom.GetSymbol()) for atom in mol.GetAtoms()]
            self.bonds = [(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()) for bond in mol.GetBonds()]

            # Crear grafo y calcular layout 3D aproximado
            G = nx.Graph()
            G.add_nodes_from(self.atoms)
            G.add_edges_from(self.bonds)
            coord_xyz = nx.spring_layout(G, dim=3, k=5, iterations=800, scale=3.4, seed=586)
            
            # Generar contenido XYZ
            self.xyz_networkx = []
            xyz_content = f"{len(self.atoms)}\n0  0   {smiles}\n"
            for atom in self.atoms:
                idx = atom[0]
                symbol = atom[1]
                x, y, z = coord_xyz[idx]
                self.xyz_networkx.append([round(x, 4), round(y, 4), round(z, 4)])
                xyz_content += f"{symbol} {x:.4f} {y:.4f} {z:.4f}\n"

            # Guardar archivo XYZ
            safe_name = smiles.translate(str.maketrans('\\/:*?"<>|', '_________'))
            output_path = os.path.join(self.dirs['xyz_openbabel'], f"{safe_name}.xyz")
            with open(output_path, 'w') as f:
                f.write(xyz_content)

            print(f"Conversión con NetworkX completada para {identifier}")
            return xyz_content

        except Exception as e:
            print(f"Error en NetworkX para {identifier}: {str(e)}")
            raise

    def auto3d_conversion(self, smiles, identifier):
        """Use Auto3D for AI-based 3D structure generation"""
        try:
            print(f"Usando Auto3D para {smiles}")
            # Create temporary SMILES file
            temp_file = os.path.join(self.dirs['smi'], f"temp_{identifier}.smi")
            with open(temp_file, 'w') as f:
                f.write(f"{smiles} {identifier}\n")

            # Run Auto3D
            args = options(temp_file, k=1, use_gpu=False)
            out_path = main(args)

            # Move output to our directory
            final_path = os.path.join(self.dirs['xyz_auto3d'], f"{identifier}.xyz")
            if os.path.isfile(out_path):
                shutil.move(out_path, final_path)
            else:
                raise FileNotFoundError(f"No se encontró el archivo de salida de Auto3D: {out_path}")

            # Read and return the content
            with open(final_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error en Auto3D: {str(e)}")
            raise

    """
    def add_lone_pairs(self, mol):
        rw_mol = Chem.RWMol(mol)
        original_num_atoms = rw_mol.GetNumAtoms()

        # Creamos lista de posiciones originales
        conf_old = mol.GetConformer()
        positions = [conf_old.GetAtomPosition(i) for i in range(original_num_atoms)]

        # Añadir átomos virtuales y calcular sus posiciones
        new_positions = []
        for atom_idx in range(original_num_atoms):
            atom = mol.GetAtomWithIdx(atom_idx)
            symbol = atom.GetSymbol()
            if symbol in ['O', 'N', 'F']:
                pos = positions[atom_idx]
                for dx, dy, dz in [(0.3, 0.3, 0.0), (-0.3, -0.3, 0.0)]:
                    dummy = Chem.Atom(0)  # átomo dummy
                    idx = rw_mol.AddAtom(dummy)
                    new_positions.append((idx, Point3D(pos.x + dx, pos.y + dy, pos.z + dz)))

        # Crear un nuevo conformador del tamaño correcto
        total_atoms = rw_mol.GetNumAtoms()
        conf_new = Chem.Conformer(total_atoms)

        # Asignar posiciones originales
        for i in range(original_num_atoms):
            conf_new.SetAtomPosition(i, positions[i])

        # Asignar posiciones de los nuevos átomos
        for idx, pos in new_positions:
            conf_new.SetAtomPosition(idx, pos)

        # Asignar el conformador al mol
        rw_mol.RemoveAllConformers()
        rw_mol.AddConformer(conf_new)

        return rw_mol.GetMol()
    """

    def _write_glomos_input(self, workdir, seed_xyz, initpop, matings, mutants,
                              generations, energy_cutoff, ani_model, nproc):
        """
        Siempre nof_processes=1: evita crash de multiprocessing.spawn.
        Parámetros ajustados para mayor velocidad en moléculas pequeñas.
        """
        import shutil
        if os.path.exists(workdir):
            shutil.rmtree(workdir)
        os.makedirs(workdir)
        with open(os.path.join(workdir, "seed.xyz"), "w") as f:
            f.write(seed_xyz)
        # prec más relajada (1E-02 1E-03) → optimizaciones más rápidas
        # nof_repeats=1, nof_stagnant=2 → termina antes si converge
        # cutoff_population=5 → mantiene menos conformeros activos
        input_txt = (
            "rotamer_seed            seed.xyz\n\n"
            "#EVOLUTIVE PARAMETERS:\n"
            f"nof_initpop             {initpop}\n"
            f"nof_matings             {matings}\n"
            f"nof_mutants             {mutants}\n\n"
            "#DISCRIMINATION PARAMETERS:\n"
            "tol_similarity          0.95\n"
            f"cutoff_energy           {energy_cutoff}\n"
            "cutoff_population       5\n\n"
            "#STOP CRITERION:\n"
            f"nof_generations         {generations}\n"
            "nof_repeats             1\n"
            "nof_stagnant            2\n\n"
            "#THEORY LEVEL: ANI1x, ANI1ccx, ANI2x\n"
            f"calculator              {ani_model}\n"
            "nof_processes           1\n"
            "prec                    1E-02 1E-03\n"
        )
        with open(os.path.join(workdir, "INPUT.txt"), "w") as f:
            f.write(input_txt)

    def _read_glomos_result(self, workdir):
        summary = os.path.join(workdir, "summary.xyz")
        if not os.path.exists(summary):
            raise RuntimeError("GLOMOS failed: summary.xyz not found")
        with open(summary) as f:
            xyzs = f.read().strip().split("\n\n")
        return xyzs[0]

    def _run_glomos(self, seed_xyz, workdir, initpop=4, matings=2, mutants=2,
                    generations=3, energy_cutoff=4.0, ani_model="ANI1ccx", nproc=2):
        self._write_glomos_input(workdir, seed_xyz, initpop, matings, mutants,
                                  generations, energy_cutoff, ani_model, nproc)
        cwd = os.getcwd()
        try:
            os.chdir(workdir)
            conformational("INPUT.txt")
        finally:
            os.chdir(cwd)
        return self._read_glomos_result(workdir)

    def run_glomos_streaming(self, seed_xyz, workdir, initpop=4, matings=2,
                              mutants=2, generations=3, energy_cutoff=4.0,
                              ani_model="ANI1ccx", nproc=2):
        """
        Generador SSE — 100 % compatible con Windows.

        Estrategia: un hilo auxiliar lee stdout del subprocess línea a línea
        y las mete en una queue.Queue. El generador principal consume la
        queue con get(timeout=3) y emite heartbeats mientras espera.
        Esto evita select() (que no funciona con pipes en Windows).
        """
        import subprocess, sys, re, time, queue, threading

        self._write_glomos_input(workdir, seed_xyz, initpop, matings, mutants,
                                  generations, energy_cutoff, ani_model, nproc)

        # ── runner hijo con flush por línea ──────────────────────────────
        runner = os.path.join(workdir, "_glomos_runner.py")
        with open(runner, "w") as f:
            f.write(
                "import sys, os\n"
                "sys.stdout.reconfigure(line_buffering=True)\n"
                "sys.stderr.reconfigure(line_buffering=True)\n"
                "from multiprocessing import freeze_support\n"
                # Inserta /app al inicio del path para que el glomos local
                # (en /app/glomos/) tenga prioridad sobre el de PyPI
                "sys.path.insert(0, '/app')\n"
                "os.chdir(os.path.dirname(os.path.abspath(__file__)))\n"
                "from glomos.heuristic_ga_rotamers import conformational\n"
                "if __name__ == '__main__':\n"
                "    freeze_support()\n"
                "    conformational('INPUT.txt')\n"
            )

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # ── Emitir inmediatamente — señal de que el proceso arrancó ────────
        # (app.py ya emitió 'loading' antes de llamar a este generador)
        yield {"type": "log", "line": "Lanzando subprocess GLOMOS…"}

        proc = subprocess.Popen(
            [sys.executable, "-u", runner],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,          # line-buffered en modo texto (suficiente en Windows)
            env=env,
        )

        # ── Hilo lector: mete líneas en la queue ─────────────────────────
        _SENTINEL = object()
        line_queue = queue.Queue()

        def _reader():
            try:
                for raw in proc.stdout:
                    line_queue.put(raw.rstrip())
            finally:
                line_queue.put(_SENTINEL)   # señal de fin

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        # ── Estado local ─────────────────────────────────────────────────
        current_gen = 0
        best_energy = None
        gen_start   = time.time()
        gen_times   = []
        last_data_t = time.time()
        HEARTBEAT_S = 3.0

        re_gen    = re.compile(r"-{2,}GENERATION\s+(\d+)-{2,}")
        re_energy = re.compile(r"#\d+\s+\S+\s+(-[\d.]+)\s+kcal/mol")
        re_conf   = re.compile(r"(random|mating|mutant)_\d+_\d+\s+at\s+")

        def _process_line(line):
            """Parsea una línea y devuelve lista de eventos SSE a emitir."""
            nonlocal current_gen, best_energy, gen_start, gen_times
            events = [{"type": "log", "line": line}]

            m = re_gen.search(line)
            if m:
                ng = int(m.group(1))
                if ng > current_gen:
                    gen_times.append(time.time() - gen_start)
                    gen_start = time.time()
                current_gen = ng
                events.append({
                    "type": "progress", "gen": current_gen, "total": generations,
                    "conformer": "", "best_energy": best_energy, "gen_times": gen_times[:],
                })

            m = re_conf.search(line)
            if m:
                events.append({
                    "type": "progress", "gen": current_gen, "total": generations,
                    "conformer": m.group(0).strip(),
                    "best_energy": best_energy, "gen_times": gen_times[:],
                })

            m = re_energy.search(line)
            if m:
                e = float(m.group(1))
                if best_energy is None or e < best_energy:
                    best_energy = e

            return events

        # ── Bucle principal: consume queue ───────────────────────────────
        try:
            while True:
                try:
                    item = line_queue.get(timeout=HEARTBEAT_S)
                except queue.Empty:
                    # Timeout → heartbeat (mantiene SSE vivo en el browser)
                    elapsed = round(time.time() - last_data_t)
                    yield {"type": "heartbeat", "elapsed": elapsed, "message": "Procesando…"}
                    continue

                if item is _SENTINEL:
                    break   # EOF del proceso

                last_data_t = time.time()
                if item:
                    for evt in _process_line(item):
                        yield evt

            t.join(timeout=5)
            proc.wait()

            if proc.returncode != 0:
                yield {"type": "error", "message": f"GLOMOS terminó con código {proc.returncode}"}
                return

            yield {"type": "done", "xyz": self._read_glomos_result(workdir)}

        except Exception as exc:
            proc.kill()
            t.join(timeout=2)
            yield {"type": "error", "message": str(exc)}

    def run_glomos_from_smiles(self, smiles, glomos_params):
        base = self.rdkit_conversion(
            smiles, identifier="glomos_seed", force_field="uff", optimize=True)
        workdir = os.path.join(self.dirs["xyz_auto3d"], "glomos_tmp")
        best_xyz = self._run_glomos(
            seed_xyz=base["xyz"], workdir=workdir,
            initpop=glomos_params.get("initpop", 4),
            matings=glomos_params.get("matings", 2),
            mutants=glomos_params.get("mutants", 2),
            generations=glomos_params.get("generations", 3),
            energy_cutoff=glomos_params.get("energy_cutoff", 4.0),
            ani_model=glomos_params.get("ani_model", "ANI1ccx"),
            nproc=1,
        )
        return {"xyz": best_xyz, "mol": None}

    def prepare_glomos_seed(self, smiles, glomos_params):
        base    = self.rdkit_conversion(
            smiles, identifier="glomos_seed", force_field="uff", optimize=True)
        workdir = os.path.join(self.dirs["xyz_auto3d"], "glomos_tmp")
        params  = {
            "initpop":       glomos_params.get("initpop", 4),
            "matings":       glomos_params.get("matings", 2),
            "mutants":       glomos_params.get("mutants", 2),
            "generations":   glomos_params.get("generations", 3),
            "energy_cutoff": glomos_params.get("energy_cutoff", 4.0),
            "ani_model":     glomos_params.get("ani_model", "ANI1ccx"),
            "nproc":         1,
        }
        return base["xyz"], workdir, params
    def visualize_3d(self, xyz_content, width=400, height=400):
        """Visualize molecule from XYZ content"""
        try:
            view = py3Dmol.view(width=width, height=height)
            view.addModel(xyz_content, "xyz")
            view.addBonds()  # <<<<<< AÑADIDO: intenta inferir enlaces desde posiciones
            view.setStyle({'sphere': {'scale': 0.3}, 'stick': {'radius': 0.2}})
            view.zoomTo()
            return view
        except Exception as e:
            print(f"Error en visualización: {str(e)}")
            raise
    
    def add_lone_pairs_openbabel(self, mol):
        """Agrega átomos virtuales tipo He para simular pares libres (visualización)"""
        from openbabel import OBAtom

        atom_count = mol.NumAtoms()
        for i in range(1, atom_count + 1):
            atom = mol.GetAtom(i)
            symbol = atom.GetType()
            if symbol in ['N', 'O', 'F']:
                x, y, z = atom.GetX(), atom.GetY(), atom.GetZ()
                
                # Crear átomo dummy tipo He como par libre (mejor si no interfiere con enlaces)
                for dx, dy, dz in [(0.3, 0.3, 0.0), (-0.3, -0.3, 0.0)]:
                    dummy = OBAtom()
                    dummy.SetAtomicNum(2)  # Helio (Z=2)
                    dummy.SetVector(x + dx, y + dy, z + dz)
                    mol.AddAtom(dummy)

    # Similarity Analysis Methods
    def tanimoto_similarity(self, xyz_file1, xyz_file2):
        """Calculate Tanimoto similarity between two XYZ structures"""
        try:
            def parse_xyz(xyz_file):
                coords = set()
                with open(xyz_file, 'r') as f:
                    lines = f.readlines()[2:]  # Skip first two lines
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 4:
                            element = parts[0]
                            x, y, z = map(lambda v: round(float(v), 2), parts[1:4])
                            coords.add((element, x, y, z))
                return coords

            set1 = parse_xyz(xyz_file1)
            set2 = parse_xyz(xyz_file2)

            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))
            return intersection / union if union != 0 else 0
        except Exception as e:
            print(f"Error en similitud Tanimoto: {str(e)}")
            raise

    def soap_similarity(self, xyz_files, species=None, r_cut=5.0):
        """Calculate SOAP similarity matrix for multiple XYZ files"""
        try:
            if not species:
                # Auto-detect species from first file
                with open(xyz_files[0], 'r') as f:
                    elements = set()
                    for line in f.readlines()[2:]:
                        parts = line.split()
                        if parts:
                            elements.add(parts[0])
                    species = list(elements)

            # Create SOAP descriptor
            soap = SOAP(
                species=species,
                r_cut=r_cut,
                n_max=4,
                l_max=4,
                periodic=False
            )

            # Process all molecules
            features = []
            for xyz_file in xyz_files:
                mol = read(xyz_file, format='xyz')
                features.append(soap.create(mol))

            # Calculate similarity matrix
            kernel = AverageKernel(metric="linear")
            return kernel.create(features)
        except Exception as e:
            print(f"Error en SOAP: {str(e)}")
            raise

    def valle_oganov_similarity(self, xyz_files, species=None):
        """Calculate Valle-Oganov similarity matrix"""
        try:
            if not species:
                # Auto-detect species from first file
                with open(xyz_files[0], 'r') as f:
                    elements = set()
                    for line in f.readlines()[2:]:
                        parts = line.split()
                        if parts:
                            elements.add(parts[0])
                    species = list(elements)

            # Create Valle-Oganov descriptor
            vo = ValleOganov(
                species=species,
                function='distance',
                n=100,
                sigma=1E-5,
                r_cut=10
            )

            # Process all molecules
            features = []
            for xyz_file in xyz_files:
                mol = read(xyz_file, format='xyz')
                features.append(vo.create(mol))

            # Calculate similarity matrix
            sim_matrix = np.zeros((len(features), len(features)))
            for i in range(len(features)):
                for j in range(i, len(features)):
                    norm_i = np.linalg.norm(features[i])
                    norm_j = np.linalg.norm(features[j])
                    dot_product = np.dot(features[i], features[j])
                    similarity = dot_product / (norm_i * norm_j)
                    sim_matrix[i, j] = similarity
                    sim_matrix[j, i] = similarity

            return sim_matrix
        except Exception as e:
            print(f"Error en Valle-Oganov: {str(e)}")
            raise

    # Connectivity Matrix Methods
    def get_connectivity_matrix(self, xyz_file, threshold=2.0):
        """Generate connectivity matrix from XYZ file"""
        try:
            with open(xyz_file, 'r') as f:
                num_atoms = int(f.readline().strip())
                _ = f.readline()  # Skip comment line
                coords = []
                elements = []
                for _ in range(num_atoms):
                    parts = f.readline().split()
                    elements.append(parts[0])
                    coords.append(list(map(float, parts[1:4])))

            coords = np.array(coords)
            distances = squareform(pdist(coords))
            connectivity = (distances < threshold).astype(int)
            np.fill_diagonal(connectivity, 0)

            return elements, connectivity
        except Exception as e:
            print(f"Error en matriz de conectividad: {str(e)}")
            raise

    # Batch Processing Methods
    def process_all_smiles(self, method='rdkit', force_field='uff'):
        """Process all loaded SMILES with 3D, 2D, and export"""
        results = {}
        for smiles, identifier in zip(self.smiles_list, self.identifiers):
            try:
                # Conversión 3D
                if method == 'rdkit':
                    result = self.rdkit_conversion(smiles, identifier, force_field)
                elif method == 'openbabel':
                    result = self.openbabel_conversion(smiles, identifier)
                elif method == 'networkx':
                    result = {"xyz": self.networkx_conversion(smiles, identifier), "mol": None}
                else:
                    raise ValueError("Método no soportado")

                # Imagen 2D
                img_paths = self.generate_2d_image(smiles, identifier)

                # Exportación de formatos estándar
                format_paths = self.export_formats(smiles, identifier)

                # Visualización
                vis = self.visualize_3d(result["xyz"])

                results[identifier] = {
                    'xyz': result["xyz"],
                    'mol': result["mol"],
                    'formats': format_paths,
                    '2d_image': img_paths["png"],
                    '2d_vector': img_paths["svg"],
                }

            except Exception as e:
                print(f"Error procesando {identifier}: {str(e)}")
                continue

        return results


    def compare_all_methods(self, identifier):
        """Compare results from all conversion methods for one molecule"""
        try:
            # Find the SMILES for this identifier
            idx = self.identifiers.index(identifier)
            smi = self.smiles_list[idx]

            # Generate with all methods
            rdkit_xyz = self.rdkit_conversion(smi, f"{identifier}_rdkit")
            obabel_xyz = self.openbabel_conversion(smi, f"{identifier}_obabel")
            networkx_xyz = self.networkx_conversion(smi, f"{identifier}_networkx")
            auto3d_xyz = self.auto3d_conversion(smi, f"{identifier}_auto3d")

            return {
                'rdkit': rdkit_xyz,
                'openbabel': obabel_xyz,
                'networkx': networkx_xyz,
                'auto3d': auto3d_xyz
            }
        except Exception as e:
            print(f"Error comparando métodos: {str(e)}")
            raise
        
    def export_formats(self, smiles, identifier):
    #Exporta la molécula a formatos comunes y añade metadatos
        try:
            mol = pybel.readstring("smi", smiles)
            mol.make3D()

            # Agregar metadatos personalizados
            mol.data["ID"] = identifier
            mol.data["SMILES"] = smiles
            mol.data["Source"] = "ELAYA"

            safe_name = smiles.translate(str.maketrans('\\/:*?"<>|', '_________'))
            base_path = os.path.join(self.dirs['xyz_openbabel'], safe_name)

            formats = ['mol', 'sdf', 'mol2', 'pdb', 'cml', 'xyz']
            paths = {}
            for fmt in formats:
                file_path = f"{base_path}.{fmt}"
                mol.write(fmt, filename=file_path, overwrite=True)
                paths[fmt] = file_path
                print(f"Archivo exportado: {file_path}")

            return paths

        except Exception as e:
            print(f"Error exportando formatos para {identifier}: {str(e)}")
            return {}
        
    def generate_2d_image(self, smiles, identifier):
        """Genera imagen 2D como PNG y SVG usando RDKit"""
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                raise ValueError(f"No se pudo generar imagen 2D para: {smiles}")

            mol = Chem.AddHs(mol)
            AllChem.Compute2DCoords(mol)

            # PNG
            img = Draw.MolToImage(mol, size=(400, 400), kekulize=True)
            png_path = os.path.join(self.dirs['xyz_rdkit'], f"{identifier}_2d.png")
            img.save(png_path)

            # SVG
            drawer = rdMolDraw2D.MolDraw2DSVG(400, 400)
            drawer.DrawMolecule(mol)
            drawer.FinishDrawing()
            svg_content = drawer.GetDrawingText()
            svg_path = os.path.join(self.dirs['xyz_rdkit'], f"{identifier}_2d.svg")
            with open(svg_path, 'w') as f:
                f.write(svg_content)

            return {
                "png": png_path,
                "svg": svg_path
            }

        except Exception as e:
            print(f"Error generando imagen 2D: {str(e)}")
            return None

if __name__ == "__main__":
    tool = MolecularTools()
    print("MolecularTools inicializado correctamente")
