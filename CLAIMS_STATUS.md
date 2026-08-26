# Claims status

Every substantive claim made during this study, with its current standing and
the artifact that decides it. Claims are only as strong as the evidence level
noted in `README.md`; nothing here is upgraded by assertion.

Status vocabulary: **SUPPORTED** (evidence presented and survives its own
control) · **REFUTED** (evidence contradicts it) · **RETRACTED** (previously
asserted by this study, now withdrawn) · **PENDING** (test defined, not yet
complete) · **NOT TESTABLE** (required data unreachable).

---

## Detection and forcing

**C1. A rainfall-driven screen independently identifies the areas that flooded.**
SUPPORTED. Under the frozen scorer, 16 of 17 documented flood locations fall in
the model's deepest water; permutation test p ≈ 0.035–0.045; chance of ≥16/17
against a matched random baseline is 3.4% (radar-only) / 6.8% (multi-sensor).
→ `analysis/scoring/rescore_run_qpe*_parent.json`

**C1a. The Phase 1 uniform-rainfall result was not itself decisive.**
SUPPORTED. With uniform forcing the 250 m neighbourhood base rate reached ~91%,
making a perfect 17/17 binary score consistent with chance (p ≈ 0.16–0.22). The
defensible Phase 1 claim was always the continuous rank test (p_median ≈ 0.003),
not the binary score. → `analysis/scoring/control_analysis.json`,
`analysis/scoring/permutation_test.json`

**C2. Operational-latency radar-only forcing retains the spatial skill.**
SUPPORTED, NARROWLY. QPE-A retained discrimination comparable to the
gauge-corrected product in this single hindcast. This is not a claim that
radar-only forcing provides operational early warning; that requires the
timestamp replay, which C6 addresses and which did not succeed.

**C3. MRMS accumulations verify against gauges over matched windows.**
SUPPORTED WITH KNOWN BIAS. Storm-window multi-sensor QPE lands within 4% at
Buckeye Lake and inside the Pataskala gauge spread; radar-only runs materially
low (~−35% at Pataskala) in this warm-rain convective event. Bias is reported,
never corrected. An earlier "−46%" figure was a time-window mismatch artifact
and is superseded. → `analysis/qpe_validation/matched_window_validation.json`

## Resolution and road-level decisions

**C4. A 60 m screening grid can support road open/closed decisions.**
REFUTED. At three of twelve corridor points the grid declares a road impassable
while the surveyed carriageway is 1.77–4.15 m above its water surface; at four
others the grid's bed sits above the real road, so genuine street flooding goes
unseen. → `analysis/geometry_audit/smear_geometry.json`

**C5. The early I-70 threshold crossing was an early warning of the closure.**
**RETRACTED.** Previously reported as a +695-minute (11.6 h) lead time. Two
independent lines refute the causal identity: the model's signal at 10:25Z
preceded the *upstream* South Fork peak at 13:00Z, and a routed wave cannot
reach a downstream point before its upstream peak; and the 60 m cell at that
crossing sits 2.07 m below the carriageway, so its "road flooding" is channel
water. Determination: **Case B** — coincidental local/channel wetting, not the
fluvial pathway that closed the road.
→ `analysis/case_ab/case_ab_determination.json`

**C5a. Sub-grid smearing biases the apparent result toward Case A.**
SUPPORTED. Where the coarse bed sits between channel invert and pavement, the
grid produces false "impassable" declarations that resemble predictive skill.
The bias also runs the other way (missed detections) where the coarse bed sits
above the road. → `analysis/geometry_audit/`

## Routing and hydraulics

**C6. The model reproduces the multi-day fluvial crest that closed I-70.**
REFUTED. The extended 56 h parent recedes at exactly the drainage-parameter rate
instead of rising to the observed crest ~24 h later. Structural causes,
identified before comparison to the observed crest: the scalar storm-drain term
removes routed river water uniformly, and no lake storage, dam or spillway
operation, baseflow, or out-of-domain inflow is represented. The observed 28 h
routing lag is outside the configured physics.
→ `prereg/amendments/`, `analysis/case_ab/timing_run_qpeB_parent_ext.json`

**C7. Automated culvert detection is reliable enough to trust unreviewed.**
PARTIALLY SUPPORTED. Blinded fixed-seed samples re-tested against 1 m LiDAR give
91–96% precision across three corridors. Useful, not sufficient: a crossing
wrongly modelled as solid embankment creates a dam that does not exist.
→ `analysis/culvert_audit/`

