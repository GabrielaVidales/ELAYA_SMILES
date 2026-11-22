"""
Test fixtures.

The CI image used to develop ELAYA v2 had no ase / rdkit / torch.  When ``ase`` is not
importable this conftest installs a *minimal stand-in* (Atoms, Atom, data, optimize.LBFGS)
that covers exactly the API surface used by the GLOMOS package, so the genetic algorithm,
USR filter, torsion machinery and job manager can be exercised end to end with a toy
force field.  With the real ase installed nothing is replaced.
These tests validate the *logic*; chemistry accuracy is covered by validation/.
"""
import os
import sys
import types

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_SYMBOLS = ["X", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P",
            "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
            "Ga", "Ge", "As", "Se", "Br"]


def _install_fake_ase():
    from scipy.optimize import minimize
    num = {s: i for i, s in enumerate(_SYMBOLS)}
    cov = np.full(len(_SYMBOLS), 1.5)
    for s, r in dict(H=0.31, C=0.76, N=0.71, O=0.66, F=0.57, S=1.05, Cl=1.02).items():
        cov[num[s]] = r

    class Atom:
        def __init__(self, symbol, position=(0, 0, 0)):
            self.symbol, self.position = symbol, np.array(position, float)

    class Atoms:
        def __init__(self, symbols=None, positions=None, numbers=None):
            if numbers is not None:
                self._z = [int(n) for n in numbers]
            elif symbols:
                self._z = [num[s] for s in _expand(symbols)]
            else:
                self._z = []
            self._pos = np.zeros((len(self._z), 3)) if positions is None else np.array(positions, float)
            self.info, self.calc = {}, None

        def __len__(self):
            return len(self._z)

        def append(self, atom):
            self._z.append(num[atom.symbol])
            self._pos = np.vstack([self._pos, atom.position[None, :]])

        def copy(self):
            a = Atoms(numbers=self._z, positions=self._pos.copy())
            a.info = dict(self.info)
            return a

        def get_positions(self):
            return self._pos.copy()

        def set_positions(self, p):
            self._pos = np.array(p, float)

        def get_atomic_numbers(self):
            return np.array(self._z)

        def get_chemical_symbols(self):
            return [_SYMBOLS[z] for z in self._z]

        def get_chemical_formula(self):
            from collections import Counter
            c = Counter(self.get_chemical_symbols())
            order = sorted(c, key=lambda s: (s != "C", s != "H", s))
            return "".join(s + (str(c[s]) if c[s] > 1 else "") for s in order)

        def get_potential_energy(self):
            return float(self.calc.energy_forces(self._pos)[0])

        def get_forces(self):
            return self.calc.energy_forces(self._pos)[1]

    def _expand(symbols):
        if isinstance(symbols, str):
            import re
            out = []
            for s, n in re.findall(r"([A-Z][a-z]?)(\d*)", symbols):
                out += [s] * int(n or 1)
            return out
        return list(symbols)

    class LBFGS:
        def __init__(self, atoms, logfile=None, maxstep=0.2):
            self.atoms, self.nsteps, self._cbs = atoms, 0, []

        def attach(self, fn, interval=1):
            self._cbs.append((fn, interval))

        def run(self, fmax=0.05, steps=100):
            a = self.atoms
            shape = a._pos.shape

            def f(x):
                e, g = a.calc.energy_forces(x.reshape(shape))
                return e, -g.ravel()

            def cb(_xk):
                self.nsteps += 1
                for fn, iv in self._cbs:
                    if self.nsteps % iv == 0:
                        fn()
            res = minimize(f, a._pos.ravel(), jac=True, method="BFGS", callback=cb,
                           options={"maxiter": steps, "gtol": 0.5 * fmax})
            a._pos = res.x.reshape(shape)
            return bool(np.abs(a.calc.energy_forces(a._pos)[1]).max() < fmax)

    ase = types.ModuleType("ase")
    ase.Atom, ase.Atoms = Atom, Atoms
    data = types.ModuleType("ase.data")
    data.covalent_radii, data.chemical_symbols = cov, _SYMBOLS
    opt = types.ModuleType("ase.optimize")
    opt.LBFGS = LBFGS
    ase.data, ase.optimize = data, opt
    sys.modules.update({"ase": ase, "ase.data": data, "ase.optimize": opt})


try:
    import ase  # noqa: F401
    from ase.calculators.calculator import Calculator as _AseCalculator, all_changes as _all_changes
    REAL_ASE = True
except ImportError:
    _install_fake_ase()
    REAL_ASE = False

    class _AseCalculator:                       # the fake Atoms calls energy_forces() directly
        def __init__(self, **kw):
            pass
    _all_changes = None


