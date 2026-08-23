#!/usr/bin/env python3
"""Model hydrograph timing vs observed gauged-reach response.

Usage: python3 gauge_timing.py <run_dir> <nest_name|parent> [...]

OBSERVED SOURCE AND ITS LIMIT
=============================
Direct USGS endpoints are egress-blocked from this host. The observed series
used here is NOAA NWM v3 **analysis_assim** channel_rt discharge, which is
nudged to live USGS gauges (large nonzero nudge values confirm assimilation
during this event). It is therefore a USGS-anchored proxy, NOT raw USGS
observation, and it carries DISCHARGE (cfs) only — no stage.

Because units differ (model: water depth/stage in m; observed: discharge in
cfs), absolute error is NOT computable. What IS comparable is TIMING and SHAPE:

    rise_start   first time the series exceeds baseline + 15% of its own range
    t_peak       time of maximum
    rise_hours   t_peak - rise_start

and the rank correlation of the two normalized series over the common window.
Reported errors are therefore timing errors in minutes, not stage RMSE. A stage
RMSE would require the USGS stage record and a datum reconciliation, both of
which are unavailable here; that is stated rather than approximated.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

T0 = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
RISE_FRAC = 0.15


def to_h(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (t - T0).total_seconds() / 3600.0


def utc(h):
    return (T0 + timedelta(hours=float(h))).strftime("%m-%d %H:%MZ")


def timing(t_h, y):
    y = np.asarray(y, float)
    t_h = np.asarray(t_h, float)
    ok = ~np.isnan(y)
    if ok.sum() < 3:
        return None
    y, t_h = y[ok], t_h[ok]
    base, top = float(np.nanmin(y)), float(np.nanmax(y))
    if top - base <= 0:
        return None
    thr = base + RISE_FRAC * (top - base)
    idx = np.nonzero(y >= thr)[0]
    rise = float(t_h[idx[0]]) if idx.size else None
    pk = float(t_h[int(np.argmax(y))])
    return {"rise_start_h": rise, "rise_start_utc": None if rise is None else utc(rise),
            "peak_h": pk, "peak_utc": utc(pk),
            "rise_to_peak_h": None if rise is None else round(pk - rise, 2),
            "baseline": round(base, 4), "peak_value": round(top, 4)}


def observed_series(site_no):
    path = os.path.join(HERE, "gauges", f"{site_no}.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    recs = d if isinstance(d, list) else (d.get("series") or [])
    t_h, q = [], []
    for r in recs:
        iso = r.get("time_utc") or r.get("time")
        val = r.get("discharge_cfs")
        if iso is None or val is None:
            continue
        iso = iso if iso.endswith("Z") else iso + "Z"
        if len(iso) == 17:            # 2026-08-18T00:00Z -> add seconds
            iso = iso[:-1] + ":00Z"
        t_h.append(to_h(iso))
        q.append(float(val))
    if len(t_h) < 3:
        return None
    o = np.argsort(t_h)
    return np.asarray(t_h)[o], np.asarray(q)[o]


def main():
    run_dir = os.path.join(HERE, sys.argv[1])
    probes_path = os.path.join(run_dir, "probes.json")
    if not os.path.exists(probes_path):
        print(f"no probes.json in {sys.argv[1]} (run may be incomplete)")
        return 1
    p = json.load(open(probes_path))
    t_h = np.asarray(p["t_s"], float) / 3600.0
    rows = []
    for name, g in p["groups"].items():
        if "gauge" not in name:
            continue
        site = name.split("_")[-1]
        d = np.asarray(g["depth_m"])
        if d.ndim == 1:
            d = d[:, None]
        model = d.max(axis=1)          # deepest channel cell = stage proxy
        mt = timing(t_h, model)
        obs = observed_series(site)
        ot = timing(*obs) if obs is not None else None
        row = {"probe": name, "site_no": site, "model": mt, "observed_nwm": ot}
        if mt and ot:
            row["peak_time_error_min"] = round((mt["peak_h"] - ot["peak_h"]) * 60, 0)
            if mt["rise_start_h"] is not None and ot["rise_start_h"] is not None:
                row["rise_start_error_min"] = round(
                    (mt["rise_start_h"] - ot["rise_start_h"]) * 60, 0)
            # shape agreement on the overlapping window, normalized 0-1
            lo = max(t_h.min(), obs[0].min())
            hi = min(t_h.max(), obs[0].max())
            if hi > lo + 1:
                gridt = np.linspace(lo, hi, 40)
                mi = np.interp(gridt, t_h, model)
                oi = np.interp(gridt, obs[0], obs[1])
                nm = (mi - mi.min()) / max(mi.ptp(), 1e-9)
                no = (oi - oi.min()) / max(oi.ptp(), 1e-9)
                row["shape_corr"] = round(float(np.corrcoef(nm, no)[0, 1]), 3)
                row["overlap_window_h"] = [round(lo, 1), round(hi, 1)]
                row["truncated"] = bool(hi < obs[0].max() - 1)
        rows.append(row)
    out = {"run_dir": sys.argv[1],
           "observed_source": "NOAA NWM v3 analysis_assim (USGS-nudged proxy); "
                              "discharge only — no stage, so no stage RMSE",
           "note": "comparison is TIMING and SHAPE, not absolute magnitude",
           "gauges": rows}
    path = os.path.join(HERE, f"gauge_timing_{os.path.basename(run_dir)}.json")
    json.dump(out, open(path, "w"), indent=2)
    for r in rows:
        m, o = r.get("model"), r.get("observed_nwm")
        print(f"{r['probe']}:")
        print(f"   model    rise {m and m['rise_start_utc']}  peak {m and m['peak_utc']}")
        print(f"   observed rise {o and o['rise_start_utc']}  peak {o and o['peak_utc']}")
        if "peak_time_error_min" in r:
            print(f"   peak-time error {r['peak_time_error_min']:+.0f} min, "
                  f"shape r={r.get('shape_corr')}, truncated={r.get('truncated')}")
    print("->", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
