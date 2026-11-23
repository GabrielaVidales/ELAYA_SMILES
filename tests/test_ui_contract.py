"""Contract between the web interface and the backend.

Every option the page offers must be accepted by the backend and must actually change what is
computed. These tests read index.html / app.js / glomos_progress.js so that adding a control to
the page without wiring it (or changing a preset on one side only) fails here.
"""
import json
import os
import re

import pytest

import elaya_jobs as ej

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


HTML = _read("index.html")
APPJS = _read("app.js")
PROGJS = _read("glomos_progress.js")


def _select_options(select_id, html=HTML):
    m = re.search(r'<select id="%s"[^>]*>(.*?)</select>' % re.escape(select_id), html, re.S)
    assert m, "select #%s not found" % select_id
    body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    out = []
    for om in re.finditer(r"<option([^>]*)>(.*?)</option>", body, re.S):
        vm = re.search(r'value="([^"]*)"', om.group(1))
        out.append(vm.group(1) if vm else om.group(2).strip())
    return out


def _number_input(input_id):
    m = re.search(r'<input[^>]*id="%s"[^>]*>' % re.escape(input_id), HTML)
    assert m, "input #%s not found" % input_id
    tag = m.group(0)
    get = lambda a: (re.search(r'%s="([^"]*)"' % a, tag) or [None, None])[1]
    return {k: get(k) for k in ("min", "max", "value", "step")}


# ---- GLOMOS panel ---------------------------------------------------------------------------
FIELD_TO_PARAM = {
    "glomos-initpop": "initpop", "glomos-matings": "matings", "glomos-mutants": "mutants",
    "glomos-generations": "generations", "glomos-ecut": "energy_cutoff", "glomos-keep": "cutoff_population",
}


def test_glomos_model_and_screening_options_are_accepted():
    assert set(_select_options("glomos-ani")) == set(ej.ANI_CHOICES)
    for s in _select_options("glomos-screening"):
        assert ej.clamp_params({"screening": s})["screening"] == s


