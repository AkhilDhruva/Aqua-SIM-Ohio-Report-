# aqua-sim — Handoff, Provenance and Chronology

> **Read this before regenerating.** This document is produced by
> `handoff/generate_handoff.py`, which walks every tracked file and the
> entire commit history. **Regenerate it only when you are stuck, onboarding
> a new machine, or seeding a new repository.** Routine work should append
> to the Chronology section by hand. Regenerating on every change wastes
> effort and, in an agent session, tokens.

Generated `2026-09-09 22:55:12Z` at commit `f08a8f2` · 130 tracked files · 27 commits

---

## 1. What this project is

**aqua-sim** is a hydrodynamic flood simulator: given rainfall and terrain,
it computes where water goes, how deep it gets, how fast it moves, and when.
Its engine repository `akhildhruva/aqua-sim` states in `docs/PLANNING.md` that
it *“supersedes and hardens the original ‘Project Deluge’ handoff note”*,
and §4 of that document lists what it fixed: CFL-limited adaptive timestepping,
bare-earth DTM as the flow floor with buildings as obstacles, a well-balanced
wet/dry treatment, infiltration and drainage as explicit losses, and real
boundary conditions. **aqua-sim is what Deluge became, not a separate project.**

**Lineage, corrected.** The engine was built in July 2026 with **New York** as
its validation ground: a Manhattan demo scenario and the Hurricane Ida (2021)
validation on real USGS terrain landed on 2026-07-05, a five-borough NYC metro
scenario with the NumPy backend on 2026-07-20, and a building-aware NYC
demonstration from official footprints on 2026-07-22. An earlier version of
this document stated that no New York work existed; that was wrong — it is
in the engine repository under `validation/`, `scenario.py` and
`ingestion/buildings.py`, named by the storm rather than the city. The Ohio
study is the engine's **second** event, run against the engine frozen at its
fifteenth and final commit `0b452c9`.

This repository is not the engine. It is the *study record* for one
application of it: a blind hindcast of the Central Ohio flood of
19–20 August 2026, asking a narrow question — can a rainfall flood model
be trusted to decide whether a road is open?

## 1b. The New York work (engine repository, July 2026)

| Date | What | Where | Outcome |
|---|---|---|---|
| 2026-07-05 | Manhattan demo scenario | `scenario.build_manhattan_demo` | First runnable scenario on the reference solver. |
| 2026-07-05 | **Hurricane Ida 2021 validation** — the record 80 mm hour at Central Park over USGS 3DEP 10 m terrain, scored against six subway stations documented as flooded | `validation/ida2021.py`, `docs/VALIDATION.md`, `docs/validation/ida2021_report.json` | POD **0/6** at design drainage, **0/6** surcharged-to-half, **1/6** with drainage failed (Dyckman St, breach at t≈83 min). Basin-scale behaviour reproduced (~3.6 × 10⁶ m³ ponded over ~62,000 wet cells); street-scale detection not. The first attempt scored 0/6 and is kept in the record; the corrections that followed are argued from event documentation, not tuned to the score. False-alarm rate explicitly out of scope. Verdict in the engine's own words: *partial validation honestly scored — not failed, not passed.* |
| 2026-07-20 | NumPy backend + DEM mosaicking + **five-borough NYC metro scenario** (2.57 M cells at 30 m over n41w074 + n41w075) | `physics/swe_numpy.py`, `ingestion/dem.py`, `scenario.build_nyc_metro_scenario` | ~20× faster than the reference solver; equivalence enforced to ≤1e-9 depth by `tests/test_swe_numpy.py`. This is the solver the Ohio study used. |
| 2026-07-22 | **Building-aware NYC demonstration** from the official NYC Open Data footprints (nqwf-w8eh) | `ingestion/buildings.py`, `viz/buildings-layer.js` | Coverage-fraction rasterisation, closed obstacle cells at dx ≤ 10 m, extruded viewer layer with LOD. Provenance includes dataset id, licence, CRS chain and source SHA-256. |

Why it matters for Ohio: the NumPy backend, DEM mosaicking, sink-node probing,
content-derived `run_id`, and the honesty conventions (keep the failed attempt,
state what is not claimed, never tune to the score) were all built for New York
and carried unchanged into the Ohio study. Buildings were *not* used in Ohio
because footprint sources were unreachable from that host.

## 2. Technology stack

| Layer | Choice | Note |
|---|---|---|
| Numerics | Local-inertial 2D shallow water (Bates et al. 2010) | Explicit, CFL-limited. Omits advection — the reason Froude > 1 is outside its envelope. |
| Implementation | Pure NumPy, vectorised | Single-core. See ML-1. |
| Timestep | Adaptive, dt ≤ cfl·dx/(\|v\|+√(gh)), cfl 0.7, max 60 s | Global — a few fast cells throttle the whole domain. See ML-3. |
| Terrain | USGS 3DEP 1 m LiDAR → resampled to nest dx | Bare earth. Buildings absent — footprint sources were unreachable. |
| Rainfall | NOAA MRMS QPE, radar-only 15 min (A) and multi-sensor hourly (B) | Applied per cell, per timestep. Never scaled to fit observations. |
| Hydrography / roads | USGS NHD, USGS NTD | Culvert orifices inferred at road×stream crossings with continuous embankment. |
| Nesting | Dirichlet stage strips from the 60 m parent, gated by parent wetness | Nests also receive full rain-on-grid. |
| River reference | NOAA NWM v3 analysis_assim | USGS-nudged proxy, discharge only — so timing and shape, never stage RMSE. |
| Runtime | Python 3.11 / Ubuntu 24.04 | numpy 2.4.6, scipy 1.17.1, rasterio 1.4.4, fiona 1.10.1, shapely 2.1.2 — pinned, because the equivalence gate depends on them. |
| Viewer | Three.js, reads pre-computed frames | Decoupled from the solver. |

## 3. How validation works, and the guard rails against cheating

The design problem is that a model tuned against a known outcome will
reproduce that outcome and prove nothing. Five mechanisms are used, in
descending order of how hard they are to game.

**1. Temporal ordering with a content-derived seal.** The simulator receives
only cause-side data — the rainfall that fell and the shape of the ground.
Predictions are then hashed into a `run_id` derived from their own content and
written to `runs/manifests/`. Only afterwards is effect-side data (what
actually flooded, when roads closed) collected and scored. A prediction cannot
be edited after the fact without changing its `run_id`.

**2. Progressive rain injection, causally.** Rainfall enters cell by cell,
timestep by timestep, in real chronological order up to and through the event.
The solver is causal: state at hour *t* cannot depend on rain after *t*. A
single QPE-A-forced run is therefore already an operational replay, and warning
times read off it are honest, with product latency added when quoted.

**3. Pre-registration with logged amendments.** Domains, resolutions,
thresholds (0.15 m caution, 0.30 m impassable, from FHWA/NWS guidance), roughness
and scoring rules were fixed in `prereg/` before effect research. Every later
change is an amendment carrying its reason and an explicit flag for whether it
postdates effect exposure. Two do, and say so.

**4. No calibration against the answer.** Rainfall is compared to gauges over
matched accumulation windows and the bias is *reported, never applied*. No
geometry, roughness or threshold was ever adjusted to improve agreement.

