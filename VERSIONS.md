# Version history

Git tag refs are rejected by this study environment's git proxy (HTTP 403 on
`refs/tags/*`, while branch pushes succeed). Version identity is therefore
recorded here by **commit SHA**, which is immutable and content-addressed — the
same principle the rest of this study relies on.

| Version | Commit | Meaning |
|---|---|---|
| `v0.1-archival` | `8d83f195f80cd921eeafc3ba6d537fd37f7ee54a` | Archival import of all work predating this repository. Historical work reconstructed and archived; see README.md for the limits of its retrospective timestamp evidence. |
| `v0.2` | `c5ff389` | Corridor checkpoint runner and restart-resilience evidence. First entry with genuine Git transaction history. |

Everything after `v0.1-archival` carries genuine Git transaction history —
authored and committed timestamps recorded by Git at the moment of the change,
not reconstructed afterwards.

## Planned

| Version | Contents |
|---|---|
| `v0.3` | Franklinton corridor result |
| `v0.4` | Pataskala corridor result |
| `v0.5` | Buckeye Lake / I-70 corridor result |
| `v0.6` | sensitivity members (no-drain, infiltration) |
| `v1.0` | frozen Phase-2 report |

To verify the archival boundary:

```bash
git log --format='%H %aI %s' 8d83f195f80cd921eeafc3ba6d537fd37f7ee54a -1
```
