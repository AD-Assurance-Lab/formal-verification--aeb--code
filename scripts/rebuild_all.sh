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
# How many bound computations share the card. Peak use is NOT uniform -- measured between
# 3.3 and 8.3 GiB depending on the policy and how much branching a sub-interval needs --
# so the safe count is set by the worst case rather than the average: three at 8.3 GiB
# fit in 31.35 with room, four do not reliably.
VERIFY_CONC=${VERIFY_CONC:-3}
# Fragmentation, not total size, is what actually kills these: the allocator reported
# 833 MiB "reserved but unallocated" while failing a 954 MiB request.
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

fresh_server() {
  say "restarting CARLA on $CARLA_PORT"
  bash tools/carla_launch.sh >>"$LOG" 2>&1 || { say "FATAL: server would not start"; exit 1; }
}

stop_server() {
  # Verification needs no simulator, and CARLA holds about 10.4 GiB of the card's 31.35.
  #
  # WAIT FOR THE PROCESS, NOT THE PORT. The first version of this function polled the
  # listening socket, and CARLA closes its socket on SIGTERM without exiting: the port
  # went quiet, the function returned, and the server sat there holding 10.6 GiB for the
  # next 23 minutes. A property-S job then died on CUDA out-of-memory with the server
  # named in the allocator's own error message, twice in one evening -- the second time
  # while a function whose entire job was to prevent it reported success.
  #
  # And wait for the VRAM, not just the process table: a process can be reaped while its
  # GPU allocation is still being released.
  say "stopping CARLA: the next stage is GPU-only and the server is holding VRAM"
  pkill -f "[C]arlaUE4" 2>/dev/null || true
  for _ in $(seq 1 20); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 2; done
  if pgrep -f "[C]arlaUE4" >/dev/null; then
    say "  SIGTERM did not stop it after 40 s; SIGKILL"
    pkill -9 -f "[C]arlaUE4" 2>/dev/null || true
    for _ in $(seq 1 15); do pgrep -f "[C]arlaUE4" >/dev/null || break; sleep 2; done
  fi
  if pgrep -f "[C]arlaUE4" >/dev/null; then
    say "FATAL: CARLA will not die; refusing to start a GPU stage beside it"; exit 1
  fi
  for _ in $(seq 1 15); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    [ -z "$used" ] && break
    [ "$used" -lt 4000 ] && break
    sleep 2
  done
  say "  CARLA stopped; GPU now at ${used:-unknown} MiB"
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
# Scope for the verifyA stage. DEFAULT IS EVERYTHING, deliberately: standing rule 7 says a
# default that quietly measures less is the worst kind, because the result still looks
# finished. Narrowing is opt-in, is echoed, and is written into the stage log.
SCOPE=${2:-all}

if [ "$FROM" = "verifyA" ]; then
  case "$SCOPE" in
    all|plate|hazard) ;;
    *) echo "verifyA scope must be one of: all (default), plate, hazard" >&2; exit 2 ;;
  esac
  # Property A: must NOT brake, certified upper bound at most 0.25 g, on the no-target
  # control at every pose rather than only inside r_req. No simulator and no ordering
  # constraint -- there is no witness drive for a property about not doing something --
  # so this is the stage to run alongside the drives.
  # The four jobs run CONCURRENTLY. They share nothing -- no simulator, no output file,
  # no ordering -- and alpha-CROWN on a 310k-parameter network at batch 1 leaves most of
  # a 32 GB card idle, so running them in series turns 1 hour of GPU into 4. Each still
  # writes its own log and its own artifact; the wait collects the exit codes.
  stop_server
  say "verifyA scope: $SCOPE"
  fail=0
  queue=""
  for pol in $POLICIES; do
    [ "$SCOPE" = "plate" ] || queue="$queue ${pol}|none|lead ${pol}|none_ped|ped"
    # Cells 5 and 6: the FMVSS false-activation scenario, if it has been captured.
    # `plate` is the STANDARD'S scenario -- the steel trench plate present, approached in
    # lane at 50 mph -- and it is the one the ledger's cells 5 and 6 name. `none_plate`
    # replays the same poses with the plate REMOVED and is the control: it says whether
    # the road, the site and the illumination alone can trigger a stop, which is what
    # makes a plate verdict attributable to the plate.
    #
    # This queued only `none_plate` when the harness landed, which certifies an empty
    # road and reads as a false-activation certificate. docs/STATE_OF_PLAY.md section 1
    # already records that exact substitution one level up -- property A on `none` is not
    # the standard's scenario -- and it was made again on the way down.
    if [ "$SCOPE" != "hazard" ] && [ -f "$REPO/results/captures/states_plate.json" ]; then
      queue="$queue ${pol}|plate|lead ${pol}|none_plate|lead"
    fi
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
  #
  # TWO PASSES, answering different questions.
  #   midpoint    every sub-interval, certified ones included, at its midpoint. The
  #               control: a test that only visits flagged cells cannot tell a working
  #               certificate from one that flags everything.
  #   at-witness  the illumination the certificate actually EXHIBITED for each falsified
  #               sub-interval. Section 10 says "drive the witness", and the midpoint is
  #               not the witness: falsifying [+28.397, +18.743] while exhibiting s = +1
  #               is a claim about 18.743 deg, and driving 23.570 tests something else.
  for pol in $POLICIES; do
    for sc in lead ped; do
      fresh_server
      run "witness_${pol}_${sc}" "$PY" -u tools/drive_witness.py --policy "$pol" --scenario "$sc"
    done
  done
  for pol in $POLICIES; do
    for sc in lead ped; do
      fresh_server
      run "witness_${pol}_${sc}_atwitness" "$PY" -u tools/drive_witness.py \
          --policy "$pol" --scenario "$sc" --at-witness
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
      for sc in lead none ped none_ped plate none_plate; do
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
