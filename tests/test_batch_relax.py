"""Batched L-BFGS (elaya_glomos.libbatch) must give exactly the trajectories of ase.optimize.LBFGS,
and the batched torch evaluator exactly the energies/forces of torchani's ASE calculator."""
import numpy as np
import pytest

from conftest import REAL_ASE

pytestmark = pytest.mark.skipif(not REAL_ASE, reason="needs the real ase package")


def _dopamine_confs(n=6, seed=7):
    pytest.importorskip("rdkit")
    from ase import Atoms
    from rdkit import Chem
    from rdkit.Chem import AllChem
    smi = "C1=CC(=C(C=C1CCN)O)O"
    m = Chem.AddHs(Chem.MolFromSmiles(smi))
    AllChem.EmbedMultipleConfs(m, n, randomSeed=seed)
    syms = [a.GetSymbol() for a in m.GetAtoms()]
    return smi, [Atoms(syms, positions=c.GetPositions()) for c in m.GetConformers()]


def test_batched_lbfgs_reproduces_ase_lbfgs():
    from ase.optimize import LBFGS
    from mmff_calc import MMFFCalculator
    from elaya_glomos.libbatch import make_evaluator, relax_many
    smi, confs = _dopamine_confs()
    calc = MMFFCalculator(smi)
    res = relax_many(confs, make_evaluator(calc, confs[0]), (2e-2, 5e-3), 400)
    for a, (mol, info) in zip(confs, res):
        b = a.copy()
        b.calc = calc
        steps = 0
        for fmax in (2e-2, 5e-3):
            dyn = LBFGS(b, logfile=None, maxstep=0.15)
            ok = bool(dyn.run(fmax=fmax, steps=400))
            steps += dyn.nsteps
        assert ok and info["converged"]
        assert info["steps"] == steps
        assert np.allclose(mol.get_positions(), b.get_positions(), atol=1e-10)
        assert abs(info["energy_eV"] - b.get_potential_energy()) < 1e-10


def test_step_limit_marks_unconverged():
    from mmff_calc import MMFFCalculator
    from elaya_glomos.libbatch import make_evaluator, relax_many
    smi, confs = _dopamine_confs(2)
    res = relax_many(confs, make_evaluator(MMFFCalculator(smi), confs[0]), (1e-4,), 5)
    assert all(not info["converged"] and info["steps"] == 5 for _, info in res)


def test_cancel_mid_batch_keeps_finished_structures():
    """The GA relies on on_done() being called as each structure converges, so that a timeout
    in the middle of a batch keeps the structures that had already finished."""
    from mmff_calc import MMFFCalculator
    from elaya_glomos.libbatch import make_evaluator, relax_many
    smi, confs = _dopamine_confs(4)
    finished = []

    class Stop(Exception):
        pass

    def check():
        if finished:
            raise Stop()
    with pytest.raises(Stop):
        relax_many(confs, make_evaluator(MMFFCalculator(smi), confs[0]), (2e-2, 5e-3), 400,
                   check=check, on_done=lambda i, m, info: finished.append(i))
    assert 1 <= len(finished) < len(confs)


def test_torch_batch_evaluator_matches_torchani_ase_calculator():
    torch = pytest.importorskip("torch")
    torchani = pytest.importorskip("torchani")
    from elaya_glomos.libbatch import TorchANIBatch, make_evaluator
    _, confs = _dopamine_confs(3)
    aev = torchani.AEVComputer(5.2, 3.5, torch.tensor([16.0]), torch.linspace(0.9, 4.9, 4),
                               torch.tensor([8.0]), torch.tensor([32.0]), torch.tensor([0.9, 2.2]),
                               torch.tensor([0.2, 1.4, 2.6]), 4)
    torch.manual_seed(0)
    d = aev.aev_length

    def net():
        return torch.nn.Sequential(torch.nn.Linear(d, 16), torch.nn.CELU(0.1), torch.nn.Linear(16, 1))
    model = torch.nn.Sequential(aev, torchani.ANIModel([net() for _ in range(4)])).double()
    model.periodic_table_index = False
    calc = torchani.ase.Calculator(["H", "C", "N", "O"], model)
    ev = make_evaluator(calc, confs[0])
    assert isinstance(ev, TorchANIBatch)
    e, f = ev(confs[0].get_chemical_symbols(), [a.get_positions() for a in confs])
    for k, a in enumerate(confs):
        b = a.copy()
        b.calc = calc
        assert abs(b.get_potential_energy() - e[k]) < 1e-9
        assert np.abs(b.get_forces() - f[k]).max() < 1e-9


def test_screening_parameter_is_validated():
    from elaya_jobs import clamp_params
    assert clamp_params({"preset": "fast"})["screening"] == "ensemble"
    assert clamp_params({"preset": "fast", "screening": "single"})["screening"] == "single"
    with pytest.raises(ValueError):
        clamp_params({"screening": "half"})


def test_single_screening_uses_first_network_of_builtin_ensemble():
    torch = pytest.importorskip("torch")
    from elaya_glomos.libbatch import TorchANIBatch

    class BuiltinEnsemble(torch.nn.Module):           # same name as torchani's class
        def __getitem__(self, i):
            return ("network", i)

    class Calc:
        model, dtype, device = BuiltinEnsemble(), torch.float64, torch.device("cpu")
        species_to_tensor = staticmethod(lambda s: torch.zeros(len(s), dtype=torch.long))
    assert TorchANIBatch(Calc(), "single").model == ("network", 0)
    assert isinstance(TorchANIBatch(Calc(), "ensemble").model, BuiltinEnsemble)
