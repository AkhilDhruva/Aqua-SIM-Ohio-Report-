# Methods

## 1. Protocol

The study separates **cause** data (rainfall, terrain, infrastructure geometry)
from **effect** data (what actually flooded, what closed, when). Predictions were
constructed from cause data alone, sealed, and only then compared to effect data.

Order of operations:

1. Forcing and terrain assembled from public sources.
2. Sensor locations placed **automatically by the terrain** (lowest basin
   points), never by hand — nothing an operator had read could steer placement.
3. Runs executed; outputs identified by `run_id`, a content hash of inputs and
   provenance.
4. Effect corpus collected from public reporting, each location requiring at
   least two independent sources.
5. Scoring by script, with thresholds (0.15 m caution, 0.30 m impassable, 250 m
   geocode neighbourhood) fixed before scoring.

No rainfall, roughness, terrain, infiltration, sensor location, or threshold was
adjusted to improve agreement with a known outcome, at any point.

**Honest limit.** This is a single-agent approximation of an air gap. The
operator saw press headlines while researching forcing. The protections are
structural — terrain-driven sensors, content-hashed outputs, pre-fixed scorer
parameters — not institutional separation.

## 2. Forcing

MRMS quantitative precipitation estimates from the NOAA Open Data bucket, in two
families:

- **QPE-A** — `RadarOnly_QPE_15M`, 15-minute cadence. Low latency; represents
  what would have been available operationally.
- **QPE-B** — `MultiSensor_QPE_01H_Pass2`, hourly, gauge-corrected. Retrospective
  best estimate.

135 files, each checksummed (`analysis/qpe_validation/qpe_inventory.json`).
Fields are cropped to the domain, negative missing codes masked, and applied as
per-cell, time-varying rain. Accumulations are validated against gauges over
**matched windows** and the bias reported, never applied.

Infiltration is zero in the primary configuration. This is a physical statement
about eleven consecutive antecedent rain days, not a tuning choice; a sensitivity
member varies it.

## 3. Terrain and hydraulic geometry

- **Parent domain**: USGS 3DEP 1/3-arcsecond, resampled to 60 m over greater
  Columbus and western Licking County.
- **Corridor domains**: USGS 3DEP **1 m LiDAR** at 6 m (8 m for Pataskala).
- **Channels**: NHD High Resolution flowlines, HU8 05060001 and 05040006.
- **Roads**: USGS National Transportation Dataset (MAF/TIGER-derived); Manning's
  n of 0.013 on carriageways, 0.035 in channels, 0.05 elsewhere.
- **Culverts**: at each road × flowline crossing whose bare-earth profile shows a
  continuous embankment, an orifice connection is inserted so the model does not
  invent a dam. Crossings the DTM already shows open (bridges) are left alone.
  Detection precision was audited blind against 1 m LiDAR: 91–96%.

## 4. Solver extension

The engine was consumed unmodified. A side-task subclass adds per-cell
time-varying rainfall, Dirichlet stage boundaries for nesting, and 60-second
depth probes. Correctness anchor: **with uniform forcing the extension reproduces
the stock solver bit-for-bit**, on both the bare and conditioned code paths, so
no result can be an artifact of the extension itself.

## 5. Nesting

Corridor domains receive rainfall on grid plus water-surface boundary conditions
taken from the parent run's perimeter, imposed only while the parent cell is
genuinely wet — a dry parent stage equals its bed elevation and would otherwise
inject phantom water into a finer domain whose bed is lower.

## 6. Execution under an unreliable host

The execution container recycles every few hours. Runs therefore checkpoint
solver state — depths, both flux fields, model time, running peak, and full probe
history — atomically, and resume automatically. Verified in practice: runs killed
mid-solve resumed at their exact model hour with probe series continuous across
the boundary.

An earlier wide-domain attempt was abandoned after measurement, not guesswork:
frame intervals grew 0.2 → 29.5 → 101.2 minutes as deep water collapsed the CFL
timestep, implying 30–100+ hours per nest. Domains were reduced in **extent**
while **preserving resolution**, the lesser scientific compromise, and the change
is logged as a pre-registration amendment.

## 7. Scoring definitions

- **Detection**: peak depth ≥ 0.15 m within 250 m of a reported location.
- **Rank skill**: permutation test on continuous neighbourhood peak depths,
  20,000 resamples, against matched random in-domain locations.
- **Base-rate control**: Monte-Carlo estimate of the chance of the observed hit
  count, which is what exposed the Phase 1 binary score as inconclusive.
- **Road inundation**: ≥ 3 contiguous carriageway cells over 0.30 m.
- **Smearing diagnostic**: the coarse cell's bed elevation compared against the
  surveyed carriageway and the channel invert, yielding the freeboard between the
  coarse model's water surface at its own impassability threshold and the real
  pavement.
- **Gauge comparison**: timing and shape only. The observed series is NWM
  analysis_assim discharge, so no stage RMSE is computable; that is stated rather
  than approximated.

## 8. What cannot be computed here

A false-alarm rate. Public reporting records what flooded, never what stayed dry.
Without an authoritative record of roads that remained open, only detection can
be quantified.