**C8. Fine-resolution nests confirm the smearing mechanism dynamically.**
SUPPORTED at Pataskala; BOUNDED at Franklinton; still PENDING at Buckeye.

`pataskala_c` (8 m, 1239×619) completed its full 20 h window. The static
freeboard diagnostic in `analysis/geometry_audit/` had made three falsifiable
predictions *before* the nest was run, from terrain alone. All three held:

| probe | freeboard to pavement | static prediction | nest road peak | nest channel peak | verdict |
|---|---|---|---|---|---|
| `main_broad_pataskala` | −0.18 m | 60 m bed ≈ pavement, so its signal is real | 3.69 m | 4.47 m | CONFIRMED |
| `kirkersville_gauge_03144816` | −0.36 m | 60 m bed ≈ pavement, so its signal is real | 2.99 m | 2.99 m | CONFIRMED |
| `sr310_sf_crossing` | **+3.44 m** | 60 m would flood a road that is dry | **0.20 m** | **4.28 m** | PARTIAL — road never reaches 0.30 m while the channel beside it carries 4.28 m |

The 4.07 m road-minus-channel differential at SR-310 is the smearing mechanism
caught in the act: the coarse grid reports that crossing as flooded because one
60 m cell averages carriageway and channel invert together, and at 8 m the two
separate cleanly. The two remaining probes (`us40_etna`, `us40_east`) carry
*negative* freeboard, meaning the coarse bed sits above the real road and the
prediction is under-reporting; both are dry-to-partial at 8 m as well, so
nothing was available to under-report and those predictions are untested rather
than confirmed.

This is dynamic confirmation of the *mechanism* only. It does not change the
direction of C4/C5, which rest on surveyed elevations and observed gauge timing.
→ `analysis/corridor_analysis_pataskala_c.json`, `runs/pataskala_c_B/`

**C8b. Franklinton bounds the mechanism: a large freeboard does not by itself
mean the coarse signal is false.**
SUPPORTED. `franklinton_c` (6 m, 628×698) completed its full 20 h window.

| probe | freeboard to pavement | static prediction | nest road peak | outcome |
|---|---|---|---|---|
| `wbroad_hilltop` | **+4.15 m** — the largest in the study | 60 m floods a road that is dry | **2.22 m** | **prediction FAILS — the road really floods** |
| `franklinton_core` | −0.38 m | 60 m bed ≈ pavement, signal real | 1.70 m | confirmed |
| `olentangy_gauge_03227107` | −5.04 m | — | 2.17 m | **not usable — see below** |

`wbroad_hilltop` is the instructive one. Its 60 m cell sits 4.15 m below the
carriageway, so the freeboard test predicts the coarse "impassable" signal there
is channel smearing. At 6 m the carriageway floods anyway, to 2.22 m. The reason
is visible in the terrain: that probe has **zero channel cells** — it is a
hilltop with no stream in it. The water is rain-on-grid ponding in a local
depression, not channel water borrowed from a neighbouring cell.

So the freeboard diagnostic identifies where the coarse grid *can* manufacture a
false road signal, not where it *does*. Pataskala shows the mechanism operating
(SR-310, 4.07 m road-minus-channel differential); Franklinton shows a large
freeboard coexisting with genuine flooding. Both are needed: a screening test
that only ever confirms itself is not a test.

**Structural limitation.** Only `olentangy_gauge_03227107` carries a `__channel`
pair, and it sits at distance **0** from the domain edge, where the Dirichlet
stage boundary imposes its water level. Franklinton therefore **cannot** run the
road-versus-channel discriminator that produced Pataskala's result, and its one
channel-paired probe is boundary-driven rather than independently resolved.
→ `analysis/corridor_analysis_franklinton_c.json`, `runs/franklinton_c_B/`

**C8c. The Franklinton nest reproduces the Olentangy gauge peak to +31 minutes.**
REPORTED, NOT CLAIMED AS SKILL. Model peak 08-20 12:31Z against 12:00Z observed,
normalised shape r = 0.917. The number is good and it is nearly meaningless as a
test of the nest: **the gauge probe sits on the domain boundary**, where the
parent's stage is imposed as a Dirichlet condition. That timing is substantially
the 60 m parent's, propagated through the boundary, not physics the 6 m nest
generated. It is recorded because suppressing a favourable number would be as
selective as featuring it — but it must not be read as independent validation.
The observed series also begins before t0 already above the rise threshold, so
only the peak comparison is meaningful, and the model window truncates the
recession. Contrast Pataskala's gauge, which is 78 cells inside its domain and
peaks 153 minutes EARLY — that one is a real test, and the nest fails it.
→ `analysis/gauge_timing_corridor_franklinton_c_B.json`

