"""Read the interior sweep: does the policy start failing where the certificate says?

    python tools/interior_report.py --interior 5

Needs no simulator. It reads the merged interior artifacts and asks three questions that
one driven midpoint per sub-interval cannot answer.

**1. Is the certificate sound, densely?** A CERTIFIED point that fails is the only thing
that can falsify a certificate, and the study has had exactly one such point in its
history -- which turned out to be a driver defect (F24). At K points per sub-interval the
same question is asked K times as often.

**2. Where does the policy actually start failing?** The certificate names falsified bands
and the study has never driven their EDGES. A grid brackets every pass-to-fail transition
between two adjacent driven illuminations, and the distance from that bracket to the
certified boundary is a measurement of the method rather than of the policy. If the knot
lies inside the bracket, the two agree to the resolution of the grid and the report says
so; if it does not, the gap is reported in degrees and is the honest error bar.

**3. How much of the falsified band is conservatism?** A falsified sub-interval whose every
driven point holds is the certificate being cautious. That is not a defect -- a sound bound
is allowed to be loose -- but the fraction is the number a reader will ask for, and over
midpoints alone it is one sample per sub-interval.

**Coverage is read from the knot file, never re-derived.** `family_knots.json` states which
sub-intervals the family covers and which it does not, and this repository has already
moved the uncovered band three times. A point in an uncovered sub-interval is reported
separately and never counted in a verdict-level total, because the family provably cannot
represent reality there and a certificate is unavailable by construction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.OUT


def coverage_map() -> dict:
    """{(from_deg, to_deg): covered} straight out of the knot file's own fields."""
    knots = json.loads((OUT / "family_knots.json").read_text())
    cov = {}
    for d in knots.get("sub_interval_detail", []):
        cov[(round(d["from_deg"], 6), round(d["to_deg"], 6))] = bool(d.get("covered"))
    for d in knots.get("uncovered", []):
        cov[(round(d["from_deg"], 6), round(d["to_deg"], 6))] = False
    return cov


def certified_band_edges(cells: list[dict], cov: dict) -> list[dict]:
    """The outer altitudes of each contiguous run of FALSIFIED covered sub-intervals.

    Sub-intervals are listed brightest to darkest, so a band's edges are the `from_deg` of
    its first sub-interval and the `to_deg` of its last."""
    seen, order = set(), []
    for c in cells:
        k = (round(c["from_deg"], 6), round(c["to_deg"], 6))
        if k not in seen:
            seen.add(k)
            order.append({"from_deg": k[0], "to_deg": k[1], "verdict": c["verdict"],
                          "covered": cov.get(k, False)})
    edges, run = [], []
    for sub in order + [None]:
        falsified = sub is not None and sub["verdict"] == "FALSIFIED" and sub["covered"]
        if falsified:
            run.append(sub)
        elif run:
            edges.append({"bright_edge_deg": run[0]["from_deg"],
                          "dark_edge_deg": run[-1]["to_deg"],
                          "sub_intervals": len(run)})
            run = []
    return edges


def driven_transitions(points: list[dict]) -> list[dict]:
    """Adjacent driven illuminations whose closed-loop verdicts differ.

    The bracket, not a boundary: bisecting inside it would assume the failure region is
    contiguous in altitude, and F6 measured that CARLA's scene brightness is not even
    monotone in sun altitude near the horizon. The bracket is what the grid actually
    establishes."""
    out = []
    for a, b in zip(points, points[1:]):
        if a["drove_ok"] != b["drove_ok"]:
            out.append({
                "from_deg": a["driven_at_deg"], "to_deg": b["driven_at_deg"],
                "width_deg": round(abs(a["driven_at_deg"] - b["driven_at_deg"]), 4),
                "direction": ("pass_to_fail" if a["drove_ok"] else "fail_to_pass"),
            })
    return out


