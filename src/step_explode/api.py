"""FastAPI service: upload a STEP file, compute a radial exploded view, download glTF.

Run:  uvicorn step_explode.api:app --port 8000   (then open http://127.0.0.1:8000)

Endpoints
---------
POST /api/upload                      multipart file (.step / .stp) -> job id + components
POST /api/jobs/{job}/explode?factor=  radial explosion -> components with vectors
GET  /api/jobs/{job}                  last result (JSON, without meshes)
GET  /api/jobs/{job}/gltf/{kind}      kind = assembled | exploded (glTF 2.0, embedded)
GET  /                                three.js viewer

Configuration (environment): ``STEP_EXPLODE_WORKDIR`` (default ``./work``),
``STEP_EXPLODE_MAX_MB`` (default 50), ``STEP_EXPLODE_CORS`` (comma-separated origins,
default none).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from . import __version__
from .explode import compute_exploded_positions
from .gltf import assembled_and_exploded, dumps

WORKDIR = Path(os.environ.get("STEP_EXPLODE_WORKDIR", "work"))
MAX_BYTES = int(float(os.environ.get("STEP_EXPLODE_MAX_MB", "50")) * 1024 * 1024)
STATIC = Path(__file__).parent / "static"
JOB_RE = re.compile(r"^[0-9a-f]{32}$")

app = FastAPI(title="STEP Exploded View API", version=__version__,
              description="Upload a STEP assembly, get a radial exploded view as JSON and glTF.")
_origins = [o for o in os.environ.get("STEP_EXPLODE_CORS", "").split(",") if o]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


def _job_dir(job: str) -> Path:
    if not JOB_RE.match(job):
        raise HTTPException(400, "invalid job id")
    d = WORKDIR / job
    if not d.is_dir():
        raise HTTPException(404, "unknown job")
    return d


def _strip_meshes(parsed: dict) -> dict:
    out = dict(parsed)
    out["components"] = [{k: v for k, v in c.items() if k != "mesh"} for c in parsed["components"]]
    return out


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), deflection: float = Query(0.3, gt=0, le=10)):
    name = os.path.basename(file.filename or "")
    if not name.lower().endswith((".step", ".stp")):
        raise HTTPException(400, "a .step or .stp file is required")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "file too large")
    job = uuid.uuid4().hex
    d = WORKDIR / job
    d.mkdir(parents=True)
    (d / "input.step").write_bytes(data)
    try:
        from .parser import parse_step   # imported lazily: needs pythonocc-core
        parsed = parse_step(str(d / "input.step"), deflection=deflection, with_mesh=True)
    except ValueError as e:
        raise HTTPException(422, str(e))
    parsed["filename"] = name
    (d / "parsed.json").write_text(json.dumps(parsed), encoding="utf-8")
    return {"job_id": job, **_strip_meshes(parsed)}


@app.post("/api/jobs/{job}/explode")
def explode(job: str, factor: float = Query(2.5, ge=0, le=20)):
    d = _job_dir(job)
    parsed = json.loads((d / "parsed.json").read_text(encoding="utf-8"))
    result = compute_exploded_positions(parsed, factor)
    g_asm, g_exp = assembled_and_exploded(result)
    (d / "assembled.gltf").write_text(dumps(g_asm), encoding="utf-8")
    (d / "exploded.gltf").write_text(dumps(g_exp), encoding="utf-8")
    light = _strip_meshes(result)
    (d / "result.json").write_text(json.dumps(light, indent=2), encoding="utf-8")
    return {"job_id": job, **light}


@app.get("/api/jobs/{job}")
def result(job: str):
    d = _job_dir(job)
    p = d / "result.json"
    if not p.exists():
        raise HTTPException(404, "no exploded view yet: call /explode first")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/jobs/{job}/gltf/{kind}")
def gltf(job: str, kind: str):
    if kind not in ("assembled", "exploded"):
        raise HTTPException(400, "kind must be assembled or exploded")
    p = _job_dir(job) / f"{kind}.gltf"
    if not p.exists():
        raise HTTPException(404, "no exploded view yet: call /explode first")
    return Response(p.read_bytes(), media_type="model/gltf+json")


@app.get("/")
def index():
    return FileResponse(STATIC / "viewer.html")
