# -*- coding: utf-8 -*-
"""
ELAYA SMILES — Energy-minimized Linear-to-structure Atom Yielding Algorithm
Gabriela Vidales, Luis Gonzalez, Filiberto Ortiz, Gabriel Merino

Facade used by the web API (app.py).  Compared with the original module:

* No banner / directories / files are created at import or construction time (a web
  server must not write per-request files; downloads are generated on demand).
* RDKit and OpenBabel are imported lazily, so the server starts (and /api/health works)
  even if one of them is missing or broken.
* OpenBabel atoms are written with their real element symbol (``atom.GetType()[0]`` gave
  'C' for Cl and 'B' for Br).
* Every conversion returns ``info`` (method, force field really used, seed) and a stereo QA.
* The NetworkX layout is flagged as *approximate* (it is a graph drawing, not a geometry).
* GLOMOS is no longer started from here: see elaya_jobs.py / glomos_worker.py.
"""
import numpy as np

import elaya_chem as ec
from elaya_chem import ChemError

# Covalent radii (A) for bond perception from XYZ (Cordero et al. 2008)
COVALENT = {"H": 0.31, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57, "Si": 1.11,
            "P": 1.07, "S": 1.05, "Cl": 1.02, "Br": 1.20, "I": 1.39}


class MolecularTools:
    """Stateless facade; kept as a class for backward compatibility."""

    # ---------------------------------------------------------------------------------
    def rdkit_conversion(self, smiles, identifier="mol1", force_field="mmff", optimize=True, seed=665):
        molh, cids, info = ec.embed_conformers(smiles, n_confs=1, seed=seed,
                                               force_field=force_field if optimize else "none")
        cid = cids[0]
        qa = ec.stereo_qa(molh, smiles, cid)
        xyz = ec.mol_to_xyz(molh, cid, "%s | %s" % (identifier, smiles))
        from rdkit import Chem
        info.update({"method": "rdkit"})
        return {"xyz": xyz, "mol": Chem.MolToMolBlock(molh, confId=cid), "info": info, "stereo_qa": qa,
                "atom_order": "rdkit"}

    # ---------------------------------------------------------------------------------
    def openbabel_conversion(self, smiles, identifier="mol1", force_field="mmff94"):
        try:
            from openbabel import pybel
        except Exception as exc:
            raise ChemError("OpenBabel is not available in this deployment (%s)." % exc)
        ec.parse_smiles(smiles)                                   # same validation / limits
        ff = (force_field or "").lower()
        ff = {"mmff": "mmff94", "uff": "uff", "gaff": "gaff", "ghemical": "ghemical"}.get(ff, ff)
        mol = pybel.readstring("smi", smiles)
        mol.addh()
        used = "none"
        if ff and ff != "none":
            if ff not in pybel.forcefields:
                ff = "mmff94" if "mmff94" in pybel.forcefields else "uff"
            mol.make3D(forcefield=ff, steps=2000)
            used = ff
        else:
            mol.make3D(forcefield="uff", steps=0)
        syms = [ec.Z_TO_SYMBOL.get(a.atomicnum) or _symbol(a.atomicnum) for a in mol.atoms]
        pos = np.array([a.coords for a in mol.atoms])
        xyz = ec.format_xyz(syms, pos, "%s | %s" % (identifier, smiles))
        return {"xyz": xyz, "mol": mol.write("sdf"),
                "info": {"method": "openbabel", "force_field": used, "embedding": "OBBuilder"},
                "stereo_qa": None, "atom_order": "openbabel"}

    # ---------------------------------------------------------------------------------
    def networkx_conversion(self, smiles, identifier="mol1"):
        """Graph layout in 3D (NOT a molecular geometry): only useful as a rough sketch."""
        import networkx as nx
        from rdkit import Chem
        mol = Chem.AddHs(ec.parse_smiles(smiles))
        G = nx.Graph()
        G.add_nodes_from(range(mol.GetNumAtoms()))
        G.add_edges_from((b.GetBeginAtomIdx(), b.GetEndAtomIdx()) for b in mol.GetBonds())
        pos = nx.spring_layout(G, dim=3, k=5, iterations=800, scale=3.4, seed=586)
        coords = np.array([pos[i] for i in range(mol.GetNumAtoms())])
        syms = [a.GetSymbol() for a in mol.GetAtoms()]
        xyz = ec.format_xyz(syms, coords, "%s | %s | APPROXIMATE graph layout" % (identifier, smiles))
        return {"xyz": xyz, "mol": None,
                "info": {"method": "networkx", "force_field": "none",
                         "embedding": "spring layout (not a real geometry)"},
                "stereo_qa": None, "atom_order": "rdkit", "approximate": True}

    # ---------------------------------------------------------------------------------
    def convert(self, smiles, method="rdkit", force_field="mmff", identifier="mol1", seed=665):
        method = (method or "rdkit").lower()
        if method == "rdkit":
            res = self.rdkit_conversion(smiles, identifier, force_field, True, seed)
        elif method == "openbabel":
            res = self.openbabel_conversion(smiles, identifier, force_field)
        elif method == "networkx":
            res = self.networkx_conversion(smiles, identifier)
        else:
            raise ChemError("Unsupported method: %s" % method)
        syms, pos = ec.parse_xyz(res["xyz"])
        try:
            res["rotational_constants"] = ec.rotational_constants(syms, pos)
        except ChemError:                       # element without a tabulated mass: still return the structure
            res["rotational_constants"] = None
        res["connectivity_check"] = self.check_bonds(smiles, syms, pos)
        return res

    # ---------------------------------------------------------------------------------
    @staticmethod
    def adjacency_from_xyz(symbols, coords, factor=1.2):
        coords = np.asarray(coords)
        r = np.array([COVALENT.get(s, 1.5) for s in symbols])
        d = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
        adj = (d < factor * (r[:, None] + r[None, :])).astype(int)
        np.fill_diagonal(adj, 0)
        return adj

    def check_bonds(self, smiles, symbols, coords):
        """Does the geometry have the same bond graph as the SMILES? (atom order must match)."""
        try:
            from rdkit import Chem
            mol = Chem.AddHs(ec.parse_smiles(smiles))
            if mol.GetNumAtoms() != len(symbols):
                return {"ok": None, "detail": "atom order differs from RDKit; not checked"}
            ref = np.zeros((len(symbols),) * 2, dtype=int)
            for b in mol.GetBonds():
                ref[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] = ref[b.GetEndAtomIdx(), b.GetBeginAtomIdx()] = 1
            if [a.GetSymbol() for a in mol.GetAtoms()] != list(symbols):
                return {"ok": None, "detail": "atom order differs from RDKit; not checked"}
            adj = self.adjacency_from_xyz(symbols, coords)
            diff = np.argwhere(np.triu(adj != ref, 1))
            return {"ok": len(diff) == 0,
                    "detail": "" if len(diff) == 0 else "bond mismatch at atoms: " +
                    ", ".join("%d-%d" % (i + 1, j + 1) for i, j in diff[:6])}
        except Exception as exc:                                  # noqa: BLE001
            return {"ok": None, "detail": str(exc)}

    # ---------------------------------------------------------------------------------
    def export(self, smiles, xyz_text, fmt, name="ELAYA", properties=None):
        """Structure in the requested format. Falls back to OpenBabel when the atom order is not RDKit's."""
        try:
            return ec.export_structure(smiles, xyz_text, fmt, name, properties)
        except ChemError as first:
            if "mismatch" not in str(first) and "atoms but" not in str(first):
                raise
            try:
                from openbabel import pybel
            except Exception:
                raise first
            m = pybel.readstring("xyz", xyz_text)
            m.title = name
            return m.write(fmt)

    @staticmethod
    def connectivity_matrix(xyz_text, factor=1.2):
        """Connectivity from a geometry with covalent radii (the old fixed 2.0 A cut-off linked
        every non-bonded pair in dense molecules and missed C-I / long bonds)."""
        syms, pos = ec.parse_xyz(xyz_text)
        return syms, MolecularTools.adjacency_from_xyz(syms, pos, factor)


def _symbol(z):
    try:
        from rdkit import Chem
        return Chem.GetPeriodicTable().GetElementSymbol(int(z))
    except Exception:                                             # noqa: BLE001
        raise ChemError("Unknown atomic number %s" % z)
