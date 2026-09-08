#!/usr/bin/env bash
# Queue item 4: is the dusk gap the axis sampling, or one draw's luck?
#
# THE PROBLEM THIS EXISTS FOR. The study's central claim is an ATTRIBUTION -- "the gap is
# attributable to how the illumination axis was sampled" -- and it rests on one seed per
# arm. The sibling steering study measured that training dispersion in this lab is
# intrinsic: not initialisation, not data order (Levene p = 0.99 between them), not
# training-pool size, and not beaten by ensembling, with an 8-model ensemble still 31%
# worse than simply drawing the best seed. Its conclusion was to plan for n = 20 to 60 to
# see a 20% effect on a driving endpoint. An attribution at n = 1 is not measured.
#
# WHAT MAKES THIS A CONTROLLED COMPARISON. Every arm at a given seed is seeded IDENTICALLY
# before its own fit, so P_pts and P_cont at seed k share weight initialisation and
# shuffling order and differ only in which frames they saw. Before 2026-09-07 the RNG was
# seeded once and the arms trained in sequence, so they were neither independent draws nor
# matched ones -- the worst of both.
#
# NO SIMULATOR. Training and property S both run on captured frames, so this is pure GPU
# and can run while CARLA is doing something else. That is the whole reason the sweep is
# affordable at all: 20 seeds x 3 arms x 2 scenarios of DRIVING would be out of reach,
# whereas verifying them is not.
#
# Usage:  bash scripts/seed_sweep.sh [n_seeds] [concurrency]
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
PY="$REPO/.venv/bin/python"
export PATH="$REPO/.venv/bin:$PATH"
unset PYTHONPATH

N=${1:-20}
CONC=${2:-4}
# train | verify | all. Split because the two phases have very different appetites: the
# training phase is a few hundred MiB and minutes, and can run happily beside a simulator
# that is busy driving; the verification phase peaks near 8 GiB per job and cannot.
PHASE=${3:-all}
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
ARMS="P_pts P_cont P_pts3"
LOG=$REPO/results/seed_sweep.log
: > "$LOG"
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

say "seed sweep: $N seeds x {$ARMS} x {lead ped}, $CONC concurrent verifications"

# --- train ------------------------------------------------------------------
# Seed 0 is the study's own run and is NOT retrained here; it is already on disk and
# retraining it would silently replace the models every committed verdict describes.
[ "$PHASE" = "verify" ] || for s in $(seq 1 "$N"); do
  for sc in lead ped; do
    say "train seed $s / $sc"
    "$PY" -u tools/train_policies.py --scenario "$sc" --input-w 128 --input-h 96 \
        --seed "$s" --policies $ARMS >> "$LOG" 2>&1 || {
      say "FATAL: training failed at seed $s / $sc"; exit 1; }
  done
done

# --- verify property S, in batches -------------------------------------------
# Property S only. It is the property the claim is about, it is 25 poses against property
# A's 104, and property A has no witness drive to disagree with.
if [ "$PHASE" = "train" ]; then
  say "training phase complete; run with phase 'verify' when the GPU is free"
  exit 0
fi

pending=()
for s in $(seq 1 "$N"); do
  for a in $ARMS; do
    for sc in lead ped; do
      pending+=("${a}_s${s}|${sc}")
    done
  done
done

say "${#pending[@]} verifications queued"
i=0
while [ $i -lt ${#pending[@]} ]; do
  pids=""
  for _ in $(seq 1 "$CONC"); do
    [ $i -ge ${#pending[@]} ] && break
    item=${pending[$i]}; i=$((i+1))
    pol=${item%%|*}; sc=${item##*|}
    say "START verify $pol / $sc"
    "$PY" -u tools/verify.py --policy "$pol" --scenario "$sc" \
        --policy-scenario "$sc" --property S \
        > "$REPO/results/seedsweep_verify_${pol}_${sc}.log" 2>&1 &
    pids="$pids $!"
  done
  for pid in $pids; do wait "$pid" || say "  (a verification returned non-zero)"; done
  say "progress $i / ${#pending[@]}"
done

"$PY" -u tools/seed_sweep_report.py --seeds "$N" 2>&1 | tee -a "$LOG"
