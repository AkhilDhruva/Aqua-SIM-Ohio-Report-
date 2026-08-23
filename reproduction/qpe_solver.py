"""Side-task extension of the aqua-sim NumPy solver (NO repo edits).

Adds, via subclass + in-process patch of ``make_solver``:
  * spatially varying, time-varying rainfall from MRMS QPE grids
    (a StormConfig proxy whose ``rainfall_at`` returns a 2-D field in m/s —
    both the bare and the conditioned depth-update paths in
    ``NumpyShallowWaterSolver.step`` consume it by broadcasting);
  * Dirichlet stage boundary strips (nest edges fed by a parent run);
  * boundary-stage recording (parent runs record what nests will consume);
  * minute-cadence depth probes at named cells (gauges, road segments) so
    threshold-crossing TIMES are resolved far finer than the frame cadence.

Equivalence guarantee: with a uniform constant field equal to the scalar
rate, results are bit-identical to the stock solver (test_qpe_solver.py).
"""

from __future__ import annotations

import copy
import json

import numpy as np

from aqua_sim.physics.swe_numpy import NumpyShallowWaterSolver
from aqua_sim.physics.boundary import BoundaryType


class RainSeries:
    """Piecewise-constant-in-time, per-cell rain rate from QPE accumulations.

    intervals: list of (t_start_s, t_end_s, native_field_mm) where the field is
    the native (cropped) QPE array in mm accumulated over the interval.
    idx_map: int array (ny*nx,) mapping each grid cell to a flat index of the
    native field (nearest-neighbor in space — QPE is ~1 km, the grid finer).
    Outside all intervals the rate is 0.
    """

    def __init__(self, intervals, idx_map, shape):
        self.intervals = sorted(intervals, key=lambda r: r[0])
        self.starts = np.array([r[0] for r in self.intervals])
        self.idx_map = np.asarray(idx_map, dtype=np.int64)
        self.shape = shape          # (ny, nx) of the model grid
        self._cache_i = None
        self._cache_field = None
        self._zero = np.zeros(shape)

    def field_at(self, t_s: float):
        """Rain rate field (m/s) on the model grid at model time t_s."""
        i = int(np.searchsorted(self.starts, t_s, side="right")) - 1
        if i < 0 or t_s >= self.intervals[i][1]:
            return self._zero
        if i != self._cache_i:
            t0, t1, native_mm = self.intervals[i]
            rate = native_mm.ravel()[self.idx_map] / 1000.0 / (t1 - t0)
            self._cache_field = rate.reshape(self.shape)
            self._cache_i = i
        return self._cache_field

    def total_mm_field(self):
        tot = np.zeros(self.shape)
        for t0, t1, native_mm in self.intervals:
            tot += native_mm.ravel()[self.idx_map].reshape(self.shape)
        return tot


class FieldStorm:
    """StormConfig proxy: spatial rainfall, scalar drainage, all else delegated."""

    def __init__(self, base, series: RainSeries):
        self._base = base
        self._series = series

    def rainfall_at(self, t_s: float):
        return self._series.field_at(t_s)

    def effective_drainage_m_per_s(self) -> float:
        return self._base.effective_drainage_m_per_s()

    def __getattr__(self, name):
        return getattr(self._base, name)


class StageBC:
    """Dirichlet water-surface-elevation strips (nest edges from a parent run).

    cells: (j_idx, i_idx) int arrays. times: (T,) model seconds.
    stages: (T, ncells) water-surface elevation (m, model datum). Between
    samples: linear interpolation; before/after: clamped to ends.
    """

    def __init__(self, j_idx, i_idx, times, stages, parent_z=None,
                 wet_threshold_m=0.02):
        self.j = np.asarray(j_idx)
        self.i = np.asarray(i_idx)
        self.times = np.asarray(times, dtype=float)
        self.stages = np.asarray(stages, dtype=float)
        # parent bed elevation under each BC cell: the stage is only IMPOSED
        # while the parent cell actually holds water (stage - parent_z above
        # threshold); a dry parent stage equals its bed, which can sit above
        # the fine nest bed and would otherwise inject phantom water.
        self.parent_z = None if parent_z is None else np.asarray(parent_z, float)
        self.wet_threshold_m = wet_threshold_m

    def stage_at(self, t_s: float):
        k = int(np.searchsorted(self.times, t_s, side="right"))
        if k <= 0:
            eta = self.stages[0]
        elif k >= len(self.times):
            eta = self.stages[-1]
        else:
            t0, t1 = self.times[k - 1], self.times[k]
            w = (t_s - t0) / (t1 - t0) if t1 > t0 else 0.0
            eta = (1.0 - w) * self.stages[k - 1] + w * self.stages[k]
        if self.parent_z is None:
            return eta, np.ones(eta.shape, dtype=bool)
        return eta, (eta - self.parent_z) > self.wet_threshold_m


