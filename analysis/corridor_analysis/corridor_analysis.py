#!/usr/bin/env python3
"""Road-vs-channel differential and smearing diagnosis from corridor output.

Usage: python3 corridor_analysis.py <nest> [<nest> ...]

Reads corridor_<nest>_B/probes.json, which carries TWO groups per site:
    "<name>"            carriageway cells   (road surface)
    "<name>__channel"   NHD flowline cells  (the stream)
both at 60 s resolution, and compares them against the 60 m parent's single
cell at the same location (from the parent's own probe series where present,
else from the parent frames).

The discriminator, evaluated at the PARENT's own threshold-crossing time and at
each site's own peak:
    CONFIRMED       nest carriageway itself reaches >= 0.30 m -> the coarse
                    signal corresponds to real road inundation (Case A locally)
    SMEARED         carriageway < 0.15 m while the channel is deep -> the
                    coarse signal was channel water on a road-bearing cell
    PARTIAL         carriageway between 0.15 and 0.30 m
    DRY             carriageway never wets

Works on a partial (still-running) probe file; it reports the model hours
actually covered so a partial result is never mistaken for a final one.
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CAUTION, IMPASS = 0.15, 0.30
T0 = "2026-08-19T18:00:00Z"


def utc(h):
    from datetime import datetime, timedelta, timezone
    return (datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
            + timedelta(hours=float(h))).strftime("%m-%d %H:%MZ")


def first_cross(t_h, y, thr):
    i = np.nonzero(np.asarray(y) >= thr)[0]
    return float(t_h[i[0]]) if i.size else None


def analyse(nest):
    d = os.path.join(HERE, f"corridor_{nest}_B")
    pj = os.path.join(d, "probes.json")
    if not os.path.exists(pj):
        return {"nest": nest, "status": "no probes yet"}
    p = json.load(open(pj))
    t_h = np.asarray(p["t_s"], float) / 3600.0
    mp = os.path.join(d, "meta.json")
    meta = json.load(open(mp)) if os.path.exists(mp) else {}
    # "complete" means the probe series actually reaches the run's target
    # window — a stale meta.json from a short smoke run must not qualify.
    target = float(meta.get("hours", 0) or 0)
    complete = bool(meta) and target > 0 and \
        (float(p["t_s"][-1]) / 3600.0) >= target - 0.05
    rows = []
    for name, g in p["groups"].items():
        if name.endswith("__channel"):
            continue
        road = np.asarray(g["depth_m"])
        road = road.max(axis=1) if road.ndim > 1 else road
        ch = p["groups"].get(name + "__channel")
        chan = None
        if ch:
            c = np.asarray(ch["depth_m"])
            chan = c.max(axis=1) if c.ndim > 1 else c
        r = {
            "probe": name,
            "n_road_cells": len(g["i"]),
            "road_peak_m": round(float(road.max()), 3),
            "road_peak_utc": utc(t_h[int(road.argmax())]),
            "road_caution_utc": (lambda x: utc(x) if x is not None else None)(
                first_cross(t_h, road, CAUTION)),
            "road_impassable_utc": (lambda x: utc(x) if x is not None else None)(
                first_cross(t_h, road, IMPASS)),
            "channel_peak_m": None if chan is None else round(float(chan.max()), 3),
            "road_minus_channel_peak_m": None if chan is None else
                round(float(road.max() - chan.max()), 3),
        }
        rp, cp = r["road_peak_m"], r["channel_peak_m"]
        if rp >= IMPASS:
            r["diagnosis"] = "CONFIRMED_ROAD_INUNDATION"
        elif rp >= CAUTION:
            r["diagnosis"] = "PARTIAL"
        elif cp is not None and cp >= IMPASS:
            r["diagnosis"] = "SMEARED_channel_wet_road_dry"
        else:
            r["diagnosis"] = "DRY"
        rows.append(r)
    return {"nest": nest, "complete": complete,
            "covered_model_hours": [round(float(t_h[0]), 2), round(float(t_h[-1]), 2)],
            "n_samples": len(t_h), "t0_utc": T0,
            "thresholds_m": {"caution": CAUTION, "impassable": IMPASS},
            "probes": rows}


def main():
    out = [analyse(n) for n in sys.argv[1:]]
    json.dump(out, open(os.path.join(HERE, "corridor_analysis.json"), "w"), indent=2)
    for res in out:
        if "status" in res:
            print(f"[{res['nest']}] {res['status']}"); continue
        tag = "FINAL" if res["complete"] else "PARTIAL"
        print(f"\n[{res['nest']}] {tag}  model hours "
              f"{res['covered_model_hours'][0]}–{res['covered_model_hours'][1]} "
              f"({res['n_samples']} samples)")
        print(f"  {'probe':<28}{'road pk':>9}{'chan pk':>9}{'road-chan':>11}  diagnosis")
        for r in res["probes"]:
            cp = r["channel_peak_m"]
            dm = r["road_minus_channel_peak_m"]
            print(f"  {r['probe']:<28}{r['road_peak_m']:>9.2f}"
                  f"{(cp if cp is not None else float('nan')):>9.2f}"
                  f"{(dm if dm is not None else float('nan')):>11.2f}"
                  f"  {r['diagnosis']}")
    print("\n-> corridor_analysis.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
