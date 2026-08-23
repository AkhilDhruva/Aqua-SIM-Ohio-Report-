#!/usr/bin/env python3
"""Extract a boundary-stage record for an ARBITRARY bbox from a completed
parent run's frames — so a tighter nest can be driven without re-running the
parent.

The parent's own boundary_stages.json only covers the originally pre-registered
nest perimeters (recorded at 300 s). This reconstructs the same structure for a
new bbox from the saved frames (30-min cadence). Coarser in time, identical in
kind; the cadence limitation is recorded in the output.

Usage: python3 extract_parent_bc.py <parent_run_dir> <name> <w> <s> <e> <n>
Writes <parent_run_dir>/boundary_stages_<name>.json
"""

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aqua_sim.ingestion.dem import DEMSource
from rasterio.warp import transform as warp_transform

from run_columbus import AOI as PARENT_AOI, TILES as PARENT_TILES


def main():
    prun, name = sys.argv[1], sys.argv[2]
    bbox = tuple(float(v) for v in sys.argv[3:7])
    run_dir = os.path.join(HERE, prun)
    man = json.load(open(os.path.join(run_dir, "manifest.json")))
    dx = man["grid"]["dx_m"]

    grid = DEMSource(PARENT_TILES, target_dx_m=dx, aoi_bounds=PARENT_AOI,
                     max_cells=4_000_000).load()
    assert (grid.nx, grid.ny) == (man["grid"]["nx"], man["grid"]["ny"]), \
        "reconstructed parent grid does not match the run"
    z = np.asarray(grid.z)
    a, _b, left, _d, e, top = grid.transform[:6]

    w, s, e_, n = bbox
    xs, ys = warp_transform("EPSG:4326", grid.crs, [w, e_], [s, n])
    i0 = max(int((xs[0] - left) / a), 0)
    i1 = min(int((xs[1] - left) / a), grid.nx - 1)
    j0 = max(int((ys[1] - top) / e), 0)
    j1 = min(int((ys[0] - top) / e), grid.ny - 1)
    # One-cell ring OUTSIDE the box where possible: the nest edge should read
    # the parent just beyond it, not the parent cell it replaces.
    i0o, i1o = max(i0 - 1, 0), min(i1 + 1, grid.nx - 1)
    j0o, j1o = max(j0 - 1, 0), min(j1 + 1, grid.ny - 1)
    js, is_ = [], []
    for i in range(i0o, i1o + 1):
        js += [j0o, j1o]; is_ += [i, i]
    for j in range(j0o + 1, j1o):
        js += [j, j]; is_ += [i0o, i1o]
    js = np.array(js); is_ = np.array(is_)
    print(f"[{name}] parent ring {js.size} cells "
          f"(i {i0o}..{i1o}, j {j0o}..{j1o}) from {prun}")

    t_s, stages = [], []
    for rec in man["frames"]:
        fr = json.load(open(os.path.join(run_dir, rec["file"])))
        d = np.asarray(fr["depth"])
        t_s.append(round(float(fr.get("time_s", rec.get("time_s", 0.0))), 1))
        stages.append(np.round(z[js, is_] + d[js, is_], 4).tolist())
    out = os.path.join(run_dir, f"boundary_stages_{name}.json")
    with open(out, "w") as f:
        json.dump({"interval_s": (t_s[1] - t_s[0]) if len(t_s) > 1 else 1800.0,
                   "t_s": t_s,
                   "source": "reconstructed from parent frames (not the 300 s "
                             "live record); cadence = frame interval",
                   "bbox_wgs84": list(bbox),
                   "groups": {name: {"j": js.tolist(), "i": is_.tolist(),
                                     "stage_m": stages}}}, f)
    print(f"[{name}] {len(t_s)} samples @ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
