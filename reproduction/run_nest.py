#!/usr/bin/env python3
"""Fine-resolution nested hindcast (side task, Phase 2).

Usage: python3 run_nest.py <franklinton|pataskala|buckeye> [A|B] [--infil MM_HR]

Per nest_prereg.json (+ logged amendments):
  * terrain: USGS 3DEP 1 m LiDAR resampled to 5-6 m (bare-earth: bridge decks
    are open, embankments are real);
  * Manning: roads 0.013 (USGS NTD centerlines, MAF/TIGER-derived),
    NHD flowline channels 0.035, elsewhere 0.05;
  * culverts: at each road x stream crossing whose DTM profile shows a
    continuous embankment (no opening), an orifice connection (cd_area 1.5 m^2)
    links the flowline ~30 m up/downstream — prevents fake dams; crossings the
    DTM already shows open (bridges) are left alone and logged;
  * rain: MRMS QPE (A radar-only 15-min / B multi-sensor hourly), never scaled;
  * boundary: Dirichlet stage strips from the 60 m QPE-B parent run, imposed
    only while the parent cell is wet; domain edges otherwise OPEN;
  * probes: 60 s depth series at corridor segments (I-70/SR-79, US-40, SR-310,
    Main St, W Broad) and at gauged reaches -> threshold-crossing times;
  * infiltration: I0 = 0 default; --infil N runs the sensitivity member.
No repo files are touched; run_mid/run_low are never overwritten.
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fiona
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_geom
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiLineString, shape
from shapely.strtree import STRtree

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.ingestion.dem import DEMSource
from aqua_sim.scenario import Scenario, _auto_sink_nodes, run_scenario

from prep_qpe import intervals_from_npz
from qpe_solver import (Probes, RainSeries, StageBC, build_idx_map,
                        last_solver, patch_make_solver)
from run_columbus import AOI as PARENT_AOI, TILES as PARENT_TILES

NESTS = {
    "franklinton": {"bbox": (-83.07, 39.93, -82.97, 39.99), "dx": 6.0,
                    "hu8s": ["05060001"]},
    "pataskala": {"bbox": (-82.72, 39.945, -82.585, 40.025), "dx": 6.0,
                  "hu8s": ["05040006", "05060001"]},
    "buckeye": {"bbox": (-82.53, 39.905, -82.44, 39.965), "dx": 5.0,
                "hu8s": ["05040006"]},
    # --- corridor domains (compute amendment #4) -------------------------
    # Same pre-registered 6 m resolution; reduced EXTENT so the storm-phase
    # CFL cost is affordable. Each still encloses its corridor of record and,
    # where possible, a gauged reach.
    "franklinton_c": {"bbox": (-83.058, 39.948, -83.015, 39.985), "dx": 6.0,
                      "hu8s": ["05060001"], "tiles_from": "franklinton",
                      "probes_from": "franklinton"},
    "pataskala_c": {"bbox": (-82.700, 39.955, -82.585, 39.998), "dx": 8.0,
                    "hu8s": ["05040006", "05060001"], "tiles_from": "pataskala",
                    "probes_from": "pataskala"},
    # north edge carries US-40 (National Road) through Hebron — the designated
    # I-70 detour — so the detour's OWN flood exposure is simulated too.
    "buckeye_c": {"bbox": (-82.512, 39.918, -82.462, 39.968), "dx": 6.0,
                  "hu8s": ["05040006"], "tiles_from": "buckeye",
                  "probes_from": "buckeye"},
}
for _k, _v in list(NESTS.items()):
    _v.setdefault("tiles_from", _k)
    _v.setdefault("probes_from", _k)

#: probe specs: name -> (kind, arg, lat, lon, radius_m); kind 'road' uses the
#: road class raster, 'channel' the flowline raster, 'crossing' computes the
#: road-class x flowline intersection nearest (lat, lon).
PROBES = {
    "franklinton": [
        ("wbroad_hilltop", "road", "us40", 39.9585, -83.0500, 350),
        ("franklinton_core", "road", "any", 39.9560, -83.0230, 300),
        ("scioto_gauge_03221646", "channel", None, 39.989, -83.068, 300),
        ("olentangy_gauge_03227107", "channel", None, 39.983, -83.021, 300),
    ],
    "pataskala": [
        ("us40_etna", "road", "us40", 39.9573, -82.6829, 400),
        ("us40_east", "road", "us40", 39.9585, -82.6300, 400),
        ("main_broad_pataskala", "road", "any", 39.9895, -82.6740, 300),
        ("sr310_sf_crossing", "crossing", "sr310", 39.975, -82.683, 300),
        ("broadst_sw_sr16", "road", "sr16", 39.9800, -82.7000, 400),
        ("kirkersville_gauge_03144816", "channel", None, 39.964, -82.595, 300),
    ],
    "buckeye": [
        ("i70_sf_licking", "crossing", "i70", 39.935, -82.495, 450),
        ("i70_sr79", "crossing_road", ("i70", "sr79"), 39.934, -82.483, 450),
        ("sr79_hebron_rd", "road", "sr79", 39.9400, -82.4835, 400),
        ("us40_hebron", "road", "us40", 39.9630, -82.4900, 500),
    ],
}


def road_class(props):
    if (props.get("interstate") or "").strip() == "70" or props.get("name") == "I- 70":
        return "i70"
    us = {(props.get(k) or "").strip() for k in ("us_route", "us_route_a",
                                                 "us_route_b", "us_route_c")}
    if "40" in us:
        return "us40"
    sr = {(props.get(k) or "").strip() for k in ("state_rout", "state_ro_1",
                                                 "state_ro_2", "state_ro_3")}
    if "310" in sr:
        return "sr310"
    if "16" in sr:
        return "sr16"
    if "79" in sr:
        return "sr79"
    return "other"


def load_roads(bbox, dst_crs):
    """NTD road segments intersecting bbox -> list[(class, shapely geom in dst)]."""
    out = []
    for part in ("Trans_RoadSegment_0.shp", "Trans_RoadSegment_1.shp"):
        path = os.path.join(HERE, "roads", "TRAN_Ohio", "Shape", part)
        with fiona.open(path) as src:
            for feat in src.filter(bbox=bbox):
                cls = road_class(feat["properties"])
                geom = transform_geom("EPSG:4269", dst_crs, dict(feat["geometry"]))
                out.append((cls, shape(geom)))
    return out


def load_flowlines(hu8s, bbox, dst_crs):
    keep = {460, 558, 336}   # StreamRiver, ArtificialPath, CanalDitch
    out = []
    for hu8 in hu8s:
        gdb = os.path.join(HERE, "hydro", f"NHD_H_{hu8}_HU8_GDB.gdb")
        with fiona.open(gdb, layer="NHDFlowline") as src:
            for feat in src.filter(bbox=bbox):
                p = feat["properties"]
                ftype = p.get("ftype") or p.get("FType")
                if ftype not in keep:
                    continue
                geom = transform_geom(src.crs, dst_crs, dict(feat["geometry"]))
                g = shape(geom)
                if isinstance(g, MultiLineString):
                    out.extend(list(g.geoms))
                elif isinstance(g, LineString):
                    out.append(g)
    return out


def flatten_lines(geoms):
    flat = []
    for g in geoms:
        if isinstance(g, MultiLineString):
            flat.extend(g.geoms)
        else:
            flat.append(g)
    return flat


def burn(shapes, transform, shape_hw):
    if not shapes:
        return np.zeros(shape_hw, dtype=bool)
    arr = rasterize(((g.__geo_interface__, 1) for g in shapes),
                    out_shape=shape_hw, transform=transform,
                    fill=0, all_touched=True, dtype="uint8")
    return arr.astype(bool)


def sample_z(zarr, transform, pts):
    a, _b, left, _d, e, top = transform[:6]
    out = []
    ny, nx = zarr.shape
    for x, y in pts:
        i = int((x - left) / a)
        j = int((y - top) / e)
        if 0 <= i < nx and 0 <= j < ny:
            out.append(zarr[j, i])
        else:
            out.append(np.nan)
    return np.array(out)


def find_culverts(roads, flowlines, zarr, transform, dx):
    """Road x stream crossings; embankment test on the DTM; orifice pairs."""
    a, _b, left, _d, e, top = transform[:6]
    ny, nx = zarr.shape
    road_geoms = [g for _c, g in roads]
    tree = STRtree(road_geoms)
    culverts, log_rows = [], []
    seen = []
    for fl in flowlines:
        if fl.length < 60:
            continue
        for ridx in tree.query(fl):
            rg = road_geoms[int(ridx)]
            inter = fl.intersection(rg)
            if inter.is_empty:
                continue
            pts = []
            if inter.geom_type == "Point":
                pts = [inter]
            elif inter.geom_type == "MultiPoint":
                pts = list(inter.geoms)
            for pt in pts:
                if any(pt.distance(s) < 40 for s in seen):
                    continue
                seen.append(pt)
                chain = fl.project(pt)
                up = fl.interpolate(max(chain - 40, 0))
                dn = fl.interpolate(min(chain + 40, fl.length))
                mid_pts = [fl.interpolate(chain + d)
                           for d in (-15, -7, 0, 7, 15)
                           if 0 <= chain + d <= fl.length]
                z_up, z_dn = sample_z(zarr, transform, [(up.x, up.y)])[0], \
                    sample_z(zarr, transform, [(dn.x, dn.y)])[0]
                z_mid = np.nanmax(sample_z(
                    zarr, transform, [(p.x, p.y) for p in mid_pts]))
                if np.isnan(z_up) or np.isnan(z_dn) or np.isnan(z_mid):
                    continue
                embank = z_mid - min(z_up, z_dn)
                blocked = embank > 1.0
                row = {"x": round(pt.x, 1), "y": round(pt.y, 1),
                       "embank_m": round(float(embank), 2), "added": bool(blocked)}
                if blocked:
                    e1 = fl.interpolate(max(chain - 30, 0))
                    e2 = fl.interpolate(min(chain + 30, fl.length))
                    i1, j1 = int((e1.x - left) / a), int((e1.y - top) / e)
                    i2, j2 = int((e2.x - left) / a), int((e2.y - top) / e)
                    if (0 <= i1 < nx and 0 <= j1 < ny and 0 <= i2 < nx
                            and 0 <= j2 < ny and (i1, j1) != (i2, j2)):
                        culverts.append((i1, j1, i2, j2, 1.5))
                    else:
                        row["added"] = False
                        row["skip"] = "endpoint outside grid"
                log_rows.append(row)
    return culverts, log_rows


def cells_near(mask_arr, transform, lat, lon, radius_m, crs, cap=400):
    xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
    a, _b, left, _d, e, top = transform[:6]
    jj, ii = np.nonzero(mask_arr)
    if not jj.size:
        return np.array([], int), np.array([], int)
    cx = left + (ii + 0.5) * a
    cy = top + (jj + 0.5) * e
    d2 = (cx - xs[0]) ** 2 + (cy - ys[0]) ** 2
    sel = d2 <= radius_m ** 2
    if sel.sum() > cap:
        order = np.argsort(d2[sel])[:cap]
        jj2, ii2 = jj[sel][order], ii[sel][order]
        return jj2, ii2
    return jj[sel], ii[sel]


def crossing_point(class_geoms, other_geoms, near_xy):
    """Nearest intersection point between two geometry sets, as (x, y)."""
    best, best_d = None, float("inf")
    for g1 in class_geoms:
        for g2 in other_geoms:
            inter = g1.intersection(g2)
            if inter.is_empty:
                continue
            pts = [inter] if inter.geom_type == "Point" else \
                list(getattr(inter, "geoms", []))
            for p in pts:
                if p.geom_type != "Point":
                    continue
                d = (p.x - near_xy[0]) ** 2 + (p.y - near_xy[1]) ** 2
                if d < best_d:
                    best, best_d = (p.x, p.y), d
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nest", choices=list(NESTS))
    ap.add_argument("tag", nargs="?", default="B", choices=["A", "B"])
    ap.add_argument("--infil", type=float, default=0.0,
                    help="uniform infiltration rate mm/hr (sensitivity member)")
    ap.add_argument("--hours", type=float, default=26.0,
                    help="sim window cap in hours (extended routing runs)")
    ap.add_argument("--dx", type=float, default=0.0,
                    help="override nest dx (logged prereg amendments only)")
    ap.add_argument("--parent", default="run_qpeB_parent",
                    help="parent run dir supplying boundary stages")
    ap.add_argument("--bcfile", default=None,
                    help="boundary_stages_<name>.json inside --parent "
                         "(reconstructed for a corridor domain)")
    ap.add_argument("--geom-only", action="store_true",
                    help="build terrain/geometry/probes, report, and exit")
    ap.add_argument("--no-drain", action="store_true",
                    help="POST-HOC SENSITIVITY (labeled): disable the scalar "
                         "storm-drain proxy, which linearly bleeds routed "
                         "river water over multi-day windows")
    args = ap.parse_args()
    spec = NESTS[args.nest]
    bbox, dx = spec["bbox"], (args.dx or spec["dx"])
    suffix = f"_I{args.infil:g}" if args.infil else ""
    if args.hours > 26.0:
        suffix += "_ext"
    if args.no_drain:
        suffix += "_nodrain"
    out = os.path.join(HERE, f"run_nest_{args.nest}_{args.tag}{suffix}")

    # --- terrain ------------------------------------------------------------
    inv = json.load(open(os.path.join(HERE, "dem1m", "inventory.json")))
    tkey = spec["tiles_from"]
    tiles = [t["path"] for t in inv["tiles"] if tkey in t["box_membership"]]
    # East sliver of the amended pataskala box may reach into buckeye's tiles.
    if tkey == "pataskala":
        tiles += [t["path"] for t in inv["tiles"]
                  if "buckeye" in t["box_membership"] and t["path"] not in tiles]
    t0 = time.time()
    grid = DEMSource(tiles, target_dx_m=dx, aoi_bounds=bbox,
                     max_cells=5_000_000).load()
    ny, nx = grid.ny, grid.nx
    zarr = np.asarray(grid.z)
    gt = grid.transform
    print(f"[{args.nest}] grid {nx}x{ny} = {nx*ny/1e6:.2f}M @ {dx:g} m "
          f"[{grid.crs}] (ingest {time.time()-t0:.0f}s)", flush=True)

    # --- hydraulic geometry -------------------------------------------------
    t0 = time.time()
    pad = 0.01
    fbbox = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    roads = load_roads(fbbox, grid.crs)
    flowlines = load_flowlines(spec["hu8s"], fbbox, grid.crs)
    class_geoms = {}
    for cls, g in roads:
        class_geoms.setdefault(cls, []).append(g)
        class_geoms.setdefault("any", []).append(g)
    chan_mask = burn(flowlines, gt, (ny, nx))
    road_mask = burn([g for _c, g in roads], gt, (ny, nx))
    man = np.full((ny, nx), 0.05)
    man[chan_mask] = 0.035
    man[road_mask] = 0.013
    grid.manning = man.tolist()
    culverts, culvert_log = find_culverts(roads, flowlines, zarr, gt, dx)
    grid.connections = culverts
    n_blocked = sum(1 for r in culvert_log if r["added"])
    print(f"[{args.nest}] roads {len(roads)} segs, flowlines {len(flowlines)}; "
          f"crossings {len(culvert_log)}: {n_blocked} culverted, "
          f"{len(culvert_log)-n_blocked} open/bridge "
          f"(geom {time.time()-t0:.0f}s)", flush=True)

    # --- probes -------------------------------------------------------------
    class_masks = {c: burn(gs, gt, (ny, nx)) for c, gs in class_geoms.items()}
    groups, probe_meta = {}, {}
    for name, kind, arg, lat, lon, radius in PROBES[spec["probes_from"]]:
        if kind == "road":
            m = class_masks.get(arg)
            if m is None or not m.any():
                print(f"[{args.nest}] probe {name}: class {arg} absent", flush=True)
                continue
            jj, ii = cells_near(m, gt, lat, lon, radius, grid.crs)
        elif kind == "channel":
            jj, ii = cells_near(chan_mask, gt, lat, lon, radius, grid.crs)
        else:  # crossing / crossing_road
            xs, ys = warp_transform("EPSG:4326", grid.crs, [lon], [lat])
            others = flowlines if kind == "crossing" else \
                class_geoms.get(arg[1], [])
            cg = class_geoms.get(arg if kind == "crossing" else arg[0], [])
            pt = crossing_point(cg, others, (xs[0], ys[0]))
            if pt is None:
                print(f"[{args.nest}] probe {name}: no crossing found", flush=True)
                continue
            base = class_masks.get(arg if kind == "crossing" else arg[0])
            lon2, lat2 = warp_transform(grid.crs, "EPSG:4326", [pt[0]], [pt[1]])
            lat, lon = lat2[0], lon2[0]
            jj, ii = cells_near(base, gt, lat, lon, radius, grid.crs)
        if not jj.size:
            print(f"[{args.nest}] probe {name}: 0 cells", flush=True)
            continue
        groups[name] = (jj, ii)
        probe_meta[name] = {"lat": lat, "lon": lon, "radius_m": radius,
                            "n_cells": int(jj.size)}
    os.makedirs(out, exist_ok=True)
    probes = Probes(groups, interval_s=60.0,
                    autodump_path=os.path.join(out, "probes.json"),
                    autodump_every=30,
                    meta={"points": probe_meta, "t0_utc": "2026-08-19T18:00:00Z",
                          "thresholds_m": {"caution": 0.15, "impassable": 0.30},
                          "partial": True})
    print(f"[{args.nest}] probes: " +
          ", ".join(f"{k}({v['n_cells']})" for k, v in probe_meta.items()),
          flush=True)
    if args.geom_only:
        print(f"[{args.nest}] geom-only smoke complete", flush=True)
        return 0

    # --- rain ---------------------------------------------------------------
    npz = os.path.join(HERE, "qpe", f"fields_{args.tag}.npz")
    intervals, q_transform, q_shape = intervals_from_npz(npz)
    idx_map = build_idx_map(gt, grid.crs, ny, nx, q_transform, q_shape)
    series = RainSeries(intervals, idx_map, (ny, nx))
    means = [(a2, b2, float(f.mean())) for a2, b2, f in intervals]
    wet = [r for r in means if r[2] > 0.05]
    t_end = (wet[-1][1] if wet else means[-1][1]) + 4 * 3600.0
    if args.hours > 26.0:
        t_end = args.hours * 3600.0   # extended routing window (prereg amendment)
    t_end = min(t_end, args.hours * 3600.0)

    # --- infiltration sensitivity ------------------------------------------
    if args.infil > 0:
        rate = args.infil / 1000.0 / 3600.0
        grid.infiltration_rate = [[rate] * nx for _ in range(ny)]

    # --- parent stage BC ----------------------------------------------------
    stage_bc = None
    brec_path = os.path.join(HERE, args.parent,
                             args.bcfile or "boundary_stages.json")
    if os.path.exists(brec_path):
        t0 = time.time()
        brec = json.load(open(brec_path))
        gkey = args.nest if args.nest in brec["groups"] else \
            next(iter(brec["groups"]))
        grp = brec["groups"][gkey]
        pgrid = DEMSource(PARENT_TILES, target_dx_m=60.0, aoi_bounds=PARENT_AOI,
                          max_cells=4_000_000).load()
        pz = np.asarray(pgrid.z)
        pa, _pb, pleft, _pd, pe, ptop = pgrid.transform[:6]
        pj = np.array(grp["j"]); pi = np.array(grp["i"])
        px = pleft + (pi + 0.5) * pa
        py = ptop + (pj + 0.5) * pe
        stages = np.array(grp["stage_m"])              # (T, nrec)
        parent_z_rec = pz[pj, pi]
        # nest edge ring cells
        mask = np.asarray(grid.mask, dtype=bool)
        ej, ei = [], []
        for i in range(nx):
            for j in (0, ny - 1):
                if mask[j, i]:
                    ej.append(j); ei.append(i)
        for j in range(1, ny - 1):
            for i in (0, nx - 1):
                if mask[j, i]:
                    ej.append(j); ei.append(i)
        ej = np.array(ej); ei = np.array(ei)
        a1, _b1, left1, _d1, e1, top1 = gt[:6]
        ex = left1 + (ei + 0.5) * a1
        ey = top1 + (ej + 0.5) * e1
        nn = cKDTree(np.c_[px, py]).query(np.c_[ex, ey])[1]
        stage_bc = StageBC(ej, ei, brec["t_s"], stages[:, nn],
                           parent_z=parent_z_rec[nn])
        del pgrid, pz
        print(f"[{args.nest}] stage BC: {ej.size} edge cells from "
              f"{pj.size} parent perimeter cells ({time.time()-t0:.0f}s)",
              flush=True)
    else:
        print(f"[{args.nest}] WARNING: no parent boundary record; edges OPEN only",
              flush=True)

    # --- run ----------------------------------------------------------------
    peak_rate = max(m[2] / ((m[1] - m[0]) / 3600.0) for m in means)
    storm = StormConfig(rainfall_mm_per_hr=round(peak_rate, 2),
                        duration_hours=t_end / 3600.0,
                        drainage_capacity_mm_per_hr=0.0 if args.no_drain else 10.0,
                        drainage_blockage=0.5)
    config = SimConfig(
        storm=storm,
        solver=SolverConfig(cfl=0.7, total_time_s=t_end,
                            output_interval_s=3600.0),
        aoi_name=(f"{args.nest} nest — Aug 19-20 2026 — MRMS QPE-{args.tag}"
                  f"{' — infil ' + str(args.infil) + 'mm/h' if args.infil else ''}"
                  f" — {dx:g} m LiDAR"),
    )
    nodes = _auto_sink_nodes(grid, count=6)
    undo = patch_make_solver(rain_series=series, stage_bc=stage_bc,
                             probes=probes)
    try:
        sc = Scenario(grid=grid, config=config, nodes=nodes)
        t0 = time.time()
        man_out = run_scenario(sc, out)
        print(f"[{args.nest}] solve {(time.time()-t0)/60:.1f} min: "
              f"{man_out['frame_count']} frames, peak {man_out['peak_depth_m']} m,"
              f" run_id {man_out['run_id']}", flush=True)
    finally:
        undo()

    probes.dump(os.path.join(out, "probes.json"),
                meta={"points": probe_meta, "t0_utc": "2026-08-19T18:00:00Z",
                      "thresholds_m": {"caution": 0.15, "impassable": 0.30}})
    with open(os.path.join(out, "culverts.json"), "w") as f:
        json.dump({"cd_area_m2": 1.5, "embank_threshold_m": 1.0,
                   "crossings": culvert_log}, f, indent=2)
    with open(os.path.join(out, "georef.json"), "w") as f:
        json.dump({"transform": list(gt[:6]), "crs": str(grid.crs),
                   "nx": nx, "ny": ny, "dx": dx, "bbox_wgs84": list(bbox),
                   "qpe_tag": args.tag, "infil_mm_hr": args.infil,
                   "buildings": "none (footprint sources egress-blocked)",
                   "bc_source": os.path.join(args.parent,
                                             args.bcfile or "boundary_stages.json"),
                   "domain_role": "corridor" if args.nest.endswith("_c") else "wide",
                   "run_id": man_out["run_id"]}, f, indent=2)
    print(f"[{args.nest}] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
