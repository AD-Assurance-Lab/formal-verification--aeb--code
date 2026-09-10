"""Check that the fixed-knot arms did not move when the axis gained knots.

    python tools/check_arms_unmoved.py <round>

`scripts/gate_repair_loop.sh` splits the illumination axis, recaptures the new knots and
retrains. Only `P_cont` trains on the continuum, so only `P_cont` should change. `P_pts`
and `P_pts3` train on the regulatory conditions, whose frames the capture stamp guard
skips, so their weights must come out byte-identical to the round before.

If they do not, F29 is back: the determinism pins are not holding, the networks are moving
between rounds, and every gate the loop is about to measure is measuring the optimiser
rather than the disturbance family. The loop's stopping rule -- does the failing count
fall -- means nothing under that condition, which is why this exits non-zero and stops it.

Exit 0 unchanged, exit 3 moved. The first round has nothing to compare against and records
the hashes for the next one.

Written for FINDINGS F30. F29 is the defect it watches for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import OUT  # noqa: E402

# The arms whose training set a split does NOT change.
FIXED_KNOT_ARMS = ("P_pts", "P_pts3")


def main() -> int:
    rnd = sys.argv[1] if len(sys.argv) > 1 else "0"
    keep_dir = OUT / "gate_repair_hashes"
    keep_dir.mkdir(parents=True, exist_ok=True)
    moved, first = [], True
    for scenario, suffix in (("lead", ""), ("ped", "_ped")):
        report = OUT / f"training{suffix}.json"
        if not report.exists():
            print(f"  no {report.name}: the retrain did not write one")
            return 3
        current = {name: arm["weights_sha256"]
                   for name, arm in json.loads(report.read_text())["policies"].items()}
        # One file per scenario, overwritten each round, so the comparison is always
        # against the round immediately before rather than against the start.
        keep = keep_dir / f"training{suffix}.json"
        if keep.exists():
            first = False
            previous = json.loads(keep.read_text())["weights_sha256"]
            for arm in FIXED_KNOT_ARMS:
                if previous.get(arm) != current.get(arm):
                    moved.append(f"{arm}/{scenario}")
        keep.write_text(json.dumps(
            {"round": rnd, "weights_sha256": current}, indent=2) + "\n")
    if moved:
        print("  FIXED-KNOT ARMS MOVED: " + ", ".join(moved))
        print("  Their frames did not change, so the determinism pins are not holding.")
        print("  This is FINDINGS F29 returning. Do not trust this round's gates.")
        return 3
    if first:
        print("  first round: recorded the arm hashes, nothing to compare against yet")
    else:
        print("  fixed-knot arms unchanged; only P_cont saw the new knots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
