"""
libbatch.py — batched L-BFGS relaxation for GLOMOS.

All structures of one generation are conformers of the same molecule (same atoms, same
order), so ANI can evaluate them in ONE forward/backward pass. On CPU that costs much less
than N separate calls (measured for dopamine with an ANI-1ccx-sized ensemble, 1 thread:
15.3 ms per structure and step alone vs 5.6 ms in a batch of 8).

The optimiser is the classic limited-memory BFGS used by ``ase.optimize.LBFGS``
(memory 100, initial inverse Hessian 1/alpha with alpha = 70, no line search, steps scaled so
that no atom moves more than ``maxstep``), run independently for every structure: batching
changes how forces are computed, not the trajectory of any structure.
``tests/test_batch_relax.py`` checks that steps and energies match ase.optimize.LBFGS.

Convergence criterion as in ASE: max_i |F_i| < fmax. The force thresholds in
``fmax_stages`` are applied in sequence, each with a fresh L-BFGS memory and at most
``max_steps`` steps (exactly what successive ``LBFGS(...).run(fmax, steps)`` calls do).
"""
import time

import numpy as np


# ----------------------------------------------------------------------------------------
# Energy/force providers: callable(symbols, [positions (N,3)]) -> (energies eV (n,), forces eV/A (n,N,3))
# ----------------------------------------------------------------------------------------
class TorchANIBatch:
    """Batched evaluation with the model inside a ``torchani.ase.Calculator``."""

    def __init__(self, calc, screening="ensemble"):
        import ase.units
        self.torch = __import__("torch")
        model = calc.model
        if screening == "single" and type(model).__name__ == "BuiltinEnsemble":
            model = model[0]                       # one network of the ensemble (same AEV, same shifter)
        self.model = model
        self.dtype = calc.dtype
        self.device = calc.device
        self.species_to_tensor = calc.species_to_tensor
        self.periodic_table_index = getattr(calc, "periodic_table_index", False)
        self.hartree = ase.units.Hartree
        self._species = None

    def _species_for(self, symbols, n):
        torch = self.torch
        key = (tuple(symbols), n)
        if self._species is None or self._species[0] != key:
            if self.periodic_table_index:
                from ase.data import atomic_numbers
                sp = torch.tensor([atomic_numbers[s] for s in symbols], dtype=torch.long)
            else:
                sp = self.species_to_tensor(list(symbols))
            self._species = (key, sp.to(self.device).unsqueeze(0).repeat(n, 1))
        return self._species[1]

    def __call__(self, symbols, positions):
        torch = self.torch
        n = len(positions)
        species = self._species_for(symbols, n)
        coords = torch.tensor(np.stack(positions), dtype=self.dtype, device=self.device, requires_grad=True)
        energies = self.model((species, coords)).energies
        grad = torch.autograd.grad(energies.sum(), coords)[0]
        e = energies.detach().to("cpu").numpy().astype(np.float64) * self.hartree
        f = -grad.to("cpu").numpy().astype(np.float64) * self.hartree
        return e, f


class LoopASE:
    """Fallback for any other ASE calculator (tests, MMFF stand-in): one call per structure."""

    def __init__(self, calc, template):
        self.calc = calc
        self.atoms = template.copy()
        self.atoms.calc = calc

    def __call__(self, symbols, positions):
        es, fs = [], []
        for p in positions:
            self.atoms.set_positions(p)
            es.append(float(self.atoms.get_potential_energy()))
            fs.append(np.array(self.atoms.get_forces(), dtype=np.float64))
        return np.array(es), np.array(fs)


def make_evaluator(calc, template, screening="ensemble"):
    if all(hasattr(calc, a) for a in ("model", "species_to_tensor", "dtype", "device")):
        return TorchANIBatch(calc, screening)
    return LoopASE(calc, template)


