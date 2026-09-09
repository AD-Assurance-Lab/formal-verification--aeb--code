#!/usr/bin/env bash
# Re-run amendment A3's own instrument on the current hardware.
#
#   setsid nohup bash scripts/map_probe_2026-09-09.sh > results/map_probe.log 2>&1 &
#
# A3 moved this study from Town13 to Town01 on a measurement, and the measurement was
# explicitly about the machine: "The hardware is an RTX 4070 with 12 GB, and the 5090 is
# not here yet." It is here now, with 32 GB. So the premise is re-measured rather than
# assumed away, with the same probe, the same cycle length, and Town01 as the control.
#
# Two renderings, because A3 measured with rendering OFF and this study cannot: every
# capture and every drive needs frames. The no-rendering pass is the like-for-like
# comparison against A3's table; the rendering pass is the number that decides anything.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH
LOG=$REPO/results/map_probe.log
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

stop_server() {
  pkill -f "[C]arlaUE4" 2>/dev/null || true
  for _ in $(seq 1 6); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 1; done
  pgrep -f "[C]arlaUE4" >/dev/null && pkill -9 -f "[C]arlaUE4" 2>/dev/null
  for _ in $(seq 1 30); do
    ss -ltn 2>/dev/null | grep -q ":$CARLA_PORT[[:space:]]" || break; sleep 1
  done
  for _ in $(seq 1 15); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    [ -z "$used" ] && break; [ "$used" -lt 4000 ] && break; sleep 1
  done
}

# A fresh server for every map AND every rendering mode: a map load into a server that has
# already held another map is not the loaded footprint of that map.
for MODE in --no-rendering ""; do
  for MAP in Town01 Town12 Town13; do
    say "=== $MAP  rendering=$([ -n "$MODE" ] && echo off || echo on) ==="
    stop_server
    bash tools/carla_launch.sh >>"$REPO/results/carla_launch.log" 2>&1 \
      || { say "$MAP: server would not start"; continue; }
    timeout 900 "$PY" tools/probe_memory.py --map "$MAP" --cycles 6 --ticks 140 $MODE \
      2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    [ "$rc" -ne 0 ] && say "$MAP rendering=$([ -n "$MODE" ] && echo off || echo on): rc=$rc (124 = timed out at 900 s)"
  done
done
stop_server
say "ALL DONE"
