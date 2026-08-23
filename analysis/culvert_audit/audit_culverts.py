#!/usr/bin/env python3
"""Blinded audit of auto-detected culverts against the native 1 m LiDAR.

The detector ran on the resampled nest grid (5-6 m). This audit re-derives the
same crossings deterministically, draws a FIXED-SEED random sample of the
'added' culverts (blind: the sample is chosen before any classification), and
re-tests each against the 1 m tiles with purely numeric criteria:

  embank_1m   max z along the flowline within +/-15 m of the crossing
              minus min(z at flowline points 40 m up/downstream)
  chan_ok     both the up- and downstream flowline points sit >= 0.7 m below
              the embankment top (channel continues through)

  TRUE            embank_1m >= 1.0 AND chan_ok
  LIKELY          0.5 <= embank_1m < 1.0 AND chan_ok
  FALSE_POSITIVE  embank_1m < 0.5  (no embankment at 1 m -> resampling artifact)
  UNRESOLVED      nodata / outside tiles

Precision (reported) = (TRUE + LIKELY) / classified.
Datum note: crossings are in EPSG:32617, tiles in EPSG:26917 — the NAD83/WGS84
horizontal offset (~1 m) is far below the 15-40 m sampling scales.

Usage: python3 audit_culverts.py <nest> [dx] [sample_n]
"""

import json
import os
import sys

import numpy as np
import rasterio

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aqua_sim.ingestion.dem import DEMSource

from run_nest import NESTS, find_culverts, load_flowlines, load_roads

SEED = 20260822


class TileSampler:
    def __init__(self, paths):
        self.srcs = [rasterio.open(p) for p in paths]

    def z(self, x, y):
        for s in self.srcs:
            b = s.bounds
            if b.left <= x <= b.right and b.bottom <= y <= b.top:
                v = next(s.sample([(x, y)]))[0]
                if v is not None and v > -1e5:
                    return float(v)
        return np.nan


def main():
    nest = sys.argv[1]
    dx = float(sys.argv[2]) if len(sys.argv) > 2 else \
        (6.0 if nest != "buckeye" else 6.0)
    sample_n = int(sys.argv[3]) if len(sys.argv) > 3 else 25
    spec = NESTS[nest]
    bbox = spec["bbox"]
    inv = json.load(open(os.path.join(HERE, "dem1m", "inventory.json")))
    tiles = [t["path"] for t in inv["tiles"] if nest in t["box_membership"]]
    if nest == "pataskala":
        tiles += [t["path"] for t in inv["tiles"]
                  if "buckeye" in t["box_membership"] and t["path"] not in tiles]

    grid = DEMSource(tiles, target_dx_m=dx, aoi_bounds=bbox,
                     max_cells=5_000_000).load()
    zarr = np.asarray(grid.z)
    pad = 0.01
    fbbox = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    roads = load_roads(fbbox, grid.crs)
    flowlines = load_flowlines(spec["hu8s"], fbbox, grid.crs)
    culverts, log_rows = find_culverts(roads, flowlines, zarr, grid.transform, dx)
    added = [r for r in log_rows if r["added"]]
    print(f"[{nest}] detector: {len(log_rows)} crossings, {len(added)} culverted")

    rng = np.random.default_rng(SEED)          # blind fixed-seed sample
    idx = rng.choice(len(added), size=min(sample_n, len(added)), replace=False)
    sample = [added[i] for i in sorted(idx)]

    # geometry lookup: re-find each sampled crossing's flowline chainage by
    # nearest flowline to the logged point
    from shapely.geometry import Point
    ts = TileSampler(tiles)
    results = []
    for row in sample:
        pt = Point(row["x"], row["y"])
        fl = min(flowlines, key=lambda f: f.distance(pt))
        chain = fl.project(pt)
        up = fl.interpolate(max(chain - 40, 0))
        dn = fl.interpolate(min(chain + 40, fl.length))
        mids = [fl.interpolate(chain + d) for d in (-15, -7, 0, 7, 15)
                if 0 <= chain + d <= fl.length]
        z_up, z_dn = ts.z(up.x, up.y), ts.z(dn.x, dn.y)
        z_mid = np.nanmax([ts.z(p.x, p.y) for p in mids])
        if np.isnan(z_up) or np.isnan(z_dn) or np.isnan(z_mid):
            cls = "UNRESOLVED"
            embank = None
            chan_ok = None
        else:
            embank = z_mid - min(z_up, z_dn)
            chan_ok = (z_up <= z_mid - 0.7) and (z_dn <= z_mid - 0.7)
            if embank >= 1.0 and chan_ok:
                cls = "TRUE"
            elif embank >= 0.5 and chan_ok:
                cls = "LIKELY"
            elif embank < 0.5:
                cls = "FALSE_POSITIVE"
            else:
                cls = "LIKELY" if embank >= 1.0 else "FALSE_POSITIVE"
        results.append({**row, "embank_1m": None if embank is None
                        else round(float(embank), 2),
                        "chan_ok": None if chan_ok is None else bool(chan_ok),
                        "class": cls})
    counts = {}
    for r in results:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    classified = sum(v for k, v in counts.items() if k != "UNRESOLVED")
    good = counts.get("TRUE", 0) + counts.get("LIKELY", 0)
    out = {"nest": nest, "dx": dx, "seed": SEED,
           "n_crossings": len(log_rows), "n_added": len(added),
           "sample_n": len(sample), "counts": counts,
           "precision": round(good / classified, 3) if classified else None,
           "sample": results}
    path = os.path.join(HERE, f"culvert_audit_{nest}.json")
    json.dump(out, open(path, "w"), indent=2)
    print(f"[{nest}] audit: {counts} -> precision "
          f"{out['precision']} ({good}/{classified}) -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