class ToyCalculator(_AseCalculator):
    """Smooth toy potential: harmonic bonds + soft repulsion + 3-fold torsion terms.
    Energies in eV, forces by central finite differences (tiny systems only).
    With the real ASE installed it behaves as a regular ASE calculator."""

    implemented_properties = ["energy", "forces"]

    def calculate(self, atoms=None, properties=("energy",), system_changes=_all_changes):
        super().calculate(atoms, properties, system_changes)
        e, f = self.energy_forces(self.atoms.get_positions())
        self.results["energy"], self.results["forces"] = e, f

    def __init__(self, atoms, bonds, torsions, v3=0.1):
        _AseCalculator.__init__(self)
        self.bonds = [(i, j, float(np.linalg.norm(atoms.get_positions()[i] - atoms.get_positions()[j])))
                      for i, j in bonds]
        self.torsions, self.v3 = torsions, v3
        self.bonded = {frozenset(b) for b in bonds}
        self.n = len(atoms)

    @staticmethod
    def _dih(p, a, b, c, d):
        b0, b1, b2 = p[a] - p[b], p[c] - p[b], p[d] - p[c]
        b1 = b1 / np.linalg.norm(b1)
        v, w = b0 - np.dot(b0, b1) * b1, b2 - np.dot(b2, b1) * b1
        return np.arctan2(np.dot(np.cross(b1, v), w), np.dot(v, w))

    def _prep(self):
        if not hasattr(self, "_bi"):
            self._bi = np.array([b[0] for b in self.bonds]); self._bj = np.array([b[1] for b in self.bonds])
            self._r0 = np.array([b[2] for b in self.bonds])
            iu = np.triu_indices(self.n, 1)
            keep = np.array([frozenset((i, j)) not in self.bonded for i, j in zip(*iu)])
            self._pi, self._pj = iu[0][keep], iu[1][keep]

    def energy(self, p):
        self._prep()
        rb = np.linalg.norm(p[self._bi] - p[self._bj], axis=1)
        e = 10.0 * np.sum((rb - self._r0) ** 2)
        rp = np.maximum(np.linalg.norm(p[self._pi] - p[self._pj], axis=1), 0.5)
        e += 0.004 * np.sum((3.0 / rp) ** 6)
        for t in self.torsions:
            e += 0.5 * self.v3 * (1 + np.cos(3 * self._dih(p, *t)))
        return float(e)

    def energy_forces(self, p):
        """Analytic forces for bonds + repulsion; central differences for the (few) torsions."""
        p = np.asarray(p, float)
        self._prep()
        g = np.zeros_like(p)
        d = p[self._bi] - p[self._bj]
        rb = np.linalg.norm(d, axis=1)
        coef = (20.0 * (rb - self._r0) / np.maximum(rb, 1e-9))[:, None] * d
        np.add.at(g, self._bi, coef); np.add.at(g, self._bj, -coef)
        d = p[self._pi] - p[self._pj]
        rp = np.maximum(np.linalg.norm(d, axis=1), 0.5)
        coef = (-6 * 0.004 * 3.0 ** 6 / rp ** 8)[:, None] * d
        np.add.at(g, self._pi, coef); np.add.at(g, self._pj, -coef)
        h = 1e-5
        for t in self.torsions:
            for i in t:
                for k in range(3):
                    q = p.copy(); q[i, k] += h
                    r = p.copy(); r[i, k] -= h
                    g[i, k] += 0.5 * self.v3 * (np.cos(3 * self._dih(q, *t)) - np.cos(3 * self._dih(r, *t))) / (2 * h)
        return self.energy(p), -g


def chain_atoms(n=6, bond=1.54, angle_deg=112.0):
    """Zig-zag carbon chain (heavy atoms only) used as a minimal flexible molecule."""
    from ase import Atoms
    half = np.radians(angle_deg) / 2
    pos = [[i * bond * np.sin(half), (i % 2) * bond * np.cos(half), 0.0] for i in range(n)]
    return Atoms(["C"] * n, positions=pos)


@pytest.fixture
def hexane_skeleton():
    atoms = chain_atoms(6)
    bonds = [[i, i + 1] for i in range(5)]
    problem = {"bonds": bonds, "rotors": [{"a": i, "b": i + 1, "kind": "sp3"} for i in range(1, 4)],
               "chiral": [], "ez": [], "charge": 0}
    tors = [(i - 1, i, i + 1, i + 2) for i in range(1, 4)]
    return atoms, problem, ToyCalculator(atoms, bonds, tors)
