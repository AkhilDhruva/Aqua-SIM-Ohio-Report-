#!/usr/bin/env python3
"""Street-depth differential + smearing diagnosis (parent 60 m vs nest 6-8 m).

Usage: python3 smearing_analysis.py <nest_name> <nest_run_dir> <parent_run_dir>

THE QUESTION
============
The 60 m parent reported the I-70/South Fork corridor "impassable" (>=0.30 m)
at model hour 16.4. A 60 m cell spans the carriageway, the embankment AND the
channel. So the parent's "road depth" may be channel water averaged onto a cell
that merely CONTAINS a road. The nest resolves them separately.

At each corridor probe, for matching times, this computes:
    parent_cell_depth        depth of the single 60 m cell at the point
    nest_road_depth          depth over ROAD-CLASS cells in the neighborhood
    nest_channel_depth       depth over NHD-FLOWLINE cells in the neighborhood
    nest_offroad_depth       depth over cells that are neither

DIAGNOSIS (per probe, at the parent's own threshold-crossing time)
    SMEARED_FALSE_POSITIVE   parent >= 0.30 m, nest road < 0.15 m,
                             nest channel >= parent  -> the parent signal is
                             channel water on a road-bearing cell
    CONFIRMED                parent >= 0.30 m and nest road >= 0.30 m
    PARTIAL                  parent >= 0.30 m, nest road in [0.15, 0.30)
    NEST_ONLY                parent < 0.15 m but nest road >= 0.30 m
                             (coarse grid MISSES real street flooding)
    DRY_BOTH                 neither exceeds

Bias direction is then reported explicitly: SMEARED_FALSE_POSITIVE inflates
apparent Case A (predictive) when the truth is Case B (coincidental adjacency);
NEST_ONLY does the reverse.
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
from run_nest import (NESTS, PROBES, burn, cells_near, crossing_point,
                      load_flowlines, load_roads)

CAUTION, IMPASS = 0.15, 0.30
T0_LABEL = "2026-08-19T18:00:00Z"


def utc_label(t_s):
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
    return (t0 + timedelta(seconds=float(t_s))).strftime("%m-%d %H:%MZ")


def build_nest_context(nest):
    """Rebuild the nest grid + road/channel masks deterministically."""
    spec = NESTS[nest]
    bbox, dx = spec["bbox"], spec["dx"]
    inv = json.load(open(os.path.join(HERE, "dem1m", "inventory.json")))
    tkey = spec["tiles_from"]
    tiles = [t["path"] for t in inv["tiles"] if tkey in t["box_membership"]]
    if tkey == "pataskala":
        tiles += [t["path"] for t in inv["tiles"]
                  if "buckeye" in t["box_membership"] and t["path"] not in tiles]
    grid = DEMSource(tiles, target_dx_m=dx, aoi_bounds=bbox,
                     max_cells=5_000_000).load()
    ny, nx = grid.ny, grid.nx
    gt = grid.transform
    pad = 0.01
    fbbox = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    roads = load_roads(fbbox, grid.crs)
    flowlines = load_flowlines(spec["hu8s"], fbbox, grid.crs)
    cls_geoms = {}
    for c, g in roads:
        cls_geoms.setdefault(c, []).append(g)
        cls_geoms.setdefault("any", []).append(g)
    masks = {c: burn(gs, gt, (ny, nx)) for c, gs in cls_geoms.items()}
    masks["_channel"] = burn(flowlines, gt, (ny, nx))
    return grid, masks, cls_geoms, flowlines


def probe_cells(nest, grid, masks, cls_geoms, flowlines):
    """Same probe geometry as run_nest.py, plus channel + off-road companions."""
    spec = NESTS[nest]
    gt = grid.transform
    out = {}
    for name, kind, arg, lat, lon, radius in PROBES[spec["probes_from"]]:
        if kind == "road":
            m = masks.get(arg)
            if m is None or not m.any():
                continue
            jj, ii = cells_near(m, gt, lat, lon, radius, grid.crs)
        elif kind == "channel":
            jj, ii = cells_near(masks["_channel"], gt, lat, lon, radius, grid.crs)
        else:
            xs, ys = warp_transform("EPSG:4326", grid.crs, [lon], [lat])
            others = flowlines if kind == "crossing" else \
                cls_geoms.get(arg[1], [])
            cg = cls_geoms.get(arg if kind == "crossing" else arg[0], [])
            pt = crossing_point(cg, others, (xs[0], ys[0]))
            if pt is None:
                continue
            lon2, lat2 = warp_transform(grid.crs, "EPSG:4326", [pt[0]], [pt[1]])
            lat, lon = lat2[0], lon2[0]
            base = masks.get(arg if kind == "crossing" else arg[0])
            jj, ii = cells_near(base, gt, lat, lon, radius, grid.crs)
        if not jj.size:
            continue
        # companions in the SAME neighborhood
        cj, ci = cells_near(masks["_channel"], gt, lat, lon, radius, grid.crs)
        allmask = np.ones(masks["_channel"].shape, bool)
        oj, oi = cells_near(allmask, gt, lat, lon, radius, grid.crs, cap=1200)
        road_set = set(zip(jj.tolist(), ii.tolist()))
        chan_set = set(zip(cj.tolist(), ci.tolist()))
        off = [(j, i) for j, i in zip(oj.tolist(), oi.tolist())
               if (j, i) not in road_set and (j, i) not in chan_set]
        out[name] = {
            "lat": lat, "lon": lon, "radius_m": radius,
            "road": (jj, ii),
            "channel": (cj, ci),
            "offroad": (np.array([p[0] for p in off]), np.array([p[1] for p in off])),
        }
    return out


def parent_context(parent_dir):
    man = json.load(open(os.path.join(parent_dir, "manifest.json")))
    dx = man["grid"]["dx_m"]
    grid = DEMSource(PARENT_TILES, target_dx_m=dx, aoi_bounds=PARENT_AOI,
                     max_cells=4_000_000).load()
    assert (grid.nx, grid.ny) == (man["grid"]["nx"], man["grid"]["ny"])
    return man, grid


def series(run_dir, cells_by_probe, reducer):
    """time -> {probe: value} reading each frame once."""
    man = json.load(open(os.path.join(run_dir, "manifest.json")))
    ts, vals = [], []
    for rec in sorted(man["frames"], key=lambda r: r["index"]):
        path = os.path.join(run_dir, rec["file"])
        if not os.path.exists(path):
            continue
        fr = json.load(open(path))
        d = np.asarray(fr["depth"])
        ts.append(float(fr["time_s"]))
        vals.append({p: reducer(d, c) for p, c in cells_by_probe.items()})
    return ts, vals


def main():
    nest, nest_dir, parent_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    nest_dir = os.path.join(HERE, nest_dir)
    parent_dir = os.path.join(HERE, parent_dir)

    grid, masks, cls_geoms, flowlines = build_nest_context(nest)
    probes = probe_cells(nest, grid, masks, cls_geoms, flowlines)
    print(f"[{nest}] probes rebuilt: " +
          ", ".join(f"{k}(road {v['road'][0].size}/chan {v['channel'][0].size}"
                    f"/off {v['offroad'][0].size})" for k, v in probes.items()))

    # nest series: max depth over each class in the neighborhood
    def mk(kind):
        return {p: v[kind] for p, v in probes.items() if v[kind][0].size}
    nt, nroad = series(nest_dir, mk("road"),
                       lambda d, c: float(d[c[0], c[1]].max()))
    _, nchan = series(nest_dir, mk("channel"),
                      lambda d, c: float(d[c[0], c[1]].max()))
    _, noff = series(nest_dir, mk("offroad"),
                     lambda d, c: float(d[c[0], c[1]].max()))

    # parent series: the single cell containing each probe point
    pman, pgrid = parent_context(parent_dir)
    a, _b, left, _d, e, top = pgrid.transform[:6]
    pcells = {}
    for name, v in probes.items():
        xs, ys = warp_transform("EPSG:4326", pgrid.crs, [v["lon"]], [v["lat"]])
        i = int((xs[0] - left) / a)
        j = int((ys[0] - top) / e)
        if 0 <= i < pgrid.nx and 0 <= j < pgrid.ny:
            pcells[name] = (np.array([j]), np.array([i]))
    pt, pvals = series(parent_dir, pcells,
                       lambda d, c: float(d[c[0], c[1]].max()))
    pt = np.asarray(pt)

    rows = []
    for name in probes:
        if name not in pcells or name not in nroad[0]:
            continue
        road = np.array([v.get(name, np.nan) for v in nroad])
        chan = np.array([v.get(name, np.nan) for v in nchan]) \
            if name in (nchan[0] if nchan else {}) else np.full(len(nt), np.nan)
        off = np.array([v.get(name, np.nan) for v in noff]) \
            if name in (noff[0] if noff else {}) else np.full(len(nt), np.nan)
        par = np.array([v[name] for v in pvals])
        # parent's own crossing time
        pidx = np.nonzero(par >= IMPASS)[0]
        p_cross_t = float(pt[pidx[0]]) if pidx.size else None
        # compare at the LAST time both cover, and at the parent crossing time
        t_common = min(max(nt), float(pt[-1]))
        kn = int(np.argmin(np.abs(np.asarray(nt) - t_common)))
        kp = int(np.argmin(np.abs(pt - t_common)))
        row = {
            "probe": name, "lat": probes[name]["lat"], "lon": probes[name]["lon"],
            "nest_frames": len(nt), "t_common_s": t_common,
            "t_common_utc": utc_label(t_common),
            "parent_depth_m": round(float(par[kp]), 3),
            "nest_road_max_m": round(float(road[kn]), 3),
            "nest_channel_max_m": None if np.isnan(chan[kn]) else round(float(chan[kn]), 3),
            "nest_offroad_max_m": None if np.isnan(off[kn]) else round(float(off[kn]), 3),
            "differential_parent_minus_road_m": round(float(par[kp] - road[kn]), 3),
            "parent_impassable_utc": None if p_cross_t is None else utc_label(p_cross_t),
        }
        pd_, nr = row["parent_depth_m"], row["nest_road_max_m"]
        nc = row["nest_channel_max_m"]
        if pd_ >= IMPASS and nr < CAUTION and (nc is not None and nc >= pd_):
            row["diagnosis"] = "SMEARED_FALSE_POSITIVE"
        elif pd_ >= IMPASS and nr >= IMPASS:
            row["diagnosis"] = "CONFIRMED"
        elif pd_ >= IMPASS and nr >= CAUTION:
            row["diagnosis"] = "PARTIAL"
        elif pd_ < CAUTION and nr >= IMPASS:
            row["diagnosis"] = "NEST_ONLY"
        elif pd_ >= IMPASS and nr < CAUTION:
            row["diagnosis"] = "PARENT_ONLY_UNEXPLAINED"
        else:
            row["diagnosis"] = "DRY_BOTH"
        rows.append(row)

    counts = {}
    for r in rows:
        counts[r["diagnosis"]] = counts.get(r["diagnosis"], 0) + 1
    bias = ("inflates Case A (parent looks predictive; nest shows channel water, "
            "not road water)" if counts.get("SMEARED_FALSE_POSITIVE") else
            "no smearing false positives at the times compared")
    out = {"nest": nest, "nest_dir": os.path.basename(nest_dir),
           "parent_dir": os.path.basename(parent_dir),
           "thresholds_m": {"caution": CAUTION, "impassable": IMPASS},
           "t0_utc": T0_LABEL, "counts": counts, "bias_direction": bias,
           "probes": rows,
           "series": {"t_s": nt,
                      "road": {p: [float(v.get(p, np.nan)) for v in nroad]
                               for p in (nroad[0] if nroad else {})},
                      "channel": {p: [float(v.get(p, np.nan)) for v in nchan]
                                  for p in (nchan[0] if nchan else {})},
                      "parent_t_s": pt.tolist(),
                      "parent": {p: [float(v[p]) for v in pvals] for p in pcells}}}
    path = os.path.join(HERE, f"smearing_{nest}.json")
    json.dump(out, open(path, "w"), indent=2)
    print(f"\n{'probe':<30}{'parent':>8}{'road':>8}{'chan':>8}{'diff':>8}  diagnosis")
    for r in rows:
        print(f"{r['probe']:<30}{r['parent_depth_m']:>8.2f}"
              f"{r['nest_road_max_m']:>8.2f}"
              f"{(r['nest_channel_max_m'] if r['nest_channel_max_m'] is not None else float('nan')):>8.2f}"
              f"{r['differential_parent_minus_road_m']:>8.2f}  {r['diagnosis']}")
    print(f"\ncounts {counts}\nbias: {bias}\n-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