**5. Base rates and blinding.** Perfect detection scores were distrusted and
tested against a matched random baseline, which exposed a ~90% neighbourhood
base rate and forced a move to a continuous permutation test. Culvert detection
was re-tested on blinded fixed-seed samples and reported as precision.

**Evidence hierarchy used throughout:** content hashes (strongest) →
filesystem timestamps and Git transaction history (supporting, described as
machine-recorded metadata rather than cryptographic attestation) → prose
(process statements only, never evidence).

## 4. What the Ohio study established

| Finding | Status |
|---|---|
| Regional 60 m screening places documented flood locations in its deepest water, against a matched random baseline | SUPPORTED |
| A 60 m grid can support road open/closed decisions | **REFUTED** — at three of twelve points it declares a road impassable while the surveyed pavement is 1.77–4.15 m above its water surface |
| The apparent 11.6-hour warning on the I-70 closure was a lead time | **RETRACTED** — the signal precedes the upstream gauge peak, so it cannot be the same wave. Case B |
| Sub-grid smearing operates dynamically | SUPPORTED at Pataskala — SR-310 carries 4.28 m in the channel while the carriageway never reaches 0.30 m |
| A large freeboard means the coarse signal is false | **BOUNDED** — W Broad St has the study's largest freeboard (+4.15 m) and the road floods anyway, because that cell contains no watercourse. A mismatch marks a closure *unverified*, not false |
| Fine grids improve timing | **NO** — the one gauge well inside a fine domain peaks 153 minutes early |
| The model reproduces the multi-day fluvial crest that closed I-70 | REFUTED — the scalar drainage term linearly drains routed river water; no lake storage, spillway, baseflow or out-of-domain inflow is represented |
| Flooding rerouted traffic onto US-40 | **NOT TESTABLE** — no traffic observations. What *is* shown is that US-40 never reached the impassable threshold while Main St peaked at 3.69 m: the detour's physical precondition held |

**Scoreboard: 5 of 12 corridor points are scoreable — 4 confirmed, 1 refuted.**
The other seven are retained with the reason each fails: four lie in the
Buckeye nest, which never completed; one sits on a domain boundary where its
water level is imposed rather than computed; two carry a prediction that the
coarse grid *misses* flooding, which cannot be confirmed because the fine grid
does not flood those roads either.

## 4b. Compute profile — what actually sizes a machine

Measured on this host against the frozen engine, each nest in its own
process so the RSS high-water mark is per-case. Synthetic terrain at the real
grid dimensions; 30 solver steps to realise every lazily-allocated temporary.

| Nest | Grid | Cells | Peak RSS | Bytes/cell |
|---|---|---|---|---|
| franklinton_c | 698 × 628 @ 6 m | 438,344 | 122 MiB | 292 |
| pataskala_c | 619 × 1239 @ 8 m | 766,941 | 189 MiB | 258 |
| buckeye_c | 937 × 727 @ 6 m | 681,199 | 166 MiB | 256 |
| fixed overhead | 10 × 10 control | 100 | 32 MiB | — |

This is the **solver working set**. The full runner also holds accumulated
hourly snapshots (~3.3 MiB per frame for Franklinton, so ~67 MiB over a 20-hour
run), the probe history, the QPE rain series, the stage-BC arrays and the setup
cache. A realistic full-run peak is therefore roughly **0.25–0.4 GB per nest**.

**Consequence for sizing.** RAM is not the binding constraint and does not pick
the plan: four concurrent nests need well under 2 GB between them, which every
small VPS already has several times over. **Cores are the constraint**, because
the solver is single-threaded by construction (ML-1) and the only available
parallelism is running separate nests side by side. One core per concurrent run,
plus one spare. Four concurrent runs therefore want a 4–6 core box, and paying
for RAM beyond ~4 GB buys nothing here.

The engine is frozen at `0b452c9` and the inner loop must **not** be optimised:
any change to the arithmetic breaks bit-identical reproduction, which is the
only cross-host gate this study has.

## 5. Chronology with provenance

Every row is a real Git transaction: the timestamp is recorded by Git at the
moment of the change, and the SHA is content-derived over the tree.

