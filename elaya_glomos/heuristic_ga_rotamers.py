"""
heuristic_ga_rotamers.py — GLOMOS genetic algorithm for conformational search.

Pipeline (same logic as the original GLOMOS rotamer GA, repaired and extended)

    seeds (RDKit ETKDG pool)  ->  generation 0 (seeds + random torsion variants)
        -> ANI relaxation -> energy window -> USR/energy deduplication
    for each generation:
        roulette selection -> crossover in torsion space ("mating")
        + mutation of the best structures ("mutants")
        -> ANI relaxation -> window -> deduplication (also against the population)
        -> keep the ``cutoff_population`` best
        stop on: max generations | stagnation | time budget | cancellation
    final: tight re-optimisation ("polish") of the survivors

Outputs (written to the working directory)
    summary.xyz   current population, absolute energies (kcal/mol) in the comment
    result.json   full ensemble + metadata (checkpointed after every generation, so a
                  cancelled / timed-out run still has a usable partial result)

INPUT.txt keys (all optional except rotamer_seed)
    rotamer_seed      multi-XYZ with one or more starting structures (same atom order)
    problem_file      JSON describing the bond graph, rotors, stereo (see build_problem)
    nof_initpop nof_matings nof_mutants nof_generations
    tol_similarity (USR, default 0.95)  tol_energy (kcal/mol, default 0.1)
    cutoff_energy (kcal/mol window)     cutoff_population (max structures kept)
    nof_repeats nof_stagnant            calculator (ANI1x | ANI1ccx | ANI2x)
    prec              force thresholds in eV/A for the staged relaxation
    polish_prec       final force threshold(s) in eV/A     max_steps
    random_seed       0 -> chosen from the clock and recorded in result.json
    max_minutes       wall-clock budget (0 = unlimited)
    -- large-molecule ("lite") engine, all optional --
    prerelax          none | mmff   MMFF94 pre-relaxation of every candidate before ANI
    prescreen         k >= 1        build k x more candidates, keep the lowest after MMFF
    ani_member        -1 | n        screen with network n of the ensemble only
    ani_dtype         float64 | float32
    polish_top        0 = polish all survivors, n = only the n best
    final_ranking     polish | ensemble_sp   (ensemble single points, networks loaded one by one)
"""
import os
import json
import random
import time
import numpy as np

from elaya_glomos.libutils import (readxyzs, writexyzs, atoms_to_xyz, sort_by_energy, rename,
                             adjacency_matrix, adjacency_from_bonds)
from elaya_glomos.libstdio import read_main_input
from elaya_glomos.librotamers import (Problem, build_rotors, make_random_rotamers,
                                make_crossover_rotamers, make_mutant_rotamers, get_torsions)
from elaya_glomos.libsel_roulette import get_fitness, get_roulette_wheel_selection
from elaya_glomos.libdisc_usr import deduplicate_by_usr
from elaya_glomos.libcalc_ani import ANI, get_calculator, ensemble_single_points, release_models
from elaya_glomos.libreport import Reporter, Stopped, console_reporter

ndigit1 = 3
ndigit2 = 4
KT_298 = 0.0019872041 * 298.15          # kcal/mol


# ------------------------------------------------------------------------------
def build_problem(problem_dict, seed0):
    """Create the Problem (bond graph, rotors, stereo restraints) for the GA.

    problem_dict (or None for legacy mode) keys:
        bonds   [[i, j], ...]                      bond graph (RDKit)
        rotors  [{"a": i, "b": j, "kind": str}]    rotatable bonds (RDKit-classified)
        chiral  [[c, n1, n2, n3, sign], ...]
        ez      [[x, a, b, y, is_cis], ...]
        charge  int
    """
    numbers = seed0.get_atomic_numbers()
    if problem_dict and problem_dict.get("bonds"):
        ref_adj = adjacency_from_bonds(len(numbers), problem_dict["bonds"])
        specs = problem_dict.get("rotors")
        legacy = False
    else:
        ref_adj = adjacency_matrix(seed0)
        specs = None
        legacy = True
    rotors = build_rotors(ref_adj, numbers, specs if specs is not None else None)
    pd = problem_dict or {}
    chiral = [(int(c[0]), int(c[1]), int(c[2]), int(c[3]), int(c[4])) for c in pd.get("chiral", [])]
    ez = [(int(e[0]), int(e[1]), int(e[2]), int(e[3]), bool(e[4])) for e in pd.get("ez", [])]
    problem = Problem(numbers, ref_adj, rotors, chiral=chiral, ez=ez, charge=pd.get("charge", 0))
    return problem, legacy


