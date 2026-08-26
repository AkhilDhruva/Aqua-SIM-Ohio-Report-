# Version history

Git tag refs are rejected by this study environment's git proxy (HTTP 403 on
`refs/tags/*`, while branch pushes succeed). Version identity is therefore
recorded here by **commit SHA**, which is immutable and content-addressed — the
same principle the rest of this study relies on.

| Version | Commit | Meaning |
|---|---|---|
| `v0.1-archival` | `8d83f195f80cd921eeafc3ba6d537fd37f7ee54a` | Archival import of all work predating this repository. Historical work reconstructed and archived; see README.md for the limits of its retrospective timestamp evidence. |
| `v0.2` | `c5ff389` | Corridor checkpoint runner and restart-resilience evidence. First entry with genuine Git transaction history. |
| `v0.2.1` | `da244b2` | Wall-aware checkpointing; deterministic step grid; full state audit; wet-phase A/B restart proven bit-identical; single-core limitation measured; engineering-failure record. |
| `v0.2.2` | `6369a98` | Boundary-velocity audit. ML-3 resolved for Franklinton and Buckeye; EF-6 records the retraction of the spurious "interior 26.28 m/s" reading, which was a flaw in my own diagnostic rather than in the model. |
| `v0.4` | `194397d` | **Pataskala corridor result — first nest to complete its full 20 h window.** Smearing mechanism confirmed dynamically: three blind static freeboard predictions, three held, including a 4.07 m road-minus-channel differential at SR-310. New claims C8a (gauge peak 153 min early) and C10a (US-40 remained passable — the detour's physical precondition). EF-7 and EF-8. |

Everything after `v0.1-archival` carries genuine Git transaction history —
authored and committed timestamps recorded by Git at the moment of the change,
not reconstructed afterwards.

## Planned

| Version | Contents |
|---|---|
| `v0.5` | Franklinton corridor result (numbered after v0.4 because Pataskala finished first — version order follows completion, not the nest list) |
| `v0.6` | Buckeye Lake / I-70 corridor result, resumed off-platform from the frozen checkpoint |
| `v0.7` | sensitivity members (no-drain, infiltration, no-boundary-stage) |
| `v1.0` | frozen Phase-2 report |

To verify the archival boundary:

```bash
git log --format='%H %aI %s' 8d83f195f80cd921eeafc3ba6d537fd37f7ee54a -1
```
