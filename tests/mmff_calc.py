"""ASE calculator backed by RDKit MMFF94.

Used only by tests to drive the *real* GLOMOS pipeline (RDKit seeds + real ASE LBFGS +
stereo/connectivity checks) without the ANI parameters, which need a download.
Not a substitute for ANI energies.
"""
import numpy as np
from ase.calculators.calculator import Calculator, all_changes
from rdkit import Chem
from rdkit.Chem import AllChem

EV_PER_KCAL = 1.0 / 23.060548012069496


class MMFFCalculator(Calculator):
    implemented_properties = ["energy", "forces"]

    def __init__(self, smiles, **kw):
        super().__init__(**kw)
        self.mol = Chem.AddHs(Chem.MolFromSmiles(smiles))      # same atom order as ELAYA's XYZ
        AllChem.EmbedMolecule(self.mol, randomSeed=1)
        self.props = AllChem.MMFFGetMoleculeProperties(self.mol)

    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        conf = self.mol.GetConformer()
        for i, p in enumerate(self.atoms.get_positions()):
            conf.SetAtomPosition(i, p.tolist())
        ff = AllChem.MMFFGetMoleculeForceField(self.mol, self.props)
        self.results["energy"] = ff.CalcEnergy() * EV_PER_KCAL
        self.results["forces"] = -np.array(ff.CalcGrad()).reshape(-1, 3) * EV_PER_KCAL
