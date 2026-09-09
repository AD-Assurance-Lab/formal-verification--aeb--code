#!/usr/bin/env bash
# The dense interior sweep: drive K illuminations inside every sub-interval, not one.
#
#   setsid nohup bash scripts/interior_sweep.sh > results/interior_sweep_stdout.log 2>&1 &
#   K=9 SCOPE=hazard bash scripts/interior_sweep.sh
#
# WHY THIS EXISTS, and it is the one thing the steering study could not reach.
#
# The certificate quantifies over the whole disturbance family: one intensity per pose,
# every combination at once. A drive can only ever apply ONE rendered illumination to a
# whole approach. So closed-loop testing probes a one-dimensional curve through a
# many-dimensional certified set, and that asymmetry is the argument for having a
# certificate at all. It is also the reason the drivable slice deserves to be measured
# properly rather than sampled at one point per sub-interval.
#
# Two things come out of it that one midpoint per sub-interval cannot give:
#
#   1. WHERE THE POLICY ACTUALLY STARTS FAILING. The certificate names falsified bands and
#      nobody has ever driven their EDGES. A grid at K points per sub-interval brackets
#      each pass-to-fail transition, and comparing that bracket to the certified boundary
#      is a sharper test of the method than any agreement count over midpoints.
#
#   2. BUGS, at scale. Every point is three repetitions on three freshly restarted
#      servers, and any disagreement is a bug -- which in this study has been true three
#      times out of three (F21, F23, F24). A sweep of eighty points per arm is the widest
#      net this harness can cast.
#
# It runs AFTER the rebuild: it reads the committed verdicts, and it is a prediction only
# if those were committed before it drove.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
K=${K:-5}                      # illuminations per sub-interval; must be odd
SCOPE=${SCOPE:-all}
POLICIES=${POLICIES:-"P_pts P_cont P_pts3"}
LOG=$REPO/results/interior_sweep.log
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

case "$SCOPE" in
  all)    SCEN="lead ped plate none_plate" ;;
  hazard) SCEN="lead ped" ;;
  plate)  SCEN="plate none_plate" ;;
  *) echo "SCOPE must be one of: all, hazard, plate" >&2; exit 2 ;;
esac

if [ $((K % 2)) -eq 0 ]; then
  echo "K must be odd, so the midpoint is one of the points and the sweep carries its" >&2
  echo "own cross-check against the ordinary midpoint pass. Got K=$K." >&2
  exit 2
fi

say "interior sweep: K=$K per sub-interval, scope $SCOPE ($SCEN), policies $POLICIES"
VOIDS=0
FAILED=""
for pol in $POLICIES; do
  for sc in $SCEN; do
    say "=== $pol / $sc ==="
    bash scripts/drive_witness_reps.sh "$pol" "$sc" --interior "$K" 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    if [ "$rc" -ne 0 ]; then
      VOIDS=$((VOIDS + 1)); FAILED="$FAILED $pol/$sc"
      # NOT a reason to stop the campaign. A void cell is a bug to chase afterwards, and
      # the remaining arms are independent measurements that would otherwise be lost to
      # an unrelated defect. Counted, named at the end, and never silently passed over.
      say "  $pol/$sc produced a VOID cell or failed; continuing, counted"
    fi
  done
done

say "sweep complete"
if [ "$VOIDS" -gt 0 ]; then
  say "$VOIDS drive(s) produced a VOID cell or failed:$FAILED"
  say "Under the standing rule each is a BUG until proven otherwise. Chase it; do not"
  say "run more repetitions, and do not report the cell until the cause is written down."
  exit 1
fi
say "no void cells"
