# Buckeye primary run — off-platform continuation bundle

The Buckeye corridor nest is the headline test of the Columbus validation study:
whether the I-70 carriageway at the South Fork Licking crossing actually wets
during the storm, or whether the 60 m screening model's "impassable" signal was
channel water smeared onto a road-bearing cell (the published Case B finding).

It could not be completed on the study host, which tears the execution container
down between interactive turns (~10% duty cycle — see ML-4 in
`runs/checkpoint_metadata/engineering_failures.json`). This bundle continues the
**same primary run**, unchanged, on a persistent machine.

## What is preserved, exactly

| | |
|---|---|
| checkpoint | model hour **7.7322**, 463 probe samples |
| solver | the same NumPy solver, unmodified |
| engine | `akhildhruva/aqua-sim` @ `0b452c9d5ccffd88ea8308322087b09807242b4b` |
| setup cache | terrain, roughness, culverts, probe cells, rain index map, stage BC |
| forcing | MRMS MultiSensor QPE-B, byte-identical |
| domain & boundary | **unchanged** — original extent, original OPEN boundary |
| parameters | unchanged (cfl 0.7, drainage 10 mm/hr @ 0.5 blockage, zero infiltration) |

`frozen/SHA256SUMS` fixes the checkpoint bytes. The domain is **not** re-scoped
and the OPEN boundary is **not** modified: those would make this a different
experiment. A smaller or repositioned Buckeye domain may be run later only as an
explicitly labelled post-hoc sensitivity member — never as a replacement.

## Run it

**Docker (recommended — reproduces the pinned stack):**

```bash
docker build -t buckeye .
docker run --rm -v "$PWD:/work" buckeye ./resume_buckeye.sh
```

**WSL2 directly:**

```bash
sudo apt install -y python3 python3-venv git
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
git clone https://github.com/AkhilDhruva/aqua-sim /tmp/aqua-sim
cd /tmp/aqua-sim && git checkout 0b452c9d5ccffd88ea8308322087b09807242b4b \
  && pip install -e . && cd -
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0
./resume_buckeye.sh
```

Single-threaded BLAS is set deliberately. The solver is elementwise NumPy, and
letting BLAS choose a thread count can change reduction order — which changes
the arithmetic and will fail the gate below.

## The equivalence gate (run before resuming — `resume_buckeye.sh` does this)

```bash
python3 crosshost_equivalence.py
```

It advances the frozen checkpoint by 600 model-seconds and compares SHA-256
hashes of depth, both flux fields and the running peak, plus max depth, max face
velocity, total volume and probe count, against `reference.json` produced on the
originating host.

* **PASS** — the arithmetic is identical; resuming continues the same run.
* **FAIL** — a different BLAS/libm/CPU rounding path. **Do not resume.** The run
  would no longer be the same experiment. Report the mismatch; a resumed run
  under different arithmetic must be labelled a separate member, not a
  continuation.

The gate is deterministic and was verified to pass against its own reference on
the originating host.

## Expected cost

At the originating host's measured rate (~1.83 model-hours per wall-hour,
single core), hour 7.73 → 20 is roughly **6.7 core-hours**. That rate is
inflated about 5× by ML-3: five cells on the southern OPEN boundary hit 21 m/s
and throttle the global CFL timestep. This is the frozen configuration and is
deliberately not "fixed" here. A faster core will help proportionally; more
cores will not — the solver is single-threaded.

## When it finishes

`corridor_buckeye_c_B/` will contain `probes.json` (60 s road and channel series
per corridor point), `peak.npz`, `snaps.npz` and `meta.json`. Return those; the
analysis (`corridor_analysis.py`, `gauge_timing.py`) runs on them directly, and
the decisive numbers are the road-versus-channel depths at `i70_sf_licking`
during model hours 13–16.
