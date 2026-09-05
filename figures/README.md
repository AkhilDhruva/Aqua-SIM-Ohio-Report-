
## Corridor result figures (added 2026-09-05)

Rendered by `figures/make_figures.py` from the **committed derived data**, not
from raster fields. The raster outputs (`peak.npz`, `snaps.npz`) were never
committed — `.gitignore` excludes `*.npz` deliberately — and the machine holding
them has since been recycled, so **inundation maps are not reproducible from this
repository**. What is committed is the 60 s depth series at every corridor probe,
which is the evidence the road-versus-channel finding actually rests on.

| file | what it shows |
|---|---|
| `fig1_road_vs_channel.png` | carriageway depth against the channel beside it, per corridor point, with the caution and impassable thresholds |
| `fig2_prediction_outcome.png` | all twelve corridor points: terrain-only freeboard prediction against what the fine grid did, including the seven that cannot be scored and why |
| `fig3_numerical_health.png` | the ten in-flight diagnostic samples from Franklinton — Froude, domain volume, outfall boundary velocity |

The earlier `columbus_*.png` files are viewer screenshots of the **60 m screening
run**, not the corridor nests, and are kept for context.

Plotting `fig1` is what exposed the single-sample overshoot on the
`wbroad_hilltop` peak, now documented under C8b — a defect that four separate
numerical audits had not surfaced, because none of them looked at the shape of
the series.
