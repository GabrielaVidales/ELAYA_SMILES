"""End-to-end GA run with the toy potential (validates the GLOMOS pipeline logic)."""
import json
import os

import numpy as np
import pytest

from elaya_glomos import libcalc_ani
from elaya_glomos.libreport import Reporter
from elaya_glomos.libutils import atoms_to_xyz


def _prepare(tmp_path, hexane_skeleton, extra=""):
    atoms, problem, calc = hexane_skeleton
    libcalc_ani._MODEL_CACHE["TOY"] = calc
    (tmp_path / "seed.xyz").write_text(atoms_to_xyz(atoms, "seed"))
    (tmp_path / "problem.json").write_text(json.dumps(problem))
    (tmp_path / "INPUT.txt").write_text(
        "rotamer_seed seed.xyz\nproblem_file problem.json\nnof_initpop 10\nnof_matings 6\n"
        "nof_mutants 6\nnof_generations 4\ncutoff_energy 3\ncutoff_population 8\n"
        "calculator TOY\nrandom_seed 7\nprec 1e-1 5e-2\npolish_prec 5e-2\n" + extra)


def test_ga_finds_distinct_sorted_conformers(tmp_path, hexane_skeleton, monkeypatch):
    from elaya_glomos.heuristic_ga_rotamers import conformational
    _prepare(tmp_path, hexane_skeleton)
    monkeypatch.chdir(tmp_path)
    events = []
    rep = Reporter(emit=events.append, echo=False)
    res = conformational("INPUT.txt", reporter=rep)
    confs = res["conformers"]
    assert len(confs) >= 2, "the toy chain has several rotamers"
    rel = [c["rel_kcal"] for c in confs]
    assert rel[0] == pytest.approx(0.0) and rel == sorted(rel)
    assert sum(c["boltzmann_298"] for c in confs) == pytest.approx(1.0)
    assert res["meta"]["n_rotors"] == 3
    assert res["meta"]["random_seed"] == 7
    assert not res["partial"]
    types = {e["type"] for e in events}
    assert {"start", "progress", "population", "optimized"} <= types
    assert os.path.isfile("result.json") and os.path.isfile("summary.xyz")


def test_ga_is_reproducible_with_seed(tmp_path, hexane_skeleton, monkeypatch):
    from elaya_glomos.heuristic_ga_rotamers import conformational
    monkeypatch.chdir(tmp_path)
    _prepare(tmp_path, hexane_skeleton)
    r1 = conformational("INPUT.txt", reporter=Reporter(emit=lambda e: None, echo=False))
    r2 = conformational("INPUT.txt", reporter=Reporter(emit=lambda e: None, echo=False))
    e1 = [round(c["rel_kcal"], 4) for c in r1["conformers"]]
    e2 = [round(c["rel_kcal"], 4) for c in r2["conformers"]]
    assert e1 == e2


def test_cancel_returns_partial_result(tmp_path, hexane_skeleton, monkeypatch):
    from elaya_glomos.heuristic_ga_rotamers import conformational
    monkeypatch.chdir(tmp_path)
    _prepare(tmp_path, hexane_skeleton)
    cancel = tmp_path / "CANCEL"
    state = {"n": 0}

    def emit(evt):                       # cancel as soon as generation 1 starts
        if evt.get("type") == "phase" and evt.get("name") == "generation":
            cancel.write_text("1")
    rep = Reporter(emit=emit, cancel_file=str(cancel), echo=False)
    res = conformational("INPUT.txt", reporter=rep)
    assert res["meta"]["stop_reason"] == "cancelled"
    assert res["partial"] is True
    assert len(res["conformers"]) >= 1          # generation 0 survived


def test_timeout_stops_run(tmp_path, hexane_skeleton, monkeypatch):
    import time
    from elaya_glomos.heuristic_ga_rotamers import conformational
    monkeypatch.chdir(tmp_path)
    _prepare(tmp_path, hexane_skeleton)
    rep = Reporter(emit=lambda e: None, deadline=time.time() - 1, echo=False)
    res = conformational("INPUT.txt", reporter=rep)
    assert res["meta"]["stop_reason"] == "timeout"


def test_no_rotors_does_not_crash(tmp_path, hexane_skeleton, monkeypatch):
    from elaya_glomos.heuristic_ga_rotamers import conformational
    monkeypatch.chdir(tmp_path)
    atoms, problem, calc = hexane_skeleton
    problem = dict(problem, rotors=[])
    _prepare(tmp_path, (atoms, problem, calc))
    res = conformational("INPUT.txt", reporter=Reporter(emit=lambda e: None, echo=False))
    assert len(res["conformers"]) >= 1
    assert res["meta"].get("note") == "no rotatable torsions"
