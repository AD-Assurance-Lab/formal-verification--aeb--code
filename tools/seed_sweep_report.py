"""Is the dusk gap the axis sampling, or one draw's luck? The answer, as a distribution.

    python tools/seed_sweep_report.py --seeds 20

Reads every `verify_<arm>_s<k>_<scenario>.json` the sweep produced and reports, per arm,
the DISTRIBUTION of the two numbers the study leads on: how many covered sub-intervals
certify, and how wide the falsified band is.

**Why a distribution and not two point estimates.** The study says the gap between `P_pts`
and `P_cont` is attributable to how the illumination axis was sampled. At one seed per arm
that is indistinguishable from the two networks having landed in different basins, and the
sibling steering study measured that this lab's training dispersion is intrinsic -- an
8-model ensemble was still 31% worse than drawing the best seed, and it recommended n = 20
to 60 before believing a 20% effect on a driving endpoint.

**The test.** Arms are matched pairwise by seed -- at seed k every arm starts from the same
initialisation and shuffling order and differs only in which frames it saw -- so the right
comparison is a PAIRED one. Reported here:

  the paired differences per seed, arm against arm
  the sign test on those differences, which assumes nothing about their distribution
  the overlap of the two arms' ranges, which is what a reader will look at first

A sign test on 20 matched pairs reaches p < 0.001 if every pair goes the same way, and it
needs no normality, no equal variances and no large-sample argument. For a claim this
central, an assumption-free test that can be checked by hand is worth more than a t-test
with more power.

**What would sink the claim.** If the arms' ranges overlap, or the paired differences do
not consistently favour `P_cont`, then the single-seed result was a draw and the study's
attribution does not hold. That outcome is reportable and this tool states it plainly
rather than hunting for a statistic that rescues it.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
ARMS = ["P_pts", "P_cont", "P_pts3"]


def cell_stats(path: Path) -> dict | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    covered = [c for c in d["cells"] if not c.get("family_uncovered")]
    if not covered:
        return None
    fals = [c for c in covered if c["verdict"] == "FALSIFIED"]
    und = [c for c in covered if c["verdict"] == "UNDECIDED"]
    return {
        "certified": len(covered) - len(fals) - len(und),
        "falsified": len(fals),
        "undecided": len(und),
        "of_covered": len(covered),
        "falsified_width_deg": round(sum(c["from_deg"] - c["to_deg"] for c in fals), 3),
        "worst_margin": min(c["margin_x_threshold"] for c in covered
                            if c["margin_x_threshold"] is not None),
    }


def sign_test(diffs: list[float]) -> dict:
    """Two-sided exact sign test. No distributional assumption at all.

    Ties are dropped, which is the standard treatment and is conservative here: a seed
    where the two arms certify the same number of sub-intervals is evidence for neither.
    """
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    n = pos + neg
    if n == 0:
        return {"n": 0, "positive": 0, "negative": 0, "p_two_sided": None}
    k = min(pos, neg)
    # P(X <= k) under Binomial(n, 1/2), doubled for two-sided.
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return {"n": n, "positive": pos, "negative": neg, "ties": len(diffs) - n,
            "p_two_sided": round(min(1.0, 2 * tail), 6)}


def summarise(values: list[float]) -> dict:
    s = sorted(values)
    n = len(s)
    return {
        "n": n,
        "min": round(s[0], 3), "max": round(s[-1], 3),
        "median": round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2, 3),
        "mean": round(sum(s) / n, 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--scenario", default="lead", choices=["lead", "ped", "both"])
    args = ap.parse_args()

    scenarios = ["lead", "ped"] if args.scenario == "both" else [args.scenario]
    report = {"seeds_requested": args.seeds, "scenarios": {}}

    for sc in scenarios:
        per_arm: dict[str, dict[int, dict]] = {a: {} for a in ARMS}
        # Seed 0 is the study's own run; it is a legitimate member of the sample.
        for seed in range(0, args.seeds + 1):
            for arm in ARMS:
                tag = "" if seed == 0 else f"_s{seed}"
                st = cell_stats(OUT / f"verify_{arm}{tag}_{sc}.json")
                if st is not None:
                    per_arm[arm][seed] = st

        common = sorted(set.intersection(*(set(per_arm[a]) for a in ARMS))
                        if all(per_arm[a] for a in ARMS) else set())
        entry = {
            "seeds_found": {a: sorted(per_arm[a]) for a in ARMS},
            "paired_seeds": common,
            "per_arm": {},
            "paired": {},
        }
        for a in ARMS:
            if per_arm[a]:
                entry["per_arm"][a] = {
                    "certified": summarise([per_arm[a][s]["certified"] for s in per_arm[a]]),
                    "falsified_width_deg": summarise(
                        [per_arm[a][s]["falsified_width_deg"] for s in per_arm[a]]),
                }

        for x, y in (("P_cont", "P_pts"), ("P_pts3", "P_pts"), ("P_cont", "P_pts3")):
            if not common or x not in per_arm or y not in per_arm:
                continue
            d_cert = [per_arm[x][s]["certified"] - per_arm[y][s]["certified"]
                      for s in common]
            d_width = [per_arm[y][s]["falsified_width_deg"]
                       - per_arm[x][s]["falsified_width_deg"] for s in common]
            # Ranges that do not overlap are the thing a reader checks first, so it is
            # computed rather than left to be eyeballed off the summary.
            xr = (min(per_arm[x][s]["certified"] for s in common),
                  max(per_arm[x][s]["certified"] for s in common))
            yr = (min(per_arm[y][s]["certified"] for s in common),
                  max(per_arm[y][s]["certified"] for s in common))
            entry["paired"][f"{x}_minus_{y}"] = {
                "certified_difference": summarise(d_cert),
                "certified_sign_test": sign_test(d_cert),
                "falsified_width_reduction_deg": summarise(d_width),
                "certified_range_x": list(xr),
                "certified_range_y": list(yr),
                "ranges_disjoint": xr[0] > yr[1] or yr[0] > xr[1],
            }
        report["scenarios"][sc] = entry

    (OUT / "seed_sweep.json").write_text(json.dumps(report, indent=2) + "\n")

    for sc, entry in report["scenarios"].items():
        print(f"\n=== {sc} ===")
        for a, st in entry["per_arm"].items():
            c, wdt = st["certified"], st["falsified_width_deg"]
            print(f"  {a:7s} n={c['n']:2d}  certified {c['min']:.0f}-{c['max']:.0f} "
                  f"(median {c['median']:.1f})   falsified width "
                  f"{wdt['min']:.1f}-{wdt['max']:.1f} deg (median {wdt['median']:.1f})")
        for pair, p in entry["paired"].items():
            s = p["certified_sign_test"]
            print(f"\n  {pair}: certified difference median "
                  f"{p['certified_difference']['median']:+.1f}, "
                  f"range {p['certified_difference']['min']:+.0f} to "
                  f"{p['certified_difference']['max']:+.0f}")
            print(f"    sign test on {s['n']} matched pairs: {s['positive']} positive, "
                  f"{s['negative']} negative, p = {s['p_two_sided']}")
            print(f"    ranges disjoint: {p['ranges_disjoint']}"
                  f"   ({p['certified_range_x']} vs {p['certified_range_y']})")
        if not entry["paired_seeds"]:
            print("  no seed has all arms verified yet")
    print(f"\n  wrote results/carla/seed_sweep.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