**C8d. The Froude-3.65 episode at Franklinton was transient, not divergence.**
SUPPORTED. Ten samples spanning h=14.28 → 20.00, recorded while the run was in
progress rather than reconstructed afterwards:

| model hour | interior faces >5 m/s | median Froude | outfall ghost max | domain volume |
|---|---|---|---|---|
| 14.28 | 198 | 3.53 | 169.0 m/s | 1.97 × 10⁶ m³ |
| 15.66 | 122 | 2.45 | 169.1 m/s | 2.84 × 10⁶ m³ |
| 16.45 | 209 | 1.72 | 87.7 m/s | 3.16 × 10⁶ m³ |
| 20.00 | 265 | 1.68 | 56.7 m/s | 4.83 × 10⁶ m³ |

Froude falls monotonically as depth grows, volume rises monotonically, no cell
is ever negative or non-finite, and the thin-film fraction of the fast faces
falls from 82/211 to **13/265** — at the final state 218 of 265 carry more than
1 m of water at median conveyance depth 1.92 m. The high-Froude episode
coincided with the pluvial peak around h≈14 and resolved as the rivers filled.
Franklinton's *final-state* velocities are inside the local-inertial scheme's
envelope; its transient peak velocities around h=14 are not, and remain
undefensible.
→ `analysis/fast_face_log.jsonl`, `analysis/boundary_velocity_audit.json`

**C8a. The nest reproduces observed hydrograph timing at a gauged reach.**
PARTIALLY SUPPORTED. At South Fork Licking below Kirkersville (03144816) the
nest peaks 08-20 10:27Z against 13:00Z observed — **153 minutes early** — with
rise onset 60 minutes early and normalised shape correlation r = 0.854 over the
overlapping window. The comparison is timing and shape only: the observed series
is NWM v3 analysis_assim discharge (USGS-nudged), so no stage RMSE is
computable, and the model window ends at 14:00Z so the recession is truncated.
A 2.5 h early peak on a flashy 8 m nest is a real error, not a success, and it
is in the direction expected from omitting channel storage and baseflow.
→ `analysis/gauge_timing_corridor_pataskala_c_B.json`

## Consequence chain

**C9. I-70 was closed by flooding near Buckeye Lake and US-40 was the designated
detour.** SUPPORTED (documentary, E1). ODOT closure at Exit 129 with official
detours routing over US-40 in both directions.
→ `evidence/road_closures/effect_research.json`

**C10. Traffic was measurably displaced onto US-40 through Etna/Pataskala.**
NOT TESTABLE. Only anticipatory statements were found; OHGO and all traffic data
hosts were egress-blocked. Designation of a detour is not evidence of
displacement, and the two are kept separate.

**C10a. US-40 (National Road) through Etna/Pataskala remained passable while
Main Street flooded — i.e. the detour's physical precondition held.**
SUPPORTED (model, cause-side). In the completed 8 m nest, US-40 never reaches
the 0.30 m impassable threshold anywhere along either probed segment
(`us40_etna` peak 0.04 m — dry; `us40_east` peak 0.22 m — caution only, from
08:42Z), while `main_broad_pataskala` crosses caution at 05:58Z, crosses
impassable at 06:12Z and peaks at 3.69 m of water on the carriageway.

This is deliberately the weaker of the two possible claims. It says the
designated detour was hydraulically available, which is a statement about water
and elevation that this model can make. It does **not** say flooding rerouted
traffic onto National Road — that requires traffic observations this study never
obtained, and remains C10, NOT TESTABLE.
→ `analysis/corridor_analysis_pataskala_c.json`

**C11. Upstream gauges give usable lead time for the I-70 corridor.**
SUPPORTED (observational). The measured Kirkersville→Buckeye Lake routing lag is
~28 h, from instruments already in the ground. This is an observation about the
river, not a model result.

## Software

**C12. The spatial-forcing extension does not alter legacy solver behaviour.**
SUPPORTED. With uniform forcing the extended solver reproduces the stock
NumPy solver bit-for-bit on both the bare and conditioned code paths.
→ `tests/solver_equivalence/test_qpe_solver.py`

**C13. The aqua-sim engine was modified by this study.**
FALSE BY CONSTRUCTION. The engine repository stayed clean throughout and is
pinned at `0b452c9d5`.
