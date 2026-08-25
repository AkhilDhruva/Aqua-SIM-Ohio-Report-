#!/usr/bin/env python3
"""Is the high face velocity a boundary artifact, and does it reach the probes?

Usage: python3 boundary_velocity_audit.py <run_dir> [<run_dir> ...]

BACKGROUND
    ML-3 recorded that the OPEN (free-outfall) domain boundary throttles the
    global CFL timestep: the ghost cell is placed at the live cell's own bed,
    so deep water at the edge sees a free drop of its full depth across one
    cell width. The question this answers is whether that velocity is confined
    to the boundary or contaminates the model interior — and specifically
    whether it reaches the corridor probes that the science depends on.

METHOD
    1. Recompute every interior face velocity from the checkpointed state,
       using the solver's own conveyance-depth definition
       (v = |q| / (max(eta) - max(z_a, z_b, crest)), gated at min_depth).
    2. Report the domain maximum as a function of how many cell rings are
       excluded from each edge. A boundary artifact collapses after one or two
       rings; a genuine interior instability does not.
    3. For every probe group, report its minimum distance from any edge and the
       maximum cell speed and depth inside it.

    Note on step 2: the *faces* the solver treats as boundary faces are the
    ghost faces outside the edge cells. The faces BETWEEN cells in the edge row
    are interior faces by that classification, yet they carry the lateral
    drawdown feeding the outfall. Excluding boundary faces alone therefore does
    NOT isolate the interior; whole cell rings must be excluded. Getting that
    wrong is what produced the spurious "franklinton interior 26.28 m/s"
    reading (EF-6).

Read-only. Nothing is written back into any run.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
G = 9.80665
MIN_DEPTH = 1e-4          # solver default used by every corridor run
BUFFERS = (0, 1, 2, 3, 5, 10, 25, 50)
FAST = 5.0                # m/s — the threshold ML-3 used


def face_fields(z, h, qx, qy, obst):
    ny, nx = z.shape

    def fv(qa, za, ha, zb, hb, crest):
        hf = np.maximum(za + ha, zb + hb) - np.maximum(np.maximum(za, zb), crest)
        ok = hf > MIN_DEPTH
        return np.where(ok, np.abs(qa) / np.where(ok, hf, 1.0), 0.0), hf

    cx = np.maximum(obst[:, :-1], obst[:, 1:])
    cy = np.maximum(obst[:-1, :], obst[1:, :])
    vx, hfx = fv(qx[:, 1:nx], z[:, :-1], h[:, :-1], z[:, 1:], h[:, 1:], cx)
    vy, hfy = fv(qy[1:ny, :], z[:-1, :], h[:-1, :], z[1:, :], h[1:, :], cy)
    return (vx, hfx), (vy, hfy)


def audit(run):
    rd = os.path.join(HERE, run)
    s = np.load(os.path.join(rd, "setup_cache.npz"), allow_pickle=True)
    st = np.load(os.path.join(rd, "state.npz"), allow_pickle=True)
    z = np.asarray(s["z"], float)
    h = np.asarray(st["h"], float)
    obst = np.asarray(s["obstacle"], float)
    qx, qy = np.asarray(st["qx"], float), np.asarray(st["qy"], float)
    ny, nx = z.shape
    (vx, hfx), (vy, hfy) = face_fields(z, h, qx, qy, obst)

    # distance from the nearest edge, per face (min over its two cells)
    J, I = np.mgrid[0:ny, 0:nx - 1]
    dex = np.minimum.reduce([J, I, ny - 1 - J, nx - 2 - I])
    J, I = np.mgrid[0:ny - 1, 0:nx]
    dey = np.minimum.reduce([J, I, ny - 2 - J, nx - 1 - I])
    v = np.concatenate([vx.ravel(), vy.ravel()])
    hf = np.concatenate([hfx.ravel(), hfy.ravel()])
    d = np.concatenate([dex.ravel(), dey.ravel()])

    profile = []
    for b in BUFFERS:
        m = d >= b
        if not m.any():
            continue
        vm = v[m]
        profile.append({"exclude_rings": b,
                        "max_v_ms": round(float(vm.max()), 3),
                        "faces_over_5ms": int((vm > FAST).sum()),
                        "median_hflow_of_fast_m": (
                            None if not (vm > FAST).any()
                            else round(float(np.median(hf[m][vm > FAST])), 4))})

    # per-cell speed, the solver's own definition, for the probe table
    sp = np.zeros((ny, nx))
    sp[:, 1:] = np.maximum(sp[:, 1:], vx)
    sp[:, :-1] = np.maximum(sp[:, :-1], vx)
    sp[1:, :] = np.maximum(sp[1:, :], vy)
    sp[:-1, :] = np.maximum(sp[:-1, :], vy)
    sp[h <= MIN_DEPTH] = 0.0

    probes = []
    for k in sorted(kk for kk in s.keys() if kk.startswith("gj_")):
        g = k[3:]
        j, i = np.asarray(s["gj_" + g]), np.asarray(s["gi_" + g])
        if not j.size:
            continue
        de = int(np.minimum.reduce([j, i, ny - 1 - j, nx - 1 - i]).min())
        probes.append({"group": g, "n_cells": int(j.size),
                       "min_dist_to_edge_cells": de,
                       "max_speed_ms": round(float(sp[j, i].max()), 3),
                       "max_depth_m": round(float(h[j, i].max()), 4),
                       "boundary_adjacent": de <= 2})

    # Classify the fast faces that survive a 5-ring exclusion. A local-inertial
    # scheme fails as a THIN FILM: small conveyance depth, large Froude. Deep
    # water at Froude near 1 is ordinary channel flow, not a numerical defect.
    deep = d >= 5
    fastdeep = deep & (v > FAST)
    fr = v / np.sqrt(G * np.maximum(hf, 1e-12))
    interior_fast = []
    if fastdeep.any():
        interior_fast = [{
            "n_faces": int(fastdeep.sum()),
            "max_v_ms": round(float(v[fastdeep].max()), 3),
            "median_hflow_m": round(float(np.median(hf[fastdeep])), 3),
            "median_froude": round(float(np.median(fr[fastdeep])), 2),
            "n_thin_film_hflow_under_0p5m": int((hf[fastdeep] < 0.5).sum()),
            "n_channel_like_hflow_over_1m": int((hf[fastdeep] > 1.0).sum()),
        }]

    v0, v1, v2 = (profile[0]["max_v_ms"], profile[1]["max_v_ms"],
                  profile[2]["max_v_ms"])
    if profile[0]["faces_over_5ms"] == 0:
        verdict = "NO_FACE_ANYWHERE_EXCEEDS_5_M_S"
    elif not fastdeep.any():
        verdict = "BOUNDARY_ARTIFACT_CONFINED_TO_EDGE_ROWS"
    elif v2 < 0.5 * v0:
        verdict = "MOSTLY_BOUNDARY_SOME_INTERIOR"
    else:
        verdict = "INTERIOR_VELOCITY_NOT_EXPLAINED_BY_BOUNDARY"

    return {"run_dir": run,
            "t_h": round(float(np.asarray(st["t"]).ravel()[0]) / 3600.0, 4),
            "domain_cells": [int(ny), int(nx)],
            "dx_m": float(np.asarray(s["dx"]).ravel()[0]),
            "min_depth_m": MIN_DEPTH,
            "max_v_all_faces_ms": profile[0]["max_v_ms"],
            "max_v_excluding_one_edge_ring_ms": v1,
            "max_v_excluding_two_edge_rings_ms": v2,
            "verdict": verdict,
            "edge_exclusion_profile": profile,
            "interior_fast_faces_beyond_5_rings": interior_fast,
            "probe_groups": probes,
            "contaminated_probe_groups": [p["group"] for p in probes
                                          if p["max_speed_ms"] > FAST],
            "boundary_adjacent_probe_groups": [p["group"] for p in probes
                                               if p["boundary_adjacent"]]}


def main():
    out = {"purpose": "test whether ML-3's open-boundary velocity is confined "
                      "to the domain edge and whether it reaches the probes",
           "threshold_fast_ms": FAST,
           "runs": [audit(r) for r in sys.argv[1:]]}
    p = os.path.join(HERE, "boundary_velocity_audit.json")
    json.dump(out, open(p, "w"), indent=2)
    for r in out["runs"]:
        print(f"\n{r['run_dir']}  t={r['t_h']:.2f} h  {r['domain_cells'][0]}x"
              f"{r['domain_cells'][1]} @ {r['dx_m']:g} m  -> {r['verdict']}")
        for f in r["interior_fast_faces_beyond_5_rings"]:
            print(f"    interior fast faces (>5 rings in): {f['n_faces']}, "
                  f"max {f['max_v_ms']} m/s, median hflow {f['median_hflow_m']} m, "
                  f"median Fr {f['median_froude']} "
                  f"({f['n_channel_like_hflow_over_1m']} channel-like, "
                  f"{f['n_thin_film_hflow_under_0p5m']} thin-film)")
        for e in r["edge_exclusion_profile"]:
            print(f"    exclude {e['exclude_rings']:>3} ring(s): max "
                  f"{e['max_v_ms']:>7.2f} m/s   faces>5 m/s "
                  f"{e['faces_over_5ms']:>5}")
        print(f"    {'probe group':<38}{'d_edge':>8}{'speed':>8}{'depth':>8}")
        for q in r["probe_groups"]:
            flag = "  <-- boundary-adjacent" if q["boundary_adjacent"] else ""
            print(f"    {q['group']:<38}{q['min_dist_to_edge_cells']:>8}"
                  f"{q['max_speed_ms']:>8.2f}{q['max_depth_m']:>8.3f}{flag}")
    print("\n->", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
