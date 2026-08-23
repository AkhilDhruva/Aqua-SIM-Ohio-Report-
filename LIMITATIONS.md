# Limitations

These bound every claim in `CLAIMS_STATUS.md`. None is rhetorical.

## Protocol

**Single-agent air gap.** The operator saw press headlines while researching
forcing. Separation is structural (terrain-placed sensors, content-hashed
outputs, pre-fixed scorer parameters), not institutional.

**Retrospective timestamp evidence.** The pre-registration file carries no
wall-clock timestamp in its body. Ordering is evidenced by filesystem mtimes —
machine-recorded, but mutable and not cryptographically attested. See the
three-level framing in `README.md`.

**One amendment postdates outcome exposure.** The simulation window was extended
after the observed crest timing was known. It is labelled as such in
`prereg/amendments/`. All forcing, geometry, roughness and thresholds were fixed
beforehand and never altered.

## Data

**No false-alarm rate.** See `METHODS.md` §8.

**River observations are a proxy.** Direct USGS endpoints were egress-blocked.
NWM analysis_assim assimilates live USGS gauges but is not raw observation and
carries discharge only — no stage, therefore no stage error statistic.

**Several impact timestamps are approximate.** Some are phrased as "around" an
hour; at least one closure start is inferred. Two reported accounts of the I-70
closure time disagree by roughly ninety minutes. Each fact carries its own
confidence and precision in the effect corpus.

**Rainfall figures rest on press paraphrase of NWS.** Primary NWS public
information statements and CoCoRaHS were unreachable. One widely quoted station
total was identified as a multi-day cumulative and excluded from bias
computation.

**Buildings are absent.** Footprint sources were unreachable, so urban flow
obstruction in Franklinton is represented by terrain alone.

**Roads are 2018-vintage MAF/TIGER** via the USGS National Transportation
Dataset; census.gov was blocked. Post-2018 alignment changes are unrepresented.

## Physics

**Multi-day fluvial routing is not represented.** The scalar drainage term
removes routed river water; lake storage, dam and spillway operation, baseflow,
and out-of-domain inflow are all absent. The observed 28 h routing lag lies
outside the configured physics.

**Rainfall is applied at its native ~1 km resolution.** Resampling onto a 6 m
hydraulic grid adds routing detail, not rainfall information.

**Corridor extents are small.** Domains were cut to fit the compute budget, so
boundary influence is proportionally larger than in the abandoned wide nests.

**Culvert geometry is inferred, not surveyed.** 91–96% precision means real
false positives remain. Culvert size is a single assumed orifice area, not a
structure inventory.

## Scope

**One event, one metropolitan area.** Nothing here establishes performance on
other storms, other terrain, or other seasons.

**Screening resolution for the regional result.** The 60 m parent identifies
corridors and neighbourhoods, not streets — which is the study's central finding
rather than an aside.