def _rel(pop):
    e0 = min(float(a.info["e"]) for a in pop) if pop else 0.0
    return e0


def display_mol_info(moleculein, reporter=None):
    """Ranked summary of a population (relative + absolute energies, fitness)."""
    if len(moleculein) == 0:
        return
    molzz = sort_by_energy(moleculein, 1)
    fitness = get_fitness(moleculein)
    e0 = float(molzz[0].info["e"])
    for ii, imol in enumerate(molzz):
        line = "#%s %-14s %12.4f kcal/mol  (+%.3f)  f=%.2f" % (
            str(ii + 1).zfill(3), imol.info["i"], float(imol.info["e"]),
            float(imol.info["e"]) - e0, fitness[ii])
        (reporter.log if reporter else print)(line)


def _population_payload(pop, limit=12):
    if not pop:
        return []
    s = sort_by_energy(pop, 1)
    e0 = float(s[0].info["e"])
    return [{"name": a.info["i"], "rel": round(float(a.info["e"]) - e0, 4)} for a in s[:limit]]


def _write_result(path, pop, meta, partial):
    """Atomically write result.json for the given population."""
    s = sort_by_energy(pop, 1) if pop else []
    e0 = float(s[0].info["e"]) if s else 0.0
    confs = []
    rel = [float(a.info["e"]) - e0 for a in s]
    w = [float(np.exp(-r / KT_298)) for r in rel]
    z = sum(w) or 1.0
    for a, r, wi in zip(s, rel, w):
        confs.append({
            "name": a.info["i"],
            "energy_kcal": float(a.info["e"]),
            "rel_kcal": r,
            "boltzmann_298": wi / z,
            "converged": bool(a.info.get("converged", True)),
            "ensemble_std": (float(a.info["e_std"]) if a.info.get("e_std") is not None else None),
            "xyz": atoms_to_xyz(a, "%.8f %s" % (float(a.info["e"]), a.info["i"])),
        })
    payload = {"partial": bool(partial), "meta": meta, "conformers": confs}
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)
    return payload


# ------------------------------------------------------------------------------

def merge_population(pop, new, tol_similarity, tol_energy, cutoff_energy, cutoff_population):
    """Merge ``new`` into ``pop``, remove duplicates, apply the energy window, truncate.

    Duplicates are resolved over the union, so the LOWER-energy member of each pair survives
    even when it is the newcomer (2.0.2 filtered ``new`` against ``pop`` and therefore kept the
    older, higher-energy copy of the same basin)."""
    merged = sort_by_energy(list(pop) + list(new or []), 1)
    if merged:
        merged = deduplicate_by_usr(merged, tol_similarity, tol_energy, flag=0)
        e0 = float(merged[0].info["e"])
        merged = [a for a in merged if float(a.info["e"]) - e0 <= cutoff_energy]
    return merged[:cutoff_population]


