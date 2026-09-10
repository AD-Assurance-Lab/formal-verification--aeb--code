#!/usr/bin/env bash
# D-8, run properly: N repetitions, a FRESH SERVER before each, then one comparison.
#
# The restart is not optional and it is not cosmetic. D-6 says a long-lived server keeps
# answering while it stops advancing physics correctly, and D-3 records that a cold server
# produces a first-run outlier that disagrees with every later run. A probe that ran three
# repetitions against one server would measure the server's age as much as its determinism.
#
# Each repetition writes its OWN artifact and the comparison refuses to run if one is
# missing (D-9), so a crashed repetition cannot leave the previous file in place and be
# compared against itself. That defect produced a false "runs are reproducible" result in
# the steering study.
#
# Usage:  bash scripts/determinism_probe.sh [reps] [policy] [scenario] [sun_altitude]
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH
# The results directory is map-scoped. Read the name from the module, never retyped.
CARLA_MAP_NAME=$("$PY" -c "import sys;sys.path.insert(0,'tools');import paths;print(paths.MAP)")

REPS=${1:-3}
POLICY=${2:-P_cont}
SCENARIO=${3:-lead}
SUN=${4:--30.0}
LOG=$REPO/results/determinism_probe.log
: > "$LOG"

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# Stale artifacts from an earlier probe would be silently reused by --compare if a
# repetition failed to write. Clear them first so "missing" means missing.
rm -f "$REPO"/results/carla/"$CARLA_MAP_NAME"/determinism_rep*.json

for i in $(seq 1 "$REPS"); do
  say "restarting CARLA for rep $i"
  bash tools/carla_launch.sh >>"$LOG" 2>&1 || { say "FATAL: server would not start"; exit 1; }
  say "START rep $i"
  "$PY" -u tools/determinism_probe.py --rep "$i" --policy "$POLICY" \
      --scenario "$SCENARIO" --sun-altitude "$SUN" >>"$LOG" 2>&1
  rc=$?
  say "DONE  rep $i rc=$rc"
  [ $rc -ne 0 ] && { say "stopping: rep $i failed"; tail -20 "$LOG"; exit 1; }
done

"$PY" -u tools/determinism_probe.py --compare --reps "$REPS" 2>&1 | tee -a "$LOG"
