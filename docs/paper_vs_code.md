# Paper draft vs. code — what is claimed, what the code does, what to fix

Reviewed: `Paper - Elaya - borrador.docx` against ELAYA v2.0.0. "✔" = the code now does it,
"⚠" = needs your action (data, citation or wording), "✖" = was not true in v1.

## 1. Claims about the software

| Draft says | v1 reality | v2 status |
|---|---|---|
| §2.4 "automated conformational search … retains lower-energy structures, reduces redundant conformations" | GLOMOS did not run on the server (see CHANGELOG, root causes) | ✔ torsion-space GA, ANI relaxation, energy window, USR + energy de-duplication, stagnation stop |
| §2.4 "user can configure the search and follow progress" | progress parsed from stdout with regexes; element-id collision (`glomos-energy`) between the input and the live panel | ✔ structured events, presets, cancel button, ETA, per-structure log |
| §2.4 "ANI … optional advanced workflow; users must consider elemental coverage" | no check: Cl/F/S with ANI-1ccx crashed or gave garbage; charged/open-shell molecules accepted | ✔ `ani_domain.py`: auto model (1ccx → 2x), explicit rejection of unsupported elements and open-shell species, warning for charged ones |
| §2.3 "fixed random seed for reproducibility" | seed 665 hard-coded, GLOMOS seed not controllable | ✔ ETKDG seed fixed (665) and reported; GLOMOS `random_seed` recorded in every result (`0` = new seed each run) |
| §2.3 UFF or MMFF94 | UFF silently used when MMFF params missing, not reported | ✔ response says which force field was actually used |
| §2.3 graph layout "not energy-optimised, interface distinguishes it" | only a note in the UI | ✔ response flagged `approximate: true`, comment line of the XYZ says "APPROXIMATE graph layout" |
| §2.3 Open Babel route | `atom.GetType()[0]` wrote **C for Cl, B for Br**, etc. | ✔ element symbols from atomic numbers |
| §2.5 export "for subsequent calculations" | XYZ only (MOL/SDF/MOL2/PDB/CML were written to server disk, never offered) | ✔ `/api/export`: xyz, mol, sdf, pdb (RDKit); mol2, cml (OpenBabel, optional) |
| §2.6 "reproducible, containerised" | unpinned deps, `pip install glomos`/`aegon` from PyPI overwritten by the local folder, dscribe/numba/Auto3D installed but unused | ✔ pinned torch 2.2.2 (CPU) + torchani 2.2.4; no unused heavy deps; `/api/health` prints exact versions |

## 2. Things the draft needs from you (not fixable by code)

1. **§2.6 version table** (`RDKit version X` …): run the deployed app and copy `GET /api/health`
   (field `versions`) — it lists Python, RDKit, Open Babel, NetworkX, TorchANI, torch, ASE, NumPy, SciPy and Flask.
2. **§3.3 aspirin validation (“deviations below 2 %”)**: the `validation/aspirin/` folder shown in the draft did not
   exist in the repository. Do not publish this sentence until you have run it:
   * `python validation/run_validation.py --only aspirin` produces the ELAYA conformers and their A, B, C;
   * compare with the **experimental** values of the microwave study you cite (put them in `results.csv` next to the
     computed ones; quote the reference, the isotopologue/vibrational state and whether you compare B0 or Be);
   * rigid-rotor constants of an *equilibrium* geometry are not B0: expect 1–3 % from vibrational averaging alone, so
     "< 2 %" must be shown with numbers, not asserted. Also state which ANI model/level generated the geometry.
   * `validation/calculate_rotational_constants.py` is the script the draft promises (pure numpy; checked against
     water, CO2 and CH4 in `tests/test_chem_numpy.py`).
3. **§3.2 representative examples**: three of the five SMILES in the web examples were wrong in v1 and are fixed:
   * "Oxytocin" was a linear 7-residue peptide, and the molecule **auto-loaded on first visit** was a tripeptide
     (Gly-Leu-Leu-NH2), not oxytocin. v2 uses the real cyclic nonapeptide (C43H66N12O12S2, 1007.19 Da, S–S bridge).
   * "Glucose" `OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@H]1O` was **galactose** (C4 epimer). v2 uses β-D-glucopyranose
     `OC[C@H]1O[C@@H](O)[C@H](O)[C@@H](O)[C@@H]1O`.
   * Aspirin was added (it is the validation molecule).
