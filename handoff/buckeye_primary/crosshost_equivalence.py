#!/usr/bin/env python3
"""Cross-host numerical equivalence gate for the Buckeye primary run.

Before resuming the scientific run on a different machine, prove that the new
host reproduces this host's arithmetic EXACTLY from the same frozen checkpoint.

It advances the frozen state by a short fixed window (600 model-seconds, one
checkpoint-grid line) using the same solver, setup cache and forcing, then
hashes the resulting fields. A reference hash produced on the original host
ships in reference.json.

    python3 crosshost_equivalence.py            # compare against reference
    python3 crosshost_equivalence.py --emit     # produce the reference

PASS  -> resume the scientific run on this host; results are continuous.
FAIL  -> do NOT resume. Differences mean a different BLAS/libm/CPU rounding
         path, and the run would no longer be the same experiment. Report the
         mismatch instead of proceeding.
"""
import argparse, hashlib, json, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # the bundle root IS the run directory

ADVANCE_S = 600.0


def field_hash(a):
    return hashlib.sha256(np.ascontiguousarray(a, dtype=np.float64).tobytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true")
    a = ap.parse_args()

    os.environ.setdefault("PYTHONHASHSEED", "0")
    import run_corridor as RC
    from aqua_sim.config import SimConfig, SolverConfig, StormConfig
    from aqua_sim.physics.boundary import BoundaryType
    from prep_qpe import intervals_from_npz
    from qpe_solver import Probes, QPESolver, RainSeries

    frozen = os.path.join(HERE, "frozen")
    # setup cache carries terrain, roughness, culverts, probes, rain map, BC
    import shutil, tempfile
    tmp = tempfile.mkdtemp()
    for f in ("setup_cache.npz", "state.npz"):
        shutil.copy2(os.path.join(frozen, f), os.path.join(tmp, f))
    grid, culverts, groups, pmeta, idx_map, stage_bc = RC.load_setup(tmp)
    ny, nx = grid.ny, grid.nx

    intervals, qtr, qsh = intervals_from_npz(os.path.join(HERE, "qpe", "fields_B.npz"))
    series = RainSeries(intervals, idx_map, (ny, nx))
    means = [(x, y, float(f.mean())) for x, y, f in intervals]
    peak_rate = max(m[2] / ((m[1] - m[0]) / 3600.0) for m in means)

    probes = Probes(groups, interval_s=60.0)
    cfg = SimConfig(
        storm=StormConfig(rainfall_mm_per_hr=round(peak_rate, 2),
                          duration_hours=20.0,
                          drainage_capacity_mm_per_hr=10.0, drainage_blockage=0.5),
        solver=SolverConfig(cfl=0.7, total_time_s=20 * 3600.0,
                            output_interval_s=3600.0),
        aoi_name="buckeye_c crosshost gate")
    solver = QPESolver(grid, cfg, BoundaryType.OPEN, rain_series=series,
                       stage_bc=stage_bc, probes=probes)
    restored = RC.load_ckpt(os.path.join(tmp, "state.npz"), solver, probes)
    assert restored is not None, "frozen checkpoint did not load"
    peak, snaps, snap_t = restored
    t0 = solver.time_s
    peak, snaps, snap_t = RC.step_loop(solver, peak, probes, snaps, snap_t,
                                       t0 + ADVANCE_S, ckpt_path=None)
    result = {
        "start_model_hour": round(t0 / 3600, 6),
        "end_model_hour": round(solver.time_s / 3600, 6),
        "advance_s": ADVANCE_S,
        "h": field_hash(solver.h), "qx": field_hash(solver.qx),
        "qy": field_hash(solver.qy), "peak": field_hash(peak),
        "max_h": repr(float(solver._max_h)),
        "max_face_v": repr(float(solver._max_face_v)),
        "volume": repr(float(solver.h.sum())),
        "n_probe_samples": len(probes.t),
    }
    shutil.rmtree(tmp, ignore_errors=True)

    ref_path = os.path.join(HERE, "reference.json")
    if a.emit:
        result["emitted_on"] = {
            "platform": sys.platform, "python": sys.version.split()[0],
            "numpy": np.__version__,
        }
        json.dump(result, open(ref_path, "w"), indent=2)
        print("reference written:", ref_path)
        for k in ("h", "qx", "qy", "peak"):
            print(f"  {k:<5} {result[k][:16]}...")
        return 0

    ref = json.load(open(ref_path))
    keys = ["h", "qx", "qy", "peak", "max_h", "max_face_v", "volume",
            "n_probe_samples", "start_model_hour", "end_model_hour"]
    bad = [k for k in keys if str(ref[k]) != str(result[k])]
    print(f"advanced {ADVANCE_S:.0f} model-seconds from hour "
          f"{result['start_model_hour']} to {result['end_model_hour']}")
    print(f"reference host: {ref.get('emitted_on')}")
    print(f"this host:      platform={sys.platform} python={sys.version.split()[0]} "
          f"numpy={np.__version__}")
    for k in keys:
        mark = "MISMATCH" if k in bad else "ok"
        rv, tv = str(ref[k]), str(result[k])
        print(f"  {k:<18} {mark:<9} ref {rv[:20]:<22} this {tv[:20]}")
    if bad:
        print("\nFAIL — do NOT resume the scientific run on this host. "
              f"Differing: {', '.join(bad)}")
        return 1
    print("\nPASS — arithmetic is identical; resuming here continues the same run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