def analyse(path: Path, cov: dict) -> dict:
    doc = json.loads(path.read_text())
    pts = []
    for c in doc["cells"]:
        k = (round(c["from_deg"], 6), round(c["to_deg"], 6))
        pts.append({
            "driven_at_deg": c["driven_at_deg"],
            "sub_interval": [c["from_deg"], c["to_deg"]],
            "covered": cov.get(k, False),
            "verdict": c["verdict"],
            "drove_ok": c["passes_protocol"] == c["of"],
            "void": bool(c.get("void")),
            "rep_verdicts": c.get("rep_verdicts"),
            "margin_x_threshold": c.get("margin_x_threshold"),
        })
    # Brightest to darkest, which is the axis's own order.
    pts.sort(key=lambda p: -p["driven_at_deg"])
    covered = [p for p in pts if p["covered"]]

    unsound = [p for p in covered if p["verdict"] == "CERTIFIED" and not p["drove_ok"]]
    conservative = [p for p in covered if p["verdict"] == "FALSIFIED" and p["drove_ok"]]
    voids = [p for p in pts if p["void"]]
    agree = sum(1 for p in covered
                if p["drove_ok"] == (p["verdict"] == "CERTIFIED"))

    edges = certified_band_edges(doc["cells"], cov)
    trans = driven_transitions(covered)
    for e in edges:
        for name, knot in (("bright", e["bright_edge_deg"]), ("dark", e["dark_edge_deg"])):
            best, gap = None, None
            for t in trans:
                lo, hi = sorted((t["from_deg"], t["to_deg"]))
                d = 0.0 if lo <= knot <= hi else min(abs(knot - lo), abs(knot - hi))
                if gap is None or d < gap:
                    best, gap = t, d
            e[f"{name}_nearest_transition"] = best
            e[f"{name}_gap_deg"] = None if gap is None else round(gap, 4)
            e[f"{name}_inside_bracket"] = (gap == 0.0) if gap is not None else None

    return {
        "artifact": path.name,
        "policy": doc["policy"], "scenario": doc["scenario"],
        "repetitions": doc.get("repetitions"),
        "points_driven": len(pts),
        "points_covered": len(covered),
        "points_uncovered": len(pts) - len(covered),
        "agreement": f"{agree}/{len(covered)}" if covered else None,
        "certified_then_failed": len(unsound),
        "certified_then_failed_points": unsound,
        "falsified_but_clean": len(conservative),
        "falsified_but_clean_frac": (round(len(conservative)
                                           / max(1, sum(1 for p in covered
                                                        if p["verdict"] == "FALSIFIED")), 4)),
        "void_points": len(voids),
        "voids": voids,
        "certified_bands": edges,
        "driven_transitions": trans,
        "points": pts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interior", type=int, default=5)
    args = ap.parse_args()

    cov = coverage_map()
    reports = [analyse(p, cov)
               for p in sorted(OUT.glob(f"witness_*_interior{args.interior}.json"))]
    if not reports:
        raise SystemExit(f"no merged interior artifacts for K={args.interior}")

    print(f"  {'policy':<8}{'scenario':<12}{'points':>7}{'agree':>10}"
          f"{'CERT->FAIL':>12}{'FALS->clean':>12}{'void':>6}")
    for r in reports:
        print(f"  {r['policy']:<8}{r['scenario']:<12}{r['points_covered']:>7}"
              f"{str(r['agreement']):>10}{r['certified_then_failed']:>12}"
              f"{r['falsified_but_clean']:>12}{r['void_points']:>6}")

    print("\n  Where the policy starts failing, against where the certificate says:")
    for r in reports:
        for e in r["certified_bands"]:
            for name in ("bright", "dark"):
                g, inside = e[f"{name}_gap_deg"], e[f"{name}_inside_bracket"]
                t = e[f"{name}_nearest_transition"]
                where = ("the certified edge is INSIDE the driven bracket" if inside
                         else f"{g} deg from the nearest driven transition"
                         if g is not None else "no driven transition anywhere")
                print(f"    {r['policy']:<7} {r['scenario']:<11} {name:<6} edge "
                      f"{e[f'{name}_edge_deg']:+8.3f}: {where}"
                      + (f"  bracket [{t['from_deg']:+.3f}, {t['to_deg']:+.3f}]" if t else ""))

    total_unsound = sum(r["certified_then_failed"] for r in reports)
    total_void = sum(r["void_points"] for r in reports)
    total_cov = sum(r["points_covered"] for r in reports)
    print(f"\n  {total_cov} covered points driven across {len(reports)} arm-scenarios.")
    print(f"  certified-then-failed: {total_unsound}")
    if total_void:
        print(f"  {total_void} VOID point(s). Each is a BUG until proven otherwise and is "
              f"not reported until the cause is written down.")

    path = J.claim_output(OUT / f"interior_report_K{args.interior}.json")
    path.write_text(json.dumps({
        "interior_K": args.interior,
        "certified_then_failed_total": total_unsound,
        "void_total": total_void,
        "covered_points_total": total_cov,
        "reports": reports,
        "note": ("Coverage is read from family_knots.json's own fields, never re-derived "
                 "from an altitude band. Uncovered points are reported and never counted "
                 "in a verdict-level total: the family provably cannot represent reality "
                 "there, so a certificate is unavailable by construction. A driven "
                 "transition is a BRACKET between adjacent driven illuminations, not a "
                 "boundary -- bisecting inside it would assume the failure region is "
                 "contiguous in altitude, and F6 measured that scene brightness is not "
                 "even monotone in sun altitude near the horizon."),
    }, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 1 if (total_unsound or total_void) else 0


if __name__ == "__main__":
    raise SystemExit(main())
