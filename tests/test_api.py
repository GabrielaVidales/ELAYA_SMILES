import os
import sys
import time

import pytest

import app as appmod
import elaya_chem as ec
import elaya_jobs as ej

FAKE = os.path.join(os.path.dirname(__file__), "fake_worker.py")


@pytest.fixture
def client(tmp_path, monkeypatch):
    os.environ["FAKE_MODE"] = "ok"
    mgr = ej.JobManager(base_dir=str(tmp_path), worker_cmd=lambda wd, m: [sys.executable, "-u", FAKE, wd])
    monkeypatch.setattr(appmod, "_jobs", mgr)
    # chemistry stand-ins (RDKit is not installed in the CI image)
    problem = {"bonds": [[0, 1]], "rotors": [], "chiral": [], "ez": [], "charge": 0}

    class FakeMol:
        def GetAtoms(self):
            class A:
                def __init__(s, sym): s.sym = sym
                def GetSymbol(s): return s.sym
            return [A("C"), A("H"), A("H"), A("H"), A("H")]
    monkeypatch.setattr(ec, "glomos_seed_pool",
                        lambda smi, n, seed: (FakeMol(), "5\nseed\nC 0 0 0\nH 1 0 0\nH 0 1 0\nH 0 0 1\nH -1 0 0\n",
                                              problem, {"n_seeds": 1}))
    monkeypatch.setattr(ec, "mol_report", lambda smi: {"formula": "CH4"})
    appmod.app.config["TESTING"] = True
    yield appmod.app.test_client()
    mgr.shutdown()


def test_health_reports_missing_libs(client):
    r = client.get("/api/health").get_json()
    assert r["status"] in ("ok", "degraded") and "libraries" in r and "glomos_ready" in r
    if not r["glomos_ready"]:
        assert r["missing_for_glomos"]


def test_static_allowlist(client):
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    for path in ("/app.py", "/elaya_jobs.py", "/requirements.txt", "/glomos/libutils.py", "/.git/config",
                 "/../app.py"):
        assert client.get(path).status_code == 404, path
    assert client.get("/api/nope").status_code == 404


def test_cors_and_preflight(client):
    r = client.options("/api/convert")
    assert r.status_code in (200, 204) and r.headers["Access-Control-Allow-Origin"]
    assert client.get("/api").headers["Access-Control-Allow-Origin"]


def test_input_validation(client):
    assert client.post("/api/analyze", json={}).status_code == 400
    assert client.post("/api/convert", json={"smiles": ""}).status_code == 400
    assert client.post("/api/convert", json={"smiles": "CC", "post_opt": "glomos"}).status_code == 400
    assert client.post("/api/export", json={"smiles": "CC", "format": "exe"}).status_code == 400
    assert client.post("/api/glomos/start", json={"smiles": "CC", "glomos_params": {"initpop": "x"}}).status_code == 400
    assert client.post("/api/glomos/start", data="not json", content_type="text/plain").status_code == 400


def test_glomos_roundtrip(client):
    r = client.post("/api/glomos/start", json={"smiles": "C", "glomos_params": {"preset": "fast"}})
    assert r.status_code == 200, r.get_data(as_text=True)
    js = r.get_json()
    assert js["model"] == "ANI1ccx" and js["job_id"]
    jid = js["job_id"]
    for _ in range(100):
        p = client.get("/api/glomos/poll/%s?cursor=0" % jid).get_json()
        if p["done"]:
            break
        time.sleep(0.05)
    assert p["status"] == "done"
    res = client.get("/api/glomos/result/%s" % jid).get_json()
    assert res["conformers"][0]["rotational_constants"]["B_MHz"] > 0       # post-processed by the API
    xyz = client.get("/api/glomos/result/%s?format=xyz" % jid)
    assert xyz.mimetype == "chemical/x-xyz" and xyz.get_data(as_text=True).startswith("2")
    assert client.post("/api/glomos/cancel/%s" % jid).status_code == 200


def test_unknown_job_is_404_not_500(client):
    assert client.get("/api/glomos/poll/doesnotexist").status_code == 404
    assert client.get("/api/glomos/result/doesnotexist").status_code == 404
    assert client.post("/api/glomos/cancel/doesnotexist").status_code == 404


def test_ani_domain_rejection(client, monkeypatch):
    class Br:
        def GetAtoms(self):
            class A:
                def GetSymbol(s): return "Br"
            return [A(), A()]
    monkeypatch.setattr(ec, "glomos_seed_pool", lambda *a: (Br(), "", {"charge": 0, "rotors": []}, {}))
    r = client.post("/api/glomos/start", json={"smiles": "BrBr"})
    assert r.status_code == 422 and r.get_json()["kind"] == "ani_domain"


def test_poll_failure_returns_json_error(client, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("kaput")
    monkeypatch.setattr(appmod.jobs(), "poll", broken)
    r = client.get("/api/glomos/poll/whatever")
    assert r.status_code == 500 and "kaput" in r.get_json()["error"]


def test_health_reports_ani_weights_and_memory(client):
    r = client.get("/api/health").get_json()
    assert "memory_limit_mb" in r
    if r["libraries"]["torchani"]:
        assert set(r["ani_weights"]) == {"ANI1x", "ANI1ccx", "ANI2x"}
