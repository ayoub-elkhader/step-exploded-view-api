"""STEP parsing with pythonocc-core (OpenCASCADE).

Every solid of the file becomes one component (compounds are exploded). For each
component the parser returns its bounding box, centre, dimensions, volume, centre of mass
and number of faces, plus (optionally) a triangle mesh for display.
"""
from __future__ import annotations

import contextlib
import io
import os
from typing import List, Optional

DEFAULT_DEFLECTION = 0.3   # mesh deflection (mm)


def _r(x: float, nd: int = 4) -> float:
    return round(float(x), nd)


def load_solids(path: str) -> list:
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.TopAbs import TopAbs_SOLID
    from OCC.Core.TopExp import TopExp_Explorer

    if not os.path.exists(path):
        raise FileNotFoundError(path)
    reader = STEPControl_Reader()
    with contextlib.redirect_stdout(io.StringIO()):
        status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise ValueError(f"cannot read STEP file: {os.path.basename(path)}")
    reader.TransferRoots()
    shapes = []
    for i in range(1, reader.NbShapes() + 1):
        shape = reader.Shape(i)
        if shape.IsNull():
            continue
        solids = []
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            solids.append(exp.Current())
            exp.Next()
        shapes.extend(solids if solids else [shape])
    return shapes


def triangulate(shape, deflection: float = DEFAULT_DEFLECTION):
    """World-space vertices (list of [x, y, z]) and triangle indices of a shape."""
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.TopoDS import topods

    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5).Perform()
    verts: List[List[float]] = []
    idx: List[int] = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = topods.Face(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            off = len(verts)
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                verts.append([p.X(), p.Y(), p.Z()])
            rev = face.Orientation() == TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                a, b, c = off + a - 1, off + b - 1, off + c - 1
                idx.extend([a, c, b] if rev else [a, b, c])
        exp.Next()
    return verts, idx


def component_data(shape, index: int) -> Optional[dict]:
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer

    box = Bnd_Box()
    box.SetGap(0.0)
    brepbndlib.Add(shape, box, True)
    if box.IsVoid():
        return None
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    center = [(xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2]
    props = GProp_GProps()
    try:
        brepgprop.VolumeProperties(shape, props)
        volume = abs(props.Mass())
        mc = props.CentreOfMass()
        mass_center = [mc.X(), mc.Y(), mc.Z()]
    except Exception:
        volume, mass_center = 0.0, center
    nb_faces = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        nb_faces += 1
        exp.Next()
    xyz = lambda v: {"x": _r(v[0]), "y": _r(v[1]), "z": _r(v[2])}  # noqa: E731
    return {
        "id": f"comp_{index:03d}",
        "index": index,
        "bounding_box": {"min": xyz([xmin, ymin, zmin]), "max": xyz([xmax, ymax, zmax])},
        "center": xyz(center),
        "dimensions": xyz([xmax - xmin, ymax - ymin, zmax - zmin]),
        "mass_center": xyz(mass_center),
        "volume": _r(volume, 6),
        "nb_faces": nb_faces,
    }


def parse_step(path: str, deflection: float = DEFAULT_DEFLECTION, with_mesh: bool = False) -> dict:
    """Parse a STEP file. With ``with_mesh=True`` each component also carries
    ``mesh = {"vertices": [...], "indices": [...]}`` in world coordinates."""
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh

    comps = []
    for i, shape in enumerate(load_solids(path), start=1):
        BRepMesh_IncrementalMesh(shape, deflection).Perform()
        data = component_data(shape, i)
        if data is None:
            continue
        if with_mesh:
            v, f = triangulate(shape, deflection)
            data["mesh"] = {"vertices": v, "indices": f}
        comps.append(data)
    return {"filename": os.path.basename(path), "nb_components": len(comps), "components": comps}
