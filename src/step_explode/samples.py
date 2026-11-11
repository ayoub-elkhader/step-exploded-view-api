"""Generate small synthetic STEP assemblies from OCCT primitives (for demos and tests).

    python -m step_explode.samples out_dir/

Shapes are generated, not taken from any dataset. Units: millimetres.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys


def _box(x, y, z, dx, dy, dz):
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.gp import gp_Pnt
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def _cyl(c, r, h):
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*c), gp_Dir(0, 0, 1)), r, h).Shape()


def _cut(a, b):
    from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
    return BRepAlgoAPI_Cut(a, b).Shape()


def bracket():
    """Base plate, two uprights and a cross bar (4 parts, touching faces)."""
    return [_box(0, 0, 0, 100, 60, 10), _box(0, 20, 10, 10, 20, 50),
            _box(90, 20, 10, 10, 20, 50), _box(0, 20, 60, 100, 20, 10)]


def flange():
    """Flange with a bore, a shaft through it and a cover (3 parts, coaxial)."""
    plate = _cut(_cyl((0, 0, 0), 40, 10), _cyl((0, 0, -1), 10.1, 12))
    shaft = _cyl((0, 0, -30), 10, 80)
    cover = _cut(_cyl((0, 0, 10), 40, 5), _cyl((0, 0, 9), 10.1, 7))
    return [plate, shaft, cover]


SAMPLES = {"bracket": bracket, "flange": flange}


def write_step(shapes, path):
    from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
    w = STEPControl_Writer()
    for s in shapes:
        w.Transfer(s, STEPControl_AsIs)
    with contextlib.redirect_stdout(io.StringIO()):
        w.Write(str(path))


def write_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, fn in SAMPLES.items():
        p = os.path.join(out_dir, f"{name}.step")
        write_step(fn(), p)
        paths.append(p)
    return paths


if __name__ == "__main__":
    for p in write_all(sys.argv[1] if len(sys.argv) > 1 else "samples"):
        print(p)
