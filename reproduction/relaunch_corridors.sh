#!/bin/bash
# Restart-safe launcher, SEQUENTIAL PRIORITY.
#
# The host recycles every few hours and three concurrent solves share four
# cores, so nothing finished. Runs are now executed one at a time in order of
# scientific priority, each resuming from its own checkpoint:
#   1. buckeye_c     — the I-70 Case A/B confirmation (headline question)
#   2. franklinton_c — urban pluvial + Scioto interaction
#   3. pataskala_c   — flash-pluvial + gauged reach
# Idempotent: re-run after any recycle.
cd /tmp/claude-0/-home-user-aqua-sim/3501f8ed-2621-5156-b327-4da2a46d8730/scratchpad/columbus_side_task

# Match ONLY real python processes: a bash wrapper whose command line merely
# contains this script's text is not a running solve.
active () { ps -eo comm,args --no-headers | awk '$1=="python3" && /run_corridor\.py/' ; }
if [ -n "$(active)" ]; then
  echo "a corridor run is already active:"; active | sed 's/^/  /'; exit 0
fi

done_p () {  # $1 nest -> 0 if that nest already reached its target
  python3 - "$1" <<'PY'
import json,os,sys
n=sys.argv[1]; d=f"corridor_{n}_B"; m=os.path.join(d,"meta.json"); p=os.path.join(d,"probes.json")
ok=False
if os.path.exists(m) and os.path.exists(p):
    tgt=float(json.load(open(m)).get("hours",0) or 0)
    cov=float(json.load(open(p))["t_s"][-1])/3600.0
    ok = tgt>0 and cov>=tgt-0.05
raise SystemExit(0 if ok else 1)
PY
}

start () {  # $1 nest  $2 parent  $3 bcfile
  nohup python3 run_corridor.py "$1" B --hours 20 --parent "$2" --bcfile "$3" \
    >> "corr_$1.log" 2>&1 &
  echo "started $1 (pid $!)"
}

if   ! done_p buckeye_c;     then start buckeye_c     run_qpeB_parent_ext boundary_stages_buckeye_c.json
elif ! done_p franklinton_c; then start franklinton_c run_qpeB_parent     boundary_stages_franklinton_c.json
elif ! done_p pataskala_c;   then start pataskala_c   run_qpeB_parent     boundary_stages_pataskala_c.json
else echo "all three corridor runs COMPLETE"; fi
