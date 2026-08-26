#!/usr/bin/env python3
"""One table, every corridor point, including the ones that failed.

Usage: python3 consolidated_table.py

Joins, per probe:
  - the STATIC freeboard prediction made from terrain alone, before any nest ran
  - the DYNAMIC outcome from the completed fine nest
  - whether the prediction was CONFIRMED, FAILED, or UNTESTABLE
  - the caveats that disqualify a row from being read as evidence

Rows that cannot be scored are printed with the reason, not dropped. A table
that silently omits its failures reports a skill the study does not have.
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IMPASS = 0.30

NESTS = {"pataskala_c": "corridor_analysis_pataskala.json",
         "franklinton_c": "corridor_analysis_franklinton.json"}


def load_dynamic():
    """corridor_analysis.py overwrites one file, so read each nest's own copy
    from the report repo where the per-nest results were archived."""
    out = {}
    repo = "/home/user/aqua-sim-ohio-report-/analysis"
    for f, nest in (("corridor_analysis_pataskala_c.json", "pataskala_c"),
                    ("corridor_analysis_franklinton_c.json", "franklinton_c")):
        p = os.path.join(repo, f)
        if not os.path.exists(p):
            continue
        for blk in json.load(open(p)):
            for r in blk["probes"]:
                out[r["probe"]] = dict(r, nest=nest, complete=blk.get("complete"))
    return out


def main():
    static = {r["probe"]: r for r in
              json.load(open(os.path.join(HERE, "smear_geometry.json")))["rows"]}
    dyn = load_dynamic()
    audit = {r["run_dir"]: r for r in
             json.load(open(os.path.join(HERE, "boundary_velocity_audit.json")))["runs"]}
    edge = {}
    for run, a in audit.items():
        for g in a["probe_groups"]:
            edge[g["group"]] = g["min_dist_to_edge_cells"]

    rows = []
    for name, s in sorted(static.items()):
        d = dyn.get(name)
        fb = s["freeboard_to_pavement_m"]
        pred = ("coarse floods a DRY road" if fb > 0.5 else
                "coarse bed ~= pavement" if abs(fb) <= 0.5 else
                "coarse bed ABOVE road (under-reports)")
        r = {"nest": s["nest"], "probe": name,
             "z_road_med_m": s["z_road_med_m"], "z_parent_m": s["z_parent_m"],
             "freeboard_to_pavement_m": fb, "n_chan_cells": s["n_chan_cells"],
             "static_prediction": pred,
             "d_edge_cells": edge.get(name)}
        if d is None:
            r["outcome"] = "NOT RUN — no completed fine nest covers this probe"
            r["scoreable"] = False
            rows.append(r); continue
        r.update({"nest_road_peak_m": d["road_peak_m"],
                  "nest_channel_peak_m": d["channel_peak_m"],
                  "road_minus_channel_m": d["road_minus_channel_peak_m"],
                  "diagnosis": d["diagnosis"],
                  "road_impassable_utc": d["road_impassable_utc"]})
        floods = d["road_peak_m"] >= IMPASS
        de = edge.get(name)
        if de is not None and de <= 2:
            r["outcome"] = "UNUSABLE — probe sits on the domain boundary, where the parent stage is imposed"
            r["scoreable"] = False
        elif fb > 0.5:
            r["outcome"] = ("PREDICTION CONFIRMED — fine grid keeps the road below the "
                            "impassable threshold while the channel is deep" if not floods
                            else "PREDICTION FAILED — fine grid floods the road anyway")
            r["scoreable"] = True
            r["why"] = (None if not floods else
                        ("no channel cells at this probe — the water is rain-on-grid "
                         "ponding, not smeared channel water"
                         if s["n_chan_cells"] == 0 else "channel present; cause not isolated"))
        elif abs(fb) <= 0.5:
            r["outcome"] = ("PREDICTION CONFIRMED — coarse bed is the road surface and the road floods"
                            if floods else "PREDICTION FAILED — coarse bed is the road but it stays dry")
            r["scoreable"] = True
        else:
            r["outcome"] = ("UNTESTED — prediction is that the coarse grid MISSES flooding, "
                            "but the fine grid does not flood this road either, so there was "
                            "nothing to miss")
            r["scoreable"] = False
        rows.append(r)

    sc = [r for r in rows if r.get("scoreable")]
    n_conf = sum("CONFIRMED" in r["outcome"] for r in sc)
    out = {"generated_from": "smear_geometry.json + per-nest corridor_analysis + boundary_velocity_audit.json",
           "impassable_threshold_m": IMPASS,
           "scoreable_rows": len(sc), "confirmed": n_conf,
           "failed": len(sc) - n_conf,
           "unscoreable_rows": len(rows) - len(sc),
           "note": "unscoreable rows are retained with their reason. A table that drops "
                   "its failures reports a skill the study does not have.",
           "rows": rows}
    p = os.path.join(HERE, "consolidated_table.json")
    json.dump(out, open(p, "w"), indent=2)

    print(f"{'nest':<14}{'probe':<30}{'freebd':>8}{'chan':>6}{'edge':>6}"
          f"{'road pk':>9}{'chan pk':>9}  outcome")
    for r in rows:
        cp = r.get("nest_channel_peak_m")
        rp = r.get("nest_road_peak_m")
        print(f"{r['nest'][:13]:<14}{r['probe'][:29]:<30}"
              f"{r['freeboard_to_pavement_m']:>+8.2f}{r['n_chan_cells']:>6}"
              f"{(r['d_edge_cells'] if r['d_edge_cells'] is not None else -1):>6}"
              f"{(rp if rp is not None else float('nan')):>9.2f}"
              f"{(cp if cp is not None else float('nan')):>9.2f}  {r['outcome'][:64]}")
    print(f"\nscoreable {len(sc)}: {n_conf} confirmed, {len(sc)-n_conf} failed; "
          f"{len(rows)-len(sc)} not scoreable")
    print("->", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
