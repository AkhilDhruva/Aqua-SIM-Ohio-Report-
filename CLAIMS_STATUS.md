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
PENDING. Corridor nests at 6–8 m were still solving at archival time. They can
strengthen or complicate the *mechanism*; they cannot change the direction of
C4/C5, which rest on surveyed elevations and observed gauge timing.
→ `runs/checkpoint_metadata/corridor_status.json`

## Consequence chain

**C9. I-70 was closed by flooding near Buckeye Lake and US-40 was the designated
detour.** SUPPORTED (documentary, E1). ODOT closure at Exit 129 with official
detours routing over US-40 in both directions.
→ `evidence/road_closures/effect_research.json`

**C10. Traffic was measurably displaced onto US-40 through Etna/Pataskala.**
NOT TESTABLE. Only anticipatory statements were found; OHGO and all traffic data
hosts were egress-blocked. Designation of a detour is not evidence of
displacement, and the two are kept separate.

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
