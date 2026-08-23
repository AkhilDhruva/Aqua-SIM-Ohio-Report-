#!/usr/bin/env python3
"""Threshold-crossing timing + lead-time analysis from run probes.

Usage: python3 timing_analysis.py <run_dir> [...]

Reads <run_dir>/probes.json (60 s depth series per named cell group) and
<run_dir>/terrain.json (bed z, for water-surface elevation at channel probes).
Model t=0 == 2026-08-19T18:00Z.

Warning definitions (pre-registered in nest_prereg.json):
  caution    depth >= 0.15 m  (>=1 cell of the group)
  impassable depth >= 0.30 m  (>=3 cells of the group, or >=1 if group < 3)

Observed anchors below come from effect_research.json (press/NWS statements);
each carries its stated precision. Lead time = T_observed - T_model_warning.
Positive = model warned before the observed impact/closure.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)
FT = 0.3048

#: (anchor_key, probe_group, observed_utc, precision, description)
ANCHORS = [
    ("wbroad_rescue", ["wbroad_hilltop", "franklinton_wbroad"],
     "2026-08-20T08:00Z", "hour", "CFD water rescue W Broad St ~4 a.m. EDT"),
    ("ffe_franklin", ["franklinton_core", "wbroad_hilltop", "franklinton_wbroad"],
     "2026-08-20T08:45Z", "minute", "NWS Flash Flood Emergency, Franklin Co"),
    ("floodwall_activation", ["scioto_gauge_03221646", "franklinton_core"],
     "2026-08-20T12:10Z", "minute", "Franklinton floodwall activated"),
    ("pataskala_onset", ["main_broad_pataskala", "pataskala_main_broad"],
     "2026-08-20T08:30Z", "half-hour", "Pataskala torrential onset (residents awakened)"),
    ("pataskala_closures", ["main_broad_pataskala", "sr310_sf_crossing"],
     "2026-08-20T12:00Z", "morning-coarse", "Pataskala road-closure list reported (morning)"),
    ("i70_eb_closure", ["i70_sf_licking", "i70_sr79", "i70_sr79_sf_licking"],
     "2026-08-20T22:00Z", "hour", "ODOT closes I-70 EB at Exit 129"),
    ("i70_wb_closure", ["i70_sf_licking", "i70_sr79", "i70_sr79_sf_licking"],
     "2026-08-21T01:00Z", "hour", "ODOT closes I-70 WB at Exit 129"),
    ("buckeye_mand_evac", ["sr79_hebron_rd"],
     "2026-08-21T00:00Z", "minute", "Buckeye Lake mandatory evacuation effective"),
]

#: BCLO1 stage checks (water-surface elevation, ft -> m); NGVD29/NAVD88 datum
#: offset in central Ohio ~0.5-0.7 ft — flagged, not corrected.
STAGE_CHECKS = [
    ("bclo1_stage_obs", "i70_sf_licking", "2026-08-21T12:45Z", 882.8 * FT,
     "BCLO1 observed 882.8 ft (NWS product via press)"),
    ("bclo1_crest", "i70_sf_licking", "2026-08-21T15:30Z", 882.9 * FT,
     "BCLO1 crest ~882.9 ft late Fri morning (coarse timing)"),
]


def hours(utc_iso):
    t = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return (t - T0).total_seconds() / 3600.0


def utc_of(h):
    return (T0 + timedelta(hours=h)).strftime("%m-%d %H:%MZ")


def analyze(run_dir):
    p = json.load(open(os.path.join(run_dir, "probes.json")))
    t_h = np.asarray(p["t_s"], float) / 3600.0
    terr_path = os.path.join(run_dir, "terrain.json")
    zfull = None
    if os.path.exists(terr_path):
        terr = json.load(open(terr_path))
        zfull = np.asarray(terr["z"])
    out = {"run_dir": os.path.basename(run_dir), "groups": {}, "leads": [],
           "stage_checks": []}
    for name, g in p["groups"].items():
        d = np.asarray(g["depth_m"])          # (T, ncells)
        if d.ndim == 1:
            d = d[:, None]
        need = 3 if d.shape[1] >= 3 else 1
        n_ge = lambda thr: (d >= thr).sum(axis=1)
        first = {}
        for label, thr in (("caution_0.15", 0.15), ("impassable_0.30", 0.30)):
            k = need if label.startswith("impass") else 1
            idx = np.nonzero(n_ge(thr) >= k)[0]
            first[label] = float(t_h[idx[0]]) if idx.size else None
        pk = d.max(axis=1)
        peak_i = int(pk.argmax())
        rec = {"n_cells": d.shape[1],
               "first": {k: (None if v is None else
                             {"model_h": round(v, 2), "utc": utc_of(v)})
                         for k, v in first.items()},
               "peak_maxcell_m": round(float(pk[peak_i]), 3),
               "peak_utc": utc_of(float(t_h[peak_i])),
               "final_maxcell_m": round(float(pk[-1]), 3)}
        if zfull is not None:
            jj = np.asarray(g["j"]); ii = np.asarray(g["i"])
            eta = d + zfull[jj, ii][None, :]
            emax = eta.max(axis=1)
            rec["stage_series_max_m"] = {
                "peak_m": round(float(emax.max()), 3),
                "peak_utc": utc_of(float(t_h[int(emax.argmax())])),
            }
            out["groups"][name] = rec
            out["groups"][name]["_eta"] = emax  # internal
        else:
            out["groups"][name] = rec
    # lead times
    for key, groups, obs_utc, prec, desc in ANCHORS:
        gname = next((g for g in groups if g in out["groups"]), None)
        if gname is None:
            continue
        rec = out["groups"][gname]
        warn = rec["first"]["impassable_0.30"] or rec["first"]["caution_0.15"]
        row = {"anchor": key, "desc": desc, "probe": gname,
               "observed_utc": obs_utc, "precision": prec}
        if warn is None:
            row["model_warning"] = None
            row["lead_min"] = None
        else:
            wh = warn["model_h"]
            row["model_warning"] = warn
            row["lead_min"] = round((hours(obs_utc) - wh) * 60.0, 0)
        out["leads"].append(row)
    # stage checks
    for key, gname, obs_utc, obs_eta_m, desc in STAGE_CHECKS:
        rec = out["groups"].get(gname)
        if rec is None or "_eta" not in rec:
            continue
        h = hours(obs_utc)
        if h <= float(t_h[-1]):
            k = int(np.searchsorted(t_h, h))
            model_eta = float(rec["_eta"][min(k, len(t_h) - 1)])
            out["stage_checks"].append(
                {"check": key, "desc": desc, "observed_utc": obs_utc,
                 "observed_eta_m": round(obs_eta_m, 3),
                 "model_eta_m": round(model_eta, 3),
                 "error_m": round(model_eta - obs_eta_m, 3),
                 "datum_note": "NGVD29-vs-NAVD88 ~0.15-0.2 m unresolved"})
        else:
            out["stage_checks"].append(
                {"check": key, "desc": desc, "observed_utc": obs_utc,
                 "note": "beyond simulated window"})
    for rec in out["groups"].values():
        rec.pop("_eta", None)
    return out


def main():
    for rd in sys.argv[1:]:
        run_dir = os.path.join(HERE, rd)
        res = analyze(run_dir)
        with open(os.path.join(HERE, f"timing_{os.path.basename(rd)}.json"), "w") as f:
            json.dump(res, f, indent=2)
        print(f"== {rd} ==")
        for name, rec in res["groups"].items():
            fi = rec["first"]
            fmt = lambda v: "never" if v is None else f"{v['utc']}"
            print(f"  {name:<28} n={rec['n_cells']:<4} "
                  f"caution {fmt(fi['caution_0.15']):<13} "
                  f"impass {fmt(fi['impassable_0.30']):<13} "
                  f"peak {rec['peak_maxcell_m']:>6.2f} m @ {rec['peak_utc']}")
        for row in res["leads"]:
            if row["lead_min"] is None:
                print(f"  LEAD {row['anchor']:<22} model: never crossed "
                      f"(obs {row['observed_utc']})")
            else:
                print(f"  LEAD {row['anchor']:<22} model "
                      f"{row['model_warning']['utc']} vs obs {row['observed_utc']}"
                      f" -> {row['lead_min']:+.0f} min [{row['precision']}]")
        for sc in res["stage_checks"]:
            if "model_eta_m" in sc:
                print(f"  STAGE {sc['check']:<21} model {sc['model_eta_m']:.2f} m"
                      f" vs obs {sc['observed_eta_m']:.2f} m "
                      f"(err {sc['error_m']:+.2f} m) @ {sc['observed_utc']}")
            else:
                print(f"  STAGE {sc['check']:<21} {sc['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
