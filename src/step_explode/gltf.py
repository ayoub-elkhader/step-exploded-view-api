"""Minimal glTF 2.0 writer (embedded buffer, one mesh and one node per component).

Vertices are stored relative to the component centre and the node translation carries
the position, so the assembled and exploded files differ only by node translations.
Pure Python (``struct`` + ``base64``), no CAD kernel needed.
"""
from __future__ import annotations

import base64
import json
import math
import struct
from typing import Iterable, List, Sequence

PALETTE = [
    [0.43, 0.90, 0.97, 1.0], [0.65, 0.55, 0.98, 1.0], [0.96, 0.45, 0.71, 1.0],
    [0.20, 0.83, 0.60, 1.0], [0.98, 0.75, 0.15, 1.0], [0.97, 0.53, 0.43, 1.0],
]


def vertex_normals(verts: Sequence[Sequence[float]], idx: Sequence[int]) -> List[List[float]]:
    acc = [[0.0, 0.0, 0.0] for _ in verts]
    for t in range(0, len(idx), 3):
        i0, i1, i2 = idx[t], idx[t + 1], idx[t + 2]
        a, b, c = verts[i0], verts[i1], verts[i2]
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        ln = math.sqrt(sum(x * x for x in n))
        if ln > 1e-12:
            n = [x / ln for x in n]
            for i in (i0, i1, i2):
                for k in range(3):
                    acc[i][k] += n[k]
    out = []
    for a in acc:
        ln = math.sqrt(sum(x * x for x in a))
        out.append([x / ln for x in a] if ln > 1e-12 else [0.0, 1.0, 0.0])
    return out


def build_gltf(pieces: Iterable[dict]) -> dict:
    """``pieces``: dicts with ``name``, ``vertices`` (local), ``indices``, ``translation``."""
    blobs: List[bytes] = []
    views, accessors, meshes, nodes, materials = [], [], [], [], []
    offset = 0

    def add(data: bytes, target: int, count: int, typ: str, comp: int = 5126, mn=None, mx=None):
        nonlocal offset
        while len(data) % 4:
            data += b"\x00"
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": count, "type": typ}
        if mn is not None:
            acc["min"], acc["max"] = mn, mx
        accessors.append(acc)
        blobs.append(data)
        offset += len(data)
        return len(accessors) - 1

    for k, p in enumerate(pieces):
        verts, idx = p["vertices"], p["indices"]
        if not verts or not idx:
            continue
        norms = vertex_normals(verts, idx)
        vb = b"".join(struct.pack("<fff", *map(float, v)) for v in verts)
        nb = b"".join(struct.pack("<fff", *map(float, n)) for n in norms)
        small = len(verts) < 65536
        ib = b"".join(struct.pack("<H" if small else "<I", i) for i in idx)
        mn = [min(v[c] for v in verts) for c in range(3)]
        mx = [max(v[c] for v in verts) for c in range(3)]
        a_pos = add(vb, 34962, len(verts), "VEC3", mn=mn, mx=mx)
        a_nrm = add(nb, 34962, len(norms), "VEC3")
        a_idx = add(ib, 34963, len(idx), "SCALAR", comp=5123 if small else 5125)
        materials.append({"name": f"mat_{k:03d}", "doubleSided": True,
                          "pbrMetallicRoughness": {"baseColorFactor": PALETTE[k % len(PALETTE)],
                                                   "metallicFactor": 0.05, "roughnessFactor": 0.55}})
        meshes.append({"name": p.get("name", f"piece_{k:03d}"),
                       "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nrm},
                                       "indices": a_idx, "material": len(materials) - 1, "mode": 4}]})
        nodes.append({"name": p.get("name", f"piece_{k:03d}"), "mesh": len(meshes) - 1,
                      "translation": [float(x) for x in p["translation"]]})

    buf = b"".join(blobs)
    return {
        "asset": {"version": "2.0", "generator": "step-exploded-view-api"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes, "meshes": meshes, "materials": materials,
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(buf),
                     "uri": "data:application/octet-stream;base64," + base64.b64encode(buf).decode()}],
    }


def assembled_and_exploded(parsed_exploded: dict):
    """Two glTF documents (assembled, exploded) from a parsed + exploded assembly whose
    components carry a ``mesh`` (see ``parse_step(..., with_mesh=True)``)."""
    asm, exp = [], []
    for c in parsed_exploded["components"]:
        ctr = [c["center"][a] for a in "xyz"]
        local = [[v[k] - ctr[k] for k in range(3)] for v in c["mesh"]["vertices"]]
        base = {"name": c["id"], "vertices": local, "indices": c["mesh"]["indices"]}
        asm.append(dict(base, translation=ctr))
        exp.append(dict(base, translation=[c["exploded_position"][a] for a in "xyz"]))
    return build_gltf(asm), build_gltf(exp)


def dumps(doc: dict) -> str:
    return json.dumps(doc, separators=(",", ":"))
