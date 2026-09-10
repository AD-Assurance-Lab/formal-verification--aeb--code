#!/usr/bin/env bash
# Everything downstream of the committed verdicts, in one launch.
#
#   setsid nohup bash scripts/overnight_after_verdicts.sh > results/overnight.log 2>&1 &
#
# RUN THIS ONLY AFTER THE VERDICTS ARE COMMITTED, and do not put the commit in here.
# `rebuild_all.sh` stops before M7 on purpose, and its reason is that a script which
# committed the verdicts for you would turn the blind protocol into a formality. That
# reasoning does not stop applying because it is late: what makes a verdict a prediction
# is that somebody wrote it down before the drive. `drive_witness.py` refuses to run
# against an uncommitted verdict, so this script cannot skip the step -- it will simply
# fail at the first drive, which is the guard working.
#
# Order is deliberate:
#   1. M7, midpoint and at-witness, on A13's harness. This completes the ledger and is
#      what the study needs to be finished at all.
#   2. The interior sweep over the HAZARD scenarios. This is the paper's new section 4.3
#      and it is the half that matters most, so it runs before the plate half in case the
#      night runs out.
#   3. The interior sweep over the plate scenarios.
#
# A VOID cell does not stop the night. It is a bug to chase in the morning, and the
# remaining arms are independent measurements that should not be lost to it. Every void is
# counted and named at the end.
set -uo pipefail
cd "$(dirname "$0")/.."
REPO=$PWD
LOG=$REPO/results/overnight.log
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

say "=== 1/3  M7: the witness drives, A13 harness ==="
bash scripts/rebuild_all.sh witness 2>&1 | tee -a "$LOG"
M7=${PIPESTATUS[0]}
say "M7 finished rc=$M7$([ "$M7" -ne 0 ] && echo '  (void cells or a failed drive)')"

say "=== 2/3  interior sweep, hazard scenarios, K=5 ==="
K=5 SCOPE=hazard bash scripts/interior_sweep.sh 2>&1 | tee -a "$LOG"
IH=${PIPESTATUS[0]}
say "interior/hazard finished rc=$IH"

# THE PLATE PHASE ONLY RUNS WHERE THE PLATE SCENARIO EXISTS. Amendment A20 defers it on
# maps whose longest straight is under the 320 m it needs, and this called it by name
# anyway: it drove three repetitions into a scenario with no site and no frames before
# anyone noticed. Ask the module, as every other stage now does.
if "$REPO/.venv/bin/python" -c "import sys;sys.path.insert(0,'tools');import carla_jobs as J;sys.exit(0 if 'plate' in J.IN_SCOPE else 1)"; then
  say "=== 3/3  interior sweep, plate scenarios, K=5 ==="
  K=5 SCOPE=plate bash scripts/interior_sweep.sh 2>&1 | tee -a "$LOG"
  IP=${PIPESTATUS[0]}
  say "interior/plate finished rc=$IP"
else
  IP=0
  say "=== 3/3  SKIPPED: the plate scenario is not in scope on this map (A20) ==="
fi

say "=== reports ==="
"$REPO/.venv/bin/python" tools/interior_report.py --interior 5 2>&1 | tee -a "$LOG"
"$REPO/.venv/bin/python" tools/family_fidelity.py --scenario lead 2>&1 | tail -6 | tee -a "$LOG"
"$REPO/.venv/bin/python" -m study.status 2>&1 | head -30 | tee -a "$LOG"

# Leave the simulator free. It is shared, and whoever gets in first tomorrow should not
# find 7 GB held by a run that finished at four in the morning.
pkill -f "[C]arlaUE4" 2>/dev/null || true

say "ALL DONE   M7 rc=$M7  interior/hazard rc=$IH  interior/plate rc=$IP"
