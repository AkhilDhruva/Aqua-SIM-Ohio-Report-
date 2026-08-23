#!/usr/bin/env python3
"""Columbus, Ohio — Aug 19-20, 2026 flood: blind hindcast (SIDE TASK).

Standalone script; imports aqua_sim as an installed library. Writes NOTHING
into the aqua-sim repository — all inputs/outputs live in this side folder.

BLIND PROTOCOL
==============
This run is constructed from CAUSE data only (published rainfall forcing +
public terrain). The prediction is frozen (content-hashed run_id) BEFORE any
list of observed flooded locations is consulted. Sensor placement is
terrain-driven (auto low points) — no human hand places anything, so nothing
the operator has read can leak into the prediction. Scoring against observed
flooded areas happens afterward, in score_columbus.py.

CAUSE DATA (sources: NWS figures quoted by Spectrum News 1, WOSU, 10TV,
The Reporting Project, Aug 2026):
  * Event: overnight Aug 19 -> Aug 20, 2026.
  * Heaviest band (Franklin + Licking counties): 4-7 in (100-178 mm).
  * Columbus proper: 4-5 in; CMH event total 6.03 in.
  * Peak convective rates: 2-3 in/hr (50-75 mm/hr).
  * Antecedent: 11 consecutive rain days; >12 in on parts of Licking County
    in under two weeks -> soil saturated. Infiltration is therefore ZERO
    (physically correct for saturated antecedent conditions).
  * Storm drains overwhelmed -> modest effective drainage.

Two forcing variants bracket the observed band (same shape, scaled):
  * mid-band  ~137 mm (5.4 in) with 60 mm/hr peak hour
  * low-band  ~100 mm (3.9 in) with 44 mm/hr peak hour
"""

import json
import os
import sys
import time

from aqua_sim.config import SimConfig, SolverConfig, StormConfig
from aqua_sim.ingestion.dem import DEMSource
from aqua_sim.scenario import Scenario, _auto_sink_nodes, run_scenario

HERE = os.path.dirname(os.path.abspath(__file__))
TILES = [os.path.join(HERE, "tiles", f"USGS_13_{t}.tif")
         for t in ("n41w083", "n41w084", "n40w083", "n40w084")]

#: Greater Columbus: Franklin County metro + western Licking County
#: (chosen from the COUNTY-level rainfall footprint — cause data).
AOI = (-83.20, 39.80, -82.45, 40.20)

#: Overnight hyetograph, (start_hour, mm/hr): leading rain, two convective
#: bursts (peak inside the documented 50-75 mm/hr), trailing rain, then a
#: drain-down window with no rain.
HYETOGRAPH_MID = ((0.0, 8.0), (2.0, 45.0), (3.0, 60.0), (4.0, 8.0))
HYETOGRAPH_LOW = ((0.0, 6.0), (2.0, 33.0), (3.0, 44.0), (4.0, 6.0))
RAIN_HOURS = 6.0
SIM_HOURS = 12.0


def build(variant: str, dx: float = 60.0) -> Scenario:
    hyeto = HYETOGRAPH_MID if variant == "mid" else HYETOGRAPH_LOW
    grid = DEMSource(TILES, target_dx_m=dx, aoi_bounds=AOI,
                     max_cells=4_000_000).load()
    # Saturated antecedent soil: zero infiltration everywhere (see header).
    # Storm drains overwhelmed: 10 mm/hr capacity, half blocked.
    storm = StormConfig(
        rainfall_mm_per_hr=max(r for _, r in hyeto),   # headline figure
        duration_hours=RAIN_HOURS,
        drainage_capacity_mm_per_hr=10.0,
        drainage_blockage=0.5,
        hyetograph=hyeto,
    )
    config = SimConfig(
        storm=storm,
        solver=SolverConfig(cfl=0.7, total_time_s=SIM_HOURS * 3600.0,
                            output_interval_s=SIM_HOURS * 3600.0 / 24),
        aoi_name=(f"Greater Columbus OH — Aug 19-20 2026 hindcast "
                  f"({variant}-band) — screening resolution {dx:.0f} m"),
    )
    # Sensors: terrain-driven auto placement ONLY (blind protocol).
    nodes = _auto_sink_nodes(grid, count=10)
    return Scenario(grid=grid, config=config, nodes=nodes)


def main() -> int:
    dx = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    frozen = {}
    for variant in ("mid", "low"):
        out = os.path.join(HERE, f"run_{variant}")
        t0 = time.time()
        sc = build(variant, dx)
        print(f"[{variant}] grid {sc.grid.nx}x{sc.grid.ny} = "
              f"{sc.grid.nx * sc.grid.ny / 1e3:.0f}k @ {dx:.0f} m "
              f"[{sc.grid.crs}]  (ingest {time.time() - t0:.0f}s)")
        t0 = time.time()
        man = run_scenario(sc, out)
        print(f"[{variant}] solve {(time.time() - t0) / 60:.1f} min: "
              f"{man['frame_count']} frames, peak {man['peak_depth_m']} m, "
              f"run_id {man['run_id']}")
        frozen[variant] = {
            "run_id": man["run_id"],
            "terrain_digest": man["provenance"]["terrain_digest"],
            "peak_depth_m": man["peak_depth_m"],
            "run_dir": out,
        }
    # FREEZE: the prediction is now these two run folders, identified by
    # content-hashed run_ids. Scoring happens in score_columbus.py AFTER this.
    with open(os.path.join(HERE, "frozen_prediction.json"), "w") as f:
        json.dump({"frozen_utc_note": "predictions frozen before effect data",
                   "aoi_wgs84": AOI, "variants": frozen}, f, indent=2)
    print("PREDICTION FROZEN ->", os.path.join(HERE, "frozen_prediction.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