class Probes:
    """Named cell groups whose depth is recorded every ``interval_s``."""

    def __init__(self, groups: dict, interval_s: float = 60.0,
                 autodump_path=None, autodump_every: int = 30, meta=None):
        # groups: name -> (j_idx array, i_idx array)
        self.groups = {k: (np.asarray(j), np.asarray(i)) for k, (j, i) in groups.items()}
        self.interval_s = interval_s
        self.t = []
        self.records = {k: [] for k in self.groups}
        self._next = 0.0
        # Crash resilience: a multi-hour run killed by a container restart would
        # otherwise lose every 60 s sample (the final dump never runs).
        self.autodump_path = autodump_path
        self.autodump_every = autodump_every
        self.meta = meta or {}

    def maybe_record(self, time_s, h, z):
        if time_s + 1e-9 < self._next:
            return
        self.t.append(round(float(time_s), 1))
        for name, (j, i) in self.groups.items():
            self.records[name].append(np.round(h[j, i], 4).tolist())
        self._next += self.interval_s
        if (self.autodump_path and self.autodump_every
                and len(self.t) % self.autodump_every == 0):
            try:
                self.dump(self.autodump_path, self.meta)
            except OSError:
                pass          # never let telemetry kill the solve

    def dump(self, path, meta=None):
        with open(path, "w") as f:
            json.dump({"interval_s": self.interval_s, "t_s": self.t,
                       "groups": {k: {"j": self.groups[k][0].tolist(),
                                      "i": self.groups[k][1].tolist(),
                                      "depth_m": self.records[k]}
                                  for k in self.groups},
                       "meta": meta or {}}, f)


class QPESolver(NumpyShallowWaterSolver):
    """Stock solver + spatial rain + stage BC + probes + boundary recording."""

    def __init__(self, grid, config, boundary=BoundaryType.OPEN, *,
                 rain_series=None, stage_bc=None, probes=None,
                 record_cells=None, record_interval_s=300.0):
        super().__init__(grid, config, boundary)
        if rain_series is not None:
            # SimConfig is a mutable dataclass: shallow-copy it and rebind storm
            # to the field proxy for the solver only; the caller's config (used
            # for manifests) is untouched.
            cfg = copy.copy(config)
            cfg.storm = FieldStorm(config.storm, rain_series)
            self.config = cfg
        self._stage_bc = stage_bc
        self._probes = probes
        # Parent-side recording of nest boundary stages.
        self._rec = None
        if record_cells is not None:
            self._rec = {name: {"j": np.asarray(j), "i": np.asarray(i)}
                         for name, (j, i) in record_cells.items()}
            self._rec_t = []
            self._rec_vals = {name: [] for name in self._rec}
            self._rec_interval = record_interval_s
            self._rec_next = 0.0

    def step(self, dt: float) -> None:
        super().step(dt)
        if self._stage_bc is not None:
            bc = self._stage_bc
            eta, active = bc.stage_at(self.time_s)
            if active.any():
                j, i = bc.j[active], bc.i[active]
                self.h[j, i] = np.maximum(eta[active] - self.z[j, i], 0.0)
                hb = float(self.h[j, i].max()) if j.size else 0.0
                if hb > self._max_h:
                    self._max_h = hb
        if self._rec is not None and self.time_s + 1e-9 >= self._rec_next:
            self._rec_t.append(round(float(self.time_s), 1))
            for name, d in self._rec.items():
                eta = self.z[d["j"], d["i"]] + self.h[d["j"], d["i"]]
                self._rec_vals[name].append(np.round(eta, 4).tolist())
            self._rec_next += self._rec_interval
        if self._probes is not None:
            self._probes.maybe_record(self.time_s, self.h, self.z)

    def dump_boundary_record(self, path):
        assert self._rec is not None
        with open(path, "w") as f:
            json.dump({"interval_s": self._rec_interval, "t_s": self._rec_t,
                       "groups": {name: {"j": d["j"].tolist(), "i": d["i"].tolist(),
                                         "stage_m": self._rec_vals[name]}
                                  for name, d in self._rec.items()}}, f)


_LAST = {"solver": None}


def patch_make_solver(**solver_kwargs):
    """Patch aqua_sim's make_solver so run_scenario builds a QPESolver.

    Returns an undo function. The constructed solver is stashed in
    ``last_solver()`` so the runner can dump probe/boundary records afterward.
    """
    import aqua_sim.physics.swe_numpy as m
    import aqua_sim.scenario as s  # noqa: F401 (imports make_solver lazily)
    orig = m.make_solver

    def patched(grid, config, boundary=BoundaryType.OPEN, backend="auto"):
        solver = QPESolver(grid, config, boundary, **solver_kwargs)
        _LAST["solver"] = solver
        return solver

    m.make_solver = patched

    def undo():
        m.make_solver = orig

    return undo


def last_solver() -> QPESolver:
    return _LAST["solver"]


def build_idx_map(grid_transform, grid_crs, ny, nx, qpe_transform, qpe_shape):
    """Nearest-neighbor map: model cell centers -> flat index into the QPE crop.

    Cells falling outside the QPE crop are clamped to its edge (QPE crop must
    generously cover the AOI, so clamping only touches sliver edges).
    """
    from rasterio.warp import transform as warp_transform

    a, b, left, d, e, top = grid_transform[:6]
    xs = left + (np.arange(nx) + 0.5) * a
    ys = top + (np.arange(ny) + 0.5) * e
    X, Y = np.meshgrid(xs, ys)
    lon, lat = warp_transform(grid_crs, "EPSG:4326",
                              X.ravel().tolist(), Y.ravel().tolist())
    lon = np.asarray(lon)
    lat = np.asarray(lat)
    qa, qb, qleft, qd, qe, qtop = qpe_transform[:6]
    ci = np.clip(((lon - qleft) / qa).astype(np.int64), 0, qpe_shape[1] - 1)
    cj = np.clip(((lat - qtop) / qe).astype(np.int64), 0, qpe_shape[0] - 1)
    return cj * qpe_shape[1] + ci
