#!/usr/bin/env bash
# The A12 rebuild, in dependency order, as one committed driver.
#
# WHY THIS IS A SCRIPT. Standing rule: a number that goes in a paper comes from an
# invocation that is committed to the repository, never from a command typed once. The
# sibling steering study survived one map and failed the other on exactly this -- Town06
# had a capture script, Town04 was driven by hand and inherited a default that covered
# 5.6% of the lap, and the certificate, the agreement rate and the write-up all read as
# complete.
#
# WHAT IT DOES NOT DO. It stops before M7. The witness drives may only run after the
# verification verdicts are COMMITTED to git (PROTOCOL section 8), and a script that
# committed on your behalf would turn the blind protocol into a formality. Stage `verify`
# ends by telling you what to commit; `bash scripts/rebuild_all.sh witness` runs the
# drives afterwards, and tools/drive_witness.py refuses if the verdicts are uncommitted.
#
# Usage:
#   bash scripts/rebuild_all.sh              # from the beginning, up to and incl. verify
#   bash scripts/rebuild_all.sh capture      # start at a stage
#   bash scripts/rebuild_all.sh witness      # M7, after the verdicts are committed
#   CARLA_PORT=3000 bash scripts/rebuild_all.sh
#
# Every simulator stage gets a FRESH SERVER. Not one server for a group of stages: the
# steering repo's own teacher gate was doing three restarts for twelve laps until
# 2026-09-01, and a server that has been up for hours keeps answering while it stops
# advancing physics correctly (R-SIM-1). The restart is the cheapest thing here.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export CARLA_PORT=${CARLA_PORT:-3000}
export CARLA_TAKEOVER=1        # this script owns the port for the duration
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH               # ROS leaks in through it; see scripts/bootstrap_env.sh
LOG=$REPO/results/rebuild.log

INPUT_W=128
INPUT_H=96

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

fresh_server() {
  say "restarting CARLA on $CARLA_PORT"
  bash tools/carla_launch.sh >>"$LOG" 2>&1 || { say "FATAL: server would not start"; exit 1; }
}

run() {   # run <name> <cmd...>
  local name=$1; shift
  say "START $name"
  "$@" >"$REPO/results/${name}.log" 2>&1
  local rc=$?
  say "DONE  $name rc=$rc"
  if [ $rc -ne 0 ]; then
    say "stopping: $name failed. Tail of results/${name}.log:"
    tail -25 "$REPO/results/${name}.log" | tee -a "$LOG"
    exit 1
  fi
}

STAGES=(jobs knots capture pairing train endpoints gates verify)
FROM=${1:-jobs}

if [ "$FROM" = "witness" ]; then
  # M7. Refuses to run until the verdicts are committed; that refusal is the protocol.
  for pol in P_pts P_cont; do
    for sc in lead ped; do
      fresh_server
      run "witness_${pol}_${sc}" "$PY" -u tools/drive_witness.py --policy "$pol" --scenario "$sc"
    done
  done
  say "M7 complete. python -m study.ledger --check-order"
  exit 0
fi

start=0
for i in "${!STAGES[@]}"; do [ "${STAGES[$i]}" = "$FROM" ] && start=$i; done

for i in $(seq $start $((${#STAGES[@]} - 1))); do
  case "${STAGES[$i]}" in
    jobs)
      # M2 and M3: primitives, contact detector, both oracles, both image-space gates,
      # and the expert at both regulatory endpoints. Stops at the first failing job.
      fresh_server
      run jobs "$PY" -u tools/carla_jobs.py --all
      ;;
    knots)
      # A6: where the illumination axis has to be cut. Must precede capture -- these
      # knots ARE the frames that get rendered.
      fresh_server
      run knots "$PY" -u tools/build_family_knots.py
      ;;
    capture)
      # Order matters and is not cosmetic: the no-target controls REPLAY the poses of
      # the scenario they control (A10), so `none` needs `lead` on disk and `none_ped`
      # needs `ped`. capture_campaign refuses if you get it wrong.
      for sc in lead none ped none_ped; do
        fresh_server
        run "capture_${sc}" "$PY" -u tools/capture_campaign.py --scenario "$sc"
      done
      ;;
    pairing)
      # Verification interpolates pixel by pixel between knots, so a pose that differs
      # by one tick between two knots is not a pair. No simulator.
      run pairing "$PY" -u tools/check_pairing.py
      ;;
    train)
      # No simulator. Both policies for both hazard scenarios; the ONLY difference
      # between P_pts and P_cont is which knots their frames came from.
      for sc in lead ped; do
        run "train_${sc}" "$PY" -u tools/train_policies.py --scenario "$sc" \
            --input-w $INPUT_W --input-h $INPUT_H
      done
      ;;
    endpoints)
      # M4. If P_pts cannot pass the regulatory endpoints there is no study, because
      # the claim is that a policy which SATISFIES the standard is unsafe between its
      # test points. The script stops here in that case, deliberately.
      for sc in lead ped; do
        fresh_server
        run "endpoints_${sc}" "$PY" -u tools/run_policy.py --all --scenario "$sc"
      done
      ;;
    gates)
      # M5. The capture check and the in-between check, BEHAVIOURALLY -- in the
      # policy's own output space, which is the one PROTOCOL section 4 says decides.
      # BOTH gates. gate_behavioural.py defaults to --gate inbetween, so running it
      # without the flag measures one of the two M5 exit criteria and leaves the other
      # unmeasured while the stage reports success.
      for pol in P_pts P_cont; do
        for sc in lead ped; do
          for g in capture inbetween; do
            fresh_server
            run "gate_${g}_${pol}_${sc}" "$PY" -u tools/gate_behavioural.py \
                --policy "$pol" --scenario "$sc" --gate "$g"
          done
        done
      done
      ;;
    verify)
      # M6. No simulator: bounds over the captured endpoint frames. Property S is the
      # one with a witness drive; property A has none, so it can run whenever.
      for pol in P_pts P_cont; do
        for sc in lead ped; do
          run "verify_${pol}_${sc}_S" "$PY" -u tools/verify.py --policy "$pol" \
              --scenario "$sc" --policy-scenario "$sc" --property S
        done
      done
      for pol in P_pts P_cont; do
        run "verify_${pol}_none_A" "$PY" -u tools/verify.py --policy "$pol" \
            --scenario none --policy-scenario lead --property A
        run "verify_${pol}_none_ped_A" "$PY" -u tools/verify.py --policy "$pol" \
            --scenario none_ped --policy-scenario ped --property A
      done
      say ""
      say "M6 done. COMMIT THE VERDICTS BEFORE DRIVING:"
      say "    git add results/carla/verify_*.json && git commit"
      say "    bash scripts/rebuild_all.sh witness"
      say "A verdict is a prediction only if it was written down first;"
      say "tools/drive_witness.py refuses to run against an uncommitted one."
      ;;
  esac
done
