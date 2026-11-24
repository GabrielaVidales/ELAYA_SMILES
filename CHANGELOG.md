# Changelog

## 2.4.0 — clearer for first-time users

### Explorer
* **Step bar** under the title: 1 Enter a molecule → 2 Choose settings → 3 Convert → 4 Explore & download. It follows
  what you do: the next step glows (pulsing ring), finished steps get ✓, step 3 spins while working; click a step to
  jump to it. On phones it becomes four dots with only the current step spelled out.
* **Spotlight on the next action**: the input box is highlighted until a molecule is entered (settings and viewer
  dimmed), a "Start here" bubble points at it, and "Next: Convert" + a pulsing Convert button once the SMILES is valid.
* **Empty results card** instead of a "Download XYZ file" button with nothing to download.
* **Guided tour** (8 steps, spotlight + card, keyboard ← → Esc), offered once on the first visit and always
  available from the step bar.
* Viewer controls (Fit, full screen, speed) sit on a dark pill so they stay visible over the white 2D drawing.

### Menu, zoom and layout
* Animated indicator under the active menu item; clearer active state.
* About hero: more space below the menu, no fixed height (the title was hidden behind the menu and buttons were cut
  when zooming), aligned with the course on wide screens.
* Input row rebuilt as a grid (no negative margins): the examples no longer overlap "SMILES File" at 125–175 % zoom.

### About / Contact
* Course menu is a light "Tutorial" card: "You are on lesson N of 7", progress bar, highlighted current lesson.
* Interactive parts (SMILES playground, butane explorer, GLOMOS stepper, quiz) are light cards with a "Try it" badge;
  "next lesson" and course buttons are light.
* Contact: the action cards and the report form are light cards.
* Floating **"More below" ↓** button (bouncing) on About and Contact; jumps to the next block and turns into
  "Back to top" at the end.

## 2.3.1

* Authors: Gabriela Vidales-Ayala, Filiberto Ortiz-Chi, Gabriel Merino, Luis Ortiz-Gonzalez (page, footer, BibTeX,
  README); © 2026.
* Course progress: a lesson is ticked when you scroll to its end or stay on it for a few seconds; finishing the quiz
  ticks it; lessons skipped over by a jump are not counted. Reset button, "Continue the course" button in the
  header and a message when all 8 lessons are done. (Before, the tick needed the "next" button fully visible for
  1.5 s, which often never happened.)
* Course search (press "/"): lessons, tables, glossary, resources, GLOMOS steps and quiz; Spanish words work
  (conformero, enlace, anillo…); results highlighted and the target flashes; recent searches kept for the session.
* Lesson 0: the video and the PNG flowchart are replaced by an animated, clickable flowchart drawn in code (each
  step explains itself and opens its lesson).
* Same background gradient as the explorer on About and Contact; Contact gets an orbit animation like the logo ring.
* Links checked one by one: JoVE (paywalled) replaced by Khan Academy's butane video; ASE now ase-lib.org.
  Info icons: RDKit documentation (3D construction), Sherrill's molecular-mechanics lecture, Georgia Tech
  (force fields), LibreTexts (conformers); each tooltip says where the icon leads.
* Back-to-top button on long pages.

## 2.3.0

### About → interactive mini-course (for people with no chemistry background)
* Eight short lessons with a sticky table of contents (scroll-spy, ✓ for lessons read, remembered in the browser),
  reading-progress bar and "next lesson" buttons; on phones the contents become a scrollable chip bar.
* **SMILES playground**: type or pick an example; every character is explained on hover/tap (atoms, bonds, branches,
  ring closures colour-paired, stereo), unclosed rings/branches are flagged, and the server draws the molecule and
  gives formula, mass, rings, rotatable bonds and stereocentres. "Build it in 3D" sends it to the explorer.
* **Butane conformer explorer**: Newman projection with a dihedral slider (and auto-rotate), energy curve, and
  Boltzmann populations with a temperature slider.
* **GLOMOS step by step**: 7-step stepper with ASCII diagrams, each mapped to the parameters of the GLOMOS panel.
* Lessons on 3D methods and quality checks, force fields vs ANI, reading results (ΔE, populations, rotational
  constants, file formats), a 5-question quiz, curated tutorials/videos/papers and a glossary.
