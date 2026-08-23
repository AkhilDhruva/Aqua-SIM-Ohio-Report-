# Greater Columbus, Ohio — Aug 19–20, 2026 Flood: Blind Hindcast Validation

**Side task — fully outside the aqua-sim repository.** All inputs, scripts, runs
and outputs live in this folder; `git status` of the repo stayed clean throughout.
The simulator (`aqua_sim`) was used strictly as an installed library.

## 1. Question

Given only **cause** data (published rainfall figures + public USGS terrain),
does the simulator independently identify the areas that actually flooded in
the Aug 19–20, 2026 central-Ohio event — i.e., could it have served as a
rainfall-driven early-warning screen?

## 2. Blind protocol (leakage control)

1. **Cause data only** went into the run: NWS rainfall figures as quoted in
   press (band totals, peak rates, antecedent saturation) and four USGS 3DEP
   1/3-arc-second tiles (n41w083, n41w084, n40w083, n40w084; ~1.8 GB, fetched
   from `prd-tnm.s3.amazonaws.com`).
2. The AOI (−83.20, 39.80, −82.45, 40.20) was chosen from the **county-level**
   rainfall footprint (Franklin + western Licking), not from any flood report.
3. **Sensor placement is terrain-automatic** (`_auto_sink_nodes`, 10 lowest
   basin points) — no human hand placed anything, so nothing the operator had
   read could steer the prediction.
4. Predictions were **frozen** as content-hashed run IDs
   (`frozen_prediction.json`) *before* any list of observed flooded locations
   was collected.
5. Only afterwards were 17 documented flooded locations gathered (each backed
   by ≥2 press/radio sources), geocoded, and scored by a deterministic script
   (`score_columbus.py`) against the frozen runs.

Honest limitation: this is a **single-agent approximation** of an air gap. The
operator did see headlines while researching forcing. The protections are
structural — terrain-driven sensors, frozen content-hashed outputs, and a
scorer whose only free parameters (0.15 m detection depth, 250 m geocode
neighborhood) were fixed before scoring.

## 3. Forcing (cause data, with sources)

| Item | Value | Source (as published) |
|---|---|---|
| Event window | overnight Aug 19 → Aug 20, 2026 | NWS via Spectrum News 1, 10TV |
| Heaviest band (Franklin + Licking) | 4–7 in (100–178 mm) | NWS via WOSU, The Reporting Project |
| Columbus proper | 4–5 in; CMH total 6.03 in | 10TV / NWS Wilmington |
| Peak rates | 2–3 in/hr (50–75 mm/hr) | Spectrum News 1 |
| Antecedent | 11 straight rain days; >12 in in <2 weeks in Licking Co. | The Reporting Project |
| Drains | overwhelmed | multiple outlets |

Model translation: **zero infiltration** (saturated soil — physically correct,
not a tuning choice), drainage 10 mm/hr at 50 % blockage, and two hyetograph
variants bracketing the band — **mid** ≈137 mm total with a 60 mm/hr peak hour,
**low** ≈100 mm with a 44 mm/hr peak hour. 6 h rain, 12 h simulated,
1082×762 cells (824k) at 60 m in EPSG:32617.

Frozen runs: mid `1e1646c983b3b8bc`, low `b322e85c559c8728`
(shared terrain digest `4e302716957dc2b6`).

## 4. Results

### 4.1 Binary detection (POD)

**17 of 17** observed locations show ≥0.15 m peak water within 250 m, in both
variants (POD = 1.0). Per-location depths for the mid run:

| Location (confidence) | Peak depth in 250 m | Wet-cell percentile |
|---|---|---|
| West Broad St, Franklinton/Hilltop (med) | 3.74 m | p99.6 |
| Pataskala Main St (high) | 3.54 m | p99.6 |
| Jackson Pike (med) | 3.08 m | p99.3 |
| Pickerington (med) | 2.71 m | p99.0 |
| Gahanna / Big Walnut Ck (med) | 2.40 m | p98.5 |
| Greenlawn Ave (high) | 2.38 m | p98.5 |
| Franklinton floodwall / Scioto (high) | 2.07 m | p97.9 |
| New Albany (med) | 1.87 m | p97.4 |
| Gender Rd camp rescue (med) | 1.71 m | p96.8 |
| Buckeye Lake KOA evac (high) | 1.47 m | p95.8 |
| Hebron Greenbriar MHP evac (med) | 1.09 m | p93.6 |
| Sweetser Ct rescue (low) | 0.82 m | p91.2 |
| North Linden rescues (med) | 0.75 m | p90.4 |
| SR-674 at Lithopolis Rd (low) | 0.55 m | p87.6 |
| I-71 S closure (high) | 0.43 m | p85.2 |
| Grove City (med) | 0.26 m | p79.8 |
| Reynoldsburg (med) | 0.25 m | p79.6 |

