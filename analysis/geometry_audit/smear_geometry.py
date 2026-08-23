#!/usr/bin/env python3
"""Static (geometric) smearing diagnostic — the mechanism, before any dynamics.

Usage: python3 smear_geometry.py <nest_name> [<nest_name> ...]

A 60 m parent cell carries ONE bed elevation for everything inside it. Where a
corridor crosses a stream, that one cell contains carriageway, embankment and
channel invert. Whatever elevation the resampler picked becomes the elevation at
which "the road" floods in the parent model.

For each corridor probe this reports, from the 1 m-derived nest terrain:
    z_road_med      median bed elevation of the carriageway cells
    z_chan_min      minimum bed elevation of the channel cells (invert)
    z_parent        the single 60 m parent cell's bed elevation at that point
    deficit_m       z_road_med - z_parent   (how far BELOW the true road
                    surface the parent's bed sits)
    position        where z_parent falls between channel invert and road:
                    0.0 = at the channel invert, 1.0 = at the road surface

INTERPRETATION
    deficit_m large and position near 0  ->  the parent cell is effectively a
    CHANNEL cell wearing a road's name. It fills at channel stage, so the parent
    will report the road inundated whenever the stream is high — regardless of
    whether water ever reaches the pavement. This inflates apparent Case A.

    deficit_m near 0 (position near 1) -> the parent bed IS the road surface;
    parent road depths are physically meaningful and Case A is testable.

This is a property of the terrain and the grid, not of the storm, so it is
computable without waiting for any simulation.
"""

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from rasterio.warp import transform as warp_transform

from aqua_sim.ingestion.dem import DEMSource
from run_columbus import AOI as PARENT_AOI, TILES as PARENT_TILES
from smearing_analysis import build_nest_context, probe_cells


def main():
    parent_grid = DEMSource(PARENT_TILES, target_dx_m=60.0,
                            aoi_bounds=PARENT_AOI, max_cells=4_000_000).load()
    pz = np.asarray(parent_grid.z)
    pa, _pb, pleft, _pd, pe, ptop = parent_grid.transform[:6]

    all_rows = []
    for nest in sys.argv[1:]:
        grid, masks, cls_geoms, flowlines = build_nest_context(nest)
        probes = probe_cells(nest, grid, masks, cls_geoms, flowlines)
        z = np.asarray(grid.z)
        for name, v in probes.items():
            rj, ri = v["road"]
            cj, ci = v["channel"]
            if not rj.size:
                continue
            z_road = np.asarray(z[rj, ri], float)
            z_road = z_road[np.isfinite(z_road)]
            z_chan = np.asarray(z[cj, ci], float) if cj.size else np.array([])
            z_chan = z_chan[np.isfinite(z_chan)]
            xs, ys = warp_transform("EPSG:4326", parent_grid.crs,
                                    [v["lon"]], [v["lat"]])
            pi = int((xs[0] - pleft) / pa)
            pj = int((ys[0] - ptop) / pe)
            if not (0 <= pi < parent_grid.nx and 0 <= pj < parent_grid.ny):
                continue
            z_par = float(pz[pj, pi])
            z_road_med = float(np.median(z_road))
            z_chan_min = float(z_chan.min()) if z_chan.size else None
            deficit = z_road_med - z_par
            pos = None
            # a meaningful position needs real road-above-channel separation;
            # where the two are within 0.5 m the ratio is degenerate.
            if z_chan_min is not None and (z_road_med - z_chan_min) > 0.5:
                pos = (z_par - z_chan_min) / (z_road_med - z_chan_min)
            row = {
                "nest": nest, "probe": name,
                "lat": round(v["lat"], 5), "lon": round(v["lon"], 5),
                "n_road_cells": int(rj.size), "n_chan_cells": int(cj.size),
                "z_road_med_m": round(z_road_med, 2),
                "z_road_min_m": round(float(z_road.min()), 2),
                "z_chan_min_m": None if z_chan_min is None else round(z_chan_min, 2),
                "z_parent_m": round(z_par, 2),
                "deficit_m": round(deficit, 2),
                "position_chan0_road1": None if pos is None else round(float(pos), 2),
                "road_relief_m": round(float(z_road.max() - z_road.min()), 2),
                # Policy-legible: when the 60 m model calls this road
                # impassable (0.30 m on its own cell), where is its water
                # surface relative to the REAL pavement?
                "parent_stage_at_impassable_m": round(z_par + 0.30, 2),
                "freeboard_to_pavement_m": round(z_road_med - (z_par + 0.30), 2),
            }
            if pos is not None and pos < 0.35 and deficit > 0.5:
                row["verdict"] = "PARENT_CELL_IS_CHANNEL_LIKE"
            elif pos is not None and pos > 0.75:
                row["verdict"] = "PARENT_CELL_IS_ROAD_LIKE"
            else:
                row["verdict"] = "MIXED"
            all_rows.append(row)

    path = os.path.join(HERE, "smear_geometry.json")
    json.dump({"parent_dx_m": 60.0,
               "explanation": "deficit_m = median carriageway elevation minus "
                              "the 60 m parent cell bed; position 0 = parent "
                              "bed at channel invert, 1 = at road surface",
               "rows": all_rows}, open(path, "w"), indent=2)

    print(f"{'probe':<30}{'z_road':>9}{'z_chan':>9}{'z_par':>9}"
          f"{'deficit':>9}{'pos':>6}  verdict")
    for r in all_rows:
        zc = r["z_chan_min_m"]
        print(f"{r['probe']:<30}{r['z_road_med_m']:>9.2f}"
              f"{(zc if zc is not None else float('nan')):>9.2f}"
              f"{r['z_parent_m']:>9.2f}{r['deficit_m']:>9.2f}"
              f"{(r['position_chan0_road1'] if r['position_chan0_road1'] is not None else float('nan')):>6.2f}"
              f"  {r['verdict']}")
    print("->", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
