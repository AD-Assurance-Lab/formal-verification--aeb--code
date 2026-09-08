"""Restate every verification artifact's SCOPE from the primary data. Standing rule 7.

    python tools/restate_scope.py            # report only
    python tools/restate_scope.py --write    # rewrite the scope fields in place

**The defect.** `verify.py` printed and stored `poses_inside_r_req` for BOTH properties.
Property S does quantify over the poses inside `r_req`, so there the field is true.
Property A quantifies over EVERY captured pose, out to 60 m, and the field recorded a
scope **3.8x narrower than the one actually verified** -- `verify_P_cont_none_A.json`
claims "104 poses inside r_req (15.846 m)" for poses spanning 2.398 to 59.962 m.

Every verdict in those files is correct: the bounds were computed over the right pose set
the whole time. Only the artifact's claim about itself was wrong, which is the version of
this defect that survives longest, because nothing downstream ever disagrees with it. The
Town04 case that produced standing rule 7 was the same shape in the other direction -- a
capture covering 5.6% of the lap whose certificate, agreement rate and write-up all read
as complete.

**How the scope is recovered, and why it is not simply recomputed.** Rule 7 says scope is
recomputed from the primary data and never read from the artifact's own claim. So the
pose set is rebuilt here from `states_<scenario>.json` and the property, exactly as
`verify.py` selects it -- and then checked against the artifact's OWN per-cell pose
verdict counts, which are a record of how many poses each sub-interval actually bounded.
If the rebuilt count and the recorded count disagree, the artifact verified a different
set from the one the code selects and this script REFUSES to touch it, because that is a
real defect and not a labelling one.

No verdict, bound, margin, witness or provenance field is modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
CAPTURES = J.REPO / "results" / "captures"
STATES_FOR = {"none": "lead", "none_ped": "ped", "none_plate": "plate"}


def rebuild_scope(art: dict) -> tuple[dict, int]:
    """The pose set `verify.py` selects for this artifact, from the primary data."""
    scenario = art["scenario"]
    states = json.loads(
        (CAPTURES / f"states_{STATES_FOR.get(scenario, scenario)}.json").read_text())
    ranges = np.array([s["range_m"] for s in states])
    rr = art["r_req_m"]
    if art["property"] == "S":
        poses = [i for i, r in enumerate(ranges) if r <= rr]
        selection = "range <= r_req"
    else:
        poses = list(range(len(states)))
        selection = "every captured pose, at any range"
    return {
        "poses_verified": len(poses),
        "poses_available": len(states),
        "pose_range_m": [round(float(ranges[poses].min()), 3),
                         round(float(ranges[poses].max()), 3)],
        "selection": selection,
        "r_req_m": round(float(rr), 3),
        "restated_by": "tools/restate_scope.py",
        "note": ("Recomputed from results/captures/states_*.json, then checked against "
                 "this file's own per-cell pose counts. The verdicts are untouched; only "
                 "the scope statement was wrong, and only for property A."),
    }, len(poses)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="rewrite the scope fields. Without it this only reports.")
    args = ap.parse_args()

    changed, ok, refused = 0, 0, 0
    for path in sorted(OUT.glob("verify_*.json")):
        art = json.loads(path.read_text())
        if "cells" not in art or "property" not in art:
            continue
        scope, n = rebuild_scope(art)

        # The artifact's own record of how many poses each sub-interval bounded. This is
        # primary evidence and it is what the rebuilt count is checked against.
        counts = {sum(c["poses"].values()) for c in art["cells"] if "poses" in c}
        if counts and counts != {n}:
            print(f"  REFUSING {path.name}: rebuilt {n} poses, the cells record "
                  f"{sorted(counts)}. That is a real scope defect, not a label one.")
            refused += 1
            continue

        claimed = art.get("poses_inside_r_req")
        wrong = (art["property"] == "A" and claimed is not None)
        if not wrong and art.get("scope") == scope:
            ok += 1
            continue
        span = scope["pose_range_m"]
        print(f"  {path.name}: property {art['property']}, {n} poses over "
              f"{span[0]}-{span[1]} m"
              + (f"   [claimed '{claimed} poses inside r_req ({art['r_req_m']} m)']"
                 if wrong else ""))
        if args.write:
            art["scope"] = scope
            if art["property"] != "S":
                art["poses_inside_r_req"] = None
            path.write_text(json.dumps(art, indent=2) + "\n")
        changed += 1

    print(f"\n  {changed} artifact(s) {'restated' if args.write else 'would be restated'}, "
          f"{ok} already correct, {refused} refused")
    if not args.write and changed:
        print("  Re-run with --write to apply.")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
