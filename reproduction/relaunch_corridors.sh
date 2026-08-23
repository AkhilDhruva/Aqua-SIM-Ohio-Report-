#!/bin/bash
# Restart-safe launcher — PARALLEL, priority-ordered.
#
# The solver is single-threaded NumPy (measured: ~100% of one core), so N runs
# occupy N cores. Sequential execution was adopted earlier on a MISDIAGNOSIS:
# runs were not converging because of the EF-4 checkpoint livelock, not because
# of core contention. With 60 s checkpointing progress is monotonic, so the idle
# cores are now used.
#
# One core is deliberately left free for the OS and analysis tooling.
# Priority order still governs which run starts first after a recycle:
#   1. buckeye_c     — I-70 Case A/B confirmation (headline question)
#   2. franklinton_c — urban pluvial + Scioto
#   3. pataskala_c   — flash-pluvial + gauged reach
cd /tmp/claude-0/-home-user-aqua-sim/3501f8ed-2621-5156-b327-4da2a46d8730/scratchpad/columbus_side_task

MAX_CONCURRENT=$(( $(nproc) - 1 ))

active_list () { ps -eo comm,args --no-headers | awk '$1=="python3" && /run_corridor\.py/{print $3}'; }
n_active () { active_list | wc -l; }

done_p () {
  python3 - "$1" <<'PY'
import json,os,sys
n=sys.argv[1]; d=f"corridor_{n}_B"
m,p=os.path.join(d,"meta.json"),os.path.join(d,"probes.json")
ok=False
if os.path.exists(m) and os.path.exists(p):
    tgt=float(json.load(open(m)).get("hours",0) or 0)
    cov=float(json.load(open(p))["t_s"][-1])/3600.0
    ok = tgt>0 and cov>=tgt-0.05
raise SystemExit(0 if ok else 1)
PY
}

running_p () { active_list | grep -qx "$1"; }

maybe_start () {  # $1 nest  $2 parent  $3 bcfile
  if done_p "$1";    then echo "$1 COMPLETE"; return; fi
  if running_p "$1"; then echo "$1 already running"; return; fi
  if [ "$(n_active)" -ge "$MAX_CONCURRENT" ]; then
    echo "$1 queued (at $MAX_CONCURRENT concurrent)"; return
  fi
  nohup python3 run_corridor.py "$1" B --hours 20 --parent "$2" --bcfile "$3" \
    >> "corr_$1.log" 2>&1 &
  echo "started $1 (pid $!)"
  sleep 3
}

maybe_start buckeye_c     run_qpeB_parent_ext boundary_stages_buckeye_c.json
maybe_start franklinton_c run_qpeB_parent     boundary_stages_franklinton_c.json
maybe_start pataskala_c   run_qpeB_parent     boundary_stages_pataskala_c.json
echo "active: $(n_active)/$MAX_CONCURRENT cores in use"