# ----------------------------------------------------------------------------------------
# L-BFGS state of one structure
# ----------------------------------------------------------------------------------------
class _LBFGSState:
    def __init__(self, memory, alpha, maxstep):
        self.memory, self.H0, self.maxstep = memory, 1.0 / alpha, maxstep
        self.reset()

    def reset(self):
        self.s, self.y, self.rho = [], [], []
        self.r0 = self.f0 = None
        self.iteration = 0

    def step(self, r, f):
        """r, f: flat arrays (3N). Returns the new flat positions."""
        if self.iteration > 0:
            s0 = r - self.r0
            y0 = self.f0 - f
            self.s.append(s0)
            self.y.append(y0)
            self.rho.append(1.0 / np.dot(y0, s0))
            if self.iteration > self.memory:
                self.s.pop(0)
                self.y.pop(0)
                self.rho.pop(0)
        loopmax = min(self.memory, self.iteration)
        a = np.empty(loopmax)
        q = -f.copy()
        for i in range(loopmax - 1, -1, -1):
            a[i] = self.rho[i] * np.dot(self.s[i], q)
            q -= a[i] * self.y[i]
        z = self.H0 * q
        for i in range(loopmax):
            b = self.rho[i] * np.dot(self.y[i], z)
            z += self.s[i] * (a[i] - b)
        p = -z
        longest = np.sqrt((p.reshape(-1, 3) ** 2).sum(axis=1).max())
        if longest >= self.maxstep:
            p = p * (self.maxstep / longest)
        self.r0, self.f0 = r, f
        self.iteration += 1
        return r + p


def relax_many(atoms_list, evaluator, fmax_stages=(2e-2, 5e-3), max_steps=400, maxstep=0.15,
               memory=100, alpha=70.0, check=None, on_done=None):
    """Relax several conformers of the same molecule together.

    in:
        atoms_list  list of ase.Atoms (not modified; copies are returned)
        evaluator   callable(symbols, positions) -> (energies eV, forces eV/A), see above
        check       called once per iteration (cooperative cancellation; may raise)
        on_done     callback(index, atoms, info) as soon as a structure finishes
    out:
        list of (atoms_copy, info) in input order; info = dict(energy_eV, converged, steps, seconds)
    """
    n = len(atoms_list)
    if n == 0:
        return []
    symbols = atoms_list[0].get_chemical_symbols()
    for a in atoms_list[1:]:
        if a.get_chemical_symbols() != symbols:
            raise ValueError("relax_many needs conformers of the same molecule (same atom order)")
    mols = []
    for a in atoms_list:
        m = a.copy()
        m.info = dict(a.info)
        m.calc = None
        mols.append(m)
    x = [m.get_positions().astype(np.float64).ravel() for m in mols]
    st = [_LBFGSState(memory, alpha, maxstep) for _ in range(n)]
    stage = [0] * n
    stage_steps = [0] * n
    steps = [0] * n
    seconds = [0.0] * n
    done = [False] * n
    converged = [False] * n
    energy = [None] * n
    forces = [None] * n
    results = [None] * n
    fmax2 = [f * f for f in fmax_stages]

    def finish(i, ok):
        done[i] = True
        converged[i] = ok
        mols[i].set_positions(x[i].reshape(-1, 3))
        info = {"energy_eV": float(energy[i]), "converged": ok, "steps": steps[i], "seconds": seconds[i],
                "forces": forces[i].reshape(-1, 3)}
        results[i] = (mols[i], info)
        if on_done is not None:
            on_done(i, mols[i], info)

    pending = list(range(n))                          # structures whose forces must be (re)computed
    while pending:
        if check is not None:
            check()
        t0 = time.time()
        e, f = evaluator(symbols, [x[i].reshape(-1, 3) for i in pending])
        share = (time.time() - t0) / len(pending)
        for k, i in enumerate(pending):
            energy[i], forces[i] = e[k], f[k].ravel()
            seconds[i] += share
        nxt = []
        for i in pending:
            # advance through stages whose threshold is already met (fresh memory each stage)
            fsq = (forces[i].reshape(-1, 3) ** 2).sum(axis=1).max()
            while fsq < fmax2[stage[i]]:
                stage[i] += 1
                stage_steps[i] = 0
                st[i].reset()
                if stage[i] == len(fmax_stages):
                    break
            if stage[i] == len(fmax_stages):
                finish(i, True)
                continue
            if stage_steps[i] >= max_steps:
                finish(i, False)
                continue
            t1 = time.time()
            x[i] = st[i].step(x[i], forces[i])
            seconds[i] += time.time() - t1
            stage_steps[i] += 1
            steps[i] += 1
            nxt.append(i)
        pending = nxt
    return results
