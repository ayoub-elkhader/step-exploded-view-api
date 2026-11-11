"""Algorithm and glTF writer (pure Python, no CAD kernel)."""
import base64
import math
import struct

import pytest

from step_explode.explode import compute_exploded_positions, explode_vectors
from step_explode.gltf import build_gltf, vertex_normals


def comp(cid, c, d):
    return {"id": cid, "center": dict(zip("xyz", c)), "dimensions": dict(zip("xyz", d))}


def test_vectors_point_away_from_centre_with_size_scaling():
    v = explode_vectors([[-10, 0, 0], [10, 0, 0]], [2.0, 4.0], factor=1.5)
    assert v[0] == pytest.approx([-3.0, 0, 0])
    assert v[1] == pytest.approx([6.0, 0, 0])


def test_part_at_centre_moves_along_y():
    v = explode_vectors([[0, 0, 0], [5, 0, 0], [-5, 0, 0]], [1.0, 1.0, 1.0], factor=2.0)
    assert v[0] == pytest.approx([0, 2.0, 0])


def test_factor_zero_keeps_positions():
    parsed = {"components": [comp("a", (0, 0, 0), (1, 1, 1)), comp("b", (3, 4, 0), (1, 2, 2))]}
    res = compute_exploded_positions(parsed, 0.0)
    for c in res["components"]:
        assert c["exploded_position"] == c["center"]


def test_compute_exploded_positions_fields():
    parsed = {"components": [comp("a", (0, 0, 0), (3, 4, 0)), comp("b", (10, 0, 0), (3, 4, 0))]}
    res = compute_exploded_positions(parsed, 2.0)
    assert res["global_center"] == {"x": 5.0, "y": 0.0, "z": 0.0}
    b = res["components"][1]
    assert b["explode_vector"] == {"x": 10.0, "y": 0.0, "z": 0.0}   # diag 5 * factor 2
    assert b["exploded_position"]["x"] == 20.0
    assert "explode_vector" not in parsed["components"][1]          # input not modified


def test_empty_assembly():
    assert compute_exploded_positions({"components": []})["components"] == []


def test_mismatched_lengths():
    with pytest.raises(ValueError):
        explode_vectors([[0, 0, 0]], [])


def test_vertex_normals_of_a_triangle():
    n = vertex_normals([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [0, 1, 2])
    assert n[0] == pytest.approx([0, 0, 1])


def test_gltf_buffer_roundtrip():
    verts = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    doc = build_gltf([{"name": "p", "vertices": verts, "indices": [0, 1, 2], "translation": [1, 2, 3]}])
    assert doc["asset"]["version"] == "2.0"
    assert doc["nodes"][0]["translation"] == [1.0, 2.0, 3.0]
    raw = base64.b64decode(doc["buffers"][0]["uri"].split(",", 1)[1])
    assert len(raw) == doc["buffers"][0]["byteLength"]
    acc = doc["accessors"][doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    bv = doc["bufferViews"][acc["bufferView"]]
    floats = struct.unpack("<9f", raw[bv["byteOffset"]:bv["byteOffset"] + 36])
    assert floats[3] == 1.0 and acc["max"] == [1, 1, 0]
    for v in doc["bufferViews"]:
        assert v["byteOffset"] % 4 == 0


def test_gltf_skips_empty_pieces():
    doc = build_gltf([{"vertices": [], "indices": [], "translation": [0, 0, 0]}])
    assert doc["nodes"] == [] and doc["buffers"][0]["byteLength"] == 0
