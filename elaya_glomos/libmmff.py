"""
libmmff.py — cheap MMFF94 pre-relaxation for GLOMOS (large molecules).

Candidates built in torsion space (crossover, mutation) often have clashes and strained
contacts. Relaxing them first with MMFF94 (RDKit, C++) costs a fraction of an ANI relaxation
and leaves them close to a minimum, so the ANI optimisation that follows needs far fewer
steps. It also allows a *funnel*: build k times more candidates than will be relaxed with
ANI, pre-relax all of them with MMFF and send only the lowest/most diverse ones to ANI.

The RDKit molecule (bond orders, aromaticity) comes from the MOL block stored in
problem.json by the worker; its atom order is the order of every XYZ in the run.
"""
import numpy as np


class MMFFRelaxer:
    def __init__(self, molblock, max_iters=250):
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=True)
        if mol is None:
            raise ValueError("invalid MOL block")
        self.Chem, self.AllChem = Chem, AllChem
        self.mol = mol
        self.max_iters = int(max_iters)
        self.props = AllChem.MMFFGetMoleculeProperties(mol)
        self.kind = "MMFF94" if self.props is not None else "UFF"
        if self.props is None and not AllChem.UFFHasAllMoleculeParams(mol):
            raise ValueError("no MMFF94/UFF parameters for this molecule")

    def relax(self, atoms):
        """Copy of ``atoms`` relaxed with MMFF94 (info['e_mmff'] in kcal/mol), or None on failure."""
        try:
            pos = np.asarray(atoms.get_positions(), dtype=float)
            if len(pos) != self.mol.GetNumAtoms():
                return None
            conf = self.Chem.Conformer(len(pos))
            for i, p in enumerate(pos):
                conf.SetAtomPosition(i, [float(v) for v in p])
            m = self.Chem.Mol(self.mol)
            m.RemoveAllConformers()
            m.AddConformer(conf, assignId=True)
            if self.props is not None:
                ff = self.AllChem.MMFFGetMoleculeForceField(m, self.props, confId=0)
            else:
                ff = self.AllChem.UFFGetMoleculeForceField(m, confId=0)
            ff.Minimize(maxIts=self.max_iters)
            e = float(ff.CalcEnergy())
            new = np.array(m.GetConformer(0).GetPositions())
            if not np.all(np.isfinite(new)):
                return None
            out = atoms.copy()
            out.info = dict(atoms.info)
            out.set_positions(new)
            out.info["e_mmff"] = e
            return out
        except Exception:                                      # noqa: BLE001
            return None
