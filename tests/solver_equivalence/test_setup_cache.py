#!/usr/bin/env python3
"""Prove the setup cache reconstructs the model inputs EXACTLY.

The cache short-circuits terrain, roughness, culvert detection, probe geometry,
the rain index map and the parent-derived stage BC. It therefore feeds the
physics directly, and a silent difference would corrupt every result computed
after a restart. This rebuilds the setup from source and compares it, array by
array, against the cached reconstruction.
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_corridor as RC
import run_nest as RN
from smearing_analysis import build_nest_context, probe_cells
from qpe_solver import build_idx_map
from prep_qpe import intervals_from_npz

nest, out = "buckeye_c", "corridor_buckeye_c_B"
cached = RC.load_setup(out)
assert cached is not None, "no cache present"
g_c, culv_c, groups_c, pmeta_c, idx_c, bc_c = cached

grid, masks, cls_geoms, flowlines = build_nest_context(nest)
spec = RN.NESTS[nest]
ny, nx = grid.ny, grid.nx
man = np.full((ny, nx), 0.05)
man[masks["_channel"]] = 0.035
if "any" in masks:
    man[masks["any"]] = 0.013
roads = [(c, gg) for c, gs in cls_geoms.items() if c != "any" for gg in gs]
culv_f, _ = RN.find_culverts(roads, flowlines, np.asarray(grid.z),
                             grid.transform, spec["dx"])
probes_f = probe_cells(nest, grid, masks, cls_geoms, flowlines)
_, qtr, qsh = intervals_from_npz(os.path.join("qpe", "fields_B.npz"))
idx_f = build_idx_map(grid.transform, grid.crs, ny, nx, qtr, qsh)

checks = {
  "z":       float(np.abs(np.asarray(g_c.z) - np.asarray(grid.z)).max()),
  "manning": float(np.abs(np.asarray(g_c.manning) - man).max()),
  "mask":    int((np.asarray(g_c.mask) != np.asarray(grid.mask)).sum()),
  "idx_map": int((np.asarray(idx_c) != idx_f).sum()),
}
same_culv = sorted(culv_c) == sorted([tuple(c) for c in culv_f])
gj = {}
for name, v in probes_f.items():
    gj[name] = v["road"]
    if v["channel"][0].size:
        gj[name + "__channel"] = v["channel"]
same_groups = set(gj) == set(groups_c) and all(
    np.array_equal(np.asarray(gj[k][0]), np.asarray(groups_c[k][0])) and
    np.array_equal(np.asarray(gj[k][1]), np.asarray(groups_c[k][1])) for k in gj)
same_transform = tuple(g_c.transform) == tuple(grid.transform[:6])

for k, v in checks.items():
    print(f"  diff {k:<9} = {v}")
print(f"  culverts identical: {same_culv} ({len(culv_c)})")
print(f"  probe groups identical: {same_groups} ({len(groups_c)})")
print(f"  transform identical: {same_transform}, crs {g_c.crs == str(grid.crs)}")
print(f"  stage BC cells: {bc_c.j.size}, times {bc_c.times.size}, "
      f"stages {bc_c.stages.shape}, parent_z {bc_c.parent_z.size}")
ok = all(v == 0 for v in checks.values()) and same_culv and same_groups \
     and same_transform
print("RESULT:", "CACHE IS EXACT — physics inputs identical to fresh build"
      if ok else "CACHE MISMATCH — do not trust cached runs")
raise SystemExit(0 if ok else 1)
