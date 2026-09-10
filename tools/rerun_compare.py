"""Compare a re-drive against the drive it replaces. D-10's reproducibility check.

    python tools/rerun_compare.py --ref HEAD~1

**Why this is not just diffing files.** D-10 says run-to-run spread is a *measurement of
closed-loop stability margin*, not noise to be averaged away: with physics bit-exact and
only the render floor left, a policy that is contractive suppresses the perturbation and a
marginal one amplifies it. So the question a re-drive answers is not "are the numbers the
same" -- D-7 says they cannot be -- but **does any cell's VERDICT flip**. A cell that
drove 10/10 and now drives 9/10 has changed its verdict under PROTOCOL section 7's
criterion; a cell that drove 7/10 and now drives 6/10 has not.

And the standing rule is explicit that a flip is a bug rather than a sampling question:
*if the repetitions disagree, that is a BUG until proven otherwise, never a reason to run
more repetitions.* A cell whose re-drive disagrees is void, not uncertain.

`--ref` names the git revision the current artifacts replace. The old artifact is read
from git rather than from a copy on disk, because a copy is something that can be stale
and git is the thing the blind protocol already trusts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import stats as ST  # noqa: E402

OUT = J.OUT


def from_git(ref: str, path: Path):
    rel = str(path.relative_to(J.REPO))
    r = subprocess.run(["git", "show", f"{ref}:{rel}"], capture_output=True, cwd=J.REPO)
    return json.loads(r.stdout) if r.returncode == 0 else None


def compare_witness(ref: str, path: Path) -> dict | None:
    new = json.loads(path.read_text())
    old = from_git(ref, path)
    if old is None:
        return None
    obn = {(c["from_deg"], c["to_deg"]): c for c in old["cells"]}
    rows, flips = [], []
    for c in new["cells"]:
        o = obn.get((c["from_deg"], c["to_deg"]))
        if o is None:
            continue
        reps_n, reps_o = c["of"], o["of"]
        ok_n = c["passes_protocol"] == reps_n
        ok_o = o["passes_protocol"] == reps_o
        row = {
            "from_deg": c["from_deg"], "to_deg": c["to_deg"],
            "driven_at_deg": c["driven_at_deg"], "verdict": c["verdict"],
            "passes_old": f"{o['passes_protocol']}/{reps_o}",
            "passes_new": f"{c['passes_protocol']}/{reps_n}",
            "contacts_old": o.get("contacts"), "contacts_new": c.get("contacts"),
            "cell_verdict_flipped": ok_n != ok_o,
        }
        rows.append(row)
        if ok_n != ok_o:
            flips.append(row)
    return {
        "artifact": str(path.relative_to(J.REPO)),
        "policy": new["policy"], "scenario": new["scenario"],
        "driven_at": new.get("driven_at"),
        "agreement_old": old.get("agreement"), "agreement_new": new.get("agreement"),
        "model_matches": old.get("model_sha256") == new.get("model_sha256"),
        # The point of the re-drive: the OLD artifact has no harness record and the new
        # one does. That asymmetry is the finding, not a defect in the comparison.
        "determinism_old": old.get("determinism"),
        "determinism_new": new.get("determinism"),
        "cells": rows, "flips": flips,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", default="HEAD",
                    help="git revision holding the drive being replaced")
    args = ap.parse_args()

    reports, all_flips, n_cells = [], [], 0
    for path in sorted(OUT.glob("witness_*.json")):
        rep = compare_witness(args.ref, path)
        if rep is None:
            print(f"  {path.name}: not present at {args.ref} (new artifact)")
            continue
        reports.append(rep)
        all_flips.extend([{**f, "artifact": rep["artifact"]} for f in rep["flips"]])
        n_cells += len(rep["cells"])
        mark = "" if not rep["flips"] else f"   {len(rep['flips'])} FLIPPED"
        if not rep["model_matches"]:
            mark += "   MODEL CHANGED -- not a re-drive of the same network"
        print(f"  {rep['policy']:<7} {rep['scenario']:<11} {rep['driven_at']:<9} "
              f"agreement {str(rep['agreement_old']):>6} -> {str(rep['agreement_new']):<6}"
              f"{mark}")

    print(f"\n  {n_cells} sub-interval drives compared across {len(reports)} artifacts")
    if all_flips:
        print(f"  {len(all_flips)} CELL VERDICT(S) FLIPPED between drives. Standing rule:\n"
              f"  a disagreement between repetitions is a BUG until proven otherwise and\n"
              f"  the cell is VOID, not uncertain. It is not a reason to run more.")
        for f in all_flips:
            print(f"    {f['artifact']}  [{f['from_deg']:+.3f},{f['to_deg']:+.3f}] "
                  f"{f['verdict']}  {f['passes_old']} -> {f['passes_new']}  "
                  f"contacts {f['contacts_old']} -> {f['contacts_new']}")
    else:
        print("  NO cell verdict flipped. Every sub-interval that passed still passes and "
              "every one that failed still fails, on an independently re-driven harness.")
        print("  Per D-10 that is a statement about the POLICIES, not only the simulator: "
              "a marginal policy amplifies the render floor into a flipped verdict.")

    k = sum(1 for r in reports if not r["flips"])
    path = J.claim_output(OUT / "rerun_compare.json")
    path.write_text(json.dumps({
        "ref": args.ref,
        "artifacts_compared": len(reports),
        "sub_interval_drives_compared": n_cells,
        "artifacts_with_no_flip": k,
        "flips": all_flips,
        "stability_rate": ST.rate(n_cells - len(all_flips), n_cells) if n_cells else None,
        "reports": reports,
        "note": ("D-7 says frames are never bit-identical across repetitions, so the "
                 "question a re-drive answers is whether any cell's VERDICT moved, not "
                 "whether the numbers did. D-10 makes a flip a statement about the "
                 "policy's stability margin; the standing rule makes it a bug and the "
                 "cell void until the cause is written down."),
    }, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 1 if all_flips else 0


if __name__ == "__main__":
    raise SystemExit(main())
