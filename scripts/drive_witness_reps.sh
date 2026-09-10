#!/usr/bin/env bash
# M7 under the harness amendment A13 requires: one repetition per process, one freshly
# restarted server per repetition, merged afterwards.
#
#   bash scripts/drive_witness_reps.sh P_cont lead
#   bash scripts/drive_witness_reps.sh P_pts lead --at-witness
#   REPS=5 bash scripts/drive_witness_reps.sh P_pts3 ped
#
# The repetition is the unit and it is a REPRODUCIBILITY CHECK, not a sample. Each
# repetition drives every sub-interval once; the server is stopped and relaunched between
# repetitions, so no two repetitions of a sub-interval share a simulator, a process, a
# client or a vehicle. That is what makes three enough (FINDINGS F22), and it is exactly
# what ten repetitions inside one loop were not.
#
# Restarting between repetitions rather than between individual runs is deliberate and it
# is the AEB analogue of the steering study's lap: a repetition is one traversal of every
# scored sub-interval, and what has to be independent is one traversal from the next.
# Restarting between the sub-intervals inside a repetition would cost seventeen times as
# much to control a difference the measurement does not depend on -- each sub-interval is
# its own condition and its own verdict, so they are not repetitions of each other.
#
# If the repetitions disagree about a sub-interval, the merge marks that cell VOID and
# exits non-zero. That is a bug until proven otherwise. It is not a reason to run more.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
POLICY=${1:?usage: drive_witness_reps.sh <policy> <scenario> [--at-witness]}
SCENARIO=${2:?usage: drive_witness_reps.sh <policy> <scenario> [--at-witness]}
shift 2 || true
EXTRA=("$@")          # --at-witness, or --interior K, passed to the driver AND the merge
ATW=""
case " ${EXTRA[*]} " in *" --at-witness "*) ATW="--at-witness" ;; esac
INTERIOR=""
for i in "${!EXTRA[@]}"; do
  [ "${EXTRA[$i]}" = "--interior" ] && INTERIOR="_interior${EXTRA[$((i+1))]}"
done
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
REPS=${REPS:-$("$PY" -c "import sys;sys.path.insert(0,'tools');import carla_jobs as J;print(J.REPS_RESTARTED)")}
LOG=$REPO/results/witness_reps_${POLICY}_${SCENARIO}${ATW:+_atwitness}${INTERIOR}.log
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

stop_server() {
  pkill -f "[C]arlaUE4" 2>/dev/null || true
  for _ in $(seq 1 6); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 1; done
  pgrep -f "[C]arlaUE4" >/dev/null && pkill -9 -f "[C]arlaUE4" 2>/dev/null
  # Wait for the SOCKET, not the process table. CARLA closes its socket on SIGTERM
  # without exiting, and a reaped process whose port is still bound makes the next launch
  # fail its bind while every later job answers from a server nobody configured.
  for _ in $(seq 1 30); do
    ss -ltn 2>/dev/null | grep -q ":$CARLA_PORT[[:space:]]" || break; sleep 1
  done
  for _ in $(seq 1 15); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    [ -z "$used" ] && break; [ "$used" -lt 4000 ] && break; sleep 1
  done
}

say "M7 for $POLICY/$SCENARIO ${EXTRA[*]:-midpoint}: $REPS repetitions, one server each"
for rep in $(seq 1 "$REPS"); do
  say "restart before repetition $rep of $REPS"
  stop_server
  bash tools/carla_launch.sh >>"$REPO/results/carla_launch.log" 2>&1 \
    || { say "FATAL: server would not start"; exit 1; }
  name="witness_${POLICY}_${SCENARIO}${ATW:+_atwitness}${INTERIOR}_rep${rep}"
  "$PY" tools/drive_witness.py --policy "$POLICY" --scenario "$SCENARIO" \
      --reps 1 --rep-index "$rep" "${EXTRA[@]}" >"$REPO/results/${name}.log" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then
    say "repetition $rep FAILED rc=$rc. Tail of results/${name}.log:"
    tail -25 "$REPO/results/${name}.log" | tee -a "$LOG"
    say "STOPPING. A merge over a missing repetition is a smaller experiment reported"
    say "as the one that was asked for."
    exit 1
  fi
  say "repetition $rep done"
done

say "merging"
"$PY" tools/merge_witness_reps.py --policy "$POLICY" --scenario "$SCENARIO" \
    "${EXTRA[@]}" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
say "merge rc=$rc$([ "$rc" -ne 0 ] && echo '  -- see above; VOID cells or a merge failure')"
exit "$rc"
