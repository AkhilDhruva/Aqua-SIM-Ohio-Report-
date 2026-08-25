#!/bin/bash
# Resume the Buckeye PRIMARY run from the frozen checkpoint.
#
# Run the equivalence gate FIRST. If it fails, stop and report — do not resume.
set -e
cd "$(dirname "$0")"

echo "== cross-host equivalence gate =="
python3 crosshost_equivalence.py || {
  echo
  echo "GATE FAILED — this host does not reproduce the reference arithmetic."
  echo "Do NOT resume the scientific run here. Report the mismatch."
  exit 1
}

echo
echo "== resuming primary run (target model hour 20) =="
mkdir -p ../corridor_buckeye_c_B
cp -n frozen/state.npz frozen/setup_cache.npz frozen/probes.json ../corridor_buckeye_c_B/ 2>/dev/null || true
cd ..
exec python3 code/run_corridor.py buckeye_c B --hours 20 \
     --parent run_qpeB_parent_ext --bcfile boundary_stages_buckeye_c.json
