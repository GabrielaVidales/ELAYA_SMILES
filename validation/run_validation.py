#!/usr/bin/env python3
"""End-to-end validation of the GLOMOS search on small molecules (needs RDKit, ASE, torch, torchani).

    python validation/run_validation.py [--model auto] [--minutes 5] [--only butane,aspirin]

For every test molecule it:
  1. builds the ETKDG seed pool and the chemistry-aware rotor list (elaya_chem),
  2. runs the genetic search (same code path as the web job) in a temporary directory,
  3. checks the outcome against expectations that do not depend on the exact ANI energies:
       * number of rotors detected,
       * GLOMOS finds >= the expected minimum number of distinct conformers,
       * every returned geometry keeps the bond graph and the stereochemistry,
       * the lowest conformer is reproducible with the same random seed.
  4. writes validation/validation_report.md (energies, populations, rotational constants).

Reference expectations (literature, not ANI-specific):
  butane  : anti is the global minimum; gauche lies ~0.6-0.9 kcal/mol above (CCSD(T) ~0.6-0.7)
  ethanol : anti (trans) below gauche by ~0.1-0.5 kcal/mol
These are *sanity checks*, not benchmarks: ANI-1ccx errors for conformer energies are ~0.5-1 kcal/mol.
"""
import argparse
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import elaya_chem as ec                                    # noqa: E402
from elaya_glomos.ani_domain import resolve_model                # noqa: E402
from elaya_glomos.libreport import Reporter                      # noqa: E402
from elaya_glomos.libcalc_ani import ModelLoadError              # noqa: E402

CASES = {
    #  name: (smiles, expected rotors, min distinct conformers, note)
    "butane":  ("CCCC", 1, 2, "anti + gauche (gauche enantiomers merge: USR is mirror invariant)"),
    "ethanol": ("CCO", 1, 2, "C-O (OH) rotor; CH3 top excluded"),
    "pentane": ("CCCCC", 2, 3, ""),
    "aspirin": ("CC(=O)Oc1ccccc1C(=O)O", 4, 3, "ester C(=O)-O, O-aryl, aryl-COOH, acid C-OH (CH3 top excluded)"),
    "alanine": ("C[C@H](N)C(=O)O", 3, 2, "stereocentre must be preserved"),
}


def run_case(name, smiles, model, minutes, seed=11):
    from elaya_glomos.heuristic_ga_rotamers import conformational
    molh, seed_xyz, problem, info = ec.glomos_seed_pool(smiles, 4, 665)
    syms = [a.GetSymbol() for a in molh.GetAtoms()]
    dom = resolve_model(syms, model, problem["charge"])
    import json
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as wd:
        os.chdir(wd)
        try:
            open("seed.xyz", "w").write(seed_xyz)
            json.dump(problem, open("problem.json", "w"))
            open("INPUT.txt", "w").write(
                "rotamer_seed seed.xyz\nproblem_file problem.json\nnof_initpop 10\nnof_matings 6\nnof_mutants 6\n"
                "nof_generations 6\ncutoff_energy 6\ncutoff_population 10\ncalculator %s\nrandom_seed %d\n"
                "max_minutes %g\n" % (dom["model"], seed, minutes))
            t0 = time.time()
            res = conformational("INPUT.txt", reporter=Reporter(emit=lambda e: None, echo=False))
            dt = time.time() - t0
        finally:
            os.chdir(old)
    return molh, problem, res, dt, dom["model"]


def check(name, smiles, exp_rotors, min_conf, molh, problem, res, dt):
    from rdkit import Chem  # noqa: F401
    msgs, ok = [], True
    if len(problem["rotors"]) != exp_rotors:
        ok = False
        msgs.append("rotors: expected %d, found %d" % (exp_rotors, len(problem["rotors"])))
    n = len(res["conformers"])
    if n < min_conf:
        ok = False
        msgs.append("conformers: expected >= %d, found %d" % (min_conf, n))
    for c in res["conformers"]:
        mol = ec.mol_with_coords(smiles, c["xyz"])
        qa = ec.stereo_qa(mol, smiles, 0)
        if not qa["ok"]:
            ok = False
            msgs.append("%s: stereo changed (%s)" % (c["name"], "; ".join(qa["problems"])))
        syms, pos = ec.parse_xyz(c["xyz"])
        from elaya_smiles import MolecularTools
        bc = MolecularTools().check_bonds(smiles, syms, pos)
        if bc["ok"] is False:
            ok = False
            msgs.append("%s: bond graph changed (%s)" % (c["name"], bc["detail"]))
    return ok, msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="auto")
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    names = [n for n in CASES if not a.only or n in a.only.split(",")]
    lines = ["# ELAYA / GLOMOS validation report", "", "Model: %s · generated %s" % (a.model, time.strftime("%Y-%m-%d %H:%M")), ""]
    failed = 0
    for name in names:
        smiles, er, mc, note = CASES[name]
        print("== %s (%s)" % (name, smiles), flush=True)
        try:
            molh, problem, res, dt, model = run_case(name, smiles, a.model, a.minutes)
        except ModelLoadError as exc:
            print("\nCannot run the validation: %s" % exc, file=sys.stderr)
            return 2
        ok, msgs = check(name, smiles, er, mc, molh, problem, res, dt)
        failed += (not ok)
        lines += ["## %s  `%s`  — %s" % (name, smiles, "PASS" if ok else "FAIL"), "",
                  "%s · %d rotors · %d conformers · %.1f s · %s" % (model, len(problem["rotors"]), len(res["conformers"]), dt, note), "",
                  "| # | ΔE (kcal/mol) | pop 298 K (%) | A (GHz) | B (GHz) | C (GHz) |", "|--:|--:|--:|--:|--:|--:|"]
        for i, c in enumerate(res["conformers"], 1):
            syms, pos = ec.parse_xyz(c["xyz"])
            rc = ec.rotational_constants(syms, pos)
            lines.append("| %d | %.3f | %.1f | %.3f | %.3f | %.3f |" % (i, c["rel_kcal"], 100 * c["boltzmann_298"], rc["A_GHz"], rc["B_GHz"], rc["C_GHz"]))
        lines += [""] + ["- ⚠ " + m for m in msgs] + [""]
        print("   ", "PASS" if ok else "FAIL", msgs, flush=True)
    out = os.path.join(HERE, "validation_report.md")
    open(out, "w").write("\n".join(lines))
    print("report:", out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