| # | UTC | Repo | Commit | Change and why it mattered |
|---|---|---|---|---|
| 1 | 2026-07-04 21:52 | ENGINE | `cb17b7c` | Plan Flood Zone Risk Simulator engine + Phase 0 scaffold |
| 2 | 2026-07-04 23:50 | ENGINE | `b4b2379` | Initial commit |
| 3 | 2026-07-04 23:52 | ENGINE | `b3fd8ec` | Add ready-to-go project scaffold |
| 4 | 2026-07-05 01:17 | ENGINE | `653338f` | Implement local-inertial shallow-water solver + Manhattan scenario |
| 5 | 2026-07-05 01:20 | ENGINE | `8ae378e` | Add per-frame provenance headers and solver-side breach records |
| 6 | 2026-07-05 01:32 | ENGINE | `f68bd0e` | Implement Phase 1: real GeoTIFF DEM ingestion (DEMSource) |
| 7 | 2026-07-05 02:46 | ENGINE | `c1b65f7` | Implement Phase 4: Three.js flood telemetry dashboard |
| 8 | 2026-07-05 03:09 | ENGINE | `619caf8` | Fix 10 verified review findings across solver, ingestion, export, viewer |
| 9 | 2026-07-05 06:08 | ENGINE | `b7f7c79` | Add Hurricane Ida 2021 historical validation on real USGS terrain |
| 10 | 2026-07-05 06:42 | ENGINE | `e8fd8c6` | UI: station markers, kinetic-speckle fix, node export, wider run input |
| 11 | 2026-07-20 07:08 | ENGINE | `13268b6` | Add NumPy solver backend, DEM mosaicking, NYC metro scenario + review fixes |
| 12 | 2026-07-22 08:11 | ENGINE | `b86bd40` | Add NYC building-aware demonstration: official footprints, physics + viewer |
| 13 | 2026-07-22 08:58 | ENGINE | `0e03afb` | Fix building-review findings: determinism, MultiPolygon, provenance, viewer |
| 14 | 2026-07-22 13:05 | ENGINE | `407bd02` | Phase 6A: NYC hydraulic surface conditioning |
| 15 | 2026-07-23 01:21 | ENGINE | `f603039` | Fix building rendering noise: terrain double-draw, slivers, lighting |
| 16 | 2026-07-23 01:23 | ENGINE | `c5795f7` | Ignore viz/ny_run (regenerable complete-NY area run, ~58 MB) |
| 17 | 2026-07-24 18:14 | ENGINE | `48bb358` | Add named-area scenario builder + multi-tile CLI |
| 18 | 2026-07-24 18:15 | ENGINE | `014c6c6` | Document named-area CLI in README |
| 19 | 2026-07-24 18:30 | ENGINE | `2c5d514` | Viewer: cap breach banners, constant-size sensor markers |
| 20 | 2026-07-24 22:44 | ENGINE | `49d49bc` | Add session checkpoint + full operating instructions in README |
| 21 | 2026-07-24 22:45 | ENGINE | `0b452c9` | Remove stray empty cmpg_keys.txt |
| 22 | 2026-08-23 06:24 | STUDY | `8d83f19` | Archive Columbus blind-hindcast validation state |
| 23 | 2026-08-23 06:25 | STUDY | `fc996c4` | Record version identity by commit SHA (tag refs blocked by proxy) |
| 24 | 2026-08-23 06:28 | STUDY | `c5ff389` | v0.2 corridor checkpoint runner and restart-resilience evidence |
| 25 | 2026-08-23 06:29 | STUDY | `841c1a9` | Record v0.2 in version history |
| 26 | 2026-08-23 07:06 | STUDY | `da244b2` | v0.2.1 wall-aware checkpointing + wet-phase bitwise equivalence proof |
| 27 | 2026-08-23 07:06 | STUDY | `af05b77` | Record v0.2.1 in version history |
| 28 | 2026-08-23 08:03 | STUDY | `13b2aec` | v0.2.2 cache deterministic setup to survive a fast-recycling host |
| 29 | 2026-08-23 08:38 | STUDY | `88a617a` | v0.2.3 fix checkpoint livelock (interval exceeded host lifetime) |
| 30 | 2026-08-23 09:01 | STUDY | `e7f2397` | v0.2.4 restore parallel corridor execution (sequential was a misdiagnosis) |
| 31 | 2026-08-23 10:08 | STUDY | `6430528` | Record ML-3: open-boundary outflow throttles the Buckeye CFL |
| 32 | 2026-08-23 11:19 | STUDY | `19ce79a` | Record ML-4: solver only runs during active turns (~10% duty cycle) |
| 33 | 2026-08-25 19:15 | STUDY | `8e454f8` | Prepare Buckeye primary run for off-platform continuation |
| 34 | 2026-08-25 21:17 | STUDY | `f1ca0fa` | Interim: dynamics confirm the geometric smearing prediction at Pataskala |
| 35 | 2026-08-25 22:50 | STUDY | `b4900d8` | ML-3 generalises: open-boundary outflow throttles ALL corridor runs |
| 36 | 2026-08-25 23:59 | STUDY | `6369a98` | Resolve ML-3 for franklinton; record EF-6 (my own diagnostic was wrong) |
| 37 | 2026-08-26 03:04 | STUDY | `194397d` | pataskala_c COMPLETE at h=20.00 — smearing mechanism confirmed dynamically |
| 38 | 2026-08-26 05:42 | STUDY | `2046939` | VERSIONS: record v0.2.2 and v0.4 by commit SHA |
| 39 | 2026-08-26 13:02 | STUDY | `3801a38` | franklinton_c COMPLETE at h=20.00 — the mechanism gets a boundary, not just a confirmation |
| 40 | 2026-08-26 13:03 | STUDY | `bd65d02` | VERSIONS v0.5; consolidated corridor table that keeps its failures |
| 41 | 2026-08-26 13:09 | STUDY | `38cf3c7` | Briefing revised for the completed corridor runs; PDF regenerated |
| 42 | 2026-08-26 13:12 | STUDY | `e47f859` | Add a claims-vs-data verifier; it immediately caught an overstatement of mine |
| 43 | 2026-09-05 19:55 | STUDY | `2bd244c` | Render the corridor figures; plotting them caught an overshoot the audits missed |
| 44 | 2026-09-07 09:51 | STUDY | `d82ae9a` | Commit the handoff summary so its SHA-256 binds to a commit |
| 45 | 2026-09-07 09:54 | STUDY | `c91f131` | HANDOFF.md: full provenance, chronology and file inventory — plus one blocker |
| 46 | 2026-09-09 22:38 | STUDY | `807e459` | HANDOFF: correct the record — the New York work exists, and is the engine's validation ground |
| 47 | 2026-09-09 22:47 | STUDY | `cce318a` | Cross-host gate, first half: every input reproduces on a fresh host |
| 48 | 2026-09-09 22:51 | STUDY | `f08a8f2` | Report assembler: journal -> HTML/PDF/DOCX with every number traceable to a file |

## 6. File inventory with content hashes

All 130 tracked files, SHA-256 computed at generation time.

### spec

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `LIMITATIONS.md` | 3,005 | `5951759e453e914b…` | Bounds on every claim, stated so they cannot be read past. |
| `METHODS.md` | 5,402 | `eaaa901e738a1d04…` | Method of record: blind CAUSE/EFFECT protocol, pre-registration, scoring definitions. |
| `README.md` | 5,110 | `a23f1d2cf5a7c561…` | Entry point and the three-level evidence rule the study is scored under. |
| `VERSIONS.md` | 2,557 | `e0fcfbc2a8961d27…` | Version identity by commit SHA. Tag pushes return HTTP 403 in this environment, so SHAs are the versioning mechanism. |

### code

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `analysis/boundary_velocity_audit.py` | 8,598 | `6f42a76964b32b4d…` | Tests whether high face velocity is confined to the domain edge and whether it reaches the probes. Written after EF-6. |
| `analysis/consolidated_table.py` | 5,948 | `c01489bd53ad3289…` | Joins static freeboard prediction to dynamic outcome across all twelve corridor points, keeping unscoreable rows. |
| `analysis/verify_published_numbers.py` | 7,806 | `99bc6b6ef9b6b6a9…` | Re-checks every number quoted in CLAIMS_STATUS.md against its source file. Exits non-zero on drift. |
| `figures/make_figures.py` | 12,387 | `02b6b0d7ad2a67cd…` | Renders the corridor figures from committed derived series. Plotting these caught the wbroad overshoot. |
| `reproduction/extract_parent_bc.py` | 3,298 | `99de36d1d5f12d9a…` | Derives nest boundary stage series from completed parent frames. |
| `reproduction/gauge_timing.py` | 6,010 | `a10ba3e50163eb90…` | Hydrograph timing and shape against NWM analysis_assim. Timing only — no stage, so no stage RMSE. |
| `reproduction/make_pdf.py` | 3,902 | `49d5994a36bb5c92…` | Renders the briefing to print-ready PDF with embedded fonts. |
| `reproduction/qpe_solver.py` | 10,887 | `2dcf604880063e43…` | Solver extension: per-cell radar rain, nested Dirichlet stage BC, 60 s probes. Subclasses the frozen engine; edits nothing in it. |
| `reproduction/relaunch_corridors.sh` | 2,171 | `76743fa235f680e0…` | Priority-ordered parallel launcher, capped at nproc-1, honours .hold. |
| `reproduction/run_columbus.py` | 4,980 | `79f92bfb9aeea570…` | Original 60 m screening run and its AOI/tile definitions. |
| `reproduction/run_corridor.py` | 17,568 | `e43068a05f507b81…` | ENTRY POINT. Restart-resilient corridor runner: setup cache, wall-clock-aware checkpointing, deterministic step grid. |
| `reproduction/run_nest.py` | 22,741 | `3f5cd5ceb4ee75bc…` | Wide-extent nest runner, superseded by the corridor runner. |
| `reproduction/run_parent_qpe.py` | 7,022 | `a786c9bbb40e1181…` | 60 m parent run driven by MRMS QPE. |
| `tests/solver_equivalence/test_checkpoint_equivalence.py` | 5,820 | `76fcf52228b3e480…` | Equivalence and determinism tests. |
| `tests/solver_equivalence/test_qpe_solver.py` | 5,320 | `fa2469df0e432ef4…` | Equivalence and determinism tests. |
| `tests/solver_equivalence/test_setup_cache.py` | 2,970 | `cbc9d4c41079454f…` | Equivalence and determinism tests. |