4. **§3.4 comparison table**: "Automated conformational exploration — RDKit ✓/workflow, Open Babel ✓/workflow" is
   fine, but CREST/other "3D generation —" should be checked; the "ELAYA ✓ for every row" reads as promotional. Suggest
   adding a row *"quantitative conformer ranking: ANI only, no ZPE/thermal"* where ELAYA is honestly limited.
5. **Editorial leftovers in the draft** (will be noticed by reviewers):
   * the Spanish editor note after §2.3 ("Ese último párrafo es especialmente importante …");
   * citation artefacts pasted as plain words: `OUP Academic`, `Publicaciones ACS`, `Springer`, `ScienceDirect`,
     `Nature`, `PubMed`, `DOI` — they must become real references;
   * the stray `[]` figure placeholders and `[URL de ELAYA]`, `[GitHub]`, `Archived version: []` (deposit a release on Zenodo);
   * author list: the draft says *Luis Ortiz*, the code header says *Luis Gonzalez*. Fix whichever is wrong, and keep
     "Filiberto Ortiz Chi" identical everywhere.

## 3. Missing references (verify the details before citing)

The methods in the code are not cited anywhere in the draft:

* **GLOMOS** – the original genetic algorithm / code you build on (cite the group's paper for it; the draft never
  names it, only "automated procedure").
* **ETKDG** – Riniker & Landrum, J. Chem. Inf. Model. 2015, 55, 2562; **ETKDGv3** – Wang, Witek, Landrum, Riniker,
  J. Chem. Inf. Model. 2020, 60, 2044.
* **ANI-1ccx** – Smith et al., Nat. Commun. 2019, 10, 2903; **ANI-2x** – Devereux et al., J. Chem. Theory Comput.
  2020, 16, 4192; **TorchANI** – Gao et al., J. Chem. Inf. Model. 2020, 60, 3408.
* **ASE** – Larsen et al., J. Phys.: Condens. Matter 2017, 29, 273002.
* **USR** (shape descriptor used to remove duplicates) – Ballester & Richards, 2007 (J. Comput. Chem. / Proc. R. Soc. A).
* **MMFF94** – Halgren, J. Comput. Chem. 1996, 17, 490; **UFF** – Rappé et al., J. Am. Chem. Soc. 1992, 114, 10024.
* NetworkX (Hagberg et al. 2008), Flask, 3Dmol.js (Rego & Koes 2015) as already planned.

## 4. What the paper can now truthfully say about GLOMOS (suggested wording)

> Conformational search is performed with a genetic algorithm in torsion space. Rotatable bonds are defined from the
> molecular graph (acyclic single bonds that are not part of a symmetric rotor), each with a chemistry-dependent set
> of preferred angles; new candidates are produced by crossover of parent torsion vectors and by mutation, and every
> candidate is rejected if it contains steric clashes, breaks the bond graph, or changes a stereocentre or a double-bond
> configuration. Structures are relaxed with ANI-1ccx (H, C, N, O) or ANI-2x (additionally F, S, Cl) in double
> precision; duplicates are removed with the ultrafast shape recognition (USR) descriptor together with an energy
> criterion, and the run ends after a fixed number of generations or when the lowest structures stop changing.
> Relative energies are ANI electronic energies without zero-point or thermal corrections; the reported populations
> (298 K, Boltzmann) are therefore indicative. The search is stochastic: results are reproducible only for a fixed seed,
> and completeness for highly flexible molecules is not guaranteed.

## 5. Limitations the paper should state (they are real)

* No guarantee of finding all conformers; use more generations/population for >6 rotors.
* Ring conformers (e.g. chair/boat, macrocycles) come from the ETKDG seed pool only — the GA rotates acyclic bonds.
* Energies are ANI single-point-on-relaxed-geometry electronic energies; no solvent, no ZPE, no entropy.
* Neutral, closed-shell molecules; H, C, N, O (+F, S, Cl with ANI-2x); no ionic species or metals.
* Hosted instance: one GLOMOS job at a time, 20 min limit, molecules up to 120 heavy atoms.
* Enantiomeric/mirror-image conformers are merged by USR (the descriptor is mirror-invariant); stereochemistry of
  the input is enforced, so this only removes conformer pairs that are mirror images of each other.
