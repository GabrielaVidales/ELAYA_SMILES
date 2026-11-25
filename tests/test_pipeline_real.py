"""Real pipeline: RDKit seeds + chemistry-aware rotors + real ASE optimiser + validity checks.

The potential is MMFF94 (tests/mmff_calc.py) instead of ANI so that the test does not need the
ANI parameter download; everything else is the code path of a web job. Skipped when RDKit or
the real ASE are missing (the fake ASE of conftest cannot drive an ASE calculator).
"""
import json
import os

import pytest

from conftest import REAL_ASE

rdkit = pytest.importorskip("rdkit")
pytestmark = pytest.mark.skipif(not REAL_ASE, reason="needs the real ase package")

MOLECULES = {
    "butane": ("CCCC", 1, 2),
    "glucose": ("OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@H]1O", 6, 2),
    "gly-leu-leu-NH2": ("CC(C)C[C@H](NC(=O)[C@H](CC(C)C)NC(=O)CN)C(=O)N", 13, 2),
}


@pytest.mark.parametrize("name", list(MOLECULES))
def test_glomos_real_pipeline_keeps_structure(name, tmp_path, monkeypatch):
    import elaya_chem as ec
    from elaya_jobs import clamp_params, write_input_txt
    from elaya_smiles import MolecularTools
    from elaya_glomos import libcalc_ani
    from elaya_glomos.heuristic_ga_rotamers import conformational
    from elaya_glomos.libreport import Reporter
    from mmff_calc import MMFFCalculator

    smiles, n_rotors, min_conf = MOLECULES[name]
    p = clamp_params({"preset": "fast", "random_seed": 5})
    molh, seed_xyz, problem, info = ec.glomos_seed_pool(smiles, p["n_seeds"], 665)
    assert len(problem["rotors"]) == n_rotors
    monkeypatch.setitem(libcalc_ani._MODEL_CACHE, "MMFF_TEST", MMFFCalculator(smiles))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "seed.xyz").write_text(seed_xyz)
    (tmp_path / "problem.json").write_text(json.dumps(problem))
    write_input_txt(str(tmp_path), p, "MMFF_TEST")
    res = conformational("INPUT.txt", reporter=Reporter(emit=lambda e: None, echo=False))

    assert len(res["conformers"]) >= min_conf
    tools = MolecularTools()
    for c in res["conformers"]:
        qa = ec.stereo_qa(ec.mol_with_coords(smiles, c["xyz"]), smiles, 0)
        assert qa["ok"], qa["problems"]
        syms, pos = ec.parse_xyz(c["xyz"])
        assert tools.check_bonds(smiles, syms, pos)["ok"] is not False


def test_glomos_lite_engine_mmff_funnel(tmp_path, monkeypatch):
    """Large-molecule engine (MMFF funnel, one network, top-n polish) keeps bonds and stereo."""
    import elaya_chem as ec
    from rdkit import Chem
    from elaya_jobs import clamp_params, size_profile, write_input_txt
    from elaya_glomos import libcalc_ani
    from elaya_glomos.heuristic_ga_rotamers import conformational
    from elaya_glomos.libreport import Reporter
    from mmff_calc import MMFFCalculator

    smiles = MOLECULES["gly-leu-leu-NH2"][0]
    p, _ = size_profile(clamp_params({"preset": "fast", "random_seed": 3}), 135)   # force the lite engine
    molh, seed_xyz, problem, info = ec.glomos_seed_pool(smiles, p["n_seeds"], 665)
    problem["molblock"] = Chem.MolToMolBlock(molh)
    monkeypatch.setitem(libcalc_ani._MODEL_CACHE, "MMFF_TEST", MMFFCalculator(smiles))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "seed.xyz").write_text(seed_xyz)
    (tmp_path / "problem.json").write_text(json.dumps(problem))
    write_input_txt(str(tmp_path), p, "MMFF_TEST")
    logs = []
    res = conformational("INPUT.txt", reporter=Reporter(emit=lambda e: logs.append(e), echo=False))
    assert res["meta"]["prerelax"] == "MMFF94" and res["conformers"]
    assert len(res["conformers"]) <= 4                       # polish_top
    for c in res["conformers"]:
        assert ec.stereo_qa(ec.mol_with_coords(smiles, c["xyz"]), smiles, 0)["ok"]
