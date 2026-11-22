"""Pure-numpy chemistry: rotational constants, XYZ parsing, ANI domain."""
import math

import numpy as np
import pytest

import elaya_chem as ec
from elaya_glomos.ani_domain import resolve_model, DomainError


def water():
    r, a = 0.9572, math.radians(104.52) / 2
    return ["O", "H", "H"], [[0, 0, 0], [r * math.sin(a), r * math.cos(a), 0], [-r * math.sin(a), r * math.cos(a), 0]]


def test_water_rotational_constants():
    # rigid-rotor values for r=0.9572 A, 104.52 deg (experimental B0: 835.8, 435.3, 278.1 GHz)
    c = ec.rotational_constants(*water())
    assert c["A_GHz"] == pytest.approx(822.5, rel=0.01)
    assert c["B_GHz"] == pytest.approx(437.6, rel=0.01)
    assert c["C_GHz"] == pytest.approx(285.6, rel=0.01)
    assert c["A_MHz"] > c["B_MHz"] > c["C_MHz"]
    assert c["top"] == "asymmetric" and -1 < c["kappa"] < 1


def test_rotational_constants_are_invariant_to_rotation_and_translation():
    sym, pos = water()
    pos = np.array(pos)
    q, _ = np.linalg.qr(np.random.RandomState(1).normal(size=(3, 3)))
    c1 = ec.rotational_constants(sym, pos)
    c2 = ec.rotational_constants(sym, pos @ q.T + np.array([5.0, -3.0, 2.0]))
    for k in ("A_MHz", "B_MHz", "C_MHz"):
        assert c1[k] == pytest.approx(c2[k], rel=1e-9)


def test_linear_and_symmetric_tops():
    c = ec.rotational_constants(["O", "C", "O"], [[-1.16, 0, 0], [0, 0, 0], [1.16, 0, 0]])
    assert c["top"] == "linear" and c["A_MHz"] is None
    assert c["B_GHz"] == pytest.approx(11.7, rel=0.02)           # CO2 B0 = 11.70 GHz
    # methane: spherical top, B ~ 157 GHz (r_CH = 1.087 A)
    r = 1.087 / math.sqrt(3)
    ch4 = [[0, 0, 0], [r, r, r], [r, -r, -r], [-r, r, -r], [-r, -r, r]]
    c = ec.rotational_constants(["C", "H", "H", "H", "H"], ch4)
    assert c["top"] == "spherical"
    assert c["B_GHz"] == pytest.approx(157.0, rel=0.02)


def test_xyz_roundtrip_and_errors():
    sym, pos = water()
    text = ec.format_xyz(sym, pos, "water")
    s2, p2 = ec.parse_xyz(text)
    assert s2 == sym and np.allclose(p2, pos, atol=1e-7)
    with pytest.raises(ec.ChemError):
        ec.parse_xyz("three\ncomment\n")
    with pytest.raises(ec.ChemError):
        ec.parse_xyz("3\ncomment\nO 0 0 0\n")


def test_ani_domain_auto_selection():
    assert resolve_model(["C", "H", "H", "H", "H"], "auto")["model"] == "ANI1ccx"
    assert resolve_model(["C", "Cl", "H", "H", "H"], "auto")["model"] == "ANI2x"
    with pytest.raises(DomainError):
        resolve_model(["C", "Br", "H", "H", "H"], "auto")           # Br outside every ANI model
    r = resolve_model(["C", "Cl", "H", "H", "H"], "ANI1ccx")        # Cl outside ANI-1ccx: auto-switch
    assert r["model"] == "ANI2x" and r["notes"]
    with pytest.raises(DomainError):
        resolve_model(["C", "H", "H", "H"], "auto")                  # methyl radical (odd electrons)
