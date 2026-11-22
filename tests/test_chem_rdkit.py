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


NX_CASES = {
    "dopamine": "C1=CC(=C(C=C1CCN)O)O",
    "glucose": "OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O",
    "E-stilbene": r"c1ccccc1/C=C/c1ccccc1",
    "Z-stilbene": r"c1ccccc1/C=C\c1ccccc1",
    "Gly-Leu-Leu-NH2": "CC(C)C[C@H](NC(=O)[C@H](CC(C)C)NC(=O)CN)C(=O)N",
    "(S)-ibuprofen": "CC(C)Cc1ccc(cc1)[C@H](C)C(=O)O",
}


@pytest.mark.parametrize("name", list(NX_CASES))
def test_networkx_layout_is_chemically_sensible(name):
    """Kamada-Kawai layout with topological distance targets + stereo inversion:
    bonds within ~0.4 A, connectivity recovered from the geometry, stereo as in the SMILES."""
    import numpy as np
    pytest.importorskip("networkx")
    from rdkit import Chem
    smiles = NX_CASES[name]
    res = MolecularTools().convert(smiles, "networkx", "none")
    assert res["connectivity_check"]["ok"]
    assert res["stereo_qa"]["ok"], res["stereo_qa"]["problems"]
    assert res["mol"] and "V2000" in res["mol"]
    syms, pos = ec.parse_xyz(res["xyz"])
    mol = Chem.AddHs(ec.parse_smiles(smiles))
    for b in mol.GetBonds():
        d = np.linalg.norm(pos[b.GetBeginAtomIdx()] - pos[b.GetEndAtomIdx()])
        assert 0.8 < d < 1.95, (b.GetBeginAtomIdx(), b.GetEndAtomIdx(), d)


def test_openbabel_reports_stereo_qa():
    pytest.importorskip("openbabel")
    res = MolecularTools().convert(NX_CASES["glucose"], "openbabel", "mmff")
    assert res["stereo_qa"] is not None and res["stereo_qa"]["ok"]


def test_glomos_finalize_adds_mol_block_with_bond_orders():
    import app as appmod
    smiles = "C1=CC(=C(C=C1CCN)O)O"
    rd = MolecularTools().convert(smiles, "rdkit", "mmff")
    out = appmod._finalize({"conformers": [{"xyz": rd["xyz"]}]}, smiles)
    mb = out["conformers"][0]["mol"]
    assert mb and "V2000" in mb
    from rdkit import Chem
    m = Chem.MolFromMolBlock(mb, removeHs=False, sanitize=False)        # keep the Kekulé form as written
    assert any(b.GetBondTypeAsDouble() == 2.0 for b in m.GetBonds())     # Kekulé double bonds present
