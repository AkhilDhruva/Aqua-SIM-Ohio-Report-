#!/usr/bin/env python3
"""Correctness anchors for the side-task solver extension.

1. EQUIVALENCE: QPESolver with a uniform constant rain field must reproduce the
   stock NumpyShallowWaterSolver bit-for-bit (bare path AND conditioned path).
2. MASS: spatially varying rain adds exactly the QPE volume (closed basin).
3. STAGE BC: a Dirichlet strip holds its prescribed stage and floods the
   neighborhood; probes record at the requested cadence.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.grid import Grid
from aqua_sim.physics.boundary import BoundaryType
from aqua_sim.physics.swe_numpy import NumpyShallowWaterSolver

from qpe_solver import Probes, QPESolver, RainSeries, StageBC


def bumpy_grid(nx=24, ny=18, dx=10.0, seed=7, conditioned=False):
    rng = np.random.default_rng(seed)
    g = Grid.empty(nx, ny, dx)
    zz = rng.uniform(0.0, 2.0, (ny, nx))
    for y in range(ny):
        for x in range(nx):
            g.z[y][x] = float(zz[y, x])
    if conditioned:
        g.infiltration_rate = [[2.0e-7] * nx for _ in range(ny)]
        g.infiltration_capacity = [[0.005] * nx for _ in range(ny)]
    return g


def cfg(total=1800.0, rain=36.0, drain=5.0):
    return SimConfig(
        storm=StormConfig(rainfall_mm_per_hr=rain, duration_hours=total / 3600.0,
                          drainage_capacity_mm_per_hr=drain, drainage_blockage=0.0),
        solver=SolverConfig(cfl=0.7, total_time_s=total, output_interval_s=total),
        aoi_name="unit")


def run_frames(solver):
    return [np.asarray(s.depth) for s in solver.run()]


def uniform_series(grid, rate_mm_hr, t0, t1):
    ny, nx = grid.ny, grid.nx
    native = np.full((3, 3), rate_mm_hr * (t1 - t0) / 3600.0)  # mm over interval
    idx = np.zeros(ny * nx, dtype=np.int64)                    # all map to cell 0
    return RainSeries([(t0, t1, native)], idx, (ny, nx))


def test_equivalence(conditioned):
    total, rain = 1800.0, 36.0
    g1 = bumpy_grid(conditioned=conditioned)
    g2 = bumpy_grid(conditioned=conditioned)
    c1, c2 = cfg(total, rain), cfg(total, rain)
    stock = NumpyShallowWaterSolver(g1, c1, BoundaryType.CLOSED)
    series = uniform_series(g1, rain, 0.0, total)
    qpe = QPESolver(g2, c2, BoundaryType.CLOSED, rain_series=series)
    f1, f2 = run_frames(stock), run_frames(qpe)
    assert len(f1) == len(f2)
    worst = max(float(np.abs(a - b).max()) for a, b in zip(f1, f2))
    label = "conditioned" if conditioned else "bare"
    assert worst == 0.0, f"{label}: max |diff| = {worst}"
    print(f"EQUIVALENCE [{label}]: bit-identical over {len(f1)} frames "
          f"(peak depth {f1[-1].max():.4f} m)")


def test_mass():
    total = 1200.0
    g = bumpy_grid()
    ny, nx = g.ny, g.nx
    c = cfg(total, rain=0.0, drain=0.0)
    native = np.zeros((2, 2))
    native[0, 0] = 30.0   # 30 mm on the west half, 6 mm on the east half
    native[0, 1] = 6.0
    idx = np.where((np.arange(ny * nx) % nx) < nx // 2, 0, 1).astype(np.int64)
    series = RainSeries([(0.0, 600.0, native)], idx, (ny, nx))
    s = QPESolver(g, c, BoundaryType.CLOSED, rain_series=series)
    frames = run_frames(s)
    vol = frames[-1].sum() * g.dx * g.dx
    expect = (nx // 2) * ny * 0.030 * g.dx * g.dx + (nx - nx // 2) * ny * 0.006 * g.dx * g.dx
    # The rate at step START applies across the whole CFL step, so one step can
    # straddle the rain-interval end — same discretization as the stock solver's
    # duration_hours cutoff. Error bound: one CFL step (~13 s) / 600 s window.
    err = abs(vol - expect) / expect
    assert err < 3e-3, f"mass error {err}"
    # Spatial pattern: west columns deeper on flat... grid is bumpy, so check totals
    # per half instead.
    west = frames[-1][:, :nx // 2].sum() * g.dx * g.dx
    assert west > 0.6 * vol
    print(f"MASS: QPE volume conserved to {err:.1e}; west-half share {west/vol:.2f}")


def test_stage_bc_and_probes():
    total = 600.0
    nx = ny = 20
    g = Grid.empty(nx, ny, 5.0)
    for y in range(ny):
        for x in range(nx):
            g.z[y][x] = 1.0
    c = cfg(total, rain=0.0, drain=0.0)
    j = np.zeros(nx, dtype=int)
    i = np.arange(nx)
    bc = StageBC(j, i, [0.0, 300.0, 600.0], np.array([[1.0] * nx, [2.0] * nx, [2.0] * nx]))
    probes = Probes({"mid": (np.array([ny // 2]), np.array([nx // 2]))}, interval_s=60.0)
    s = QPESolver(g, c, BoundaryType.CLOSED, stage_bc=bc, probes=probes)
    frames = run_frames(s)
    # Strip stage 2.0 on bed 1.0 -> ~1.0 m held at the strip at the end.
    strip = frames[-1][0, :]
    assert abs(strip.mean() - 1.0) < 0.05, strip.mean()
    interior = frames[-1][ny // 2, nx // 2]
    assert interior > 0.05, "stage BC did not propagate into the domain"
    assert len(probes.t) >= 9, f"probe cadence broke: {len(probes.t)} records"
    depths = [row[0] for row in probes.records["mid"]]
    assert depths == sorted(depths) or max(depths) > 0.0
    print(f"STAGE BC: strip held {strip.mean():.3f} m; interior reached "
          f"{interior:.3f} m; probes recorded {len(probes.t)} samples")


if __name__ == "__main__":
    test_equivalence(False)
    test_equivalence(True)
    test_mass()
    test_stage_bc_and_probes()
    print("ALL EXTENSION TESTS PASSED")
