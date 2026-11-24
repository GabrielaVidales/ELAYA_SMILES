# Validation

* `calculate_rotational_constants.py` — A, B, C from any (multi-)XYZ. Reference checks (water, CO2, CH4) run in
  `tests/test_chem_numpy.py`.
* `run_validation.py` — runs the real pipeline (needs the ANI parameters: they are downloaded when the Docker image is built; locally run `python -c "import torchani; torchani.models.ANI1ccx(); torchani.models.ANI2x()"` once with internet) (RDKit + ASE + TorchANI) on butane, ethanol, pentane, aspirin and alanine
  and writes `validation_report.md`. **It could not be run in the environment where ELAYA v2 was written (no RDKit/torch
  there)**: run it once in the deployed image (`python validation/run_validation.py`) before quoting any number.
* For the aspirin comparison with microwave data, put the experimental A, B, C of each conformer in `aspirin/results.csv`
  next to the ELAYA values and report the percentage difference per constant (see `docs/paper_vs_code.md` §2).
* `benchmark_builders.py` — the 13-molecule benchmark of the paper (Tables 3–4): every builder (RDKit+MMFF94,
  RDKit+UFF, Open Babel, NetworkX) × 3 runs; records time, bond check and stereo check.
  `python validation/benchmark_builders.py . validation/benchmark_builders.json`