* Technologies table updated (Waitress, OpenBabel, NetworkX, TorchANI, ASE, 3Dmol.js); outdated entries removed.

### Contact
* Guided problem report: fills in version, browser, screen and the current settings (incl. all GLOMOS parameters),
  prefills the SMILES from the explorer, previews the report, opens a GitHub issue or copies it.
* "Suggest a feature" opens an issue labelled enhancement; compact 3-card layout.
* Citation card with BibTeX (version filled in from the server) and copy button.
* FAQ: cost, data retention (GLOMOS job files deleted ~2 h after the job), supported molecules, run time, ANI model
  choice, reproducibility, running locally with Docker.

### Explorer
* The structure card (formats, downloads, QA chips) stays hidden while GLOMOS runs and appears with the conformers.
* File upload: drag-and-drop zone, .smi/.txt/.csv/.tsv with names, a downloadable example file, and a checked
  summary table (`POST /api/validate`) with "Remove invalid".
* All links that open a new tab use `rel="noopener"`.

## 2.2.1

* Fullscreen: leaving it restored an inline `position: relative`, so the viewer lost its sticky layout and the
  controls (Fit, fullscreen) landed on the footer. The stylesheet position is restored and the view re-fitted.
* Format tabs: switching back to XYZ kept the previous format's text (the card assumed app.js had rewritten it).
  The card now always writes its own content and discards stale exports; the record name inside MOL/SDF/PDB is
  readable ("dopamine | conformer 1 (mating_004_0002)"); file names stay safe.
* GLOMOS parameters in two compact rows (label above its field, 6 per row; 4 on tablets, 2 on phones).
* "Running" badge replaced by an ASCII lab driven by the job's real events: one worker spins bonds, candidates ride
  a conveyor belt, the other relaxes and stamps them; a new generation makes them cheer; click to say hi.
  Static frame with prefers-reduced-motion. Hidden when the job ends.
* Space: on desktop the results column is as tall as the 3D view and scrolls inside (no long page with an empty area
  under the viewer); the log collapses when the job ends; compact one-row stats; wider results column (3:2).

## 2.2.0

### Viewer and results
* **The whole molecule is always in view.** The 3D view has a bounded height and stays in sight (sticky)
  while the results column scrolls; it is re-fitted whenever its box changes size (ResizeObserver).
  Before, it stretched to the height of the GLOMOS card (1500 px+) and the molecule was cropped. New "Fit" button.
* **Conformer bar over the 3D view** (◀ Conformer 2/6 ▶ · name · ΔE · population), synchronised with the
  highlighted row of the GLOMOS table; ← → keys browse conformers (or the molecules of a file).
* **Structure card with format tabs** (XYZ · MOL · SDF · PDB · MOL2 · CML) for every result: single SMILES, file
  batch and GLOMOS. Title of what is on screen (molecule i/n with its name from the .smi file, or conformer i/n),
  Copy button, "Download <FORMAT>" for the structure on screen and "Download all N molecules/conformers" as .zip.
  The separate format selector of the GLOMOS card was removed (one list of formats).

### Interface ↔ backend audit (tests/test_ui_contract.py)
* Every control is checked against the backend: ANI model and screening choices, presets (identical numbers in
  page and server), min/max of every GLOMOS field = server limits, every parameter reaches the GA's INPUT.txt,
  every method x force-field choice is applied as selected, export formats, scripts served, and (with a toy
  potential) that a random seed reproduces a run and that Ecut and Keep best bound the result.
* Found and fixed: the time limit accepted 60 min while the server capped it at 20 without saying so. The field
  now takes its maximum from /api/health and explains the limit.

