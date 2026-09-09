#!/usr/bin/env bash
# The lighting settle curve, one altitude per process on a freshly restarted server.
#
#   setsid nohup bash scripts/lighting_settle_sweep.sh > results/lighting_settle.log 2>&1 &
#
# Two altitudes in one process would have the second starting from wherever the first
# left off, which is exactly the confound being measured. Hence the restarts.
#
# The three altitudes are chosen, not swept: the two horizon sub-interval midpoints whose
# ten repetitions split (+0.403 and +0.013) and one daylight midpoint whose repetitions
# were unanimous (+51.383), so the curve has a control that is expected to be flat.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH
LOG=$REPO/results/lighting_settle.log
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

for ALT in 0.403 0.013 51.383; do
  say "restarting CARLA, then sweeping altitude $ALT"
  pkill -f "[C]arlaUE4" 2>/dev/null || true
  for _ in $(seq 1 6); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 1; done
  pgrep -f "[C]arlaUE4" >/dev/null && pkill -9 -f "[C]arlaUE4" 2>/dev/null
  for _ in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$CARLA_PORT[[:space:]]" || break; sleep 1; done
  bash tools/carla_launch.sh >>"$REPO/results/carla_launch.log" 2>&1 \
    || { say "FATAL: server would not start"; exit 1; }
  "$PY" tools/lighting_settle.py --altitude "$ALT" --ticks 3000 --every 20 \
      2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && { say "FATAL: sweep at $ALT failed rc=$rc"; exit 1; }
done
say "ALL DONE"
