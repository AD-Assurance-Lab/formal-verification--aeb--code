#!/usr/bin/env bash
# One repetition, one process, one freshly restarted server -- the harness D-6 asks for
# and the one the repetition floor is conditional on.
#
#   bash scripts/probe_split_cells.sh
#
# WHAT IT MEASURES. Of the 281 committed ten-repetition cells in this repository, 277 are
# unanimous and 4 are split, and none of the four looks like sampling (see
# tools/repetition_floor.py). This drives all four again under a per-repetition restart,
# plus two controls that were unanimous on the shared server -- one 10/10 and one 0/10 --
# because "the split disappeared" and "the probe cannot see a split" look identical
# without them.
#
# Every repetition gets: a stopped server, a fresh launch through tools/carla_launch.sh
# (which runs the determinism preflight and refuses an occupied port), a new process, a
# new client, a new vehicle and a new camera. Nothing is shared between repetitions
# except the committed network and the committed verdict.
#
# Long. Roughly 90 s of restart per repetition on top of the drive, so about an hour and
# a half for the default cell list. Detached, per this repo's operating notes:
#   setsid nohup bash scripts/probe_split_cells.sh > results/probe_split.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
LOG=$REPO/results/probe_split_cells.log

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

stop_server() {
  # The launcher's own takeover path waits 60 s on a SIGTERM that CARLA does not honour
  # before it reaches for SIGKILL, and it reaches for SIGKILL every single time. That is
  # correct there -- it is stopping a server it does not own and may be someone's mid-run
  # -- but here the server is one this script started for one repetition and is throwing
  # away, so the polite wait is 60 s of nothing, 46 times over. Stop it properly and
  # leave the port clear, then let the launcher find nothing to take over.
  pkill -f "[C]arlaUE4" 2>/dev/null || true
  for _ in $(seq 1 6); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 1; done
  if pgrep -f "[C]arlaUE4" >/dev/null; then
    pkill -9 -f "[C]arlaUE4" 2>/dev/null || true
  fi
  # Wait for the SOCKET, not the process table: CARLA closes its socket on SIGTERM
  # without exiting, and the reverse also bites -- a reaped process whose port is still
  # bound makes the next launch fail its bind and answer from a server it did not
  # configure. rebuild_all.sh's stop_server carries the same warning.
  for _ in $(seq 1 30); do
    ss -ltn 2>/dev/null | grep -q ":$CARLA_PORT[[:space:]]" || break
    sleep 1
  done
  # And for the VRAM: a process can be reaped while its allocation is still being freed,
  # and the next repetition loads a network onto the same card.
  for _ in $(seq 1 15); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    [ -z "$used" ] && break
    [ "$used" -lt 4000 ] && break
    sleep 1
  done
}

fresh_server() {
  stop_server
  bash tools/carla_launch.sh >>"$REPO/results/carla_launch.log" 2>&1 \
    || { say "FATAL: server would not start"; exit 1; }
}

# policy  scenario  from_deg  to_deg  at_witness  reps  why
CELLS=(
  "P_cont   plate  0.026   0.0    0  10  split 6/10 on the shared server; runs 0-3 braked over the limit and 4-9 did not, which is a step in run INDEX. F19 rests on this cell."
  "P_pts3   ped    0.779   0.026  0  10  split 2/10; bimodal -- two runs brake at 377 ft and pass, eight never brake and hit the pedestrian."
  "P_pts    lead   0.779   0.026  0  10  split 9/10; the one repetition that failed is F21's scoring defect, fixed in run_policy.py. Should now be unanimous."
  "P_pts    lead   0.026   0.0    1  10  split 8/10; two repetitions, same F21 defect."
  "P_cont   lead   60.0    42.766 0  3   CONTROL, unanimous 10/10 on the shared server."
  "P_pts3   lead   10.128  7.715  0  3   CONTROL, unanimous 0/10 on the shared server."
)

total=0
for spec in "${CELLS[@]}"; do
  read -r _p _s _f _t _w reps _rest <<<"$spec"
  total=$((total + reps))
done
say "probing ${#CELLS[@]} sub-intervals, $total repetitions, one server restart each"

done_n=0
for spec in "${CELLS[@]}"; do
  read -r pol scen from to atw reps why <<<"$spec"
  wflag=""; [ "$atw" = "1" ] && wflag="--at-witness"
  say "CELL $pol/$scen [$from, $to] ${wflag:-midpoint}  ($reps reps)"
  say "  why: $why"
  for rep in $(seq 1 "$reps"); do
    done_n=$((done_n + 1))
    say "  restart before rep $rep  [$done_n/$total]"
    fresh_server
    name="probe_${pol}_${scen}${wflag:+_atwitness}_${from}_${to}_rep${rep}"
    "$PY" tools/repetition_probe.py --policy "$pol" --scenario "$scen" \
        --from-deg "$from" --to-deg "$to" --rep "$rep" $wflag \
        >"$REPO/results/${name}.log" 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
      say "  rep $rep FAILED rc=$rc. Tail of results/${name}.log:"
      tail -20 "$REPO/results/${name}.log" | tee -a "$LOG"
      say "  STOPPING. A probe that skips a repetition and carries on is measuring a "
      say "  different experiment from the one it reports."
      exit 1
    fi
    tail -1 "$REPO/results/${name}.log" | tee -a "$LOG"
  done
done

say "all repetitions done; aggregating"
"$PY" tools/repetition_probe.py --report 2>&1 | tee -a "$LOG"
say "ALL DONE"
