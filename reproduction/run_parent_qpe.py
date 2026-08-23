#!/usr/bin/env python3
"""Parent 60 m Columbus rerun forced by real MRMS QPE (side task, Phase 2).

Usage: python3 run_parent_qpe.py A|B [dx]
  A = RadarOnly QPE (operational replay)   -> run_qpeA_parent/
  B = MultiSensor Pass2 (retrospective)    -> run_qpeB_parent/

Same domain/terrain/drainage as the frozen uniform runs (run_mid/run_low —
untouched); the only change is rainfall: spatial+temporal MRMS fields.
Infiltration: I0 = 0 (saturated antecedent; ensemble variants run separately).

Extras recorded for the nests and the timing analysis:
  * boundary_stages.json — water-surface elevation along each nest's bbox
    perimeter (parent cells) every 300 s -> Dirichlet BC for nested runs;
  * probes.json — depth every 60 s at gauge cells (if gauges/gauge_summary.json
    exists) and at fixed infrastructure points (I-70/SR-79, US-40 Etna,
    Pataskala Main St, Franklinton W Broad) -> threshold-crossing times.
"""

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.ingestion.dem import DEMSource
from aqua_sim.scenario import Scenario, _auto_sink_nodes, run_scenario

from prep_qpe import intervals_from_npz
from qpe_solver import Probes, RainSeries, build_idx_map, last_solver, patch_make_solver
from run_columbus import AOI, TILES

NESTS = json.load(open(os.path.join(HERE, "nest_prereg.json")))["nests"]
NEST_BBOXES = {k: v["bbox_wgs84"] for k, v in NESTS.items()}
NEST_BBOXES["buckeye"] = [-82.53, 39.905, -82.44, 39.965]   # amended (compute)

#: Fixed infrastructure probe points (cause-side geometry, not tuned).
PROBE_POINTS = {
    "i70_sr79_sf_licking": (39.9345, -82.4840),
    "us40_etna": (39.9573, -82.6829),
    "pataskala_main_broad": (39.9895, -82.6740),
    "franklinton_wbroad": (39.9585, -83.0500),
}


def ll_to_ji(grid, lat, lon):
    from rasterio.warp import transform as wt
    xs, ys = wt("EPSG:4326", grid.crs, [lon], [lat])
    a, _b, left, _d, e, top = grid.transform[:6]
    i = int((xs[0] - left) / a)
    j = int((ys[0] - top) / e)
    return j, i