def conformational(inputfile="INPUT.txt", reporter=None, problem=None, seeds=None):
    """Run the GLOMOS rotamer GA.

    in:
        inputfile : INPUT.txt path (see module docstring)
        reporter  : glomos.libreport.Reporter (progress, cancellation, deadline)
        problem, seeds : optional pre-built Problem / list of ase.Atoms (testing)
    out:
        dict (the content of result.json)
    """
    df = read_main_input(inputfile)
    rotamer_seed = df.get_str("rotamer_seed", "rotamer.xyz")
    problem_file = df.get_str("problem_file", "")
    nof_initpop = max(1, df.get_int("nof_initpop", 10))
    nof_matings = max(0, df.get_int("nof_matings", 5))
    nof_mutants = max(0, df.get_int("nof_mutants", 5))
    tol_similarity = df.get_float("tol_similarity", 0.95)
    tol_energy = df.get_float("tol_energy", 0.1)
    cutoff_energy = df.get_float("cutoff_energy", 5.0)
    cutoff_population = max(1, df.get_int("cutoff_population", 8))
    nof_generations = max(0, df.get_int("nof_generations", 3))
    nof_repeats = max(1, df.get_int("nof_repeats", 2))
    nof_stagnant = max(1, df.get_int("nof_stagnant", 3))
    calculator = df.get_str("calculator", "ANI1ccx")
    preclist = tuple(df.get_floatlist("prec", [2e-2, 5e-3]))
    polish_prec = tuple(df.get_floatlist("polish_prec", [1e-3]))
    max_steps = df.get_int("max_steps", 400)
    random_seed = df.get_int("random_seed", 0)
    max_minutes = df.get_float("max_minutes", 0.0)
    screening = df.get_str("screening", "ensemble").lower()
    if screening not in ("ensemble", "single"):
        raise ValueError("screening must be 'ensemble' or 'single'")
    prerelax = df.get_str("prerelax", "none").lower()
    prescreen = max(1, df.get_int("prescreen", 1))
    ani_member = df.get_int("ani_member", -1)
    ani_member = None if ani_member < 0 else ani_member
    ani_dtype = df.get_str("ani_dtype", "") or None
    polish_top = max(0, df.get_int("polish_top", 0))
    final_ranking = df.get_str("final_ranking", "polish").lower()

    if reporter is None:
        reporter = console_reporter(
            deadline=(time.time() + 60.0 * max_minutes) if max_minutes > 0 else None)
    elif max_minutes > 0 and reporter.deadline is None:
        reporter.deadline = time.time() + 60.0 * max_minutes

    if random_seed <= 0:
        random_seed = int(time.time() * 1000) % 2147483647
    rng = random.Random(random_seed)
    t_start = time.time()

    # ---- seeds and problem -----------------------------------------------------
    if seeds is None:
        seeds = readxyzs(rotamer_seed)
    if not seeds:
        raise ValueError("No starting structure found in %s" % rotamer_seed)
    pdict = None
    if problem is None:
        if problem_file and os.path.isfile(problem_file):
            with open(problem_file) as fh:
                pdict = json.load(fh)
        problem, legacy = build_problem(pdict, seeds[0])
        if legacy:
            reporter.log("WARNING: no problem file; rotors inferred from geometry "
                         "(includes multiple bonds). Use the ELAYA backend for chemistry-aware rotors.")
    usable = []
    for k, s in enumerate(seeds):
        reason = problem.why_invalid(s, check_clash=False)
        if reason:
            reporter.log("Seed %d discarded (%s)" % (k + 1, reason))
        else:
            usable.append(s)
    if not usable:
        raise ValueError("None of the starting structures is consistent with the bond graph.")
    seeds = usable

    formula = seeds[0].get_chemical_formula()
    meta = {
        "formula": formula, "n_atoms": len(seeds[0]), "n_rotors": len(problem.rotors),
        "rotors": [r.as_dict() for r in problem.rotors], "calculator": calculator,
        "nof_initpop": nof_initpop, "nof_matings": nof_matings, "nof_mutants": nof_mutants,
        "nof_generations": nof_generations, "cutoff_energy": cutoff_energy,
        "cutoff_population": cutoff_population, "tol_similarity": tol_similarity,
        "tol_energy": tol_energy, "prec": list(preclist), "polish_prec": list(polish_prec),
        "random_seed": random_seed, "n_seeds": len(seeds), "units": "kcal/mol", "screening": screening,
    }

    # ---- optional MMFF funnel (large molecules) ---------------------------------
    mmff = None
    if prerelax == "mmff" and pdict and pdict.get("molblock"):
        try:
            from elaya_glomos.libmmff import MMFFRelaxer
            mmff = MMFFRelaxer(pdict["molblock"])
            meta.update({"prerelax": mmff.kind, "prescreen": prescreen})
        except Exception as exc:                          # noqa: BLE001
            reporter.log("MMFF pre-relaxation unavailable (%s); candidates go straight to ANI." % exc)
    if ani_member is not None:
        meta["ani_member"] = ani_member
    if ani_dtype:
        meta["ani_dtype"] = ani_dtype

    def torsions_of(a):
        return get_torsions(a.get_positions(), problem.rotors) if problem.rotors else np.zeros(0)

    def same_basin(t1, t2, tol=30.0):
        d = np.abs((t1 - t2 + 180.0) % 360.0 - 180.0)
        return d.size == 0 or float(d.max()) < tol

    def funnel(cands, keep, avoid=()):
        """MMFF-relax the candidates, drop invalid ones, those that repeat a torsion pattern already
        in ``avoid`` (the population) or in the batch, and keep the ``keep`` lowest in MMFF energy."""
        if mmff is None or not cands:
            return cands[:keep]
        known = [torsions_of(a) for a in avoid]
        relaxed = []
        for c in cands:
            reporter.check()
            r = mmff.relax(c)
            if r is not None and problem.why_invalid(r, check_clash=False) is None:
                relaxed.append(r)
        relaxed.sort(key=lambda a: a.info["e_mmff"])
        out, skipped = [], 0
        for r in relaxed:
            t = torsions_of(r)
            if any(same_basin(t, k) for k in known):
                skipped += 1
                continue
            known.append(t)
            out.append(r)
            if len(out) == keep:
                break
        if skipped:
            reporter.log("MMFF funnel: %d candidate(s) repeat a known conformer and were skipped" % skipped)
        return out

    reporter.log("----------------- Genetic Algorithm for Rotamers -----------------")
    reporter.log("Chemical Formula      = %s" % formula)
    reporter.log("Rotatable torsions    = %d" % len(problem.rotors))
    for k, r in enumerate(problem.rotors):
        reporter.log(" -Rotor[%d]  %d-%d  (%s, %d atoms move)" % (k + 1, r.a + 1, r.b + 1, r.kind, len(r.moving)))
    reporter.log("Starting structures   = %d   random seed = %d" % (len(seeds), random_seed))
    reporter.log("Theory level          = %s%s" % (calculator, "" if ani_member is None else
                 "  (screening with network %d, %s)" % (ani_member, ani_dtype or "float64")))
    if mmff is not None:
        reporter.log("Pre-relaxation        = %s, %dx candidates per slot" % (mmff.kind, prescreen))
    # Build the potential once, before any optimisation: a missing dependency / parameter set
    # must stop the run with one clear message instead of failing every structure.
    reporter.log("Loading %s model..." % calculator)
    t_model = time.time()
    if ani_member is None and not ani_dtype:
        get_calculator(calculator)
    else:
        get_calculator(calculator, ani_member, ani_dtype)
    reporter.log("Model ready (%.1f s)" % (time.time() - t_model))
    reporter.event("start", generations=nof_generations, n_rotors=len(problem.rotors),
                   n_atoms=len(seeds[0]), formula=formula, seed=random_seed, model=calculator)

    result_path = "result.json"
    population = []
    stop_reason = "completed"
    n_evaluated = 0
    gen_times = []

    def relax_batch(batch, collected):
        # all candidates of a generation are relaxed together (one batched ANI call per step)
        ANI(batch, opt=calculator, preclist=preclist, problem=problem, reporter=reporter,
            max_steps=max_steps, sink=collected, screening=screening, member=ani_member, dtype=ani_dtype)

    def merge_into(pop, new):
        return merge_population(pop, new, tol_similarity, tol_energy, cutoff_energy, cutoff_population)

    try:
        # ---- generation 0 -------------------------------------------------------
        reporter.log("---------------------------GENERATION 0---------------------------")
        reporter.event("phase", name="generation0")
        xrand = make_random_rotamers(seeds, nof_initpop * prescreen, problem, rng)
        if mmff is not None:
            reporter.log("MMFF pre-relaxation of %d candidates..." % len(xrand))
        xrand = funnel(xrand, nof_initpop)
        rename(xrand, "random_" + str(0).zfill(ndigit1), ndigit2)
        reporter.log("Generation 0: %d starting structures (%d rotors)" % (len(xrand), len(problem.rotors)))
        reporter.event("progress", gen=0, total=nof_generations, conformer="", best_energy=None,
                       gen_times=[], done=0, of=len(xrand))
        t0 = time.time()
        collected = []
        try:
            relax_batch(xrand, collected)
        finally:
            n_evaluated += len(xrand)
            population = merge_into([], collected)
        gen_times.append(time.time() - t0)
        if not population:
            raise RuntimeError("All starting structures were discarded after ANI relaxation. "
                               "Check the molecule (charge, unusual bonding) or the ANI model.")
        display_mol_info(population, reporter)
        writexyzs(population, "summary.xyz")
        _write_result(result_path, population, meta, partial=True)
        reporter.event("population", gen=0, conformers=_population_payload(population))
        reporter.event("progress", gen=0, total=nof_generations, conformer=population[0].info["i"],
                       best_energy=float(population[0].info["e"]), gen_times=gen_times[:],
                       done=len(xrand), of=len(xrand))

        # ---- evolution -----------------------------------------------------------
        can_evolve = len(problem.rotors) > 0
        if not can_evolve:
            reporter.log("No rotatable torsions: skipping the genetic search (ring/seed conformers only).")
            meta["note"] = "no rotatable torsions"
        names_prev = [m.info["i"] for m in population][:nof_repeats]
        stagnant = 0
        for igen in range(nof_generations if can_evolve else 0):
            reporter.check()
            reporter.log("---------------------------GENERATION %d---------------------------" % (igen + 1))
            reporter.event("phase", name="generation", gen=igen + 1)
            t0 = time.time()
            parents_p = get_roulette_wheel_selection(population, nof_matings * prescreen, rng)
            parents_m = get_roulette_wheel_selection(population, nof_matings * prescreen, rng)
            children = funnel(make_crossover_rotamers(parents_p, parents_m, problem, rng), nof_matings,
                              avoid=population)
            rename(children, "mating_" + str(igen + 1).zfill(ndigit1), ndigit2)
            reporter.log("Crossovers: %d of %d" % (len(children), nof_matings))
            mutants = []
            for _ in range(prescreen):
                mutants += make_mutant_rotamers(population[:nof_mutants], problem, rng)
            mutants = funnel(mutants, nof_mutants, avoid=population + children)
            rename(mutants, "mutant_" + str(igen + 1).zfill(ndigit1), ndigit2)
            reporter.log("Mutants:    %d of %d" % (len(mutants), nof_mutants if mmff is not None
                                                     else min(nof_mutants, len(population))))
            batch = children + mutants
            reporter.event("progress", gen=igen + 1, total=nof_generations, conformer="",
                           best_energy=float(population[0].info["e"]), gen_times=gen_times[:],
                           done=0, of=len(batch))
            collected = []
            try:
                relax_batch(batch, collected)
            finally:
                n_evaluated += len(batch)
                population = merge_into(population, collected)
            gen_times.append(time.time() - t0)
            display_mol_info(population, reporter)
            writexyzs(population, "summary.xyz")
            _write_result(result_path, population, meta, partial=True)
            reporter.event("population", gen=igen + 1, conformers=_population_payload(population))
            reporter.event("progress", gen=igen + 1, total=nof_generations,
                           conformer=population[0].info["i"],
                           best_energy=float(population[0].info["e"]), gen_times=gen_times[:],
                           done=len(batch), of=len(batch))
            names_now = [m.info["i"] for m in population][:nof_repeats]
            stagnant = stagnant + 1 if names_now == names_prev else 0
            names_prev = names_now
            if stagnant >= nof_stagnant:
                reporter.log("Early termination: the lowest %d structure(s) did not change for %d cycles."
                             % (nof_repeats, nof_stagnant))
                stop_reason = "stagnation"
                break

        # ---- polish ------------------------------------------------------------------
        reporter.check()
        reporter.event("phase", name="polish")
        targets = population[:polish_top] if polish_top else population
        reporter.log("Final tight re-optimisation of %d structure(s) (fmax = %s eV/A)"
                     % (len(targets), ", ".join("%g" % p for p in polish_prec)))
        if screening == "single" and ani_member is None:
            reporter.log("Screening used one ANI network; the final ranking uses the full %s ensemble."
                         % calculator)
        done = {m.info["i"]: m for m in ANI(targets, opt=calculator, preclist=polish_prec,
                                            problem=problem, reporter=reporter,
                                            max_steps=max(max_steps, 600), keep_unconverged=True,
                                            member=ani_member, dtype=ani_dtype)}
        polished = []
        for m in targets:
            if m.info["i"] in done:
                polished.append(done[m.info["i"]])
            elif screening == "single" or ani_member is not None:
                # its energy is a single-network one: not comparable with the polished ones
                reporter.log("%s: dropped (final ensemble re-optimisation failed)" % m.info["i"])
            else:
                polished.append(m)
        if final_ranking == "ensemble_sp" and polished:
            reporter.event("phase", name="ranking")
            reporter.log("Ranking with the full %s ensemble (8 networks, single points, one at a time)..."
                         % calculator)
            release_models()
            sp = ensemble_single_points(calculator, polished, check=reporter.check)
            if sp is not None:
                for m, e, sd in zip(polished, sp[0], sp[1]):
                    m.info["e"] = e
                    m.info["e_std"] = sd
                meta["final_ranking"] = ("%s ensemble single points at geometries relaxed with network %s"
                                         % (calculator, ani_member if ani_member is not None else "ensemble"))
                reporter.log("Ensemble spread (std of the 8 networks): %s kcal/mol"
                             % ", ".join("%.2f" % m.info["e_std"] for m in polished[:6]))
        population = merge_into([], polished)
        meta["polished"] = True

    except Stopped as stop:
        stop_reason = stop.reason
        if (screening == "single" or ani_member is not None) and population and "polished" not in meta:
            meta["note"] = ("stopped before the final ensemble re-optimisation: energies come from a "
                            "single ANI network")
        reporter.log("Run stopped (%s); returning the best structures found so far." % stop.reason)

    meta.update({
        "stop_reason": stop_reason, "n_evaluated": n_evaluated,
        "generations_run": max(0, len(gen_times) - 1),
        "wall_seconds": round(time.time() - t_start, 2), "gen_seconds": [round(t, 2) for t in gen_times],
    })
    if population:
        writexyzs(population, "summary.xyz")
    result = _write_result(result_path, population, meta, partial=(stop_reason in ("cancelled", "timeout")))
    reporter.log("Global optimization complete (%s): %d conformer(s)." % (stop_reason, len(population)))
    return result