### result

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `CLAIMS_STATUS.md` | 14,502 | `79ca4c6ecbf7fcf1…` | Every claim with a verdict — SUPPORTED, REFUTED, RETRACTED, NOT TESTABLE. The document that matters. |
| `analysis/boundary_velocity_audit.json` | 3,279 | `958a9eeff4a6626a…` | Analysis output. |
| `analysis/case_ab/case_ab_determination.json` | 4,229 | `4a991b51066c0890…` | Case A versus Case B determination and the formal retraction of the lead-time claim. |
| `analysis/case_ab/timing_analysis.py` | 8,033 | `4485e9a73a6588ec…` | Case A versus Case B determination and the formal retraction of the lead-time claim. |
| `analysis/case_ab/timing_run_qpeA_parent.json` | 2,942 | `fb8e845a8307db95…` | Case A versus Case B determination and the formal retraction of the lead-time claim. |
| `analysis/case_ab/timing_run_qpeB_parent.json` | 3,010 | `46157ad3fc10c382…` | Case A versus Case B determination and the formal retraction of the lead-time claim. |
| `analysis/case_ab/timing_run_qpeB_parent_ext.json` | 3,015 | `fbf3575ec9f769b0…` | Case A versus Case B determination and the formal retraction of the lead-time claim. |
| `analysis/consolidated_table.json` | 6,981 | `0b5f1afdacbce10c…` | The scoreboard: 5 of 12 scoreable, 4 confirmed, 1 refuted, 7 retained with reasons. |
| `analysis/corridor_analysis/corridor_analysis.json` | 1,549 | `3858ea17d28b0adc…` | Analysis output. |
| `analysis/corridor_analysis/corridor_analysis.py` | 5,128 | `2c00ddf1fe21f05c…` | Analysis output. |
| `analysis/corridor_analysis/corridor_analysis_INTERIM.json` | 3,364 | `5eb50bdfc7776549…` | Analysis output. |
| `analysis/corridor_analysis/gauge_timing.py` | 5,992 | `9d6c7542b8276c26…` | Analysis output. |
| `analysis/corridor_analysis/geometric_vs_dynamic_INTERIM.json` | 2,948 | `3261bc83b67c6ec7…` | Analysis output. |
| `analysis/corridor_analysis/smearing_analysis.py` | 12,031 | `8fb4281dbdf0e6a8…` | Analysis output. |
| `analysis/corridor_analysis_franklinton_c.json` | 1,391 | `a42942c0bc50b4ed…` | Analysis output. |
| `analysis/corridor_analysis_pataskala_c.json` | 2,036 | `95eecd0c097009b1…` | Analysis output. |
| `analysis/crosshost_gate_pataskala_inputs.json` | 31,912 | `1c0ad8d53f8af272…` | Analysis output. |
| `analysis/culvert_audit/audit_culverts.py` | 5,443 | `034c737fd1a806c1…` | Blinded fixed-seed culvert re-tests against 1 m LiDAR, reported as precision. |
| `analysis/culvert_audit/culvert_audit_buckeye.json` | 4,559 | `0d4cb5f588698bbf…` | Blinded fixed-seed culvert re-tests against 1 m LiDAR, reported as precision. |
| `analysis/culvert_audit/culvert_audit_franklinton.json` | 2,132 | `b1265b97aefd2412…` | Blinded fixed-seed culvert re-tests against 1 m LiDAR, reported as precision. |
| `analysis/culvert_audit/culvert_audit_pataskala.json` | 4,537 | `e55a28853bf13ac9…` | Blinded fixed-seed culvert re-tests against 1 m LiDAR, reported as precision. |
| `analysis/gauge_timing_corridor_franklinton_c_B.json` | 1,441 | `0cbbe3f07408306c…` | Analysis output. |
| `analysis/gauge_timing_corridor_pataskala_c_B.json` | 1,388 | `1c166003599066a3…` | Analysis output. |
| `analysis/geometry_audit/smear_geometry.json` | 6,231 | `6322a5ba266e550c…` | The freeboard diagnostic: carriageway elevation against the coarse cell's water surface at 'impassable'. |
| `analysis/geometry_audit/smear_geometry.py` | 6,022 | `9854d8ab4abaf684…` | The freeboard diagnostic: carriageway elevation against the coarse cell's water surface at 'impassable'. |
| `analysis/qpe_validation/matched_window_validation.json` | 1,179 | `982e74b4cf719b04…` | Rainfall checked against gauges over matched accumulation windows; bias reported, never applied. |
| `analysis/qpe_validation/prep_qpe.py` | 4,249 | `f705f7679bf804cd…` | Rainfall checked against gauges over matched accumulation windows; bias reported, never applied. |
| `analysis/qpe_validation/qpe_inventory.json` | 73,144 | `d93d9d2d5c26450f…` | Rainfall checked against gauges over matched accumulation windows; bias reported, never applied. |
| `analysis/scoring/control_analysis.json` | 293 | `08d38a19f6d35fd8…` | Blind scoring of sealed predictions against documented flood locations. |
| `analysis/scoring/permutation_test.json` | 455 | `c25cb9dc990fa83f…` | Blind scoring of sealed predictions against documented flood locations. |
| `analysis/scoring/rescore_parent.py` | 4,729 | `c222b48e8e3963f4…` | Blind scoring of sealed predictions against documented flood locations. |
| `analysis/scoring/rescore_run_qpeA_parent.json` | 7,194 | `630b1692c4e57959…` | Blind scoring of sealed predictions against documented flood locations. |
| `analysis/scoring/rescore_run_qpeB_parent.json` | 7,193 | `fa8f5ba365d42ecd…` | Blind scoring of sealed predictions against documented flood locations. |
| `analysis/scoring/score_columbus.py` | 5,291 | `17ae0742590657d8…` | Blind scoring of sealed predictions against documented flood locations. |
| `analysis/scoring/validation_report.json` | 16,129 | `151c1e4ead2550e3…` | Blind scoring of sealed predictions against documented flood locations. |
| `runs/checkpoint_metadata/corridor_status.json` | 2,712 | `45a7ce19ab0e5e7d…` | Per-run status, throughput, and the caveats attached to each nest. |
| `runs/checkpoint_metadata/engineering_failures.json` | 18,911 | `c4cc86d073030cc8…` | EF-1..EF-8 and ML-1..ML-4. Every defect found, including the ones in my own diagnostics. |
| `runs/franklinton_c_B/meta.json` | 443 | `cd948bca53d118fe…` | Franklinton corridor result: metadata and the derived 60 s depth series (raw probes.json not committed; its SHA-256 is). |
| `runs/franklinton_c_B/probe_series.json` | 43,829 | `e84a409b8103596c…` | Franklinton corridor result: metadata and the derived 60 s depth series (raw probes.json not committed; its SHA-256 is). |
| `runs/pataskala_c_B/meta.json` | 441 | `58804172b4e9f7e7…` | Pataskala corridor result: metadata and the derived 60 s depth series (raw probes.json not committed; its SHA-256 is). |
| `runs/pataskala_c_B/probe_series.json` | 91,009 | `ea8b1a183f7effb1…` | Pataskala corridor result: metadata and the derived 60 s depth series (raw probes.json not committed; its SHA-256 is). |
| `runs/summary_metrics/runs.json` | 1,114 | `282d92ff2a384891…` | Roll-up metrics across runs. |