def bbox_perimeter_cells(grid, bbox):
    from rasterio.warp import transform as wt
    w, s, e_, n = bbox
    xs, ys = wt("EPSG:4326", grid.crs, [w, e_], [s, n])
    a, _b, left, _d, e, top = grid.transform[:6]
    i0 = max(int((xs[0] - left) / a), 0)
    i1 = min(int((xs[1] - left) / a), grid.nx - 1)
    j0 = max(int((ys[1] - top) / e), 0)          # north edge -> smaller j
    j1 = min(int((ys[0] - top) / e), grid.ny - 1)
    js, is_ = [], []
    for i in range(i0, i1 + 1):
        js += [j0, j1]; is_ += [i, i]
    for j in range(j0 + 1, j1):
        js += [j, j]; is_ += [i0, i1]
    return np.array(js), np.array(is_)


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "B"
    dx = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    cap_h = float(sys.argv[3]) if len(sys.argv) > 3 else 26.0
    npz = os.path.join(HERE, "qpe", f"fields_{tag}.npz")
    out = os.path.join(HERE, f"run_qpe{tag}_parent"
                       + ("" if cap_h <= 26.0 else "_ext"))

    t0 = time.time()
    grid = DEMSource(TILES, target_dx_m=dx, aoi_bounds=AOI,
                     max_cells=4_000_000).load()
    ny, nx = grid.ny, grid.nx
    print(f"[{tag}] grid {nx}x{ny} @ {dx:.0f} m [{grid.crs}] "
          f"(ingest {time.time()-t0:.0f}s)", flush=True)

    intervals, qpe_transform, qpe_shape = intervals_from_npz(npz)
    idx_map = build_idx_map(grid.transform, grid.crs, ny, nx,
                            qpe_transform, qpe_shape)
    series = RainSeries(intervals, idx_map, (ny, nx))

    # Sim window from the QPE itself: end = last interval whose AOI-crop mean
    # exceeds 0.05 mm, + 4 h drain-down (t=0 is 2026-08-19T18:00Z).
    means = [(t0i, t1i, float(f.mean())) for t0i, t1i, f in intervals]
    wet = [r for r in means if r[2] > 0.05]
    t_end = (wet[-1][1] if wet else means[-1][1]) + 4 * 3600.0
    if cap_h > 26.0:
        t_end = cap_h * 3600.0        # extended routing run (see prereg amendment)
    t_end = min(t_end, cap_h * 3600.0)
    peak_rate = max((m[2] / ((m[1] - m[0]) / 3600.0)) for m in means)
    print(f"[{tag}] window 0..{t_end/3600:.1f} h; AOI-crop peak interval rate "
          f"{peak_rate:.1f} mm/h", flush=True)

    storm = StormConfig(
        rainfall_mm_per_hr=round(peak_rate, 2),      # headline/label only
        duration_hours=t_end / 3600.0,
        drainage_capacity_mm_per_hr=10.0,
        drainage_blockage=0.5,
    )
    config = SimConfig(
        storm=storm,
        solver=SolverConfig(cfl=0.7, total_time_s=t_end,
                            output_interval_s=1800.0),
        aoi_name=(f"Greater Columbus OH — Aug 19-20 2026 — MRMS QPE-{tag} "
                  f"forcing — screening {dx:.0f} m"),
    )
    nodes = _auto_sink_nodes(grid, count=10)

    record_cells = {name: bbox_perimeter_cells(grid, bbox)
                    for name, bbox in NEST_BBOXES.items()}
    groups = {}
    for name, (lat, lon) in PROBE_POINTS.items():
        j, i = ll_to_ji(grid, lat, lon)
        groups[name] = (np.array([j]), np.array([i]))
    gsum_path = os.path.join(HERE, "gauges", "gauge_summary.json")
    if os.path.exists(gsum_path):
        for gsite in json.load(open(gsum_path)):
            try:
                j, i = ll_to_ji(grid, float(gsite["lat"]), float(gsite["lon"]))
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= j < ny and 0 <= i < nx:
                groups[f"gauge_{gsite['site_no']}"] = (np.array([j]), np.array([i]))
    probes = Probes(groups, interval_s=60.0)

    undo = patch_make_solver(rain_series=series, probes=probes,
                             record_cells=record_cells, record_interval_s=300.0)
    try:
        sc = Scenario(grid=grid, config=config, nodes=nodes)
        t0 = time.time()
        man = run_scenario(sc, out)
        print(f"[{tag}] solve {(time.time()-t0)/60:.1f} min: "
              f"{man['frame_count']} frames, peak {man['peak_depth_m']} m, "
              f"run_id {man['run_id']}", flush=True)
    finally:
        undo()

    sol = last_solver()
    sol.dump_boundary_record(os.path.join(out, "boundary_stages.json"))
    probes.dump(os.path.join(out, "probes.json"),
                meta={"points": PROBE_POINTS, "t0_utc": "2026-08-19T18:00:00Z"})
    d = np.load(npz)
    with open(os.path.join(out, "qpe_provenance.json"), "w") as f:
        json.dump({"product_tag": tag, "npz": os.path.basename(npz),
                   "n_fields": int(d["accum_mm"].shape[0]),
                   "cadence_s": float(d["cadence_s"][0]),
                   "t0_utc": str(d["t0_utc"][0]),
                   "sha256": [str(s) for s in d["sha256"]],
                   "run_id": man["run_id"]}, f, indent=2)
    print(f"[{tag}] boundary stages + probes + provenance written to {out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
