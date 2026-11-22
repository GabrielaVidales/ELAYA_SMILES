# Changelog

## 2.0.2

* **The local GLOMOS package is now `elaya_glomos/` (was `glomos/`).** PyPI has an unrelated `glomos` package
  (0.3.x, installed by ELAYA v1 with `pip install glomos`) that has no `libreport.py`. When it is present in the
  deployment it can be imported instead of the local folder, giving
  `Could not start GLOMOS: No module named 'glomos.libreport'` and `ani_weights: null` in `/api/health`.
  A unique name makes that impossible.
* Dockerfile: removes a stale PyPI `glomos`/`aegon` and checks at build time that `elaya_glomos` imports
  (the build fails instead of the first GLOMOS request).
* `/api/health`: `glomos_package` (path or import error); `ani_weights` shows the error instead of `null`.

## 2.0.1

### Why GLOMOS still failed in 2.0.0 (found by running the real pipeline: RDKit + ASE + torch + torchani)
v2.0.0 was written and tested only with stand-ins for RDKit/ASE (see `tests/conftest.py`), so these were never exercised:

1. **`Bond.IsInRingOfSize` does not exist in RDKit** (the method is `IsInRingSize`). It is only evaluated for double
   bonds, so butane or glucose worked, but *every molecule with C=O or C=C* (peptides, aspirin, dopamine, the
   examples...) made `/api/analyze` and `/api/glomos/start` fail with HTTP 500.
2. **`torchani 2.2.4` imports `pkg_resources`**, removed in setuptools >= 81. On a fresh install every ANI
   optimisation failed; because errors were caught per structure, the only visible message was
   "All starting structures were discarded after ANI relaxation". `setuptools<81` is now pinned.
3. **torchani 2.2.4 ships empty parameter files** and downloads the ANI weights from GitHub the first time a model
   is built, i.e. inside the first GLOMOS job and again after every container restart (time, memory, network).
   The Dockerfile now downloads them at build time and the build fails if it cannot.

### Fixed / improved
* The ANI model is built once, before generation 0; a load failure stops the job with one actionable message
  (`ModelLoadError`) instead of one "optimisation failed" per structure.
* torchani deprecation warnings no longer appear in the job log.
* Worker killed by a signal (e.g. out of memory) is reported as such; an error reported by the worker is no longer
  duplicated in the event stream.
* `/api/glomos/poll` never returns an opaque 500: errors come back as JSON with the cause (and a traceback in the
  server log). The web client shows that message, recognises 502/503/504 as "server restarting" and, if the job is
  then gone, says the server most likely ran out of memory.
* `/api/health` reports `ani_weights` (which ANI parameter sets are installed) and the container memory limit
  (`memory_limit_mb`, with a warning below 1 GB).
* `/api/convert` no longer fails for elements without a tabulated mass (e.g. Na): the structure is returned with
  `rotational_constants: null`.
* Frontend: JSZip was loaded twice and the second tag had an invalid SRI hash (the browser blocked it); the 3Dmol
  rotation loop no longer renders into a hidden 0x0 canvas (`GL_INVALID_FRAMEBUFFER_OPERATION` flood).
* `validation/run_validation.py` exits with a clear message when the ANI parameters are missing.

### Tests (34 -> 56)
* `ToyCalculator` is a real ASE calculator when ASE is installed (the GA tests failed with the real ASE).
* `tests/test_chem_rdkit.py` (real RDKit: stereo summary, report, seed pool) and `tests/test_pipeline_real.py`
  (full GA with real RDKit + ASE on butane, glucose and Gly-Leu-Leu-NH2, using MMFF94 as a stand-in potential
  so no download is needed; checks stereo and bond graph of every conformer).
* Regression tests for model-load failure, OOM-killed worker, non-duplicated errors and poll errors.

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
