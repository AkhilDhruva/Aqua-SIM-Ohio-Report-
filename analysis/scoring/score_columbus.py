#!/usr/bin/env python3
"""Score the FROZEN Columbus hindcast against observed flooded locations.

Run strictly AFTER run_columbus.py has written frozen_prediction.json.
Input:  observed_flooding.json — [{"name", "lat", "lon", "kind", "sources":[...]}]
        collected from press/NWS AFTER the freeze (each entry needs >=1
        authoritative or >=2 independent sources).
Output: validation_report.json + console summary.

Method
======
For each observed location, sample the model's PEAK water depth over the run
within a small neighborhood (coordinate uncertainty for "road/neighborhood"
reports ~250 m). A location counts as DETECTED if peak depth >= DETECT_DEPTH_M
(enough water to flood roads/basements — 0.15 m) anywhere in that
neighborhood. POD = detected / total. A false-alarm rate is NOT computed: that
would need an authoritative list of places that did NOT flood, which press
coverage cannot provide (stated honestly in the report).

Also reported per location: the percentile of its neighborhood peak depth
among all wet cells — showing whether the model ranks it among its most
flooded places (rank skill, independent of the absolute threshold).
"""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from rasterio.warp import transform as warp_transform

HERE = os.path.dirname(os.path.abspath(__file__))
DETECT_DEPTH_M = 0.15
NEIGHBORHOOD_M = 250.0


def load_run(run_dir):
    man = json.load(open(os.path.join(run_dir, "manifest.json")))
    terr = json.load(open(os.path.join(run_dir, "terrain.json")))
    ny, nx = terr["ny"], terr["nx"]
    peak = np.zeros((ny, nx))
    for rec in man["frames"]:
        fr = json.load(open(os.path.join(run_dir, rec["file"])))
        peak = np.maximum(peak, np.asarray(fr["depth"]))
    mask = np.asarray(terr["mask"], dtype=bool)
    return man, peak, mask


def grid_georef(dx):
    """Exact grid geometry by deterministic reconstruction: same tiles, same
    AOI, same dx -> identical grid, so the transform is exact (the run folder
    itself doesn't carry the affine)."""
    from run_columbus import AOI, TILES
    from aqua_sim.ingestion.dem import DEMSource
    g = DEMSource(TILES, target_dx_m=dx, aoi_bounds=AOI,
                  max_cells=4_000_000).load()
    return g.transform, g.crs, g.nx, g.ny


def score_variant(name, run_dir, observed):
    man, peak, mask = load_run(run_dir)
    dx = man["grid"]["dx_m"]
    (a, _b, left, _d, e, top), crs, gnx, gny = grid_georef(dx)
    assert (gnx, gny) == (man["grid"]["nx"], man["grid"]["ny"]), \
        "reconstructed grid does not match the frozen run"
    wet = peak[mask & (peak > 0.01)]
    wet_sorted = np.sort(wet)
    rows = []
    detected = 0
    r_cells = max(int(round(NEIGHBORHOOD_M / dx)), 1)
    ny, nx = peak.shape
    for loc in observed:
        xs, ys = warp_transform("EPSG:4326", crs, [loc["lon"]], [loc["lat"]])
        i = int((xs[0] - left) / dx)
        j = int((top - ys[0]) / dx)
        if not (0 <= i < nx and 0 <= j < ny):
            rows.append({**loc, "in_domain": False})
            continue
        i0, i1 = max(i - r_cells, 0), min(i + r_cells + 1, nx)
        j0, j1 = max(j - r_cells, 0), min(j + r_cells + 1, ny)
        nb = peak[j0:j1, i0:i1]
        nb_mask = mask[j0:j1, i0:i1]
        pk = float(nb[nb_mask].max()) if nb_mask.any() else 0.0
        hit = pk >= DETECT_DEPTH_M
        detected += int(hit)
        pct = float((wet_sorted.searchsorted(pk) / max(len(wet_sorted), 1)) * 100)
        rows.append({**loc, "in_domain": True, "peak_depth_m": round(pk, 3),
                     "detected": hit, "wet_cell_percentile": round(pct, 1)})
    in_dom = [r for r in rows if r.get("in_domain")]
    return {
        "variant": name, "run_id": man["run_id"],
        "detected": detected, "of": len(in_dom),
        "pod": round(detected / len(in_dom), 3) if in_dom else None,
        "locations": rows,
    }


def main():
    frozen = json.load(open(os.path.join(HERE, "frozen_prediction.json")))
    observed = json.load(open(os.path.join(HERE, "observed_flooding.json")))
    report = {
        "protocol": "prediction frozen (see frozen_prediction.json run_ids) "
                    "before observed locations were collected; sensors were "
                    "terrain-auto-placed; FAR not computable from press data",
        "detect_depth_m": DETECT_DEPTH_M,
        "neighborhood_m": NEIGHBORHOOD_M,
        "variants": [],
    }
    for name, v in frozen["variants"].items():
        report["variants"].append(score_variant(name, v["run_dir"], observed))
    out = os.path.join(HERE, "validation_report.json")
    json.dump(report, open(out, "w"), indent=2)
    for v in report["variants"]:
        print(f"[{v['variant']}] POD {v['detected']}/{v['of']}"
              f" = {v['pod']}   (run {v['run_id']})")
        for r in v["locations"]:
            if not r.get("in_domain"):
                print(f"   OUT-OF-DOMAIN  {r['name']}")
                continue
            mark = "HIT " if r["detected"] else "miss"
            print(f"   {mark} {r['name']:<38} peak {r['peak_depth_m']:>6.2f} m"
                  f"  (p{r['wet_cell_percentile']})")
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