### data

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `analysis/fast_face_log.jsonl` | 6,718 | `26c0bac8da7af3c2…` | Ten in-flight numerical-health samples from the Franklinton run, recorded while it ran rather than reconstructed after. |
| `runs/probes/run_qpeA_parent__probes.json` | 61,177 | `7147922a100e8874…` | Parent-run probe series. |
| `runs/probes/run_qpeB_parent__probes.json` | 61,649 | `b24c5bc3ccf374e8…` | Parent-run probe series. |
| `runs/probes/run_qpeB_parent_ext__probes.json` | 137,566 | `6670f0ce52168f05…` | Parent-run probe series. |

### provenance

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `PROVENANCE_MANIFEST.json` | 20,039 | `729f8d603190d713…` | Machine-readable provenance index for the study inputs. |
| `evidence/dem1m_tile_inventory.json` | 6,635 | `5f68c39b13155a3e…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/effect_locations/observed_flooding.json` | 3,812 | `a70013ab54b0a045…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03144816.json` | 9,988 | `c2e8004583cd8af3…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03145000.json` | 10,061 | `9839fd02edc27373…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03145173.json` | 10,048 | `65f035025a34165d…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03145483.json` | 9,976 | `56e1a30b4b013b21…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03145534.json` | 9,916 | `9fb6cb4143b65666…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03146000.json` | 9,931 | `8760ff4eacce57e3…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03220000.json` | 9,824 | `14b5b8c92b92512e…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03221000.json` | 10,147 | `db018df159efcf5e…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03221646.json` | 10,192 | `af5f0726651e7bd5…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03226800.json` | 9,937 | `4949ba82edefeb80…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03227107.json` | 10,063 | `65909752c883e5a9…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03227500.json` | 10,060 | `9883c73ebd1606cb…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03228300.json` | 9,951 | `de2b2c6481ae1546…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03228500.json` | 9,939 | `1559c6bf63b6ce46…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03228805.json` | 9,782 | `0ea8c193adb27266…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03229500.json` | 10,155 | `92ea02d4221a6cb0…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03229610.json` | 10,259 | `36d98975b0d26581…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/03230450.json` | 9,942 | `b44d286935e36a3b…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/chrtout_zmeta.json` | 14,027 | `88d9c32df2d86933…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/gauge_metadata/gauge_summary.json` | 12,227 | `2b9110c5109fe136…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/ntd_roads_summary.json` | 2,044 | `078cf63646585745…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/road_closures/effect_research.json` | 42,100 | `41285e0dedbed7a1…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `evidence/source_manifest.json` | 2,796 | `aefe900fd636b67c…` | Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed. |
| `prereg/amendments/01_amendment.json` | 720 | `5966d540bfa5113c…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `prereg/amendments/02_amendment.json` | 614 | `d2ed19bdd1411b0a…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `prereg/amendments/03_amendment.json` | 963 | `bcf8df9b19cfc9aa…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `prereg/amendments/04_amendment.json` | 946 | `7d02edc340c14603…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `prereg/amendments/05_amendment.json` | 1,993 | `083b504c3dfa8c1d…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `prereg/frozen_prediction.json` | 666 | `62188157b4be5c99…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `prereg/nest_prereg.json` | 9,705 | `9555a6856f96a6e7…` | Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure. |
| `runs/manifests/run_qpeA_parent.json` | 3,923 | `3da115d0a41de67e…` | Frozen run manifest: the content-derived run_id that seals a prediction before outcome data is read. |
| `runs/manifests/run_qpeA_parent__qpe_provenance.json` | 7,957 | `8aa525340c2ddc67…` | Frozen run manifest: the content-derived run_id that seals a prediction before outcome data is read. |
| `runs/manifests/run_qpeB_parent.json` | 3,937 | `e43d75cbfa03843b…` | Frozen run manifest: the content-derived run_id that seals a prediction before outcome data is read. |
| `runs/manifests/run_qpeB_parent__qpe_provenance.json` | 2,125 | `f157ce8d8067f639…` | Frozen run manifest: the content-derived run_id that seals a prediction before outcome data is read. |
| `runs/manifests/run_qpeB_parent_ext.json` | 4,802 | `e9c903314cdf7dde…` | Frozen run manifest: the content-derived run_id that seals a prediction before outcome data is read. |

### figure

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `figures/README.md` | 1,406 | `b794af8c83a11662…` | Figure or figure source. |
| `figures/columbus_overview_peak.png` | 836,482 | `2130ec1af9a4382d…` | Figure or figure source. |
| `figures/columbus_zoom_end.png` | 874,263 | `d9865374e840c818…` | Figure or figure source. |
| `figures/columbus_zoom_peak.png` | 1,129,435 | `8c5dfd84bbd16691…` | Figure or figure source. |
| `figures/fig1_road_vs_channel.png` | 342,297 | `51a9cd0eeeec9175…` | Figure or figure source. |
| `figures/fig2_prediction_outcome.png` | 174,655 | `d2e62109c4d4a9e1…` | Figure or figure source. |
| `figures/fig3_numerical_health.png` | 186,411 | `d89ac37c48a91684…` | Figure or figure source. |
| `figures/timeline_fixed.png` | 24,081 | `a86932e68ad21248…` | Figure or figure source. |

### deliverable

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `briefing/Ohio-flood-model-briefing.pdf` | 436,152 | `372b1e1ace9e61d7…` | Policy briefing: HTML source, print CSS, and the rendered PDF. |
| `briefing/make_pdf.py` | 3,902 | `49d5994a36bb5c92…` | Policy briefing: HTML source, print CSS, and the rendered PDF. |
| `briefing/ohio_briefing.html` | 39,632 | `3497a898c41ea62a…` | Policy briefing: HTML source, print CSS, and the rendered PDF. |
| `briefing/phase1_validation_report.md` | 7,987 | `30bca356003bc7d4…` | Policy briefing: HTML source, print CSS, and the rendered PDF. |

### handoff

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `handoff/SUMMARY_2026-09-05.txt` | 1,988 | `d5622b2c42dfa66a…` | Prose handoff summary; its SHA-256 is quoted in chat and binds here. |
| `handoff/buckeye_primary/BUNDLE_SHA256SUMS` | 1,204 | `c22c2f115dd3625c…` | Handoff material. |
| `handoff/buckeye_primary/Dockerfile` | 1,333 | `627f5d98ff826d39…` | Handoff material. |
| `handoff/buckeye_primary/FROZEN_SHA256SUMS` | 236 | `13d2a00e738db4bf…` | Handoff material. |
| `handoff/buckeye_primary/HOLD_REASON.txt` | 548 | `1484bb6f36b1ac28…` | Handoff material. |
| `handoff/buckeye_primary/README.md` | 3,962 | `9c7b82390f4bd0ff…` | Handoff material. |
| `handoff/buckeye_primary/crosshost_equivalence.py` | 5,234 | `2352afe889c1f38f…` | Handoff material. |
| `handoff/buckeye_primary/reference.json` | 615 | `e33a34965d90b2af…` | Handoff material. |
| `handoff/buckeye_primary/requirements.txt` | 213 | `54b9f36eb7f895cb…` | Handoff material. |
| `handoff/buckeye_primary/resume_buckeye.sh` | 777 | `10176c21d01d282a…` | Handoff material. |
| `handoff/generate_handoff.py` | 31,398 | `c7727447d019d29f…` | This generator. |

### other

| Path | Bytes | SHA-256 | What it holds, and why |
|---|---|---|---|
| `.gitignore` | 190 | `560dae57cd8d796c…` | — |
| `HANDOFF.md` | 49,518 | `224b2e48790177b4…` | — |
| `report/build_report.py` | 24,110 | `37b611933796d5d1…` | — |

## 6b. Engine file inventory (akhildhruva/aqua-sim @ 0b452c9)

142 tracked files (vendored viewer libraries under `viz/vendor/` omitted). SHA-256 computed at generation time.

| Path | Bytes | SHA-256 | What it holds |
|---|---|---|---|
| `.gitignore` | 318 | `3d922484b0867563…` |  |
| `Last operation results.md` | 9,427 | `1dcfde47c0f722f7…` |  |
| `README.md` | 12,331 | `23b198efccf0d187…` |  |
| `docs/ARCHITECTURE.md` | 16,947 | `637f0804acdca58f…` | System layers, physics engine, offline-solve design, data flow. |
| `docs/CONDITIONING.md` | 5,939 | `7e194b9e1ac3f9d9…` |  |
| `docs/DATA_INGESTION.md` | 7,642 | `5c9c386f04b0c99d…` | DEM / LiDAR / photogrammetry input formats and how they converge to one grid. |
| `docs/DATA_SOURCING.md` | 6,897 | `993c1e81b358cda9…` | What a DEM is; the public Manhattan datasets used (USGS 3DEP, NYC LiDAR). |
| `docs/PLANNING.md` | 11,833 | `d3d851d19ef7cb4c…` | Master plan. States that aqua-sim supersedes and hardens the original Project Deluge note. |
| `docs/VALIDATION.md` | 7,207 | `09c7dac73b1a7a2a…` | The historical-validation programme. Event 1 is Hurricane Ida over Manhattan, scored as a drainage-sensitivity POD matrix, with the failed first attempt kept in the record. |
| `docs/validation/ida2021_report.json` | 3,923 | `e08f3d1be10596f7…` | Scored Ida report: POD 0/6, 0/6, 1/6 across drainage blockage 0 / 0.5 / 1.0; run_id per case. |
| `pyproject.toml` | 739 | `8c8e9742d35d0c59…` |  |
| `src/aqua_sim/__init__.py` | 73 | `d8e11b02bdbeee81…` |  |
| `src/aqua_sim/__main__.py` | 88 | `1505c02da18505b4…` |  |
| `src/aqua_sim/config.py` | 3,966 | `216e840b292b609a…` | SimConfig / SolverConfig / StormConfig; GRAVITY. |
| `src/aqua_sim/export/__init__.py` | 78 | `b45129e074e925b2…` |  |
| `src/aqua_sim/export/frames.py` | 9,943 | `3b62869cd030f6c3…` | Frame export and the content-derived run_id: sha256 over the canonical provenance block, including a terrain digest. |
| `src/aqua_sim/geofence.py` | 806 | `b2220d791dc70089…` |  |
| `src/aqua_sim/grid.py` | 4,623 | `d877fed83611ebba…` | Structured raster Grid: z, obstacle, manning, mask, crest fields, transform, CRS. |
| `src/aqua_sim/ingestion/__init__.py` | 330 | `cdd632de345916bf…` |  |
| `src/aqua_sim/ingestion/base.py` | 996 | `64b8929db4fa0a3e…` |  |
| `src/aqua_sim/ingestion/buildings.py` | 22,420 | `dbfaa636aaab935a…` | BuildingsSource: footprints -> coverage fraction -> closed obstacle cells. Built for the NYC demo; unused in Ohio (sources unreachable). |
| `src/aqua_sim/ingestion/conditioning.py` | 16,212 | `62c691203ff68869…` |  |
| `src/aqua_sim/ingestion/dem.py` | 8,116 | `2a8810f522a088ce…` | DEMSource: GeoTIFF ingestion, reprojection, tile mosaicking (first-path-wins), resampling to target dx. |
| `src/aqua_sim/ingestion/fetch.py` | 4,296 | `e6b74a36e1d5f0de…` |  |
| `src/aqua_sim/ingestion/lidar.py` | 823 | `2c2f2a9be5f85864…` |  |
| `src/aqua_sim/ingestion/photogrammetry.py` | 1,462 | `0b75838eba127fd7…` |  |
| `src/aqua_sim/ingestion/synthetic.py` | 2,386 | `f3e5b84b10fd3bc2…` |  |
| `src/aqua_sim/main.py` | 4,931 | `dd13bd81e4db5142…` |  |
| `src/aqua_sim/physics/__init__.py` | 412 | `faebb8273493b3d6…` |  |
| `src/aqua_sim/physics/boundary.py` | 636 | `ba696396b4052e1c…` | OPEN / CLOSED / inflow boundary types. OPEN is the free-outfall whose ghost cell drives ML-3. |
| `src/aqua_sim/physics/friction.py` | 1,254 | `e59debc081e512de…` | Manning friction. |
| `src/aqua_sim/physics/infiltration.py` | 564 | `6ea92d7ca7f5b58f…` | Infiltration losses. |
| `src/aqua_sim/physics/stability.py` | 1,673 | `1b184a18d357cf05…` | CFL timestep. |
| `src/aqua_sim/physics/swe.py` | 20,990 | `36fe3399c418c13b…` | Reference local-inertial solver (pure Python). Mass-conserving, well-balanced, non-negative depths, CFL-adaptive. |
| `src/aqua_sim/physics/swe_numpy.py` | 15,647 | `04f272f12e9dbc21…` | Vectorised NumPy twin of the reference solver; equivalence enforced to <=1e-9 depth by tests. THE solver the Ohio study ran. |
| `src/aqua_sim/risk/__init__.py` | 472 | `f907310a26b5576f…` |  |
| `src/aqua_sim/risk/alerts.py` | 1,393 | `32a1937691c13e48…` | Alert matrix and breach records. |
| `src/aqua_sim/risk/hazard.py` | 2,210 | `4511bc6843ffba77…` | Depth x velocity hazard classes. |
| `src/aqua_sim/risk/sink_nodes.py` | 2,258 | `72079ed72e20cb99…` | Subterranean sink nodes (orifice inflow when head exceeds the lip). |
| `src/aqua_sim/scenario.py` | 18,406 | `a48062f6f2cd9f19…` | build_manhattan_demo, build_scenario_from_dem, build_nyc_metro_scenario (five boroughs, 2.57M cells at 30 m), run_scenario. |
| `src/aqua_sim/validation/__init__.py` | 85 | `4446fe7f8927666a…` |  |
| `src/aqua_sim/validation/hydraulic.py` | 6,433 | `16ba00c18dde4d30…` |  |
| `src/aqua_sim/validation/ida2021.py` | 13,491 | `ce43565f07db0dbb…` | Hurricane Ida 2021 Manhattan validation: hyetograph, six documented-flooded stations, sink-node probing, POD matrix. |
| `tests/test_area_scenarios.py` | 3,381 | `968c34a21130820c…` |  |
| `tests/test_buildings_source.py` | 11,234 | `4bc02e929475bcc9…` |  |
| `tests/test_conditioned_physics.py` | 8,681 | `f80c6a0c38bcd185…` |  |
| `tests/test_conditioning.py` | 8,203 | `61d9649907eabf99…` |  |
| `tests/test_dem_ingestion.py` | 3,331 | `ccd7cb43dc3231a6…` |  |
| `tests/test_hydraulic_validation.py` | 2,850 | `d867c8d850ea3e0b…` |  |
| `tests/test_ida_pieces.py` | 2,770 | `33d97bcbcf8a9be4…` |  |
| `tests/test_risk.py` | 1,365 | `a6642f91e8556207…` |  |
| `tests/test_scenario.py` | 5,576 | `ed65fcaad4b3eb31…` |  |
| `tests/test_smoke.py` | 169 | `ea6bc68a9209d007…` |  |
| `tests/test_stability.py` | 748 | `5041382e277f1e15…` |  |
| `tests/test_swe.py` | 6,582 | `96c869becfab1c7e…` | Analytic benchmarks: mass conservation, lake-at-rest, dam-break, non-negativity. |
| `tests/test_swe_numpy.py` | 4,814 | `5189736c98346761…` | Backend equivalence: NumPy vs reference, cell-by-cell. |
| `tests/test_terrain_and_grid.py` | 1,157 | `36df090382560336…` |  |
| `viz/README.md` | 3,453 | `b05b6030ccd152a3…` |  |
| `viz/app.js` | 31,656 | `f7d68a0c0ce360b3…` | Three.js telemetry dashboard. |
| `viz/buildings-layer.js` | 8,641 | `949bf5080ef33f6f…` | Extruded-footprint layer with LOD and per-tile culling. |
| `viz/index.html` | 8,908 | `4aa1a41cec27ef0b…` |  |
| `viz/ny_run/alerts.json` | 2,141 | `2a08cacd83e14ebd…` |  |
| `viz/ny_run/frame_001.json` | 1,887,024 | `5385f4f6f05329d1…` |  |
| `viz/ny_run/frame_002.json` | 1,887,026 | `669678cb4fcbe8a7…` |  |
| `viz/ny_run/frame_003.json` | 1,887,027 | `1d3b6bb2764946cb…` |  |
| `viz/ny_run/frame_004.json` | 1,887,027 | `1daf021b367df570…` |  |
| `viz/ny_run/frame_005.json` | 1,887,027 | `b0cf3e6f4b5a7180…` |  |
| `viz/ny_run/frame_006.json` | 2,423,506 | `cfc601e563fa4535…` |  |
| `viz/ny_run/frame_007.json` | 2,404,149 | `7427b86c75deadfd…` |  |
| `viz/ny_run/frame_008.json` | 2,436,263 | `b43bd1b88394b1a6…` |  |
| `viz/ny_run/frame_009.json` | 2,425,008 | `efcdf6b07137ddf5…` |  |
| `viz/ny_run/frame_010.json` | 2,449,391 | `e827e5abb146ac6c…` |  |
| `viz/ny_run/frame_011.json` | 2,445,800 | `f518570d546c4fb5…` |  |
| `viz/ny_run/frame_012.json` | 2,461,704 | `a18e183d9f45c6fe…` |  |
| `viz/ny_run/frame_013.json` | 2,461,087 | `be5bb8d992eed017…` |  |
| `viz/ny_run/frame_014.json` | 2,469,152 | `bab7a0a71fd2f35b…` |  |
| `viz/ny_run/frame_015.json` | 2,469,047 | `20917774d855008e…` |  |
| `viz/ny_run/frame_016.json` | 2,455,356 | `3e9d3ab957c14d65…` |  |
| `viz/ny_run/frame_017.json` | 2,425,942 | `e83c58c57b9fb641…` |  |
| `viz/ny_run/frame_018.json` | 2,251,151 | `adcdb869f36b2c4f…` |  |
| `viz/ny_run/frame_019.json` | 2,200,953 | `1f7baf21ae01baa1…` |  |
| `viz/ny_run/frame_020.json` | 2,175,741 | `1e6ea11e16770058…` |  |
| `viz/ny_run/frame_021.json` | 2,160,280 | `715b0c757a51d7b9…` |  |
| `viz/ny_run/frame_022.json` | 2,148,636 | `9574870083d8a0b3…` |  |
| `viz/ny_run/frame_023.json` | 2,139,784 | `f82e7fd033d0ffc1…` |  |
| `viz/ny_run/frame_024.json` | 2,133,014 | `978d28a31ab4b4dd…` |  |
| `viz/ny_run/frame_025.json` | 2,126,912 | `0ee916ab85c9e005…` |  |
| `viz/ny_run/manifest.json` | 6,382 | `b8a9246cefb29083…` |  |
| `viz/ny_run/terrain.json` | 3,450,617 | `07034078fcd81d49…` |  |
| `viz/palettes.js` | 4,159 | `5769a151270e9c31…` |  |
| `viz/sample_run/alerts.json` | 383 | `bce76fc569706309…` |  |
| `viz/sample_run/frame_001.json` | 24,560 | `90a5606d9e8a4ce9…` |  |
| `viz/sample_run/frame_002.json` | 36,302 | `d30e88188f5a6e22…` |  |
| `viz/sample_run/frame_003.json` | 35,284 | `9e71b0bcf8fd2ceb…` |  |
| `viz/sample_run/frame_004.json` | 36,204 | `3fee1f52ac1267dc…` |  |
| `viz/sample_run/frame_005.json` | 36,095 | `09f418d711a9803a…` |  |
| `viz/sample_run/frame_006.json` | 36,058 | `514872913ddfb661…` |  |
| `viz/sample_run/frame_007.json` | 35,973 | `bfc16dada3a966c9…` |  |
| `viz/sample_run/frame_008.json` | 36,262 | `8a8344f1e38d333b…` |  |
| `viz/sample_run/frame_009.json` | 36,246 | `030534a643629d56…` |  |
| `viz/sample_run/frame_010.json` | 36,229 | `162bb94e596c0cbd…` |  |
| `viz/sample_run/frame_011.json` | 36,215 | `b2edce633a3e9207…` |  |
| `viz/sample_run/frame_012.json` | 36,210 | `e12de8f85a5c26e3…` |  |
| `viz/sample_run/frame_013.json` | 36,296 | `9407edc53b4633b4…` |  |
| `viz/sample_run/frame_014.json` | 36,279 | `5af726f05ec7acd5…` |  |
| `viz/sample_run/frame_015.json` | 36,290 | `e14a003bb63d624b…` |  |
| `viz/sample_run/frame_016.json` | 36,272 | `f953edff754d36e9…` |  |
| `viz/sample_run/frame_017.json` | 36,276 | `e8f40a72a7550d51…` |  |
| `viz/sample_run/frame_018.json` | 36,278 | `07899ad84016d7cf…` |  |
| `viz/sample_run/frame_019.json` | 36,252 | `7bf0f56e2f82c452…` |  |
| `viz/sample_run/frame_020.json` | 36,240 | `afa12c920fa9a4bc…` |  |
| `viz/sample_run/frame_021.json` | 36,244 | `45855bca542d1440…` |  |
| `viz/sample_run/frame_022.json` | 36,231 | `7b7c03c174b96226…` |  |
| `viz/sample_run/frame_023.json` | 36,242 | `e46e49a0cd059848…` |  |
| `viz/sample_run/frame_024.json` | 36,244 | `12b56a40d2877fcd…` |  |
| `viz/sample_run/frame_025.json` | 36,258 | `12a50ced4d1b7434…` |  |
| `viz/sample_run/frame_026.json` | 36,264 | `a405d2be880ca2b8…` |  |
| `viz/sample_run/frame_027.json` | 36,269 | `6f9b69abcc847596…` |  |
| `viz/sample_run/frame_028.json` | 36,270 | `86100e13567da5bb…` |  |
| `viz/sample_run/frame_029.json` | 36,254 | `8de360a409e4bd5f…` |  |
| `viz/sample_run/frame_030.json` | 36,265 | `58bdc328347b56be…` |  |
| `viz/sample_run/frame_031.json` | 36,261 | `bc7b36a0f2fa84d8…` |  |
| `viz/sample_run/frame_032.json` | 36,260 | `fe4307a1514e39d8…` |  |
| `viz/sample_run/frame_033.json` | 36,248 | `f204ed708edd1142…` |  |
| `viz/sample_run/frame_034.json` | 36,233 | `e9971455b8d79d98…` |  |
| `viz/sample_run/frame_035.json` | 36,242 | `f153759e012defa5…` |  |
| `viz/sample_run/frame_036.json` | 36,238 | `a7a75b8cc74b8adc…` |  |
| `viz/sample_run/frame_037.json` | 36,255 | `ef838c5b232ab8d1…` |  |
| `viz/sample_run/frame_038.json` | 36,258 | `3073266303de0f7d…` |  |
| `viz/sample_run/frame_039.json` | 36,250 | `289b3ef44611d6d5…` |  |
| `viz/sample_run/frame_040.json` | 36,270 | `17599d210c403f38…` |  |
| `viz/sample_run/frame_041.json` | 36,267 | `fb181f2180670893…` |  |
| `viz/sample_run/frame_042.json` | 36,266 | `a41239720c7f618e…` |  |
| `viz/sample_run/frame_043.json` | 36,257 | `9e8e2eb134ef7748…` |  |
| `viz/sample_run/frame_044.json` | 36,253 | `3ed81798cb30b87c…` |  |
| `viz/sample_run/frame_045.json` | 36,266 | `c49fbc1019a4022b…` |  |
| `viz/sample_run/frame_046.json` | 36,266 | `c75bd3927a30acfb…` |  |
| `viz/sample_run/frame_047.json` | 36,254 | `f851e0efab45def3…` |  |
| `viz/sample_run/frame_048.json` | 36,269 | `792e1fbacbbe8618…` |  |
| `viz/sample_run/frame_049.json` | 36,254 | `947281cbb8d1d402…` |  |
| `viz/sample_run/manifest.json` | 8,949 | `d9233bb060e80a35…` |  |
| `viz/sample_run/terrain.json` | 43,203 | `7c04ef0bcbfd7656…` |  |

## 7. Missing artefacts — what cannot be reproduced from this repository

This section exists because omitting it would misrepresent what the repository
can do. `.gitignore` excludes `*.npz`, `*.tif`, `*.grib2`, `data/raw/` and
`data/cache/` — a deliberate choice to keep 8.8 GB of replaceable bulk out of
Git. The machine holding those files was an ephemeral cloud container and has
since been recycled. The consequences are concrete.

| Artefact | Status | Recorded identity | Consequence |
|---|---|---|---|
| Buckeye frozen checkpoint (`state.npz`, `setup_cache.npz`, `probes.json`) | **GONE** | `handoff/buckeye_primary/FROZEN_SHA256SUMS` | **Buckeye cannot be resumed.** The handoff bundle in this repo is scaffolding only — Dockerfile, pinned requirements, equivalence gate, reference hashes. It has no state to restore. Buckeye must be re-run from t=0. |
| Franklinton / Pataskala `state.npz`, `peak.npz`, `snaps.npz` | GONE | — | Inundation maps are not reproducible. Depth series survive. |
| Raw `probes.json` for both completed nests | GONE | `runs/*/probe_series.json` → `probes_json_sha256` | **A from-scratch re-run can still be verified byte-for-byte against the committed hash.** This is the strongest available cross-host gate, and it survives only because the hash was committed even though the data was not. |
| MRMS QPE fields, 1 m LiDAR tiles, NHD, NTD | not committed | `evidence/source_manifest.json`, `evidence/dem1m_tile_inventory.json` | Re-fetchable from public sources by recorded identity. |
| Parent boundary-stage series for each nest | GONE | — | Must be regenerated by re-running the 60 m parent, then `reproduction/extract_parent_bc.py`. |

## 8. Open failures and measured limitations

| ID | Title |
|---|---|
| EF-1 |  |
| EF-2 |  |
| EF-3 |  |
| ML-1 | the solver executes on ONE core (~100% CPU measured via /proc jiffies: 999/10 s), not four — elementwise NumPy kernels do not use BLAS threading |
| ML-2 | restart start-up cost dominated short process lifetimes: rebuilding nest terrain, roughness, culverts, probe geometry and the parent-derived stage BC  |
| EF-4 |  |
| EF-5 |  |
| ML-3 | buckeye_c solves 6-8x slower than the other corridors (1.83 model-hours per wall-hour vs 10.8 franklinton / 15.1 pataskala) despite fewer cells than p |
| ML-4 | the execution container is torn down between interactive turns, so the solver only advances WHILE A TURN IS ACTIVE. Background processes do not accumu |
| EF-6 | Self-caught measurement error: 'interior' velocity diagnostic did not exclude the boundary CELL ROW |
| EF-7 | Run crashed writing meta.json AFTER completing, because the setup-cache path leaves a variable unbound |
| EF-8 | gauge_timing.py used ndarray.ptp(), removed in NumPy 2.0 |

## 9. How to resume this work

1. Clone the engine at the frozen commit `0b452c9` and this repository.
2. Build the pinned environment from `handoff/buckeye_primary/Dockerfile`.
3. Re-fetch inputs by identity from `evidence/source_manifest.json`.
4. **Gate first.** Re-run Pataskala end to end and check its `probes.json`
   against the committed `probes_json_sha256`. A byte-identical match
   establishes cross-host determinism; anything else must be diagnosed with
   `runs/pataskala_c_B/probe_series.json` before any new science is admitted.
5. Only then re-run Buckeye from t=0, and the three sensitivity members.
6. Run `python3 analysis/verify_published_numbers.py` — it must exit 0.

---

*Regenerate with `python3 handoff/generate_handoff.py`. Prefer appending to
the Chronology by hand; regenerate only when stuck or seeding a new repo.*

