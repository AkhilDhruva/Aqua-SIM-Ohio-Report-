#!/usr/bin/env python3
"""Restart-resilient corridor nest runner (side task, Phase 2).

The execution container recycles every few hours, killing any long solve. This
runner therefore CHECKPOINTS solver state to a single .npz and resumes from it
automatically, so progress survives a restart. It also drops the streaming
frame-writer (27 x 20-50 MB JSONs) in favour of what the analysis actually
needs: the 60 s probe series, a running peak-depth field, and a few snapshots.

Usage: python3 run_corridor.py <nest> [B|A] [--hours H] [--parent DIR]
                               [--bcfile F] [--infil MM_HR] [--no-drain]

Outputs into corridor_<nest>_<tag><suffix>/:
    state.npz      checkpoint (h, qx, qy, t, peak, probe history)  [atomic]
    probes.json    60 s depth series per probe group
    peak.npz       running peak depth + grid georeference
    snaps.npz      depth snapshots at ~hourly model times
    meta.json      provenance, geometry counts, culvert log
No repo files are touched.
"""
import argparse, json, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.physics.boundary import BoundaryType
from prep_qpe import intervals_from_npz
from qpe_solver import Probes, QPESolver, RainSeries, StageBC, build_idx_map
import run_nest as RN

CKPT_EVERY_S = 600.0        # model seconds between checkpoints
SNAP_EVERY_S = 3600.0


