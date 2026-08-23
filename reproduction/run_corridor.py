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
import argparse, json, math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.physics.boundary import BoundaryType
from prep_qpe import intervals_from_npz
from qpe_solver import Probes, QPESolver, RainSeries, StageBC, build_idx_map
import run_nest as RN

CKPT_EVERY_S = 600.0        # model-second checkpoint GRID (absolute-aligned)
CKPT_WALL_S = 60.0          # ...but never lose more than this much wall time.
#: The host recycles as often as every 1-2 minutes. At 420 s this produced a
#: LIVELOCK: every process died before its first checkpoint, so the run
#: resumed from the same model hour indefinitely (observed: 37 min, three
#: relaunches, zero progress). The interval must be shorter than the host's
#: shortest lifetime, not merely shorter than its average.
SNAP_EVERY_S = 3600.0


def atomic_savez(path, **kw):
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, **kw)
    os.replace(tmp, path)




def save_ckpt(path, solver, peak, probes, snaps, snap_t):
    """Checkpoint EVERY stateful quantity carried across steps.

    Audited against NumpyShallowWaterSolver/QPESolver: h, qx, qy, time, CFL
    bookkeeping (_max_h, _max_face_v), cumulative infiltration, running peak,
    snapshots, and the probe scheduler INCLUDING its _next deadline (restoring
    it as time+interval can skip a sample and shift the probe grid). RainSeries
    interval cache, StageBC interpolation, culvert transfers and scalar
    drainage are stateless or deterministic in model time — not duplicated.
    """
    kw = {f"snap{i}": s for i, s in enumerate(snaps)}
    atomic_savez(path, h=solver.h, qx=solver.qx, qy=solver.qy,
                 t=np.array([solver.time_s]), peak=peak,
                 mx=np.array([solver._max_h]),
                 mv=np.array([solver._max_face_v]),
                 shape=np.array(list(solver.h.shape)),
                 pt=np.array(probes.t),
                 pr=np.array([json.dumps(probes.records)]),
                 pn=np.array([probes._next]),
                 snap_t=np.array(snap_t, dtype=float),
                 **({"ci": solver._cum_infil}
                    if solver._cum_infil is not None else {}),
                 **kw)


def load_ckpt(path, solver, probes):
    """Restore save_ckpt output; returns (peak, snaps, snap_t) or None."""
    if not os.path.exists(path):
        return None
    d = np.load(path, allow_pickle=True)
    if tuple(d["shape"]) != tuple(solver.h.shape):
        return None
    solver.h = d["h"]; solver.qx = d["qx"]; solver.qy = d["qy"]
    solver.time_s = float(d["t"][0])
    solver._max_h = float(d["mx"][0])
    solver._max_face_v = float(d["mv"][0])
    if solver._cum_infil is not None and "ci" in d:
        solver._cum_infil = d["ci"]
    probes.t = list(d["pt"])
    probes.records = json.loads(str(d["pr"][0]))
    probes._next = float(d["pn"][0]) if "pn" in d \
        else solver.time_s + probes.interval_s
    snap_t = list(d["snap_t"]) if "snap_t" in d else []
    snaps = [d[f"snap{i}"] for i in range(len(snap_t))]
    return d["peak"], snaps, snap_t


def _grid_next(t, step):
    return (math.floor(t / step + 1e-9) + 1) * step


def step_loop(solver, peak, probes, snaps, snap_t, t_end, ckpt_path=None,
              log_prefix="", wall_ckpt_s=CKPT_WALL_S):
    """Deterministic stepping loop shared by production runs and the
    checkpoint-equivalence test.

    dt is clipped ONLY by boundaries fixed in MODEL time (the absolute
    CKPT_EVERY_S grid, the snapshot grid, t_end), so the step sequence is
    identical whether or not the run was ever interrupted. Wall-clock pressure
    saves AFTER whichever step is in flight completes, without clipping dt, so
    it cannot perturb the solution either.
    """
    next_ck = _grid_next(solver.time_s, CKPT_EVERY_S)
    next_sn = _grid_next(solver.time_s, SNAP_EVERY_S)
    wall_last = wall0 = time.time()
    while solver.time_s < t_end - 1e-9:
        dt = min(solver.adaptive_dt(), t_end - solver.time_s,
                 next_ck - solver.time_s, next_sn - solver.time_s)
        if dt <= 0:
            break
        solver.step(dt)
        np.maximum(peak, solver.h, out=peak)
        if solver.time_s >= next_sn - 1e-9:
            snaps.append(np.round(solver.h, 3).astype(np.float32))
            snap_t.append(solver.time_s)
            next_sn = _grid_next(solver.time_s, SNAP_EVERY_S)
        due_model = solver.time_s >= next_ck - 1e-9
        due_wall = ckpt_path is not None and \
            (time.time() - wall_last) >= wall_ckpt_s
        if due_model or due_wall:
            if ckpt_path is not None:
                save_ckpt(ckpt_path, solver, peak, probes, snaps, snap_t)
                wall_last = time.time()
                print(f"{log_prefix} h={solver.time_s/3600:5.2f}  "
                      f"peak={peak.max():5.2f} m  "
                      f"wall={(time.time()-wall0)/60:5.1f}m"
                      + ("  [wall-ckpt]" if (due_wall and not due_model) else ""),
                      flush=True)
            if due_model:
                next_ck = _grid_next(solver.time_s, CKPT_EVERY_S)
    return peak, snaps, snap_t




