"""What ten repetitions actually bought, measured on this study's own committed runs.

    python tools/repetition_floor.py

Needs no simulator. It reads every committed artifact that carries per-repetition
records and asks one question: **how many cells did the repetitions disagree about?**

`PROTOCOL.md` section 3 fixes the closed-loop number as a rate over at least ten
repetitions with Wilson intervals, which is the right instrument if the repetitions are
draws from a distribution. The sibling steering study's amendment A-4 says they are not:
on a fully enforced harness a repetition is a REPRODUCIBILITY CHECK, and three is enough
because rep-to-rep verdict disagreement was 0 of 48 section-pairs. That conflict is
recorded in `CARLA_DETERMINISM_PENDING.md` and this repository has been following the
ten-repetition reading while it stood.

This measures the same thing here rather than importing the answer, because the sibling
study's number is about a lane-keeper on a lap and this one is about a braking policy on
a discrete approach, and the two have no reason to share a floor.

Three quantities, and the third is the one that matters:

1. **Unanimity.** A cell's verdict is PASS iff every repetition passes, so only a SPLIT
   cell can be sensitive to the repetition count at all.
2. **What a smaller draw would have done.** For a split cell with p of n passing, a
   k-repetition draw reports PASS with probability C(p,k)/C(n,k) -- it has to miss every
   failing repetition -- and shows the split at all with probability
   1 - [C(p,k) + C(n-p,k)]/C(n,k).
3. **Whether the splits look like sampling.** They do not, and that is the finding. The
   report prints each split cell's per-repetition sequence, because a split whose failing
   repetitions are the first four in run order is not a rate, it is D-6: ten repetitions
   sharing one server, measuring the server.

The standing rule is that repetitions which disagree make a cell VOID, not uncertain, and
that more repetitions are never the answer. Under that rule a Wilson interval on a split
cell is not a weaker result, it is the wrong object: it turns an identified defect into a
plausible failure rate and loses it.
"""

from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"


def cells_of(doc: dict):
    cells = doc.get("cells")
    if isinstance(cells, list):
        return cells
    if isinstance(cells, dict):
        return list(cells.values())
    return []


def collect() -> list[dict]:
    rows = []
    for path in sorted(OUT.glob("*.json")):
        try:
            doc = json.loads(path.read_text())
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for cell in cells_of(doc):
            if not isinstance(cell, dict):
                continue
            n, p = cell.get("of"), cell.get("passes_protocol")
            if not isinstance(n, int) or not isinstance(p, int) or n < 2:
                continue
            rows.append({
                "artifact": path.name,
                "policy": doc.get("policy") or cell.get("policy"),
                "scenario": doc.get("scenario"),
                "driven_at": doc.get("driven_at"),
                "from_deg": cell.get("from_deg"), "to_deg": cell.get("to_deg"),
                "verdict": cell.get("verdict"),
                "n": n, "p": p,
                "unanimous": p in (0, n),
                "runs": cell.get("runs"),
                # The per-run series the artifacts carry. Identical values across ten
                # repetitions are the harness reporting that it is doing its job; a
                # STEP in the series is the harness reporting that it is not.
                "series": {k: v for k, v in cell.items()
                           if isinstance(v, list) and len(v) == n
                           and all(isinstance(x, (int, float, type(None))) for x in v)},
            })
    return rows


def draw_pass(p: int, n: int, k: int) -> float:
    """P(a k-repetition draw sees only passing repetitions) for a cell with p of n."""
    return comb(p, k) / comb(n, k) if p >= k else 0.0


def draw_split(p: int, n: int, k: int) -> float:
    same = (comb(p, k) if p >= k else 0) + (comb(n - p, k) if n - p >= k else 0)
    return 1.0 - same / comb(n, k)


def main() -> int:
    rows = collect()
    n10 = [r for r in rows if r["n"] == 10]
    split = [r for r in n10 if not r["unanimous"]]

    print(f"  cells carrying a ten-repetition protocol count : {len(n10)}")
    print(f"    unanimous                                    : {len(n10) - len(split)}")
    print(f"    split                                        : {len(split)}")
    print()

    for r in split:
        print(f"  SPLIT  {r['artifact']}  [{r['from_deg']:+.3f}, {r['to_deg']:+.3f}]  "
              f"{r['verdict']}  {r['p']}/{r['n']}")
        if r["runs"]:
            seq = "".join("P" if _run_passed(x) else "F" for x in r["runs"])
            print(f"         repetitions in run order: {seq}")
        for key, series in sorted(r["series"].items()):
            vals = [x for x in series if x is not None]
            if len(set(vals)) > 1:
                print(f"         {key}: {series}")
        print()

    print("  What a smaller draw would have reported, over the split cells only:")
    print(f"    {'k':>3}  {'E[cells read PASS that are not]':>32}  "
          f"{'P(split is visible), worst cell':>32}")
    per_k = {}
    for k in range(1, 11):
        e = sum(draw_pass(r["p"], r["n"], k) for r in split)
        worst = min((draw_split(r["p"], r["n"], k) for r in split), default=1.0)
        per_k[k] = {"expected_false_pass_cells": round(e, 4),
                    "worst_cell_probability_split_is_visible": round(worst, 4)}
        print(f"    {k:>3}  {e:>32.4f}  {worst:>32.4f}")

    ident = tot = 0
    for r in n10:
        for series in r["series"].values():
            vals = [x for x in series if x is not None]
            if len(vals) == r["n"]:
                tot += 1
                ident += len(set(vals)) == 1
    print()
    print(f"  per-repetition series that are IDENTICAL across all ten repetitions: "
          f"{ident} of {tot}" + (f" ({100 * ident / tot:.1f}%)" if tot else ""))

    payload = {
        "cells_with_ten_repetitions": len(n10),
        "unanimous": len(n10) - len(split),
        "split": len(split),
        "split_cells": [{k: v for k, v in r.items() if k != "runs"} for r in split],
        "smaller_draw": per_k,
        "identical_series": {"identical": ident, "of": tot},
        "note": ("Only a split cell can be sensitive to the repetition count, because a "
                 "cell passes iff every repetition passes. The split cells here are not "
                 "draws from a rate: see their per-repetition sequences. Under the "
                 "standing rule a split cell is VOID, so the repetition count is buying "
                 "DETECTION of a split, not precision on a rate."),
    }
    path = J.claim_output(OUT / "repetition_floor.json")
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


def _run_passed(run: dict) -> bool:
    if "passes" in run:
        return bool(run["passes"])
    return (not run.get("contact", False)) and bool(run.get("standoff_ok"))


if __name__ == "__main__":
    raise SystemExit(main())
