"""STEP parsing, CLI and REST API on generated assemblies (needs pythonocc-core)."""
import importlib
import json
import os

import pytest

pytest.importorskip("OCC")

from step_explode import samples  # noqa: E402
from step_explode.parser import parse_step  # noqa: E402


@pytest.fixture(scope="module")
def step_files(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    return {os.path.splitext(os.path.basename(p))[0]: p for p in samples.write_all(str(d))}


def test_parse_bracket(step_files):
    parsed = parse_step(step_files["bracket"])
    assert parsed["nb_components"] == 4
    base = parsed["components"][0]
    assert base["dimensions"] == {"x": 100.0, "y": 60.0, "z": 10.0}
    assert base["center"] == {"x": 50.0, "y": 30.0, "z": 5.0}
    assert base["volume"] == pytest.approx(60000.0, rel=1e-6)
    assert base["nb_faces"] == 6


def test_parse_with_mesh(step_files):
    parsed = parse_step(step_files["flange"], with_mesh=True)
    assert parsed["nb_components"] == 3
    for c in parsed["components"]:
        m = c["mesh"]
        assert m["vertices"] and len(m["indices"]) % 3 == 0
        assert max(m["indices"]) < len(m["vertices"])


def test_unreadable_file(tmp_path):
    bad = tmp_path / "bad.step"
    bad.write_text("not a step file")
    with pytest.raises(ValueError):
        parse_step(str(bad))


def test_cli(step_files, tmp_path):
    from step_explode.cli import main
    assert main([step_files["bracket"], "--out-dir", str(tmp_path)]) == 0
    res = json.loads((tmp_path / "bracket_exploded.json").read_text())
    assert res["nb_components"] == 4
    assert (tmp_path / "bracket_exploded.gltf").exists()


def test_api_flow(step_files, tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    monkeypatch.setenv("STEP_EXPLODE_WORKDIR", str(tmp_path))
    import step_explode.api as api
    api = importlib.reload(api)
    client = TestClient(api.app)

    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200

    with open(step_files["flange"], "rb") as f:
        r = client.post("/api/upload", files={"file": ("flange.step", f, "application/octet-stream")})
    assert r.status_code == 200, r.text
    up = r.json()
    assert up["nb_components"] == 3 and "mesh" not in up["components"][0]
    job = up["job_id"]

    assert client.get(f"/api/jobs/{job}").status_code == 404           # not exploded yet
    r = client.post(f"/api/jobs/{job}/explode", params={"factor": 1.0})
    assert r.status_code == 200
    assert all("explode_vector" in c for c in r.json()["components"])
    g = client.get(f"/api/jobs/{job}/gltf/exploded").json()
    assert len(g["nodes"]) == 3

    assert client.post("/api/upload", files={"file": ("x.txt", b"abc")}).status_code == 400
    assert client.get("/api/jobs/../../etc/gltf/exploded").status_code in (400, 404)
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404
    assert client.get(f"/api/jobs/{job}/gltf/other").status_code == 400
