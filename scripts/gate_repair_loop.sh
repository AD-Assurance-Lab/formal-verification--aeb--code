#!/usr/bin/env bash
# PROTOCOL section 4's repair, run to convergence or to a hard stop.
#
#   setsid nohup bash scripts/gate_repair_loop.sh > results/gate_repair_stdout.log 2>&1 &
#
# The behavioural in-between gate decides whether a sub-interval's chord represents the
# rendered interior well enough for a certificate over it to mean anything. When one fails,
# section 4's repair is shorter intervals with rendered interior endpoints: split, capture
# the new knots, and measure again.
#
# Three things about the loop, none of them cosmetic.
#
# ALL THE GATES RUN BEFORE ANY SPLIT. `failing_sub_intervals()` reads every gate artifact,
# because a sub-interval that fails for one arm must be split for all of them or the arms
# end up certified over different axes and stop being comparable. Splitting on a partial
# set would need a second recapture to undo. So the gates run as a batch that TOLERATES
# failure, and the split happens once per round with the whole picture.
#
# IT IS BOUNDED. Each round subdivides the axis further, and an axis that needs a fourth
# round is not converging -- it is telling you the chord does not represent the interior
# at that illumination at all, which is a result about the disturbance family and not
# something to grind away at overnight. MAX_ROUNDS stops and says so.
#
# IT STOPS IF THE FAILING SET DOES NOT SHRINK. Splitting an interval that fails at 3.2x
# can leave both halves failing. If the count does not fall, another round will not help.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH
MAX_ROUNDS=${MAX_ROUNDS:-3}
LOG=$REPO/results/gate_repair.log
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

stop_server() {
  pkill -f "[C]arlaUE4" 2>/dev/null || true
  for _ in $(seq 1 6); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 1; done
  pgrep -f "[C]arlaUE4" >/dev/null && pkill -9 -f "[C]arlaUE4" 2>/dev/null
  for _ in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$CARLA_PORT[[:space:]]" || break; sleep 1; done
}
fresh() { stop_server; bash tools/carla_launch.sh >>"$REPO/results/carla_launch.log" 2>&1; }

count_failing() {
  "$PY" - <<'PY'
import json, pathlib
bad = set()
for p in pathlib.Path('results/carla').glob('gate_inbetween_*.json'):
    d = json.loads(p.read_text())
    for c in d['sub_intervals']:
        if c['as_fraction_of_threshold'] > 1.0 and not c.get('family_uncovered'):
            bad.add((round(c['from_deg'], 3), round(c['to_deg'], 3)))
print(len(bad))
PY
}

run_all_gates() {
  for pol in P_pts P_cont P_pts3; do
    for sc in lead ped; do
      for g in capture inbetween; do
        n="gate_${g}_${pol}_${sc}"
        fresh || { say "$n: no server"; continue; }
        "$PY" -u tools/gate_behavioural.py --policy "$pol" --scenario "$sc" --gate "$g" \
          >"$REPO/results/${n}.log" 2>&1
        say "  $n rc=$?"
      done
    done
  done
}

prev=999
for round in $(seq 1 "$MAX_ROUNDS"); do
  say "=== round $round: all twelve gates ==="
  run_all_gates
  n=$(count_failing)
  say "round $round: $n covered sub-interval(s) fail the behavioural gate"
  if [ "$n" -eq 0 ]; then
    say "GATES PASS. M5 is met; the next stage is verification."
    stop_server; exit 0
  fi
  if [ "$n" -ge "$prev" ]; then
    say "STOPPING: the failing count did not fall ($prev -> $n). Splitting further will"
    say "not help. The chord does not represent the rendered interior at these"
    say "illuminations, which is a result about the disturbance family and needs a"
    say "decision, not another round."
    stop_server; exit 2
  fi
  prev=$n
  if [ "$round" -eq "$MAX_ROUNDS" ]; then
    say "STOPPING: $MAX_ROUNDS rounds reached with $n still failing."
    stop_server; exit 2
  fi
  say "=== round $round: splitting, then capturing only the new knots ==="
  fresh
  "$PY" -u tools/build_family_knots.py --refine 2>&1 | tee -a "$LOG"
  [ "${PIPESTATUS[0]}" -ne 0 ] && { say "refine failed"; stop_server; exit 1; }
  # CAPTURE ONLY. The first version called `rebuild_all.sh capture`, which starts AT
  # capture and runs every stage AFTER it -- so each round also retrained the policies and
  # re-ran the endpoints. That is not merely wasteful. FINDINGS F29 measured that training
  # is not reproducible, so every round measured its gates on DIFFERENT networks: round 1
  # ran against models trained at 04:35 and round 2 against models trained at 07:39. The
  # loop was converging against a moving target, and its stopping rule -- does the failing
  # count fall -- cannot mean anything when the thing being measured changes underneath it.
  #
  # DO NOT RUN THIS LOOP AT ALL until F29 is resolved. Splitting an axis on gates measured
  # against non-reproducible networks is measuring the optimiser, not the family.
  for sc in lead none ped none_ped plate none_plate; do
    fresh
    "$PY" -u tools/capture_campaign.py --scenario "$sc" >"$REPO/results/capture_${sc}.log" 2>&1
    [ $? -ne 0 ] && { say "capture $sc failed"; tail -5 "$REPO/results/capture_${sc}.log" | tee -a "$LOG"; stop_server; exit 1; }
    say "  recaptured $sc"
  done
done