def test_glomos_presets_identical_in_page_and_backend():
    assert set(_select_options("glomos-preset")) == set(ej.PRESETS) | {"custom"}
    js = re.search(r"const GLOMOS_PRESETS = \{(.*?)\n\};", APPJS, re.S).group(1)
    names = {"initpop": "initpop", "matings": "matings", "mutants": "mutants", "generations": "generations",
             "ecut": "energy_cutoff", "keep": "cutoff_population"}
    for preset, body in re.findall(r"(\w+):\s*\{([^}]*)\}", js):
        vals = {names[k]: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", body)}
        assert vals == {k: float(v) for k, v in ej.PRESETS[preset].items()}, preset


def test_glomos_number_fields_match_backend_limits():
    for field, param in FIELD_TO_PARAM.items():
        attrs = _number_input(field)
        lo, hi = ej.LIMITS[param]
        assert float(attrs["min"]) == lo and float(attrs["max"]) == hi, field
        assert float(attrs["value"]) == ej.PRESETS["fast"][param], field   # page opens on "fast"


def test_every_glomos_param_reaches_the_ga():
    """collectGlomosParams() keys -> clamp_params -> INPUT.txt keys that the GA really reads."""
    body = re.search(r"function collectGlomosParams\(\) \{(.*?)\n\}", APPJS, re.S).group(1)
    sent = set(re.findall(r"^\s*(\w+):", body, re.M))
    assert sent == {"preset", "initpop", "matings", "mutants", "generations", "energy_cutoff",
                    "cutoff_population", "ani_model", "max_minutes", "random_seed", "screening"}
    raw = {"preset": "custom", "initpop": 7, "matings": 3, "mutants": 2, "generations": 5,
           "energy_cutoff": 4.5, "cutoff_population": 9, "ani_model": "ANI1x", "max_minutes": 3,
           "random_seed": 42, "screening": "single"}
    p = ej.clamp_params(raw)
    import tempfile
    wd = tempfile.mkdtemp()
    ej.write_input_txt(wd, p, "ANI1x")
    txt = open(os.path.join(wd, "INPUT.txt")).read()
    kv = dict(line.split(None, 1) for line in txt.splitlines() if line.strip() and not line.startswith("#"))
    expect = {"nof_initpop": "7", "nof_matings": "3", "nof_mutants": "2", "nof_generations": "5",
              "cutoff_energy": "4.500", "cutoff_population": "9", "calculator": "ANI1x",
              "random_seed": "42", "screening": "single"}
    for k, v in expect.items():
        assert kv.get(k, "").strip() == v, (k, kv.get(k))
    assert float(kv["max_minutes"]) <= 3.0
    ga = _read(os.path.join("elaya_glomos", "heuristic_ga_rotamers.py"))
    read_keys = set(re.findall(r'df\.get_\w+\("(\w+)"', ga))
    assert set(kv) <= read_keys | {"rotamer_seed", "problem_file"}, set(kv) - read_keys


def test_time_limit_field_respects_server_limit():
    attrs = _number_input("glomos-minutes")
    assert float(attrs["max"]) <= ej.max_minutes_limit()
    assert float(attrs["value"]) <= ej.max_minutes_limit()
    p = ej.clamp_params({"max_minutes": 999})
    assert p["max_minutes"] == ej.max_minutes_limit()


def test_export_formats_offered_are_supported():
    """Format tabs of the structure card (every result, GLOMOS or not) -> /api/export."""
    import elaya_chem as ec
    panel = _read("structure_panel.js")
    fmts = re.findall(r"'(\w+)'", re.search(r"const FORMATS = \[(.*?)\]", panel).group(1))
    assert set(fmts) == set(ec.EXPORT_FORMATS)
    assert "gl-fmt" not in PROGJS                    # no second, diverging format list


# ---- conversion selectors -------------------------------------------------------------------
@pytest.mark.parametrize("method", _select_options("conversion-method"))
@pytest.mark.parametrize("ff", _select_options("force-field"))
def test_every_method_and_force_field_choice_is_applied(method, ff):
    pytest.importorskip("rdkit")
    if method == "openbabel":
        pytest.importorskip("openbabel")
    import app as appmod
    c = appmod.app.test_client()
    r = c.post("/api/convert", json={"smiles": "CC(=O)Oc1ccccc1C(=O)O", "method": method, "force_field": ff})
    assert r.status_code == 200, r.get_data(as_text=True)
    info = r.get_json()["info"]
    assert info["method"] == method
    if method != "networkx":                         # the page hides the force-field box for NetworkX
        want = {"none": "none", "uff": "uff", "mmff94": "mmff94"}[ff.lower()]
        assert info["force_field"] == want


def test_page_hides_force_field_for_networkx():
    body = re.search(r"function toggleForceField\(\) \{(.*?)\n\}", APPJS, re.S).group(1)
    assert "networkx" in body and "'none'" in body


# ---- behaviour behind the GLOMOS numbers ----------------------------------------------------
def test_seed_reproducibility_window_and_keep_best(tmp_path, monkeypatch, hexane_skeleton):
    """Random seed reproduces a run; Ecut and Keep best bound the final ensemble."""
    from elaya_glomos import libcalc_ani
    from elaya_glomos.heuristic_ga_rotamers import conformational
    from elaya_glomos.libreport import Reporter
    from elaya_glomos.libutils import atoms_to_xyz
    atoms, problem, toy_calc = hexane_skeleton
    monkeypatch.setitem(libcalc_ani._MODEL_CACHE, "TOY", toy_calc)

    def run(seed, ecut, keep, sub):
        d = tmp_path / sub
        d.mkdir()
        monkeypatch.chdir(d)
        (d / "seed.xyz").write_text(atoms_to_xyz(atoms, "seed"))
        (d / "problem.json").write_text(json.dumps(problem))
        (d / "INPUT.txt").write_text(
            "rotamer_seed seed.xyz\nproblem_file problem.json\nnof_initpop 6\nnof_matings 4\nnof_mutants 4\n"
            "nof_generations 2\ncalculator TOY\nrandom_seed %d\ncutoff_energy %.2f\ncutoff_population %d\n"
            % (seed, ecut, keep))
        return conformational("INPUT.txt", reporter=Reporter(emit=lambda e: None, echo=False))

    a = run(7, 40.0, 20, "a")
    b = run(7, 40.0, 20, "b")
    assert [round(c["energy_kcal"], 6) for c in a["conformers"]] == [round(c["energy_kcal"], 6) for c in b["conformers"]]
    k = run(7, 40.0, 2, "k")
    assert len(k["conformers"]) <= 2
    w = run(7, 0.5, 20, "w")
    e = [c["energy_kcal"] for c in w["conformers"]]
    assert max(e) - min(e) <= 0.5 + 1e-9


def test_every_script_of_the_page_is_served():
    """A local <script src> missing from the server's whitelist breaks the page silently."""
    import app as appmod
    c = appmod.app.test_client()
    for src in re.findall(r'<script src="/([^"]+)"', HTML):
        assert c.get("/" + src).status_code == 200, src
    assert c.get("/styles.css").status_code == 200


def test_info_icon_of_post_optimisation_points_to_conformer_reading():
    m = re.search(r'data-tooltip-id="tooltip-postopt"\s*data-url="([^"]+)"', HTML)
    assert m and "github.com" not in m.group(1) and "onformation" in m.group(1)
