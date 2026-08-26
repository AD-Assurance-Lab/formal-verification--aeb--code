"""The order and binding checker for the blind protocol.

    python -m study.ledger --check-order

PROTOCOL section 8: verdicts are committed to git before the corresponding
closed-loop run — that is what makes a verdict a prediction. tools/verify.py has
cited this module since M6; it now exists. Beyond ordering it also closes the holes
an adversarial audit found:

  - CONTENT commits, not first-adds. The A10 retrain overwrote verify_*.json in
    place, so a first-add checker would credit retrained verdicts with the
    pre-retrain commit time. The check finds the earliest commit whose blob equals
    the file's CURRENT content.
  - Artifact <-> cell binding. Measured results were once filed under the wrong
    ledger rows (lead results in the ped-cross cells) and nothing noticed. Each
    results.json cell names its artifacts; the artifact's own scenario/policy
    fields are cross-checked against the frozen section 9 row.
  - Model binding. verify/witness JSONs record sha256 of the .pt they used (newer
    runs); when both carry it, they must match — a verdict is a prediction about
    one specific network.
  - Same-commit pairs and uncommitted artifacts are refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "study" / "results.json"

# Frozen section 9 rows: cell -> (policy, scenario token expected in artifacts)
LEDGER_ROWS = {
    "1": ("P_pts", "ped"),
    "2": ("P_pts", "lead"),
    "3": ("P_cont", "ped"),
    "4": ("P_cont", "lead"),
    "5": ("P_pts", "plate"),
    "6": ("P_cont", "plate"),
}


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              check=True, cwd=REPO).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _content_commit(path: Path) -> tuple[str, int] | None:
    """(hash, committer_time) of the EARLIEST commit whose blob equals the file's
    current content, or None if the current content was never committed."""
    rel = str(path.relative_to(REPO))
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    log = _git("log", "--format=%H %ct", "--", rel)
    if not log:
        return None
    earliest = None
    for line in log.splitlines():
        h, t = line.split()
        blob = subprocess.run(["git", "show", f"{h}:{rel}"], capture_output=True,
                              cwd=REPO)
        if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == current:
            earliest = (h, int(t))
    return earliest


def _is_ancestor(a: str, b: str) -> bool | None:
    r = subprocess.run(["git", "merge-base", "--is-ancestor", a, b],
                       capture_output=True, cwd=REPO)
    return r.returncode == 0 if r.returncode in (0, 1) else None


def check_order() -> list[str]:
    problems: list[str] = []
    cells = json.loads(RESULTS.read_text())["cells"]

    for cid, cell in cells.items():
        if cell.get("fv") is None:
            continue
        v_rel, w_rel = cell.get("artifact"), cell.get("witness_artifact")
        if not v_rel:
            problems.append(f"cell {cid}: measured but names no verify artifact")
            continue
        v_path = REPO / v_rel
        if not v_path.exists():
            problems.append(f"cell {cid}: artifact missing: {v_rel}")
            continue

        # Binding: the artifact's own declared scenario/policy must match the row.
        policy, scenario = LEDGER_ROWS[cid]
        v = json.loads(v_path.read_text())
        if policy not in (v.get("policy") or v_rel):
            problems.append(f"cell {cid}: artifact {v_rel} is policy "
                            f"{v.get('policy')!r}, row expects {policy}")
        art_scen = v.get("scenario") or v_rel
        if scenario not in art_scen:
            problems.append(f"cell {cid}: artifact {v_rel} is scenario "
                            f"{art_scen!r}, row expects {scenario!r} -- results "
                            f"filed under the wrong ledger cell")

        # PROTOCOL section 9: a falsified cell must record the violating width.
        if str(cell.get("fv", "")).upper().startswith("FALSIFIED") \
                and cell.get("width") is None:
            problems.append(f"cell {cid}: FALSIFIED but no violating width recorded "
                            f"(PROTOCOL section 9 requires it)")

        v_commit = _content_commit(v_path)
        if v_commit is None:
            problems.append(f"cell {cid}: {v_rel}'s CURRENT content was never "
                            f"committed -- the verdict on disk is not the one on "
                            f"record")
            continue
        if not w_rel:
            if cell.get("witness") is not None:
                problems.append(f"cell {cid}: witness recorded but no witness artifact")
            # A committed verdict awaiting its drive is the blind protocol working,
            # not a problem: the verdict sits on record before CARLA is available.
            continue
        w_path = REPO / w_rel
        if not w_path.exists():
            problems.append(f"cell {cid}: witness artifact missing: {w_rel}")
            continue
        w_commit = _content_commit(w_path)
        if w_commit is None:
            problems.append(f"cell {cid}: {w_rel}'s current content was never committed")
            continue

        if v_commit[0] == w_commit[0]:
            problems.append(f"cell {cid}: verdict and witness landed in the SAME "
                            f"commit -- order unverifiable")
        else:
            anc = _is_ancestor(v_commit[0], w_commit[0])
            ordered = anc if anc is not None else v_commit[1] < w_commit[1]
            if not ordered:
                problems.append(f"cell {cid}: verdict committed AFTER the witness "
                                f"drive -- postdiction is not prediction")

        # Model binding, when both artifacts record it.
        w = json.loads(w_path.read_text())
        vm, wm = v.get("model_sha256"), w.get("model_sha256")
        if vm and wm and vm != wm:
            problems.append(f"cell {cid}: verify and witness used DIFFERENT models "
                            f"({vm[:12]} vs {wm[:12]})")

    # Untracked result artifacts have no git anchor at all.
    status = _git("status", "--porcelain", "--", "results/carla") or ""
    for line in status.splitlines():
        if line.startswith("??") and line.strip().endswith(".json"):
            problems.append(f"untracked result artifact (no git anchor): "
                            f"{line[3:].strip()}")
        elif line.startswith(" M"):
            problems.append(f"result artifact MODIFIED since commit: "
                            f"{line[3:].strip()} -- the committed verdict is stale")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-order", action="store_true",
                    help="verify verdicts preceded their witness drives (default)")
    ap.parse_args()

    problems = check_order()
    if problems:
        print("ORDER/BINDING PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("Blind protocol holds: every measured cell's verdict content was committed "
          "before its witness drive, artifacts match their ledger rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
