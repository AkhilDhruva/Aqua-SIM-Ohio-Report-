#!/usr/bin/env python3
"""Compile downloaded MRMS QPE grib2 files into compact forcing archives.

Reads qpe/qpe_inventory.json (written by the acquisition agent), crops each
field to the AOI plus margin, and writes qpe/fields_A.npz / fields_B.npz:
    times_end_utc (ISO strings), accum_mm (T, ny, nx) float32,
    transform (6,), shape, cadence_s, sha256 list (provenance).
Model time base: T0_UTC below; interval k covers [end_k - cadence, end_k].
"""

import glob
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import rasterio
from rasterio.windows import from_bounds

HERE = os.path.dirname(os.path.abspath(__file__))
QPE = os.path.join(HERE, "qpe")
AOI = (-83.20, 39.80, -82.45, 40.20)
MARGIN = 0.15            # degrees of slack so nests near edges still map inside
T0_UTC = datetime(2026, 8, 19, 18, 0, tzinfo=timezone.utc)


def parse_valid(name_or_iso):
    s = name_or_iso
    if s.endswith("Z"):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    # filename form ..._YYYYMMDD-HHMMSS.grib2
    base = os.path.basename(s)
    stamp = base.split("_")[-1].split(".")[0]
    return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)


def compile_product(files, cadence_s, out_path):
    recs = []
    ref_transform = None
    ref_shape = None
    for f in files:
        path = f["local_path"] if os.path.isabs(f["local_path"]) \
            else os.path.join(QPE, f["local_path"])
        valid = parse_valid(f.get("valid_time_utc") or path)
        with rasterio.open(path) as src:
            # MRMS stores lon as 230..300 East; AOI in that convention:
            lon_off = 360.0 if src.bounds.left > 180.0 else 0.0
            win = from_bounds(AOI[0] - MARGIN + lon_off, AOI[1] - MARGIN,
                              AOI[2] + MARGIN + lon_off, AOI[3] + MARGIN,
                              src.transform)
            arr = src.read(1, window=win).astype(np.float32)
            t = src.window_transform(win)
            transform = (t.a, t.b, t.c - lon_off, t.d, t.e, t.f)
        arr[arr < 0] = 0.0          # -1/-3 missing codes -> treat as zero rain
        if ref_transform is None:
            ref_transform, ref_shape = transform, arr.shape
        else:
            assert arr.shape == ref_shape, f"shape drift in {path}"
        recs.append((valid, arr, f.get("sha256", "")))
    recs.sort(key=lambda r: r[0])
    times = [r[0] for r in recs]
    stack = np.stack([r[1] for r in recs])
    np.savez_compressed(
        out_path,
        times_end_utc=np.array([t.isoformat() for t in times]),
        accum_mm=stack,
        transform=np.array(ref_transform, dtype=np.float64),
        shape=np.array(ref_shape),
        cadence_s=np.array([cadence_s]),
        sha256=np.array([r[2] for r in recs]),
        t0_utc=np.array([T0_UTC.isoformat()]),
    )
    total_series = stack.mean(axis=(1, 2))
    print(f"  {os.path.basename(out_path)}: {len(times)} fields "
          f"{times[0]:%m-%d %H:%M}Z..{times[-1]:%H:%M}Z, "
          f"crop {ref_shape}, AOI-crop mean total {stack.sum(axis=0).mean():.1f} mm, "
          f"peak interval mean {total_series.max():.2f} mm")
    return times


def intervals_from_npz(npz_path):
    """RainSeries-ready (t_start_s, t_end_s, field) list + transform/shape."""
    d = np.load(npz_path, allow_pickle=False)
    cadence = float(d["cadence_s"][0])
    t0 = datetime.fromisoformat(str(d["t0_utc"][0]))
    out = []
    for k, iso in enumerate(d["times_end_utc"]):
        end = datetime.fromisoformat(str(iso))
        te = (end - t0).total_seconds()
        out.append((te - cadence, te, d["accum_mm"][k]))
    return out, tuple(d["transform"]), tuple(int(x) for x in d["shape"])


def main():
    inv = json.load(open(os.path.join(QPE, "qpe_inventory.json")))
    for tag in ("A", "B"):
        prod = inv["products"].get(tag)
        if not prod or not prod.get("files"):
            print(f"  product {tag}: MISSING from inventory")
            continue
        cadence_s = 60.0 * float(prod.get("cadence_min", 60))
        compile_product(prod["files"], cadence_s,
                        os.path.join(QPE, f"fields_{tag}.npz"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
