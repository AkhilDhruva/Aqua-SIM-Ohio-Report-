#!/usr/bin/env python3
"""Regenerate HANDOFF.md from the repository's own state.

Usage: python3 handoff/generate_handoff.py        (from the repo root)

WHEN TO RUN THIS
    Only when you are stuck, onboarding a new machine, or seeding a new repo.
    It walks every tracked file and the whole commit history, which is cheap in
    CPU and expensive in reading. Routine work should APPEND to the chronology
    section by hand, not regenerate the document.

WHAT IT GUARANTEES
    Every hash in the output is computed here, from bytes on disk, at generation
    time. Nothing is transcribed. Where a file is absent, the document says so
    and — where a hash of the absent file was recorded earlier — carries that
    hash forward so the missing artefact keeps a verifiable identity.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

R = subprocess.run


def sh(*a):
    return R(list(a), capture_output=True, text=True).stdout.strip()


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tracked():
    return [p for p in sh("git", "ls-files").splitlines() if p]


ENGINE = os.environ.get("AQUA_SIM_ENGINE", "/home/user/aqua-sim")


def engine_present():
    return os.path.isdir(os.path.join(ENGINE, ".git"))


def engine_commits():
    if not engine_present():
        return []
    raw = R(["git", "-C", ENGINE, "log", "--reverse", "--date=iso-strict",
             "--pretty=format:%H\x1f%ad\x1f%s\x1e"], capture_output=True, text=True).stdout
    out = []
    for c in raw.split("\x1e"):
        c = c.strip("\n")
        if not c:
            continue
        a = c.split("\x1f")
        if len(a) >= 3:
            out.append({"sha": a[0], "date": a[1], "subj": a[2], "repo": "ENGINE"})
    return out


def engine_files():
    if not engine_present():
        return []
    files = [f for f in R(["git", "-C", ENGINE, "ls-files"], capture_output=True,
                          text=True).stdout.splitlines() if f]
    rows = []
    for f in files:
        fp = os.path.join(ENGINE, f)
        if os.path.exists(fp) and not f.startswith("viz/vendor/"):
            rows.append((f, sha(fp), os.path.getsize(fp)))
    return rows


ENGINE_WHY = {
 "docs/PLANNING.md": "Master plan. States that aqua-sim supersedes and hardens the original Project Deluge note.",
 "docs/VALIDATION.md": "The historical-validation programme. Event 1 is Hurricane Ida over Manhattan, scored as a drainage-sensitivity POD matrix, with the failed first attempt kept in the record.",
 "docs/validation/ida2021_report.json": "Scored Ida report: POD 0/6, 0/6, 1/6 across drainage blockage 0 / 0.5 / 1.0; run_id per case.",
 "docs/ARCHITECTURE.md": "System layers, physics engine, offline-solve design, data flow.",
 "docs/DATA_INGESTION.md": "DEM / LiDAR / photogrammetry input formats and how they converge to one grid.",
 "docs/DATA_SOURCING.md": "What a DEM is; the public Manhattan datasets used (USGS 3DEP, NYC LiDAR).",
 "src/aqua_sim/physics/swe.py": "Reference local-inertial solver (pure Python). Mass-conserving, well-balanced, non-negative depths, CFL-adaptive.",
 "src/aqua_sim/physics/swe_numpy.py": "Vectorised NumPy twin of the reference solver; equivalence enforced to <=1e-9 depth by tests. THE solver the Ohio study ran.",
 "src/aqua_sim/physics/stability.py": "CFL timestep.",
 "src/aqua_sim/physics/boundary.py": "OPEN / CLOSED / inflow boundary types. OPEN is the free-outfall whose ghost cell drives ML-3.",
 "src/aqua_sim/physics/infiltration.py": "Infiltration losses.",
 "src/aqua_sim/physics/friction.py": "Manning friction.",
 "src/aqua_sim/ingestion/dem.py": "DEMSource: GeoTIFF ingestion, reprojection, tile mosaicking (first-path-wins), resampling to target dx.",
 "src/aqua_sim/ingestion/buildings.py": "BuildingsSource: footprints -> coverage fraction -> closed obstacle cells. Built for the NYC demo; unused in Ohio (sources unreachable).",
 "src/aqua_sim/export/frames.py": "Frame export and the content-derived run_id: sha256 over the canonical provenance block, including a terrain digest.",
 "src/aqua_sim/scenario.py": "build_manhattan_demo, build_scenario_from_dem, build_nyc_metro_scenario (five boroughs, 2.57M cells at 30 m), run_scenario.",
 "src/aqua_sim/validation/ida2021.py": "Hurricane Ida 2021 Manhattan validation: hyetograph, six documented-flooded stations, sink-node probing, POD matrix.",
 "src/aqua_sim/risk/sink_nodes.py": "Subterranean sink nodes (orifice inflow when head exceeds the lip).",
 "src/aqua_sim/risk/alerts.py": "Alert matrix and breach records.",
 "src/aqua_sim/risk/hazard.py": "Depth x velocity hazard classes.",
 "src/aqua_sim/config.py": "SimConfig / SolverConfig / StormConfig; GRAVITY.",
 "src/aqua_sim/grid.py": "Structured raster Grid: z, obstacle, manning, mask, crest fields, transform, CRS.",
 "tests/test_swe_numpy.py": "Backend equivalence: NumPy vs reference, cell-by-cell.",
 "tests/test_swe.py": "Analytic benchmarks: mass conservation, lake-at-rest, dam-break, non-negativity.",
 "viz/app.js": "Three.js telemetry dashboard.",
 "viz/buildings-layer.js": "Extruded-footprint layer with LOD and per-tile culling.",
}


# --- what each path is, and why it exists. Keyed by exact path or by prefix. --
WHY = {
 "README.md": ("Entry point and the three-level evidence rule the study is scored under.", "spec"),
 "METHODS.md": ("Method of record: blind CAUSE/EFFECT protocol, pre-registration, scoring definitions.", "spec"),
 "CLAIMS_STATUS.md": ("Every claim with a verdict — SUPPORTED, REFUTED, RETRACTED, NOT TESTABLE. The document that matters.", "result"),
 "LIMITATIONS.md": ("Bounds on every claim, stated so they cannot be read past.", "spec"),
 "VERSIONS.md": ("Version identity by commit SHA. Tag pushes return HTTP 403 in this environment, so SHAs are the versioning mechanism.", "spec"),
 "PROVENANCE_MANIFEST.json": ("Machine-readable provenance index for the study inputs.", "provenance"),
 "handoff/SUMMARY_2026-09-05.txt": ("Prose handoff summary; its SHA-256 is quoted in chat and binds here.", "handoff"),
 "handoff/generate_handoff.py": ("This generator.", "handoff"),
 "handoff/buckeye_primary/": ("Scaffolding for resuming Buckeye off-platform. THE FROZEN STATE IT NEEDS IS NOT HERE — see the Missing Artefacts section.", "handoff"),
 "reproduction/run_corridor.py": ("ENTRY POINT. Restart-resilient corridor runner: setup cache, wall-clock-aware checkpointing, deterministic step grid.", "code"),
 "reproduction/qpe_solver.py": ("Solver extension: per-cell radar rain, nested Dirichlet stage BC, 60 s probes. Subclasses the frozen engine; edits nothing in it.", "code"),
 "reproduction/run_parent_qpe.py": ("60 m parent run driven by MRMS QPE.", "code"),
 "reproduction/run_columbus.py": ("Original 60 m screening run and its AOI/tile definitions.", "code"),
 "reproduction/run_nest.py": ("Wide-extent nest runner, superseded by the corridor runner.", "code"),
 "reproduction/extract_parent_bc.py": ("Derives nest boundary stage series from completed parent frames.", "code"),
 "reproduction/gauge_timing.py": ("Hydrograph timing and shape against NWM analysis_assim. Timing only — no stage, so no stage RMSE.", "code"),
 "reproduction/relaunch_corridors.sh": ("Priority-ordered parallel launcher, capped at nproc-1, honours .hold.", "code"),
 "reproduction/make_pdf.py": ("Renders the briefing to print-ready PDF with embedded fonts.", "code"),
 "analysis/boundary_velocity_audit.py": ("Tests whether high face velocity is confined to the domain edge and whether it reaches the probes. Written after EF-6.", "code"),
 "analysis/verify_published_numbers.py": ("Re-checks every number quoted in CLAIMS_STATUS.md against its source file. Exits non-zero on drift.", "code"),
 "analysis/consolidated_table.py": ("Joins static freeboard prediction to dynamic outcome across all twelve corridor points, keeping unscoreable rows.", "code"),
 "analysis/fast_face_log.jsonl": ("Ten in-flight numerical-health samples from the Franklinton run, recorded while it ran rather than reconstructed after.", "data"),
 "analysis/consolidated_table.json": ("The scoreboard: 5 of 12 scoreable, 4 confirmed, 1 refuted, 7 retained with reasons.", "result"),
 "runs/checkpoint_metadata/engineering_failures.json": ("EF-1..EF-8 and ML-1..ML-4. Every defect found, including the ones in my own diagnostics.", "result"),
 "runs/checkpoint_metadata/corridor_status.json": ("Per-run status, throughput, and the caveats attached to each nest.", "result"),
 "figures/make_figures.py": ("Renders the corridor figures from committed derived series. Plotting these caught the wbroad overshoot.", "code"),
}
PREFIX_WHY = [
 ("runs/manifests/", ("Frozen run manifest: the content-derived run_id that seals a prediction before outcome data is read.", "provenance")),
 ("runs/probes/", ("Parent-run probe series.", "data")),
 ("runs/franklinton_c_B/", ("Franklinton corridor result: metadata and the derived 60 s depth series (raw probes.json not committed; its SHA-256 is).", "result")),
 ("runs/pataskala_c_B/", ("Pataskala corridor result: metadata and the derived 60 s depth series (raw probes.json not committed; its SHA-256 is).", "result")),
 ("runs/summary_metrics/", ("Roll-up metrics across runs.", "result")),
 ("evidence/", ("Cause- and effect-side evidence with source identity. Effect data was collected only after predictions were sealed.", "provenance")),
 ("analysis/qpe_validation/", ("Rainfall checked against gauges over matched accumulation windows; bias reported, never applied.", "result")),
 ("analysis/geometry_audit/", ("The freeboard diagnostic: carriageway elevation against the coarse cell's water surface at 'impassable'.", "result")),
 ("analysis/culvert_audit/", ("Blinded fixed-seed culvert re-tests against 1 m LiDAR, reported as precision.", "result")),
 ("analysis/case_ab/", ("Case A versus Case B determination and the formal retraction of the lead-time claim.", "result")),
 ("analysis/scoring/", ("Blind scoring of sealed predictions against documented flood locations.", "result")),
 ("analysis/", ("Analysis output.", "result")),
 ("figures/", ("Figure or figure source.", "figure")),
 ("briefing/", ("Policy briefing: HTML source, print CSS, and the rendered PDF.", "deliverable")),
 ("prereg/", ("Pre-registration and its logged amendments, each with the reason and whether it postdates effect exposure.", "provenance")),
 ("tests/", ("Equivalence and determinism tests.", "code")),
 ("handoff/", ("Handoff material.", "handoff")),
]


def why(p):
    if p in WHY:
        return WHY[p]
    for pre, v in PREFIX_WHY:
        if p.startswith(pre):
            return v
    return ("—", "other")


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    head = sh("git", "rev-parse", "HEAD")
    files = tracked()
    rows = [(p, sha(p), os.path.getsize(p)) + why(p) for p in files if os.path.exists(p)]

    log = sh("git", "log", "--reverse", "--date=iso-strict",
             "--pretty=format:%H\x1f%ad\x1f%s\x1f%b\x1e").split("\x1e")
    commits = []
    for c in log:
        c = c.strip("\n")
        if not c:
            continue
        parts = c.split("\x1f")
        if len(parts) >= 3:
            commits.append({"sha": parts[0], "date": parts[1], "subj": parts[2],
                            "body": (parts[3] if len(parts) > 3 else "").strip()})

    out = []
    W = out.append
    W("# aqua-sim — Handoff, Provenance and Chronology\n")
    W("> **Read this before regenerating.** This document is produced by\n"
      "> `handoff/generate_handoff.py`, which walks every tracked file and the\n"
      "> entire commit history. **Regenerate it only when you are stuck, onboarding\n"
      "> a new machine, or seeding a new repository.** Routine work should append\n"
      "> to the Chronology section by hand. Regenerating on every change wastes\n"
      "> effort and, in an agent session, tokens.\n")
    W(f"Generated `{now}` at commit `{head[:7]}` · {len(rows)} tracked files · "
      f"{len(commits)} commits\n")
    W("---\n")

    # ---------------- 1. what this is -------------------------------------
    W("## 1. What this project is\n")
    W("**aqua-sim** is a hydrodynamic flood simulator: given rainfall and terrain,\n"
      "it computes where water goes, how deep it gets, how fast it moves, and when.\n"
      "Its engine repository `akhildhruva/aqua-sim` states in `docs/PLANNING.md` that\n"
      "it *\u201csupersedes and hardens the original \u2018Project Deluge\u2019 handoff note\u201d*,\n"
      "and §4 of that document lists what it fixed: CFL-limited adaptive timestepping,\n"
      "bare-earth DTM as the flow floor with buildings as obstacles, a well-balanced\n"
      "wet/dry treatment, infiltration and drainage as explicit losses, and real\n"
      "boundary conditions. **aqua-sim is what Deluge became, not a separate project.**\n")
    W("**Lineage, corrected.** The engine was built in July 2026 with **New York** as\n"
      "its validation ground: a Manhattan demo scenario and the Hurricane Ida (2021)\n"
      "validation on real USGS terrain landed on 2026-07-05, a five-borough NYC metro\n"
      "scenario with the NumPy backend on 2026-07-20, and a building-aware NYC\n"
      "demonstration from official footprints on 2026-07-22. An earlier version of\n"
      "this document stated that no New York work existed; that was wrong \u2014 it is\n"
      "in the engine repository under `validation/`, `scenario.py` and\n"
      "`ingestion/buildings.py`, named by the storm rather than the city. The Ohio\n"
      "study is the engine's **second** event, run against the engine frozen at its\n"
      "fifteenth and final commit `0b452c9`.\n")
    W("This repository is not the engine. It is the *study record* for one\n"
      "application of it: a blind hindcast of the Central Ohio flood of\n"
      "19\u201320 August 2026, asking a narrow question \u2014 can a rainfall flood model\n"
      "be trusted to decide whether a road is open?\n")

    # ---------------- 1b. the New York work --------------------------------
    W("## 1b. The New York work (engine repository, July 2026)\n")
    W("| Date | What | Where | Outcome |\n|---|---|---|---|")
    for a, b, c_, d in [
      ("2026-07-05", "Manhattan demo scenario", "`scenario.build_manhattan_demo`", "First runnable scenario on the reference solver."),
      ("2026-07-05", "**Hurricane Ida 2021 validation** \u2014 the record 80 mm hour at Central Park over USGS 3DEP 10 m terrain, scored against six subway stations documented as flooded",
       "`validation/ida2021.py`, `docs/VALIDATION.md`, `docs/validation/ida2021_report.json`",
       "POD **0/6** at design drainage, **0/6** surcharged-to-half, **1/6** with drainage failed (Dyckman St, breach at t\u224883 min). Basin-scale behaviour reproduced (~3.6 \u00d7 10\u2076 m\u00b3 ponded over ~62,000 wet cells); street-scale detection not. The first attempt scored 0/6 and is kept in the record; the corrections that followed are argued from event documentation, not tuned to the score. False-alarm rate explicitly out of scope. Verdict in the engine's own words: *partial validation honestly scored \u2014 not failed, not passed.*"),
      ("2026-07-20", "NumPy backend + DEM mosaicking + **five-borough NYC metro scenario** (2.57 M cells at 30 m over n41w074 + n41w075)", "`physics/swe_numpy.py`, `ingestion/dem.py`, `scenario.build_nyc_metro_scenario`", "~20\u00d7 faster than the reference solver; equivalence enforced to \u22641e-9 depth by `tests/test_swe_numpy.py`. This is the solver the Ohio study used."),
      ("2026-07-22", "**Building-aware NYC demonstration** from the official NYC Open Data footprints (nqwf-w8eh)", "`ingestion/buildings.py`, `viz/buildings-layer.js`", "Coverage-fraction rasterisation, closed obstacle cells at dx \u2264 10 m, extruded viewer layer with LOD. Provenance includes dataset id, licence, CRS chain and source SHA-256."),
    ]:
        W(f"| {a} | {b} | {c_} | {d} |")
    W("")
    W("Why it matters for Ohio: the NumPy backend, DEM mosaicking, sink-node probing,\n"
      "content-derived `run_id`, and the honesty conventions (keep the failed attempt,\n"
      "state what is not claimed, never tune to the score) were all built for New York\n"
      "and carried unchanged into the Ohio study. Buildings were *not* used in Ohio\n"
      "because footprint sources were unreachable from that host.\n")

    # ---------------- 2. tech stack ---------------------------------------
    W("## 2. Technology stack\n")
    W("| Layer | Choice | Note |\n|---|---|---|")
    for a, b, cc in [
      ("Numerics", "Local-inertial 2D shallow water (Bates et al. 2010)",
       "Explicit, CFL-limited. Omits advection \u2014 the reason Froude > 1 is outside its envelope."),
      ("Implementation", "Pure NumPy, vectorised", "Single-core. See ML-1."),
      ("Timestep", "Adaptive, dt \u2264 cfl\u00b7dx/(\\|v\\|+\u221a(gh)), cfl 0.7, max 60 s", "Global \u2014 a few fast cells throttle the whole domain. See ML-3."),
      ("Terrain", "USGS 3DEP 1 m LiDAR \u2192 resampled to nest dx", "Bare earth. Buildings absent \u2014 footprint sources were unreachable."),
      ("Rainfall", "NOAA MRMS QPE, radar-only 15 min (A) and multi-sensor hourly (B)", "Applied per cell, per timestep. Never scaled to fit observations."),
      ("Hydrography / roads", "USGS NHD, USGS NTD", "Culvert orifices inferred at road\u00d7stream crossings with continuous embankment."),
      ("Nesting", "Dirichlet stage strips from the 60 m parent, gated by parent wetness", "Nests also receive full rain-on-grid."),
      ("River reference", "NOAA NWM v3 analysis_assim", "USGS-nudged proxy, discharge only \u2014 so timing and shape, never stage RMSE."),
      ("Runtime", "Python 3.11 / Ubuntu 24.04", "numpy 2.4.6, scipy 1.17.1, rasterio 1.4.4, fiona 1.10.1, shapely 2.1.2 \u2014 pinned, because the equivalence gate depends on them."),
      ("Viewer", "Three.js, reads pre-computed frames", "Decoupled from the solver."),
    ]:
        W(f"| {a} | {b} | {cc} |")
    W("")

    # ---------------- 3. how validation works ------------------------------
    W("## 3. How validation works, and the guard rails against cheating\n")
    W("The design problem is that a model tuned against a known outcome will\n"
      "reproduce that outcome and prove nothing. Five mechanisms are used, in\n"
      "descending order of how hard they are to game.\n")
    W("**1. Temporal ordering with a content-derived seal.** The simulator receives\n"
      "only cause-side data \u2014 the rainfall that fell and the shape of the ground.\n"
      "Predictions are then hashed into a `run_id` derived from their own content and\n"
      "written to `runs/manifests/`. Only afterwards is effect-side data (what\n"
      "actually flooded, when roads closed) collected and scored. A prediction cannot\n"
      "be edited after the fact without changing its `run_id`.\n")
    W("**2. Progressive rain injection, causally.** Rainfall enters cell by cell,\n"
      "timestep by timestep, in real chronological order up to and through the event.\n"
      "The solver is causal: state at hour *t* cannot depend on rain after *t*. A\n"
      "single QPE-A-forced run is therefore already an operational replay, and warning\n"
      "times read off it are honest, with product latency added when quoted.\n")
    W("**3. Pre-registration with logged amendments.** Domains, resolutions,\n"
      "thresholds (0.15 m caution, 0.30 m impassable, from FHWA/NWS guidance), roughness\n"
      "and scoring rules were fixed in `prereg/` before effect research. Every later\n"
      "change is an amendment carrying its reason and an explicit flag for whether it\n"
      "postdates effect exposure. Two do, and say so.\n")
    W("**4. No calibration against the answer.** Rainfall is compared to gauges over\n"
      "matched accumulation windows and the bias is *reported, never applied*. No\n"
      "geometry, roughness or threshold was ever adjusted to improve agreement.\n")
    W("**5. Base rates and blinding.** Perfect detection scores were distrusted and\n"
      "tested against a matched random baseline, which exposed a ~90% neighbourhood\n"
      "base rate and forced a move to a continuous permutation test. Culvert detection\n"
      "was re-tested on blinded fixed-seed samples and reported as precision.\n")
    W("**Evidence hierarchy used throughout:** content hashes (strongest) \u2192\n"
      "filesystem timestamps and Git transaction history (supporting, described as\n"
      "machine-recorded metadata rather than cryptographic attestation) \u2192 prose\n"
      "(process statements only, never evidence).\n")

    # ---------------- 4. what the Ohio study did ---------------------------
    W("## 4. What the Ohio study established\n")
    W("| Finding | Status |\n|---|---|")
    for a, b in [
      ("Regional 60 m screening places documented flood locations in its deepest water, against a matched random baseline", "SUPPORTED"),
      ("A 60 m grid can support road open/closed decisions", "**REFUTED** \u2014 at three of twelve points it declares a road impassable while the surveyed pavement is 1.77\u20134.15 m above its water surface"),
      ("The apparent 11.6-hour warning on the I-70 closure was a lead time", "**RETRACTED** \u2014 the signal precedes the upstream gauge peak, so it cannot be the same wave. Case B"),
      ("Sub-grid smearing operates dynamically", "SUPPORTED at Pataskala \u2014 SR-310 carries 4.28 m in the channel while the carriageway never reaches 0.30 m"),
      ("A large freeboard means the coarse signal is false", "**BOUNDED** \u2014 W Broad St has the study's largest freeboard (+4.15 m) and the road floods anyway, because that cell contains no watercourse. A mismatch marks a closure *unverified*, not false"),
      ("Fine grids improve timing", "**NO** \u2014 the one gauge well inside a fine domain peaks 153 minutes early"),
      ("The model reproduces the multi-day fluvial crest that closed I-70", "REFUTED \u2014 the scalar drainage term linearly drains routed river water; no lake storage, spillway, baseflow or out-of-domain inflow is represented"),
      ("Flooding rerouted traffic onto US-40", "**NOT TESTABLE** \u2014 no traffic observations. What *is* shown is that US-40 never reached the impassable threshold while Main St peaked at 3.69 m: the detour's physical precondition held"),
    ]:
        W(f"| {a} | {b} |")
    W("")
    W("**Scoreboard: 5 of 12 corridor points are scoreable \u2014 4 confirmed, 1 refuted.**\n"
      "The other seven are retained with the reason each fails: four lie in the\n"
      "Buckeye nest, which never completed; one sits on a domain boundary where its\n"
      "water level is imposed rather than computed; two carry a prediction that the\n"
      "coarse grid *misses* flooding, which cannot be confirmed because the fine grid\n"
      "does not flood those roads either.\n")

    # ---------------- 4b. compute profile ---------------------------------
    W("## 4b. Compute profile \u2014 what actually sizes a machine\n")
    W("Measured on this host against the frozen engine, each nest in its own\n"
      "process so the RSS high-water mark is per-case. Synthetic terrain at the real\n"
      "grid dimensions; 30 solver steps to realise every lazily-allocated temporary.\n")
    W("| Nest | Grid | Cells | Peak RSS | Bytes/cell |\n|---|---|---|---|---|")
    for a, b, c_, d, e in [
      ("franklinton_c", "698 \u00d7 628 @ 6 m", "438,344", "122 MiB", "292"),
      ("pataskala_c", "619 \u00d7 1239 @ 8 m", "766,941", "189 MiB", "258"),
      ("buckeye_c", "937 \u00d7 727 @ 6 m", "681,199", "166 MiB", "256"),
      ("fixed overhead", "10 \u00d7 10 control", "100", "32 MiB", "\u2014"),
    ]:
        W(f"| {a} | {b} | {c_} | {d} | {e} |")
    W("")
    W("This is the **solver working set**. The full runner also holds accumulated\n"
      "hourly snapshots (~3.3 MiB per frame for Franklinton, so ~67 MiB over a 20-hour\n"
      "run), the probe history, the QPE rain series, the stage-BC arrays and the setup\n"
      "cache. A realistic full-run peak is therefore roughly **0.25\u20130.4 GB per nest**.\n")
    W("**Consequence for sizing.** RAM is not the binding constraint and does not pick\n"
      "the plan: four concurrent nests need well under 2 GB between them, which every\n"
      "small VPS already has several times over. **Cores are the constraint**, because\n"
      "the solver is single-threaded by construction (ML-1) and the only available\n"
      "parallelism is running separate nests side by side. One core per concurrent run,\n"
      "plus one spare. Four concurrent runs therefore want a 4\u20136 core box, and paying\n"
      "for RAM beyond ~4 GB buys nothing here.\n")
    W("The engine is frozen at `0b452c9` and the inner loop must **not** be optimised:\n"
      "any change to the arithmetic breaks bit-identical reproduction, which is the\n"
      "only cross-host gate this study has.\n")

    # ---------------- 5. chronology ---------------------------------------
    W("## 5. Chronology with provenance\n")
    W("Every row is a real Git transaction: the timestamp is recorded by Git at the\n"
      "moment of the change, and the SHA is content-derived over the tree.\n")
    merged = sorted(engine_commits() + [dict(c, repo="STUDY") for c in commits],
                    key=lambda c: c["date"])
    if not engine_present():
        W(f"*(engine repository not found at `{ENGINE}`; only study commits listed \u2014 "
          "set AQUA_SIM_ENGINE to include it)*\n")
    W("| # | UTC | Repo | Commit | Change and why it mattered |\n|---|---|---|---|---|")
    for i, cm in enumerate(merged, 1):
        first = cm["subj"].replace("|", "\\|")
        W(f"| {i} | {cm['date'][:16].replace('T',' ')} | {cm['repo']} | `{cm['sha'][:7]}` | {first} |")
    W("")

    # ---------------- 6. file inventory -----------------------------------
    W("## 6. File inventory with content hashes\n")
    W(f"All {len(rows)} tracked files, SHA-256 computed at generation time.\n")
    bykind = {}
    for p, hsh, sz, w, kind in rows:
        bykind.setdefault(kind, []).append((p, hsh, sz, w))
    for kind in ["spec", "code", "result", "data", "provenance", "figure",
                 "deliverable", "handoff", "other"]:
        if kind not in bykind:
            continue
        W(f"### {kind}\n")
        W("| Path | Bytes | SHA-256 | What it holds, and why |\n|---|---|---|---|")
        for p, hsh, sz, w in sorted(bykind[kind]):
            W(f"| `{p}` | {sz:,} | `{hsh[:16]}\u2026` | {w} |")
        W("")

    # ---------------- 6b. engine inventory --------------------------------
    W("## 6b. Engine file inventory (akhildhruva/aqua-sim @ 0b452c9)\n")
    ef = engine_files()
    if not ef:
        W(f"*(engine repository not present at `{ENGINE}`)*\n")
    else:
        W(f"{len(ef)} tracked files (vendored viewer libraries under `viz/vendor/` omitted). "
          "SHA-256 computed at generation time.\n")
        W("| Path | Bytes | SHA-256 | What it holds |\n|---|---|---|---|")
        for f, hsh, sz in ef:
            W(f"| `{f}` | {sz:,} | `{hsh[:16]}\u2026` | {ENGINE_WHY.get(f, '')} |")
        W("")

    # ---------------- 7. missing artefacts --------------------------------
    W("## 7. Missing artefacts \u2014 what cannot be reproduced from this repository\n")
    W("This section exists because omitting it would misrepresent what the repository\n"
      "can do. `.gitignore` excludes `*.npz`, `*.tif`, `*.grib2`, `data/raw/` and\n"
      "`data/cache/` \u2014 a deliberate choice to keep 8.8 GB of replaceable bulk out of\n"
      "Git. The machine holding those files was an ephemeral cloud container and has\n"
      "since been recycled. The consequences are concrete.\n")
    W("| Artefact | Status | Recorded identity | Consequence |\n|---|---|---|---|")
    for a, b, c_, d in [
      ("Buckeye frozen checkpoint (`state.npz`, `setup_cache.npz`, `probes.json`)",
       "**GONE**",
       "`handoff/buckeye_primary/FROZEN_SHA256SUMS`",
       "**Buckeye cannot be resumed.** The handoff bundle in this repo is scaffolding only \u2014 Dockerfile, pinned requirements, equivalence gate, reference hashes. It has no state to restore. Buckeye must be re-run from t=0."),
      ("Franklinton / Pataskala `state.npz`, `peak.npz`, `snaps.npz`", "GONE",
       "\u2014", "Inundation maps are not reproducible. Depth series survive."),
      ("Raw `probes.json` for both completed nests", "GONE",
       "`runs/*/probe_series.json` \u2192 `probes_json_sha256`",
       "**A from-scratch re-run can still be verified byte-for-byte against the committed hash.** This is the strongest available cross-host gate, and it survives only because the hash was committed even though the data was not."),
      ("MRMS QPE fields, 1 m LiDAR tiles, NHD, NTD", "not committed",
       "`evidence/source_manifest.json`, `evidence/dem1m_tile_inventory.json`",
       "Re-fetchable from public sources by recorded identity."),
      ("Parent boundary-stage series for each nest", "GONE",
       "\u2014", "Must be regenerated by re-running the 60 m parent, then `reproduction/extract_parent_bc.py`."),
    ]:
        W(f"| {a} | {b} | {c_} | {d} |")
    W("")

    # ---------------- 8. open failures ------------------------------------
    W("## 8. Open failures and measured limitations\n")
    try:
        ef = json.load(open("runs/checkpoint_metadata/engineering_failures.json"))
        W("| ID | Title |\n|---|---|")
        for e in ef["entries"]:
            t = e.get("title") or e.get("measured_limitation") or ""
            W(f"| {e['id']} | {str(t)[:150].replace('|', '/')} |")
        W("")
    except Exception as ex:
        W(f"(could not read engineering_failures.json: {ex})\n")

    # ---------------- 9. resuming -----------------------------------------
    W("## 9. How to resume this work\n")
    W("1. Clone the engine at the frozen commit `0b452c9` and this repository.\n"
      "2. Build the pinned environment from `handoff/buckeye_primary/Dockerfile`.\n"
      "3. Re-fetch inputs by identity from `evidence/source_manifest.json`.\n"
      "4. **Gate first.** Re-run Pataskala end to end and check its `probes.json`\n"
      "   against the committed `probes_json_sha256`. A byte-identical match\n"
      "   establishes cross-host determinism; anything else must be diagnosed with\n"
      "   `runs/pataskala_c_B/probe_series.json` before any new science is admitted.\n"
      "5. Only then re-run Buckeye from t=0, and the three sensitivity members.\n"
      "6. Run `python3 analysis/verify_published_numbers.py` \u2014 it must exit 0.\n")
    W("---\n")
    W("*Regenerate with `python3 handoff/generate_handoff.py`. Prefer appending to\n"
      "the Chronology by hand; regenerate only when stuck or seeding a new repo.*\n")

    text = "\n".join(out) + "\n"
    open("HANDOFF.md", "w", encoding="utf-8").write(text)
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(f"HANDOFF.md written: {len(text):,} bytes, {len(rows)} files, {len(commits)} commits")
    print(f"sha256(HANDOFF.md) = {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
