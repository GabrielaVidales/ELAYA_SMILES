# Changelog

## 2.0.0

### Why GLOMOS did not run in v1 (root causes found by reading the code)
1. `glomos/libcalc_ani.py` wrote a debugging `[diag]` print and ran BFGS in **float32** with `fmax=1e-3 eV/Å`: forces have
   ~1e-4 eV/Å of numerical noise at ~10³ eV total energy, so optimisations never converged within the step limit.
2. A **new `multiprocessing` pool per generation** (spawn/fork after torch had started its OpenMP pool) could deadlock or
   crash; `nof_processes` had to be forced to 1.
3. The child process was launched through a generated runner with **`sys.path.insert(0, '/app')` hard-coded**, so any
   deployment not in `/app` imported nothing.
4. `Dockerfile` ran `pip install glomos` / `aegon` from PyPI; with the local `glomos/` folder shadowing the name the
   result depended on the working directory, and failures were swallowed (`|| echo WARNING`).
5. Progress was reconstructed with **regexes over stdout**; any print change silently froze the UI. The live panel and the
   parameter form shared the DOM id `glomos-energy`.
6. Rotors were taken from *geometry-perceived* bonds, including double bonds and **ring bonds** (rotating a ring bond
   breaks the ring), with no clash, stereo or connectivity validation.
7. `nof_stagnant 2 / nof_repeats 1`, `cutoff_population 5`: the search stopped after two non-improving generations and
   kept 5 structures, regardless of the molecule.
8. Jobs were written to `/tmp` as JSON files and read by a second process; a restart returned 404 and the UI retried forever.

### New
* Self-contained GLOMOS (`glomos/`): chemistry-aware rotors (RDKit-classified: sp3, X–H, planar amide/ester/acid, generic),
  symmetric tops excluded, ring bonds excluded, Bondi-radius clash filter, chirality and E/Z preservation, connectivity
  check after ANI relaxation, USR + energy de-duplication against the whole population, roulette selection, crossover in
  torsion space, mutants, final tight re-optimisation, partial results after cancel/timeout, reproducible seeds.
* Job manager (`elaya_jobs.py`) with subprocess worker, structured events, cancel, wall-clock limit, queue, watchdog kill.
* ANI domain handling (`glomos/ani_domain.py`): automatic ANI-1ccx → ANI-2x, rejection of unsupported/open-shell molecules.
* Results: relative energies, Boltzmann populations (298 K), rotational constants A/B/C, multi-XYZ / JSON download,
  export to xyz/mol/sdf/pdb (RDKit) and mol2/cml (OpenBabel).
* `/api/analyze` (descriptors, stereo summary, warnings), `/api/health` (+ `?deep=1` real ANI self-test), `/api/version`.
* Tests (`tests/`, 34), validation scripts (`validation/`), `docs/paper_vs_code.md`.

### Fixed
* OpenBabel XYZ element symbols (Cl → "C", Br → "B").
* Ring bonds were accepted as rotors (bug in the ring test, found by the new unit tests).
* Example SMILES: "Glucose" was galactose; "Oxytocin" and the auto-loaded molecule were short linear peptides.
* NetworkX layout is flagged as approximate; force field really used is reported.
* Static file route served the whole project directory (source code, requirements) — now an allow-list.
* Connectivity matrix used a fixed 2.0 Å cut-off; now covalent radii × 1.2.

### Removed
* Per-request files written to the server (`output_*` directories), the console banner, py3Dmol, dscribe/numba, Auto3D,
  flask-cors (15 lines replace it), the SSE leftovers.

### Behaviour changes to know about
* GLOMOS is no longer reachable through `/api/convert`; use `/api/glomos/start` (the web UI does this).
* Default force field in the API is MMFF94 when none is given.
* `render.yaml` uses the *standard* (2 GB) plan: ANI + torch do not fit in 512 MB.