def _setup_cache_path(out):
    return os.path.join(out, "setup_cache.npz")


def save_setup(out, grid, culverts, groups, pmeta, idx_map, bc):
    """Cache everything expensive to rebuild: nest terrain, roughness, culverts,
    probe indices, the rain index map and the parent-derived stage BC.

    Under a host that recycles every few minutes, reconstructing this from
    LiDAR + shapefiles + the parent DEM (~50 s) dominated each short process
    lifetime. It is a pure function of the frozen inputs, so caching it changes
    no result — only start-up cost.
    """
    kw = dict(z=np.asarray(grid.z, float), manning=np.asarray(grid.manning, float),
              mask=np.asarray(grid.mask, bool), obstacle=np.asarray(grid.obstacle, float),
              transform=np.array(grid.transform[:6], float),
              dims=np.array([grid.nx, grid.ny]), dx=np.array([grid.dx]),
              crs=np.array([str(grid.crs)]),
              culverts=np.array(culverts, dtype=float).reshape(-1, 5),
              idx_map=np.asarray(idx_map, np.int64),
              group_names=np.array(list(groups)),
              pmeta=np.array([json.dumps(pmeta)]))
    for k, (j, i) in groups.items():
        kw[f"gj_{k}"] = np.asarray(j); kw[f"gi_{k}"] = np.asarray(i)
    if bc is not None:
        kw.update(bc_j=bc.j, bc_i=bc.i, bc_t=bc.times, bc_s=bc.stages,
                  bc_pz=bc.parent_z)
    atomic_savez(_setup_cache_path(out), **kw)


def load_setup(out):
    """Rebuild (grid, culverts, groups, pmeta, idx_map, bc) from the cache."""
    p = _setup_cache_path(out)
    if not os.path.exists(p):
        return None
    from aqua_sim.grid import Grid
    d = np.load(p, allow_pickle=False)
    nx, ny = (int(v) for v in d["dims"])
    g = Grid.empty(nx, ny, float(d["dx"][0]))
    g.z = d["z"].tolist(); g.manning = d["manning"].tolist()
    g.mask = d["mask"].tolist(); g.obstacle = d["obstacle"].tolist()
    g.transform = tuple(float(v) for v in d["transform"])
    g.crs = str(d["crs"][0])
    culverts = [(int(a), int(b), int(c), int(e), float(f))
                for a, b, c, e, f in d["culverts"]]
    g.connections = culverts
    groups = {str(k): (d[f"gj_{k}"], d[f"gi_{k}"]) for k in d["group_names"]}
    pmeta = json.loads(str(d["pmeta"][0]))
    bc = None
    if "bc_j" in d:
        bc = StageBC(d["bc_j"], d["bc_i"], d["bc_t"], d["bc_s"],
                     parent_z=d["bc_pz"])
    return g, culverts, groups, pmeta, d["idx_map"], bc


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

    # ---- setup: from cache when available (see save_setup docstring) ----
    t0 = time.time()
    cached = load_setup(out)
    if cached is not None:
        grid, culverts, groups, pmeta, idx_map, stage_bc = cached
        ny, nx = grid.ny, grid.nx
        gt = grid.transform
        culvert_log = []
        if a.infil > 0:
            rate = a.infil / 1000.0 / 3600.0
            grid.infiltration_rate = [[rate] * nx for _ in range(ny)]
        print(f"[{a.nest}] setup from cache: {nx}x{ny} @ {spec['dx']:g} m, "
              f"{len(culverts)} culverts, {len(groups)} probe groups "
              f"({time.time()-t0:.1f}s)", flush=True)
        probes = Probes(groups, interval_s=60.0,
                        autodump_path=os.path.join(out, "probes.json"),
                        autodump_every=20,
                        meta={"points": pmeta, "t0_utc": "2026-08-19T18:00:00Z",
                              "thresholds_m": {"caution": 0.15, "impassable": 0.30}})
        intervals, qtr, qsh = intervals_from_npz(
            os.path.join(HERE, "qpe", f"fields_{a.tag}.npz"))
        series = RainSeries(intervals, idx_map, (ny, nx))
        means = [(x, y, float(f.mean())) for x, y, f in intervals]
        peak_rate = max(m[2] / ((m[1] - m[0]) / 3600.0) for m in means)
        t_end = a.hours * 3600.0
    else:
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
        idx_map = build_idx_map(gt, grid.crs, ny, nx, qtr, qsh)
        series = RainSeries(intervals, idx_map, (ny, nx))
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

        save_setup(out, grid, culverts, groups, pmeta, idx_map, stage_bc)
        print(f"[{a.nest}] setup cached for future restarts", flush=True)

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
    restored = load_ckpt(ck, solver, probes)
    if restored is not None:
        peak, snaps, snap_t = restored
        print(f"[{a.nest}] RESUMED at model hour {solver.time_s/3600:.2f} "
              f"({len(probes.t)} probe samples)", flush=True)

    peak, snaps, snap_t = step_loop(solver, peak, probes, snaps, snap_t, t_end,
                                    ckpt_path=ck, log_prefix=f"[{a.nest}]")
    save_ckpt(ck, solver, peak, probes, snaps, snap_t)
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