def atomic_savez(path, **kw):
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, **kw)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nest", choices=list(RN.NESTS))
    ap.add_argument("tag", nargs="?", default="B", choices=["A", "B"])
    ap.add_argument("--hours", type=float, default=20.0)
    ap.add_argument("--parent", default="run_qpeB_parent")
    ap.add_argument("--bcfile", default=None)
    ap.add_argument("--infil", type=float, default=0.0)
    ap.add_argument("--no-drain", action="store_true")
    a = ap.parse_args()

    suffix = (f"_I{a.infil:g}" if a.infil else "") + ("_nodrain" if a.no_drain else "")
    out = os.path.join(HERE, f"corridor_{a.nest}_{a.tag}{suffix}")
    os.makedirs(out, exist_ok=True)
    spec = RN.NESTS[a.nest]

    # ---- terrain + hydraulic geometry (same construction as run_nest) ----
    t0 = time.time()
    grid, masks, cls_geoms, flowlines = __import__("smearing_analysis").build_nest_context(a.nest)
    ny, nx = grid.ny, grid.nx
    zarr = np.asarray(grid.z)
    gt = grid.transform
    man = np.full((ny, nx), 0.05)
    man[masks["_channel"]] = 0.035
    if "any" in masks:
        man[masks["any"]] = 0.013
    grid.manning = man.tolist()
    roads = [(c, g) for c, gs in cls_geoms.items() if c != "any" for g in gs]
    culverts, culvert_log = RN.find_culverts(roads, flowlines, zarr, gt, spec["dx"])
    grid.connections = culverts
    if a.infil > 0:
        rate = a.infil / 1000.0 / 3600.0
        grid.infiltration_rate = [[rate] * nx for _ in range(ny)]
    print(f"[{a.nest}] grid {nx}x{ny}={nx*ny/1e6:.2f}M @ {spec['dx']:g} m; "
          f"{len(culverts)} culverts ({time.time()-t0:.0f}s)", flush=True)

    # ---- probes ----
    probes_geom = __import__("smearing_analysis").probe_cells(
        a.nest, grid, masks, cls_geoms, flowlines)
    groups, pmeta = {}, {}
    for name, v in probes_geom.items():
        groups[name] = v["road"]
        pmeta[name] = {"lat": v["lat"], "lon": v["lon"],
                       "n_cells": int(v["road"][0].size), "kind": "road_or_crossing"}
        cj, ci = v["channel"]
        if cj.size:
            groups[name + "__channel"] = (cj, ci)
            pmeta[name + "__channel"] = {"lat": v["lat"], "lon": v["lon"],
                                         "n_cells": int(cj.size), "kind": "channel"}
    probes = Probes(groups, interval_s=60.0,
                    autodump_path=os.path.join(out, "probes.json"),
                    autodump_every=20,
                    meta={"points": pmeta, "t0_utc": "2026-08-19T18:00:00Z",
                          "thresholds_m": {"caution": 0.15, "impassable": 0.30}})
    print(f"[{a.nest}] probe groups: {len(groups)}", flush=True)

    # ---- rain ----
    intervals, qtr, qsh = intervals_from_npz(os.path.join(HERE, "qpe", f"fields_{a.tag}.npz"))
    series = RainSeries(intervals, build_idx_map(gt, grid.crs, ny, nx, qtr, qsh), (ny, nx))
    means = [(x, y, float(f.mean())) for x, y, f in intervals]
    peak_rate = max(m[2] / ((m[1] - m[0]) / 3600.0) for m in means)
    t_end = a.hours * 3600.0

    # ---- boundary stage from parent ----
    stage_bc = None
    bcp = os.path.join(HERE, a.parent, a.bcfile or "boundary_stages.json")
    if os.path.exists(bcp):
        from scipy.spatial import cKDTree
        from aqua_sim.ingestion.dem import DEMSource
        from run_columbus import AOI as PAOI, TILES as PTILES
        brec = json.load(open(bcp))
        grp = brec["groups"][next(iter(brec["groups"]))]
        pg = DEMSource(PTILES, target_dx_m=60.0, aoi_bounds=PAOI,
                       max_cells=4_000_000).load()
        pz = np.asarray(pg.z)
        pa, _pb, pl, _pd, pe, pt_ = pg.transform[:6]
        pj, pi = np.array(grp["j"]), np.array(grp["i"])
        px, py = pl + (pi + .5) * pa, pt_ + (pj + .5) * pe
        mask = np.asarray(grid.mask, bool)
        ej, ei = [], []
        for i in range(nx):
            for j in (0, ny - 1):
                if mask[j, i]: ej.append(j); ei.append(i)
        for j in range(1, ny - 1):
            for i in (0, nx - 1):
                if mask[j, i]: ej.append(j); ei.append(i)
        ej, ei = np.array(ej), np.array(ei)
        a1, _b1, l1, _d1, e1, t1 = gt[:6]
        nn = cKDTree(np.c_[px, py]).query(
            np.c_[l1 + (ei + .5) * a1, t1 + (ej + .5) * e1])[1]
        stage_bc = StageBC(ej, ei, brec["t_s"],
                           np.array(grp["stage_m"])[:, nn], parent_z=pz[pj, pi][nn])
        del pg, pz
        print(f"[{a.nest}] stage BC: {ej.size} edge cells", flush=True)

    cfg = SimConfig(
        storm=StormConfig(rainfall_mm_per_hr=round(peak_rate, 2),
                          duration_hours=t_end / 3600.0,
                          drainage_capacity_mm_per_hr=0.0 if a.no_drain else 10.0,
                          drainage_blockage=0.5),
        solver=SolverConfig(cfl=0.7, total_time_s=t_end, output_interval_s=SNAP_EVERY_S),
        aoi_name=f"{a.nest} corridor — MRMS QPE-{a.tag} — {spec['dx']:g} m")
    solver = QPESolver(grid, cfg, BoundaryType.OPEN,
                       rain_series=series, stage_bc=stage_bc, probes=probes)

    # ---- resume ----
    ck = os.path.join(out, "state.npz")
    peak = np.zeros((ny, nx))
    snaps, snap_t = [], []
    if os.path.exists(ck):
        d = np.load(ck, allow_pickle=True)
        if tuple(d["shape"]) == (ny, nx):
            solver.h = d["h"]; solver.qx = d["qx"]; solver.qy = d["qy"]
            solver.time_s = float(d["t"][0])
            solver._max_h = float(d["mx"][0]); solver._max_face_v = float(d["mv"][0])
            if solver._cum_infil is not None and "ci" in d:
                solver._cum_infil = d["ci"]
            peak = d["peak"]
            probes.t = list(d["pt"])
            probes.records = json.loads(str(d["pr"][0]))
            probes._next = solver.time_s + 60.0
            snap_t = list(d["snap_t"]) if "snap_t" in d else []
            snaps = [d[f"snap{i}"] for i in range(len(snap_t))]
            print(f"[{a.nest}] RESUMED at model hour {solver.time_s/3600:.2f} "
                  f"({len(probes.t)} probe samples)", flush=True)

    def save():
        kw = {f"snap{i}": s for i, s in enumerate(snaps)}
        atomic_savez(ck, h=solver.h, qx=solver.qx, qy=solver.qy,
                     t=np.array([solver.time_s]), peak=peak,
                     mx=np.array([solver._max_h]), mv=np.array([solver._max_face_v]),
                     shape=np.array([ny, nx]), pt=np.array(probes.t),
                     pr=np.array([json.dumps(probes.records)]),
                     snap_t=np.array(snap_t, dtype=float),
                     **({"ci": solver._cum_infil} if solver._cum_infil is not None else {}),
                     **kw)

    next_ck = solver.time_s + CKPT_EVERY_S
    next_sn = (int(solver.time_s / SNAP_EVERY_S) + 1) * SNAP_EVERY_S
    wall = time.time()
    while solver.time_s < t_end:
        dt = min(solver.adaptive_dt(), t_end - solver.time_s,
                 next_ck - solver.time_s, next_sn - solver.time_s)
        if dt <= 0:
            break
        solver.step(dt)
        np.maximum(peak, solver.h, out=peak)
        if solver.time_s >= next_sn - 1e-9:
            snaps.append(np.round(solver.h, 3).astype(np.float32))
            snap_t.append(solver.time_s); next_sn += SNAP_EVERY_S
        if solver.time_s >= next_ck - 1e-9:
            save(); next_ck += CKPT_EVERY_S
            print(f"[{a.nest}] h={solver.time_s/3600:5.2f}  peak={peak.max():5.2f} m  "
                  f"wall={(time.time()-wall)/60:5.1f}m", flush=True)
    save()
    probes.dump(os.path.join(out, "probes.json"), probes.meta)
    atomic_savez(os.path.join(out, "peak.npz"), peak=peak,
                 transform=np.array(gt[:6]), shape=np.array([ny, nx]))
    atomic_savez(os.path.join(out, "snaps.npz"),
                 t=np.array(snap_t, dtype=float),
                 **{f"snap{i}": s for i, s in enumerate(snaps)})
    json.dump({"nest": a.nest, "tag": a.tag, "dx": spec["dx"],
               "bbox": list(spec["bbox"]), "crs": str(grid.crs),
               "transform": list(gt[:6]), "nx": nx, "ny": ny,
               "hours": a.hours, "infil_mm_hr": a.infil, "no_drain": a.no_drain,
               "bc": os.path.basename(bcp) if stage_bc else None,
               "culverts": len(culverts), "culvert_log": culvert_log,
               "peak_depth_m": round(float(peak.max()), 3)},
              open(os.path.join(out, "meta.json"), "w"), indent=2)
    print(f"[{a.nest}] COMPLETE t={solver.time_s/3600:.2f} h peak={peak.max():.2f} m -> {out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
