"""Radial exploded-view algorithm (pure Python, no CAD kernel needed).

Each component moves away from the global centre of the assembly, along the direction
from that centre to its own bounding-box centre, by ``factor * diagonal`` of its own
bounding box. A component that sits exactly at the global centre moves along +Y.

This is a fast heuristic. It does **not** check for interference: coaxial or nested parts
(a shaft and its bearings, a pin in a hole) usually still collide after this explosion.
See the companion repository ``cad-exploded-view-verifier`` for a geometric check and
repair.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

DEFAULT_DIRECTION = (0.0, 1.0, 0.0)


def _xyz(d: dict) -> List[float]:
    return [float(d["x"]), float(d["y"]), float(d["z"])]


def _as_dict(v: Sequence[float], nd: int = 4) -> Dict[str, float]:
    return {"x": round(float(v[0]), nd), "y": round(float(v[1]), nd), "z": round(float(v[2]), nd)}


def explode_vectors(centers: Sequence[Sequence[float]], diagonals: Sequence[float],
                    factor: float = 2.5) -> List[List[float]]:
    """Translation vector of each component."""
    if len(centers) != len(diagonals):
        raise ValueError("centers and diagonals must have the same length")
    if not centers:
        return []
    n = len(centers)
    g = [sum(c[k] for c in centers) / n for k in range(3)]
    out = []
    for c, diag in zip(centers, diagonals):
        d = [c[k] - g[k] for k in range(3)]
        norm = math.sqrt(sum(x * x for x in d))
        u = [x / norm for x in d] if norm >= 1e-6 else list(DEFAULT_DIRECTION)
        out.append([u[k] * diag * factor for k in range(3)])
    return out


def compute_exploded_positions(parsed: dict, factor: float = 2.5) -> dict:
    """Add ``explode_vector`` and ``exploded_position`` to every component of a parsed
    assembly (output of :func:`step_explode.parser.parse_step`)."""
    comps = parsed.get("components", [])
    centers = [_xyz(c["center"]) for c in comps]
    diags = [math.sqrt(sum(float(v) ** 2 for v in c["dimensions"].values())) for c in comps]
    vectors = explode_vectors(centers, diags, factor)
    n = len(centers)
    g = [sum(c[k] for c in centers) / n for k in range(3)] if n else [0.0, 0.0, 0.0]
    out_comps = []
    for c, ctr, v in zip(comps, centers, vectors):
        c2 = dict(c)
        c2["explode_vector"] = _as_dict(v)
        c2["exploded_position"] = _as_dict([ctr[k] + v[k] for k in range(3)])
        out_comps.append(c2)
    result = dict(parsed)
    result["components"] = out_comps
    result["global_center"] = _as_dict(g)
    result["explode_factor"] = factor
    return result
