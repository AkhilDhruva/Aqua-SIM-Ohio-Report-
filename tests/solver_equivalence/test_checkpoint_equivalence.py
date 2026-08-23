#!/usr/bin/env python3
"""Wet-phase checkpoint/resume equivalence test.

Proves that a restart DURING active physics — spatial QPE rain, wet/dry
transitions, Dirichlet stage BC, culvert transfer, cumulative infiltration,
scalar drainage, small CFL steps — reproduces the uninterrupted solution
exactly, using the PRODUCTION save_ckpt / load_ckpt / step_loop code paths
from run_corridor.py.

  A  uninterrupted        0 -> 2 h
  B  interrupted          0 -> 50 min, save_ckpt, FRESH solver, load_ckpt,
                          50 min -> 2 h
     (50 min = a checkpoint-grid line in mid-storm: rain active, cells wet,
      culvert transferring, infiltration accumulating)

Compared bitwise: depth, qx, qy, peak field, cumulative infiltration, probe
times and every probe record, total volume. Pass criterion: hash-identical.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.grid import Grid
from aqua_sim.physics.boundary import BoundaryType

from qpe_solver import Probes, QPESolver, RainSeries, StageBC
from run_corridor import load_ckpt, save_ckpt, step_loop

NX, NY, DX = 48, 40, 10.0
T_END = 7200.0
T_CUT = 3000.0        # mid-storm, on the 600 s checkpoint grid


def build_grid():
    g = Grid.empty(NX, NY, DX)
    rng = np.random.default_rng(11)
    for y in range(NY):
        for x in range(NX):
            # west-high plane with a channel along row 20 and a road
            # embankment along column 30 crossing it
            z = 8.0 - 0.12 * x + 0.4 * rng.random()
            if y == 20:
                z -= 1.5                      # channel
            if x == 30 and y != 99:
                z += 2.0                      # embankment (blocks the channel)
            g.z[y][x] = z
    g.infiltration_rate = [[2.0e-6] * NX for _ in range(NY)]
    g.infiltration_capacity = [[0.02] * NX for _ in range(NY)]
    g.connections = [(28, 20, 32, 20, 0.8)]   # culvert through the embankment
    return g


def build_solver():
    g = build_grid()
    # spatial rain: heavy north-west quadrant, light elsewhere; two intervals
    native0 = np.array([[40.0, 10.0], [10.0, 4.0]])   # mm over 0-1800 s
    native1 = np.array([[25.0, 6.0], [6.0, 2.0]])     # mm over 1800-3600 s
    idx = np.zeros(NY * NX, np.int64)
    for j in range(NY):
        for i in range(NX):
            idx[j * NX + i] = (0 if j < 20 else 1) * 2 + (0 if i < 24 else 1)
    series = RainSeries([(0.0, 1800.0, native0), (1800.0, 3600.0, native1)],
                        idx, (NY, NX))
    # stage BC on the east edge: rises then holds, gated by a fake parent bed
    ej = np.arange(NY); ei = np.full(NY, NX - 1)
    stages = np.array([[2.0] * NY, [4.5] * NY, [4.5] * NY])
    bc = StageBC(ej, ei, [0.0, 2400.0, T_END], stages,
                 parent_z=np.full(NY, 3.0))
    probes = Probes({"chan": (np.full(6, 20), np.arange(24, 30)),
                     "road": (np.arange(14, 20), np.full(6, 30))},
                    interval_s=60.0)
    cfg = SimConfig(
        storm=StormConfig(rainfall_mm_per_hr=80.0, duration_hours=1.0,
                          drainage_capacity_mm_per_hr=6.0,
                          drainage_blockage=0.5),
        solver=SolverConfig(cfl=0.7, total_time_s=T_END,
                            output_interval_s=3600.0),
        aoi_name="ckpt-equivalence")
    s = QPESolver(g, cfg, BoundaryType.OPEN, rain_series=series,
                  stage_bc=bc, probes=probes)
    return s, probes


def run_A():
    s, probes = build_solver()
    peak = np.zeros((NY, NX))
    peak, snaps, snap_t = step_loop(s, peak, probes, [], [], T_END,
                                    ckpt_path=None)
    return s, probes, peak


def run_B(tmp="ckpt_equiv_test.npz"):
    s1, probes1 = build_solver()
    peak = np.zeros((NY, NX))
    peak, snaps, snap_t = step_loop(s1, peak, probes1, [], [], T_CUT,
                                    ckpt_path=None)
    assert s1.h.max() > 0.05, "interruption point is not wet — test misbuilt"
    assert s1._cum_infil is not None and s1._cum_infil.max() > 0, \
        "no cumulative infiltration at cut — test misbuilt"
    save_ckpt(tmp, s1, peak, probes1, snaps, snap_t)
    del s1
    s2, probes2 = build_solver()          # FRESH process-equivalent state
    peak2, snaps2, snap_t2 = load_ckpt(tmp, s2, probes2)
    peak2, snaps2, snap_t2 = step_loop(s2, peak2, probes2, snaps2, snap_t2,
                                       T_END, ckpt_path=None)
    os.remove(tmp)
    return s2, probes2, peak2


def main():
    sA, pA, peakA = run_A()
    sB, pB, peakB = run_B()
    checks = {
        "depth":  float(np.abs(sA.h - sB.h).max()),
        "qx":     float(np.abs(sA.qx - sB.qx).max()),
        "qy":     float(np.abs(sA.qy - sB.qy).max()),
        "peak":   float(np.abs(peakA - peakB).max()),
        "cum_infil": float(np.abs(sA._cum_infil - sB._cum_infil).max()),
        "volume": abs(float(sA.h.sum() - sB.h.sum())),
    }
    same_t = pA.t == pB.t
    same_rec = pA.records == pB.records
    wet_frac = float((sA.h > 0.01).mean())
    print(f"domain {NX}x{NY}, cut at {T_CUT/60:.0f} min "
          f"(wet fraction at end {wet_frac:.2f}, "
          f"peak depth {sA.h.max():.3f} m)")
    for k, v in checks.items():
        print(f"  max|A-B| {k:<10} = {v:.3e}")
    print(f"  probe times identical:   {same_t} ({len(pA.t)} samples)")
    print(f"  probe records identical: {same_rec}")
    ok = all(v == 0.0 for v in checks.values()) and same_t and same_rec
    print("RESULT:", "BIT-IDENTICAL — checkpoint/resume is exact in the wet "
          "code path" if ok else "MISMATCH — checkpoint is NOT faithful")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
