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
SEED=${SEED:-0}
POLICIES="P_pts P_cont P_pts3"
# How many bound computations share the card. Measured: each peaks near 4.5 GiB, so four
# fit comfortably in 31.35 GiB with the server stopped and six do not fit with it running.
VERIFY_CONC=${VERIFY_CONC:-4}

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

fresh_server() {
  say "restarting CARLA on $CARLA_PORT"
  bash tools/carla_launch.sh >>"$LOG" 2>&1 || { say "FATAL: server would not start"; exit 1; }
}

stop_server() {
  # Verification needs no simulator, and CARLA holds about 10.4 GiB of the card's 31.35.
  # Leaving it up through a GPU-only stage cost this study two of six concurrent
  # property-S jobs to CUDA out-of-memory on 2026-09-07: six jobs at ~4.5 GiB each plus
  # CARLA does not fit, and the two that died had nothing to do with the simulator.
  say "stopping CARLA: the next stage is GPU-only and the server is holding VRAM"
  pkill -f "[C]arlaUE4" || true
  for _ in $(seq 1 30); do
    ss -ltn 2>/dev/null | grep -q ":$CARLA_PORT[[:space:]]" || break; sleep 2
  done
  sleep 3
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

if [ "$FROM" = "verifyA" ]; then
  # Property A: must NOT brake, certified upper bound at most 0.25 g, on the no-target
  # control at every pose rather than only inside r_req. No simulator and no ordering
  # constraint -- there is no witness drive for a property about not doing something --
  # so this is the stage to run alongside the drives.
  # The four jobs run CONCURRENTLY. They share nothing -- no simulator, no output file,
  # no ordering -- and alpha-CROWN on a 310k-parameter network at batch 1 leaves most of
  # a 32 GB card idle, so running them in series turns 1 hour of GPU into 4. Each still
  # writes its own log and its own artifact; the wait collects the exit codes.
  stop_server
  fail=0
  queue=""
  for pol in $POLICIES; do
    queue="$queue ${pol}|none|lead ${pol}|none_ped|ped"
  done
  set -- $queue
  while [ $# -gt 0 ]; do
    pids=""; names=""
    for _ in $(seq 1 "$VERIFY_CONC"); do
      [ $# -eq 0 ] && break
      item=$1; shift
      pol=${item%%|*}; rest=${item#*|}; sc=${rest%%|*}; ps=${rest##*|}
      say "START verify_${pol}_${sc}_A (background)"
      "$PY" -u tools/verify.py --policy "$pol" --scenario "$sc" \
          --policy-scenario "$ps" --property A \
          > "$REPO/results/verify_${pol}_${sc}_A.log" 2>&1 &
      pids="$pids $!"; names="$names verify_${pol}_${sc}_A"
    done
    set -- $names $@
    for pid in $pids; do
      wait "$pid"; rc=$?
      say "DONE  $1 rc=$rc"
      [ $rc -ne 0 ] && { fail=1; tail -20 "$REPO/results/$1.log" | tee -a "$LOG"; }
      shift
    done
  done
  say "property A complete (rc=$fail)."
  exit $fail
fi

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
      # FMVSS 127's third lighting condition: the darkness knot with UPPER beam. Same
      # illumination, different headlamp state, so it is a training condition and an
      # endpoint test rather than a point on the axis, and it is filed where the family's
      # globs cannot reach it.
      for sc in lead none ped none_ped; do
        fresh_server
        run "capture_${sc}_hb" "$PY" -u tools/capture_campaign.py --scenario "$sc" --highbeam
      done
      ;;
    pairing)
      # Verification interpolates pixel by pixel between knots, so a pose that differs
      # by one tick between two knots is not a pair. No simulator.
      run pairing "$PY" -u tools/check_pairing.py
      # And the photometric cross-check: the four campaigns render the same site at the
      # same knots and differ only by what stands in front of the camera, so a knot
      # rendered at the wrong illumination in one of them shows up as that campaign
      # disagreeing with the other three at that knot and nowhere else. It is the only
      # illumination check here that rests on no assumption about the renderer.
      run illumination "$PY" -u tools/condition_signature.py
      ;;
    train)
      # No simulator. Both policies for both hazard scenarios; the ONLY difference
      # between P_pts and P_cont is which knots their frames came from.
      # All three arms in ONE invocation per scenario, so the equalisation target is
      # shared and every arm is seeded identically.
      for sc in lead ped; do
        run "train_${sc}" "$PY" -u tools/train_policies.py --scenario "$sc" \
            --input-w $INPUT_W --input-h $INPUT_H --seed $SEED
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
      for pol in $POLICIES; do
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
      # M6, PROPERTY S ONLY. No simulator: bounds over the captured endpoint frames.
      #
      # Property A is deliberately NOT here. It is the expensive half -- 104 poses per
      # sub-interval against property S's 25, measured at ~3.7 h against ~50 min -- and
      # it has no witness drive, so nothing waits on it. Running it in this stage would
      # put four hours of work in front of the commit that lets the drives start, for no
      # reason. `bash scripts/rebuild_all.sh verifyA` runs it, and it can run at the same
      # time as `witness`: one wants the GPU, the other wants the simulator.
      # Concurrent, but in BATCHES of $VERIFY_CONC and with the simulator stopped first.
      # alpha-CROWN at batch 1 on a 310k-parameter network is latency-bound rather than
      # throughput-bound, so several jobs share the card well -- until they do not fit.
      # Six at once alongside CARLA is what OOM'd on 2026-09-07.
      stop_server
      vfail=0
      queue=""
      for pol in $POLICIES; do
        for sc in lead ped; do queue="$queue ${pol}|${sc}"; done
      done
      set -- $queue
      while [ $# -gt 0 ]; do
        pids=""; names=""
        for _ in $(seq 1 "$VERIFY_CONC"); do
          [ $# -eq 0 ] && break
          item=$1; shift
          pol=${item%%|*}; sc=${item##*|}
          say "START verify_${pol}_${sc}_S (background)"
          "$PY" -u tools/verify.py --policy "$pol" --scenario "$sc" \
              --policy-scenario "$sc" --property S \
              > "$REPO/results/verify_${pol}_${sc}_S.log" 2>&1 &
          pids="$pids $!"; names="$names verify_${pol}_${sc}_S"
        done
        set -- $names $@
        for pid in $pids; do
          wait "$pid"; rc=$?
          say "DONE  $1 rc=$rc"
          [ $rc -ne 0 ] && { vfail=1; tail -20 "$REPO/results/$1.log" | tee -a "$LOG"; }
          shift
        done
      done
      [ $vfail -ne 0 ] && { say "stopping: a property S job failed"; exit 1; }
      say ""
      say "M6 property S done. COMMIT THE VERDICTS BEFORE DRIVING:"
      say "    python tools/record_cells.py --write"
      say "    git add results/carla/verify_*.json study/results.json && git commit"
      say "    bash scripts/rebuild_all.sh witness      # simulator"
      say "    bash scripts/rebuild_all.sh verifyA      # GPU, concurrently"
      say "A verdict is a prediction only if it was written down first;"
      say "tools/drive_witness.py refuses to run against an uncommitted one."
      ;;
  esac
done