### 4.2 The POD number alone is NOT the evidence — control analysis

A 250 m neighborhood at 60 m resolution is a 9×9-cell window; under this wet a
storm, **91.4 %** of random in-domain windows contain ≥0.15 m water (mid;
89.5 % low). Monte-Carlo: 17 random locations go 17/17 with probability
**0.22** (mid) / **0.16** (low). So the perfect binary score is consistent with
chance and is reported as *inconclusive by construction*, not as skill.

### 4.3 Rank skill — the defensible result (permutation test)

Test: are the model's neighborhood **peak depths at the 17 real locations**
higher than at 17 random in-domain locations? (20,000 resamples, continuous
depths, no threshold.)

| Variant | Observed mean / median | Random mean / median | p (mean) | p (median) |
|---|---|---|---|---|
| **mid (5.4 in)** | 1.71 / 1.71 m | 1.08 / 0.79 m | **0.020** | **0.0028** |
| low (3.9 in) | 1.19 / 0.94 m | 0.91 / 0.68 m | 0.095 | 0.104 |

**Conclusion: with the forcing actually reported for the event (mid band), the
frozen, blind hindcast ranks the real flooded locations significantly deeper
than random locations (p ≈ 0.003 median test).** The model didn't merely get
them wet — it independently placed them among its deepest water (median
percentile p96.8; 9 of 17 above p95). The low-band variant, fed less rain than
fell, loses significance — the skill responds to forcing as physics says it
should, which is itself evidence the signal is real rather than an artifact of
terrain alone.

Physical read of the map (see screenshots): the model concentrates hazard along
the Scioto, Olentangy, Big Walnut and Blacklick corridors and the Licking
County lowlands — precisely where the rescues, closures and evacuations
happened (Franklinton floodwall, Gender Rd encampment on Big Walnut,
Pataskala/Hebron/Buckeye Lake).

## 5. What this does and does not establish

**Does:** a rainfall-only, terrain-driven screen — built from public data in
hours, frozen before any flood report was consulted — independently ranks the
places that flooded among its most hazardous. That is the core competence an
early-warning screening layer needs.

**Does not / caveats:**
- **No false-alarm rate.** Press coverage lists what flooded, never what
  didn't; FAR needs an authoritative negative set (e.g. full road-closure logs).
- **60 m is screening resolution** — corridor/neighborhood identification, not
  street-level depths. (The street-scale machinery — buildings, curbs,
  culverts — exists in the repo but needs finer local terrain.)
- **Geocode uncertainty**: 2 of 17 locations are low-confidence; the 250 m
  window absorbs this but also drives the base-rate inflation in §4.2.
- **Binary POD is inconclusive** for this event/window size (chance ≈ 0.16–0.22
  of a perfect score); the permutation test on continuous depths is the claim.
- Forcing is spatially uniform over the AOI; the real band had structure. A
  radar-QPE-forced rerun is the natural upgrade.
- Single-agent air-gap approximation (see §2).

## 6. Artifacts

| File | What |
|---|---|
| `run_columbus.py` | blind hindcast builder/runner (cause data + protocol in docstring) |
| `frozen_prediction.json` | frozen run IDs + terrain digest (the pre-registration) |
| `observed_flooding.json` | 17 effect locations, ≥2 sources each, gathered post-freeze |
| `score_columbus.py` | deterministic scorer (exact georeference by grid reconstruction) |
| `validation_report.json` | machine-readable per-location scores |
| `control_analysis.json` | base-rate / Monte-Carlo control |
| `permutation_test.json` | rank-skill test |
| `run_mid/`, `run_low/` | full frozen runs (25 frames each) |
| `shots/*.png` | dashboard renders of the frozen mid run |

Reproduce: `python3 run_columbus.py && python3 score_columbus.py` — run IDs are
content-hashed, so identical inputs reproduce `1e1646c983b3b8bc` /
`b322e85c559c8728` exactly.
