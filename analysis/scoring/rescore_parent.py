#!/usr/bin/env python3
"""Rescore a 60 m parent run against the same 17 observed locations used for
the frozen uniform-forcing hindcast — SAME scorer parameters (0.15 m detection,
250 m neighborhood), plus the same permutation test (20k resamples). Usage:

    python3 rescore_parent.py run_qpeB_parent [run_qpeA_parent ...]

Writes rescore_<dirname>.json for each and prints a comparison against the
frozen uniform-mid result.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))

from score_columbus import DETECT_DEPTH_M, NEIGHBORHOOD_M, grid_georef, load_run
from rasterio.warp import transform as warp_transform

RNG_SEED = 20260822


def neighborhood_peaks(peak, mask, transform, crs, pts_lonlat, dx):
    a, _b, left, _d, e, top = transform[:6]
    r = max(int(round(NEIGHBORHOOD_M / dx)), 1)
    ny, nx = peak.shape
    out = []
    for lon, lat in pts_lonlat:
        xs, ys = warp_transform("EPSG:4326", crs, [lon], [lat])
        i = int((xs[0] - left) / dx)
        j = int((top - ys[0]) / dx)
        if not (0 <= i < nx and 0 <= j < ny):
            out.append(None)
            continue
        i0, i1 = max(i - r, 0), min(i + r + 1, nx)
        j0, j1 = max(j - r, 0), min(j + r + 1, ny)
        nb, nbm = peak[j0:j1, i0:i1], mask[j0:j1, i0:i1]
        out.append(float(nb[nbm].max()) if nbm.any() else 0.0)
    return out


def permutation(peak, mask, dx, obs_peaks, n=20000):
    rng = np.random.default_rng(RNG_SEED)
    r = max(int(round(NEIGHBORHOOD_M / dx)), 1)
    ny, nx = peak.shape
    jj, ii = np.nonzero(mask)
    k = len(obs_peaks)
    obs_mean = float(np.mean(obs_peaks))
    obs_med = float(np.median(obs_peaks))
    means = np.empty(n)
    meds = np.empty(n)
    for t in range(n):
        sel = rng.integers(0, len(jj), k)
        vals = np.empty(k)
        for q, s in enumerate(sel):
            j, i = jj[s], ii[s]
            i0, i1 = max(i - r, 0), min(i + r + 1, nx)
            j0, j1 = max(j - r, 0), min(j + r + 1, ny)
            nb, nbm = peak[j0:j1, i0:i1], mask[j0:j1, i0:i1]
            vals[q] = nb[nbm].max() if nbm.any() else 0.0
        means[t] = vals.mean()
        meds[t] = np.median(vals)
    return {
        "observed_mean_nb_peak_m": round(obs_mean, 3),
        "random_mean_nb_peak_m": round(float(means.mean()), 3),
        "p_value_mean": round(float((means >= obs_mean).mean()), 5),
        "observed_median_nb_peak_m": round(obs_med, 3),
        "random_median_nb_peak_m": round(float(meds.mean()), 3),
        "p_value_median": round(float((meds >= obs_med).mean()), 5),
        "n_resamples": n,
    }


def main():
    run_dirs = sys.argv[1:] or ["run_qpeB_parent"]
    observed = json.load(open(os.path.join(HERE, "observed_flooding.json")))
    pts = [(o["lon"], o["lat"]) for o in observed]
    for rd in run_dirs:
        run_dir = os.path.join(HERE, rd)
        man, peak, mask = load_run(run_dir)
        dx = man["grid"]["dx_m"]
        (a, _b, left, _d, e, top), crs, gnx, gny = grid_georef(dx)
        assert (gnx, gny) == (man["grid"]["nx"], man["grid"]["ny"])
        transform = (a, _b, left, _d, e, top)
        nbp = neighborhood_peaks(peak, mask, transform, crs, pts, dx)
        wet = np.sort(peak[mask & (peak > 0.01)])
        rows, obs_peaks = [], []
        detected = 0
        for o, p in zip(observed, nbp):
            if p is None:
                rows.append({**o, "in_domain": False})
                continue
            hit = p >= DETECT_DEPTH_M
            detected += int(hit)
            obs_peaks.append(p)
            pct = float(wet.searchsorted(p) / max(len(wet), 1) * 100)
            rows.append({**o, "in_domain": True, "peak_depth_m": round(p, 3),
                         "detected": hit, "wet_cell_percentile": round(pct, 1)})
        perm = permutation(peak, mask, dx, obs_peaks)
        rep = {"run_dir": rd, "run_id": man["run_id"],
               "aoi_name": man.get("provenance", {}).get("aoi_name") or
               man.get("aoi_name"),
               "pod": {"detected": detected, "of": len(obs_peaks),
                       "pod": round(detected / len(obs_peaks), 3)},
               "permutation": perm, "locations": rows}
        out = os.path.join(HERE, f"rescore_{rd}.json")
        json.dump(rep, open(out, "w"), indent=2)
        print(f"[{rd}] run {man['run_id']}  POD {detected}/{len(obs_peaks)}  "
              f"perm p_mean={perm['p_value_mean']} p_med={perm['p_value_median']} "
              f"obs_med={perm['observed_median_nb_peak_m']} m "
              f"rand_med={perm['random_median_nb_peak_m']} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
