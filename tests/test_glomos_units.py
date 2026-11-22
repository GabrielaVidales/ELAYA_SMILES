"""Unit tests of the GLOMOS building blocks (torsions, USR, roulette, clash/stereo checks)."""
import random

import numpy as np
import pytest

from conftest import chain_atoms
from elaya_glomos.librotamers import (build_rotors, get_torsion, set_torsion, Problem, make_random_rotamers,
                                make_crossover_rotamers, make_mutant_rotamers)
from elaya_glomos.libutils import adjacency_from_bonds, angular_distance, wrap180
from elaya_glomos.libdisc_usr import usr_descriptor, usr_similarity, deduplicate_by_usr
from elaya_glomos.libsel_roulette import get_fitness, get_roulette_wheel_selection


def _setup(n=7):
    atoms = chain_atoms(n)
    adj = adjacency_from_bonds(n, [[i, i + 1] for i in range(n - 1)])
    rotors = build_rotors(adj, atoms.get_atomic_numbers(),
                          [{"a": i, "b": i + 1, "kind": "sp3"} for i in range(1, n - 2)])
    return atoms, adj, rotors


def test_torsion_roundtrip_and_rigid_fragments():
    atoms, adj, rotors = _setup()
    pos = atoms.get_positions()
    bonds0 = np.linalg.norm(pos[1:] - pos[:-1], axis=1)
    rng = random.Random(3)
    for r in rotors:
        for target in (60.0, -60.0, 180.0, 123.0):
            p = pos.copy()
            set_torsion(p, r, target)
            assert abs(wrap180(get_torsion(p, r) - target)) < 1e-6
            assert np.allclose(np.linalg.norm(p[1:] - p[:-1], axis=1), bonds0, atol=1e-9)
    # rotating one torsion must not change the others on the fixed side
    p = pos.copy()
    before = [get_torsion(p, r) for r in rotors]
    set_torsion(p, rotors[-1], 77.0)
    after = [get_torsion(p, r) for r in rotors]
    assert np.allclose(before[:-1], after[:-1], atol=1e-6)


def test_ring_bonds_are_not_rotors():
    # cyclopentane-like graph: 5-ring + 1 substituent
    n = 7
    bonds = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0], [0, 5], [5, 6]]
    adj = adjacency_from_bonds(n, bonds)
    rotors = build_rotors(adj, np.array([6] * n), [{"a": a, "b": b, "kind": "generic"} for a, b in bonds])
    assert all((r.a, r.b) not in {(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)} for r in rotors)


def test_problem_detects_clash_and_broken_connectivity():
    atoms, adj, rotors = _setup()
    prob = Problem(atoms.get_atomic_numbers(), adj, rotors)
    assert prob.why_invalid(atoms) is None
    bad = atoms.copy()
    pos = bad.get_positions(); pos[6] = pos[0] + [0.5, 0, 0]
    bad.set_positions(pos)
    assert prob.why_invalid(bad) is not None
    far = atoms.copy()
    pos = far.get_positions(); pos[6] += [20, 0, 0]
    far.set_positions(pos)
    assert "connect" in prob.why_invalid(far, check_clash=False).lower()


