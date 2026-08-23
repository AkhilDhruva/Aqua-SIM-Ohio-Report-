# Aqua-Sim Columbus Validation — Central Ohio flood, 19–20 August 2026

An independent, blind hindcast of the Franklin and Licking County flood, used to
test what a rainfall-driven flood model can and cannot be trusted to decide.

This repository is **the validation study**, not the simulator. The engine lives
in [`akhildhruva/aqua-sim`](https://github.com/AkhilDhruva/aqua-sim) and was
consumed here as an installed library and **never modified**:

```
engine repository: akhildhruva/aqua-sim
engine commit:     0b452c9d5   (pinned; see evidence/source_manifest.json)
```

## Headline results

| Claim | Status |
|---|---|
| Regional screening identifies the flooded areas | **Supported** — 16/17 with frozen scorer; chance 3–7% |
| Radar-only (operational-latency) forcing retains that skill | **Supported, narrowly** — this hindcast only |
| A 60 m grid can decide whether a road is open | **Refuted** — quantified below |
| "11.6-hour early warning of the I-70 closure" | **RETRACTED** — see `analysis/case_ab/` |
| Model reproduces the multi-day fluvial crest | **Refuted** — structural defect, documented |
| Traffic displaced onto US-40 (National Road) | **Not testable** — data unreachable |

The central quantitative finding: at the I-70 crossing of the South Fork Licking
River, the 60 m grid carries a bed elevation **2.07 m below the surveyed
carriageway**. When that cell reports the interstate impassable, its water
surface is still **1.77 m below the real pavement**. It is seeing the channel,
not the road. Across twelve corridor points, three invent closures and four
would miss real street flooding.

## Evidentiary standing — read this before citing anything

Claims in this repository are supported at three distinct strengths, and they
are not interchangeable.

**Level 1 — strongest: content-addressed reproducibility.** Every run carries a
`run_id` that is a hash of its inputs and provenance (e.g. `1e1646c983b3b8bc`).
Re-running identical frozen inputs regenerates the identical id. This
establishes *prediction identity* independently of any clock.

**Level 2 — supporting chronology: filesystem metadata.** `PROVENANCE_MANIFEST.json`
records SHA-256 and mtime for every file, evidencing the order of work:

```
04:06:32Z  frozen_prediction.json   ← predictions sealed
04:08:37Z  observed_flooding.json   ← effect data written, 2m05s later
04:09:03Z  validation_report.json   ← scoring
```

This is machine-recorded historical metadata, **not cryptographic attestation**.
Treat it as supporting evidence of ordering, never as proof.

**Level 3 — process statements.** Phrases in the pre-registration such as
"before any effect-side results were read" are recorded process claims. They are
preserved as written and are **not** upgraded into timestamp proof.

The first Git commit here proves only that these files existed in this form no
later than that commit. It does **not** retroactively prove the original air
gap. Work from this tag forward carries genuine Git transaction history.

## Layout

```
prereg/       predictions and design, sealed before outcomes were consulted
analysis/     scoring, QPE validation, geometry and culvert audits, Case A/B
runs/         manifests, probe series, summary metrics (no bulk arrays)
evidence/     effect corpus, gauge metadata, source manifest with checksums
figures/      dashboard renders and study figures
briefing/     policy briefing (HTML + PDF) and the Phase 1 report
reproduction/ acquisition and run scripts
tests/        solver-equivalence tests for the spatial-forcing extension
```

`METHODS.md` documents the protocol, `CLAIMS_STATUS.md` fixes the standing of
every claim including the retraction, and `LIMITATIONS.md` bounds all of them.

## What is deliberately not committed

The 8.8 GB of public bulk inputs — 1 m LiDAR, MRMS radar grids, hydrography and
road shapefiles — are re-downloadable and are identified instead by URL, subset,
and checksum in `evidence/source_manifest.json` and
`analysis/qpe_validation/qpe_inventory.json`. Solver restart checkpoints are
also excluded; they are regenerable and support no claim.

## Reproducing

```bash
pip install numpy rasterio fiona shapely scipy
python3 reproduction/run_columbus.py      # Phase 1 uniform-forcing hindcast
python3 reproduction/run_parent_qpe.py B  # 60 m parent, MRMS multi-sensor QPE
python3 analysis/scoring/score_columbus.py
python3 tests/solver_equivalence/test_qpe_solver.py
```

Run ids are content-derived, so identical inputs reproduce
`1e1646c983b3b8bc` (mid) and `b322e85c559c8728` (low) exactly.

## Status

Corridor nests at 6–8 m were still solving when this archive was created; see
`runs/checkpoint_metadata/corridor_status.json`. Their results land in later
tags. The findings above rest on surveyed elevations and observed gauge timing
and do not depend on them.

**This is independent research. It is not a product of, endorsed by, or reviewed
by ODOT, the National Weather Service, USGS, or any Ohio agency, and must not be
used operationally without agency review and independent verification.**
