"""Merge the per-repetition witness artifacts into the one the study reads.

    python tools/merge_witness_reps.py --policy P_cont --scenario lead

`tools/drive_witness.py --rep-index k --reps 1` drives one repetition of every
sub-interval in its own process against its own freshly restarted server, and writes it
to `results/carla/witness_reps/`. This assembles those into
`results/carla/witness_<policy>_<scenario>[_atwitness].json` with the schema every
consumer already expects, plus two fields that only exist because the repetitions are now
genuinely independent:

    "void"           the repetitions disagreed about this sub-interval
    "rep_verdicts"   what each one said, in repetition order

**A void cell is not an uncertain cell.** The standing rule is that repetitions which
disagree are a bug until proven otherwise, and that a bigger sample is never the answer:
it turns an identified defect into a plausible failure rate and loses it. So this tool
does not average, does not compute a Wilson interval over the repetitions, and exits
non-zero when any cell is void. What it reports is a verdict plus the margin behind it.

**What it refuses to merge.** Repetitions that drove different networks, different
sub-intervals or different illuminations are not repetitions of one experiment, and a
merge that quietly reconciled them would produce a result-shaped artifact out of two
different studies. Each is checked and each is fatal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
REPS_DIR = OUT / "witness_reps"


def key_of(cell: dict) -> tuple:
    # The DRIVEN ILLUMINATION is part of the key, not just the sub-interval. An interior
    # sweep puts several driven points inside one sub-interval, and keying on the
    # sub-interval alone would silently merge five different conditions into one cell.
    return (round(cell["from_deg"], 6), round(cell["to_deg"], 6),
            round(cell["driven_at_deg"], 3))


def merge(policy: str, scenario: str, at_witness: bool, interior: int = 0) -> int:
    sfx = ("_atwitness" if at_witness
           else f"_interior{interior}" if interior else "")
    stem = f"witness_{policy}_{scenario}{sfx}"
    paths = sorted(REPS_DIR.glob(f"{stem}_rep*.json"))
    if not paths:
        raise SystemExit(f"no per-repetition artifacts matching {stem}_rep*.json")
    docs = [json.loads(p.read_text()) for p in paths]
    n = len(docs)

    # Same network, or these are not repetitions of one measurement.
    hashes = {d.get("model_sha256") for d in docs}
    if len(hashes) != 1:
        raise SystemExit(f"{stem}: {len(hashes)} distinct model hashes across {n} "
                         f"repetitions. These are not repetitions of one experiment.")
    # Same sub-intervals, in the same order.
    keysets = [tuple(key_of(c) for c in d["cells"]) for d in docs]
    if len(set(keysets)) != 1:
        raise SystemExit(f"{stem}: the repetitions do not cover the same sub-intervals.")
    # Same rendered illumination per sub-interval. A repetition that drove a different
    # altitude is a different condition, and nothing else here would notice.
    for i, key in enumerate(keysets[0]):
        alts = {round(d["cells"][i]["driven_at_deg"], 3) for d in docs}
        if len(alts) != 1:
            raise SystemExit(
                f"{stem}: point {key} was driven at {sorted(alts)} deg across "
                f"repetitions. Scope is recomputed from the primary data and this is it.")

    plate = scenario in ("plate", "none_plate")
    rows, agree, void_cells = [], 0, []
    for i, key in enumerate(keysets[0]):
        per_rep = [d["cells"][i] for d in docs]
        base = dict(per_rep[0])
        # Each per-repetition artifact holds exactly one run per sub-interval, so the
        # pass count is the count of repetitions whose single run passed.
        rep_ok = [c["passes_protocol"] == c["of"] for c in per_rep]
        passes = sum(rep_ok)
        void = 0 < passes < n
        runs = [r for c in per_rep for r in c.get("runs", [])]

        base.update({
            "passes": passes, "passes_protocol": passes, "of": n,
            "rate": round(passes / n, 4),
            "void": void,
            "rep_verdicts": ["PASS" if ok else "FAIL" for ok in rep_ok],
            "runs": runs,
            # No Wilson interval. Under the standing rule these repetitions are a
            # reproducibility check and not a sample, so an interval on them would be
            # an interval on nothing.
            "wilson_95": None,
        })
        for k in ("never_braked", "contacts", "standoff_short", "premature",
                  "passes_no_nuisance", "braked", "exceeded_limit", "did_not_cross"):
            vals = [c.get(k) for c in per_rep]
            if all(isinstance(v, int) for v in vals):
                base[k] = sum(vals)
        if plate:
            peaks = [p for c in per_rep for p in c.get("peak_demand_mps2", [])]
            if peaks:
                base["peak_demand_mps2"] = peaks
                base["worst_peak_mps2"] = round(max(peaks), 4)
                lim = per_rep[0].get("nuisance_limit_mps2")
                if lim:
                    base["worst_peak_x_limit"] = round(max(peaks) / lim, 4)
        else:
            base["min_gap_ft"] = [r.get("min_gap_ft") for r in runs]

        drove_ok = passes == n
        matched = drove_ok == (base["verdict"] == "CERTIFIED")
        base["agrees"] = matched
        agree += matched
        if void:
            void_cells.append(base)
        rows.append(base)

    payload = {
        "policy": policy, "scenario": scenario,
        "rep_index": None,
        "repetitions": n,
        "merged_from": [p.name for p in paths],
        "model_sha256": docs[0].get("model_sha256"),
        "provenance": docs[0].get("provenance"),
        # One per repetition, because the point of the restart is that each repetition
        # ran on a different server and the artifact has to be able to prove it.
        "determinism": [d.get("determinism") for d in docs],
        "illumination": docs[0].get("illumination"),
        "agreement": f"{agree}/{len(rows)}",
        "void_cells": len(void_cells),
        "cells": rows,
        "note": (
            "Each repetition drove every sub-interval once, in its own process against "
            "its own freshly restarted server (D-6). A sub-interval whose repetitions "
            "disagree is marked void: under the standing rule that is a bug until proven "
            "otherwise, not a failure rate, and more repetitions are not the answer."),
    }
    path = J.claim_output(OUT / f"{stem}.json")
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  {stem}: {n} repetitions, agreement {agree}/{len(rows)}, "
          f"{len(void_cells)} void")
    for c in void_cells:
        print(f"    VOID [{c['from_deg']:+8.3f}, {c['to_deg']:+8.3f}]  "
              f"{c['verdict']}  {''.join('P' if v == 'PASS' else 'F' for v in c['rep_verdicts'])}")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 1 if void_cells else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--at-witness", action="store_true")
    ap.add_argument("--interior", type=int, default=0)
    args = ap.parse_args()
    return merge(args.policy, args.scenario, args.at_witness, args.interior)


if __name__ == "__main__":
    raise SystemExit(main())
