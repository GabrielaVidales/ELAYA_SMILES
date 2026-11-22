"""Chemistry helpers with the real RDKit (skipped when RDKit is not installed).

The API tests replace RDKit with stand-ins, which is how a call to a non-existent RDKit
method (Bond.IsInRingOfSize) went unnoticed: every molecule with a C=O or C=C made
/api/analyze and /api/glomos/start fail. These tests exercise the real code."""
import pytest

pytest.importorskip("rdkit")

import elaya_chem as ec                                   # noqa: E402
from elaya_smiles import MolecularTools                   # noqa: E402

CASES = {
    "Gly-Leu-Leu-NH2": ("CC(C)C[C@H](NC(=O)[C@H](CC(C)C)NC(=O)CN)C(=O)N", 2, {"E": 0, "Z": 0, "undefined": 0}),
    "aspirin": ("CC(=O)Oc1ccccc1C(=O)O", 0, {"E": 0, "Z": 0, "undefined": 0}),
    "E-2-butene": ("C/C=C/C", 0, {"E": 1, "Z": 0, "undefined": 0}),
    "2-butene, unspecified": ("CC=CC", 0, {"E": 0, "Z": 0, "undefined": 1}),
    "Z-cyclooctene": (r"C1CCC/C=C\CC1", 0, {"E": 0, "Z": 1, "undefined": 0}),
    "cyclohexene (no E/Z)": ("C1CCC=CC1", 0, {"E": 0, "Z": 0, "undefined": 0}),
}


@pytest.mark.parametrize("name", list(CASES))
def test_stereo_summary(name):
    smiles, n_centres, dbl = CASES[name]
    specified, unspecified, got = ec._stereo_info(ec.parse_smiles(smiles))
    assert len(specified) == n_centres and got == dbl


@pytest.mark.parametrize("name", list(CASES))
def test_mol_report_and_seed_pool(name):
    smiles = CASES[name][0]
    rep = ec.mol_report(smiles)
    assert rep["formula"]
    molh, xyz, problem, info = ec.glomos_seed_pool(smiles, 2, 665)
    assert xyz.strip() and info["n_seeds"] >= 1


def test_convert_returns_structure_even_without_rotational_constants():
    res = MolecularTools().convert("[Na+].[Cl-]", "rdkit", "none", "salt")
    assert res["xyz"] and res["rotational_constants"] is None
