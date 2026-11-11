"""Command line: ``step-explode assembly.step --factor 2.5 --out-dir out/``.

Writes ``<name>_exploded.json``, ``<name>_assembled.gltf`` and ``<name>_exploded.gltf``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .explode import compute_exploded_positions
from .gltf import assembled_and_exploded, dumps


def main(argv=None):
    ap = argparse.ArgumentParser(prog="step-explode", description=__doc__)
    ap.add_argument("step")
    ap.add_argument("--factor", type=float, default=2.5)
    ap.add_argument("--deflection", type=float, default=0.3)
    ap.add_argument("--out-dir", default=".")
    a = ap.parse_args(argv)

    from .parser import parse_step
    parsed = parse_step(a.step, a.deflection, with_mesh=True)
    res = compute_exploded_positions(parsed, a.factor)
    g_asm, g_exp = assembled_and_exploded(res)
    base = os.path.splitext(os.path.basename(a.step))[0]
    os.makedirs(a.out_dir, exist_ok=True)
    light = dict(res, components=[{k: v for k, v in c.items() if k != "mesh"} for c in res["components"]])
    paths = {
        "json": os.path.join(a.out_dir, f"{base}_exploded.json"),
        "assembled": os.path.join(a.out_dir, f"{base}_assembled.gltf"),
        "exploded": os.path.join(a.out_dir, f"{base}_exploded.gltf"),
    }
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(light, f, indent=2)
    for k, doc in (("assembled", g_asm), ("exploded", g_exp)):
        with open(paths[k], "w", encoding="utf-8") as f:
            f.write(dumps(doc))
    print(f"{res['nb_components']} components")
    for c in light["components"]:
        v = c["explode_vector"]
        print(f"  {c['id']}: vector ({v['x']}, {v['y']}, {v['z']})")
    for p in paths.values():
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