### Convenience
* SMILES field: ✕ to clear; live check while typing (formula, mass, atoms, rotatable bonds, or the parser's error).
* Options are remembered in the browser (method, force field, GLOMOS settings, format); post-optimisation is not
  restored, so GLOMOS never starts by itself.
* GLOMOS estimate: number of ANI relaxations of the chosen settings and, after one run on the server, an
  approximate duration scaled by the number of atoms.
* GLOMOS parameters in two columns; info icon of post-optimisation links to a text on conformers (LibreTexts)
  instead of the repository; no "Connection established" toast on every visit; GLOMOS option disabled when the
  server cannot run it.

## 2.1.1

* Example molecules as visible chips (mint outline, highlighted when selected) on one line with the SMILX link
  ("Only a formula? SMILX-isogenerator"); Oxytocin removed from the chips (it is already the first-visit demo).
  The previous colour (#42e27273, 45 % opacity) made them almost invisible.
* Enter in the SMILES field runs Convert; examples are real buttons (keyboard accessible).

## 2.1.0

### GLOMOS speed (same results)
* **Batched relaxation** (`elaya_glomos/libbatch.py`): every candidate of a generation is relaxed together, with one batched
  ANI forward/backward pass per step instead of one call per structure. The optimiser is an exact re-implementation of
  `ase.optimize.LBFGS` (memory 100, alpha 70, maxstep 0.15, staged fmax), run independently per structure: steps, positions
  and energies are identical to the sequential ASE run (tests compare them bit for bit with MMFF; the batched torch
  evaluator matches torchani's ASE calculator to 1e-15 eV). Measured on an ANI-1ccx-sized ensemble with the step counts of a
  real dopamine run: 2.7x less relaxation time (about 20 min -> 7 min on the 0.1-CPU Render instance).
* **Optional single-network screening** (`screening: "single"`, "Screening" selector in the GLOMOS panel): candidates are
  relaxed with the first network of the ANI ensemble and the final polish/ranking uses the full ensemble (8.4x with batching
  on the same run). Default stays `ensemble`; the choice is recorded in the result metadata.
* `ELAYA_TORCH_THREADS=auto` (new default): torch threads = whole CPUs of the container (cgroup quota), 1..4. Two threads on
  a 0.1-CPU instance only added contention. `/api/health` reports `cpus` and `torch_threads`.
* A cancellation/time limit in the middle of a batch keeps the structures already relaxed (`sink`).

### 3D generation and viewer
* **Double/aromatic bonds are drawn**: the viewer now prefers the MOL block (bond orders) over XYZ. GLOMOS conformers carry
  a MOL block too (`conformers[i].mol` in `/api/glomos/result`).
* **NetworkX method rewritten**: Kamada-Kawai stress layout (still NetworkX) with target distances for every atom pair from
  the molecular graph (RDKit topological distance bounds; through-bond path length for distant pairs), least-squares scaling
  to angstrom, then inversion of wrongly oriented stereocentres / double bonds and re-layout. Bond-length RMSE vs MMFF went
  from 0.20-0.44 A to 0.04-0.15 A; bonds and stereo now match the SMILES for typical drug-size molecules (fused polycycles and
  macrocycles remain approximate and are flagged). It now returns a MOL block and a stereo report.
* OpenBabel results now include the stereo check (`stereo_qa`).
* Under the viewer: chips with the stereo check, bond check, "approximate layout" warning and rotational constants.

### Responsive layout and details
* Mobile: Convert button right after the selectors (it was below the viewer whenever the GLOMOS panel was hidden); SMILES
  field full width (the hidden "show full SMILES" button took half the row); "View code" shows the icon only; long SMILES
  no longer widen the page; GLOMOS parameters with the label above the field, two per row.
* Desktop: GLOMOS parameter fields no longer overlap the next label.
* Notifications stack at the bottom-right (click to dismiss, at most 3) instead of covering the title; long SMILES are
  shortened in messages and in the download button.
* `prefers-reduced-motion` respected; visible keyboard focus on the main controls.

## 2.0.3

* **GA duplicate handling kept the wrong copy.** When an offspring was a duplicate (same USR shape,
  |dE| <= tol_energy) of a structure already in the population, the offspring was always dropped, even
  when it was lower in energy. Seen on the production server with dopamine: `mutant_002_0002`
  (-323869.198 kcal/mol) was discarded in favour of `random_000_0001` (-323869.119). Duplicates are now
  resolved over the union of population and offspring (`merge_population`), so the lower-energy
  member always survives. Regression test added.
* `/api/health?deep=1` runs the ANI self-test in a separate process (with a timeout). Before, it imported
  torch into the web server, which then kept ~250 MB for the life of the process (half of a 512 MB instance).
* Frontend: no `viewer.render()` while the 3D viewer is hidden (removes the last
  `GL_INVALID_FRAMEBUFFER_OPERATION` lines).

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
