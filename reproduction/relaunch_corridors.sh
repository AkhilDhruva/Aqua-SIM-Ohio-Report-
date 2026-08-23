#!/bin/bash
# Restart-safe launcher: each run resumes from its own checkpoint, so this is
# idempotent and can be re-run after any container recycle.
cd /tmp/claude-0/-home-user-aqua-sim/3501f8ed-2621-5156-b327-4da2a46d8730/scratchpad/columbus_side_task
launch () {  # $1 nest  $2 parent  $3 bcfile  $4 extra
  if ! pgrep -f "run_corridor.py $1 " >/dev/null; then
    nohup python3 run_corridor.py "$1" B --hours 20 --parent "$2" --bcfile "$3" $4 \
      >> "corr_$1.log" 2>&1 &
    echo "launched $1"
  else
    echo "$1 already running"
  fi
}
launch buckeye_c     run_qpeB_parent_ext boundary_stages_buckeye_c.json
sleep 2
launch franklinton_c run_qpeB_parent     boundary_stages_franklinton_c.json
sleep 2
launch pataskala_c   run_qpeB_parent     boundary_stages_pataskala_c.json