def test_problem_detects_inverted_stereocentre():
    # tetrahedral carbon with 4 neighbours; chirality tuple from the reference geometry
    from ase import Atoms
    pos = np.array([[0, 0, 0], [1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float) * 0.63
    atoms = Atoms(["C", "H", "H", "H", "H"], positions=pos)
    adj = adjacency_from_bonds(5, [[0, 1], [0, 2], [0, 3], [0, 4]])
    n1, n2, n3 = 1, 2, 3
    vol = np.dot(pos[n1] - pos[0], np.cross(pos[n2] - pos[0], pos[n3] - pos[0]))
    prob = Problem(atoms.get_atomic_numbers(), adj, [], chiral=[(0, n1, n2, n3, 1 if vol > 0 else -1)])
    assert prob.why_invalid(atoms, check_clash=False) is None
    mirror = atoms.copy(); mirror.set_positions(pos * [1, 1, -1])
    assert "stereo" in (prob.why_invalid(mirror, check_clash=False) or "").lower()


def test_generators_respect_problem():
    atoms, adj, rotors = _setup()
    prob = Problem(atoms.get_atomic_numbers(), adj, rotors)
    rng = random.Random(0)
    pool = make_random_rotamers([atoms], 12, prob, rng)
    assert pool and all(prob.why_invalid(m) is None for m in pool)
    for m in pool:
        m.info["e"] = rng.random()
    kids = make_crossover_rotamers(pool[:4], pool[4:8], prob, rng)
    muts = make_mutant_rotamers(pool[:4], prob, rng)
    assert all(prob.why_invalid(m) is None for m in kids + muts)


def test_usr_is_mirror_and_rotation_invariant():
    rng = np.random.RandomState(0)
    pos = rng.normal(size=(12, 3))
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    d0 = usr_descriptor(pos)
    assert len(d0) == 12
    assert usr_similarity(d0, usr_descriptor(pos @ q.T + 3.0)) == pytest.approx(1.0, abs=1e-9)
    assert usr_similarity(d0, usr_descriptor(pos * [1, 1, -1])) == pytest.approx(1.0, abs=1e-9)
    other = rng.normal(size=(12, 3)) * [3, 1, .3]
    assert usr_similarity(d0, usr_descriptor(other)) < 0.95


def test_dedupe_keeps_distinct_structures():
    atoms, adj, rotors = _setup()
    a, b, c = atoms.copy(), atoms.copy(), atoms.copy()
    pb = b.get_positions(); b.set_positions(pb + 1e-4)
    pc = set_torsion(c.get_positions(), rotors[0], 60.0); c.set_positions(pc)
    a.info["e"], b.info["e"], c.info["e"] = 0.0, 0.01, 0.5
    out = deduplicate_by_usr([a, b, c], 0.95, 0.1, flag=0)
    energies = sorted(round(float(m.info['e']), 3) for m in out)
    assert energies == [0.0, 0.5]             # b duplicates a (same shape, |dE| <= 0.1); c is distinct


def test_roulette_degenerate_and_fitness():
    atoms = chain_atoms(4)
    pop = []
    for _ in range(3):
        m = atoms.copy(); m.info["e"] = 5.0
        pop.append(m)
    assert np.allclose(get_fitness(pop), 1.0)               # zero energy span must not divide by zero
    chosen = get_roulette_wheel_selection(pop, 5, random.Random(1))
    assert len(chosen) == 5
    pop[0].info["e"] = 0.0; pop[1].info["e"] = 1.0; pop[2].info["e"] = 10.0
    f = get_fitness(pop)
    assert f[0] > f[1] > f[2]


def test_angular_distance_wraps():
    assert angular_distance(179.0, -179.0) == pytest.approx(2.0)


def test_model_load_error_stops_the_run_once(tmp_path, monkeypatch, hexane_skeleton):
    """A missing ANI dependency/parameter set must abort with one clear message,
    not 'optimisation failed' for every structure followed by 'all structures discarded'."""
    import json
    from elaya_glomos import libcalc_ani
    from elaya_glomos.heuristic_ga_rotamers import conformational
    from elaya_glomos.libreport import Reporter
    from elaya_glomos.libutils import atoms_to_xyz
    atoms, problem, _ = hexane_skeleton
    monkeypatch.chdir(tmp_path)
    (tmp_path / "seed.xyz").write_text(atoms_to_xyz(atoms, "seed"))
    (tmp_path / "problem.json").write_text(json.dumps(problem))
    (tmp_path / "INPUT.txt").write_text("rotamer_seed seed.xyz\nproblem_file problem.json\ncalculator NOPE_MODEL\n")
    events = []
    with pytest.raises(ValueError):           # unknown model name: rejected before any optimisation
        conformational("INPUT.txt", reporter=Reporter(emit=events.append, echo=False))
    assert not any(e["type"] == "discard" for e in events)

    def boom(opt):
        raise libcalc_ani.ModelLoadError(libcalc_ani._explain_model_error(
            opt, ModuleNotFoundError("No module named 'pkg_resources'")))
    monkeypatch.setattr("elaya_glomos.heuristic_ga_rotamers.get_calculator", boom)
    (tmp_path / "INPUT.txt").write_text("rotamer_seed seed.xyz\nproblem_file problem.json\ncalculator ANI1ccx\n")
    with pytest.raises(libcalc_ani.ModelLoadError, match="setuptools<81"):
        conformational("INPUT.txt", reporter=Reporter(emit=events.append, echo=False))


def test_explain_model_error_messages():
    from elaya_glomos.libcalc_ani import _explain_model_error
    import zipfile
    assert "setuptools<81" in _explain_model_error("ANI1ccx", ModuleNotFoundError("No module named 'pkg_resources'"))
    assert "Docker" in _explain_model_error("ANI2x", zipfile.BadZipFile("File is not a zip file"))


def test_merge_keeps_lower_energy_duplicate(hexane_skeleton):
    """A newcomer that duplicates a population member but is lower in energy must replace it
    (seen in a real dopamine run: mutant at -0.08 kcal/mol below its twin was dropped)."""
    from elaya_glomos.heuristic_ga_rotamers import merge_population
    atoms, _, _ = hexane_skeleton
    old = atoms.copy(); old.info.update(e=-100.00, i="old")
    twin = atoms.copy(); twin.info.update(e=-100.08, i="new")       # same geometry, 0.08 lower
    other = atoms.copy(); pos = other.get_positions(); pos[0] += [3.0, 0.0, 0.0]; other.set_positions(pos); other.info.update(e=-99.0, i="other")
    out = merge_population([old, other], [twin], 0.95, 0.1, 10.0, 10)
    names = [a.info["i"] for a in out]
    assert "new" in names and "old" not in names and "other" in names
    assert [a.info["e"] for a in out] == sorted(a.info["e"] for a in out)
