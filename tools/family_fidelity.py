"""How much image-space distance does each sub-interval actually span?

    python tools/family_fidelity.py [--scenario lead]

Needs no simulator. Reads the captured frame sets the certificates are computed on and
measures, per sub-interval, the mean absolute per-pixel distance between its two endpoint
frame sets — the same norm `build_family_knots.blend_error` uses, on the same 0–1 scale.

**Why this is not already known.** The axis is bisected until the chord's midpoint error
falls under an ABSOLUTE tolerance of 0.01. That rule has no notion of how much the interval
spans, so nothing prevents it from producing a sub-interval across which almost nothing
changes. Both maps produced exactly one: Town01's [−29.554°, −30.000°] and Town12's
[−29.539°, −30.000°], whose endpoint frame sets are identical to within the render floor.
The family over such a sub-interval interpolates between two copies of the same image, and
its certificate is a statement about nothing — while still contributing a verdict to every
count the study reports.

**What this measures, and what it does not.** The distance here is computed over the whole
captured pose set, which is what `verify.py` bounds. `blend_error` in the knot file is a
different measurement: ONE frame at a fixed empty-road pose (`along=25.0`). The two are not
directly comparable and this tool does not pretend they are — it reports the distance and
leaves the ratio to a measurement that renders both quantities at the same poses, which
needs the simulator and is queued rather than guessed at here.

**What to do with it.** Report the span beside every verdict. A count of certified
sub-intervals treats one spanning 0.047 and one spanning 0.0002 as equal evidence, and they
are not.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
from capture_campaign import capture_stem  # noqa: E402

OUT = J.REPO / "results" / "carla"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--floor", type=float, default=0.002,
                    help="a sub-interval spanning less than this in mean absolute pixel "
                         "distance is flagged as spanning nothing. The default is about "
                         "half a grey level at 8 bits, which is above the render floor "
                         "D-7 measures and far below anything the policy resolves.")
    args = ap.parse_args()

    knots = json.loads((OUT / "family_knots.json").read_text())
    cache: dict[float, np.ndarray | None] = {}

    def frames(knot: float):
        key = round(knot, 3)
        if key not in cache:
            p = J.CAPTURES / f"{capture_stem(args.scenario, knot, False)}.npz"
            cache[key] = (np.load(p)["images"].astype(np.float32) if p.exists() else None)
        return cache[key]

    rows = []
    for d in knots["sub_interval_detail"]:
        a, b = frames(d["from_deg"]), frames(d["to_deg"])
        if a is None or b is None or a.shape != b.shape:
            continue
        rows.append({
            "from_deg": d["from_deg"], "to_deg": d["to_deg"],
            "width_deg": round(abs(d["from_deg"] - d["to_deg"]), 4),
            "endpoint_distance": round(float(np.abs(a - b).mean()) / 255.0, 6),
            "blend_error_one_pose": d["blend_error"],
            "covered": bool(d.get("covered")),
            "poses": int(a.shape[0]),
        })
    if not rows:
        raise SystemExit(f"no captured frame sets for scenario {args.scenario!r} under "
                         f"{J.CAPTURES.relative_to(J.REPO)}")

    rows.sort(key=lambda r: r["endpoint_distance"])
    spans_nothing = [r for r in rows if r["endpoint_distance"] < args.floor]
    dists = [r["endpoint_distance"] for r in rows]

    print(f"  {'sub-interval':<22}{'deg':>8}{'endpoint dist':>15}{'covered':>9}")
    for r in rows:
        mark = "   <-- spans nothing" if r["endpoint_distance"] < args.floor else ""
        print(f"  [{r['from_deg']:+8.3f},{r['to_deg']:+8.3f}]{r['width_deg']:>8.3f}"
              f"{r['endpoint_distance']:>15.6f}{str(r['covered']):>9}{mark}")
    print(f"\n  {len(rows)} sub-intervals, distance {min(dists):.6f} to {max(dists):.6f} "
          f"— a factor of {max(dists) / max(min(dists), 1e-9):.0f}")
    print(f"  median {statistics.median(dists):.6f}")
    if spans_nothing:
        print(f"  {len(spans_nothing)} span less than {args.floor} and are verdicts about "
              f"nothing:")
        for r in spans_nothing:
            print(f"    [{r['from_deg']:+8.3f}, {r['to_deg']:+8.3f}]  "
                  f"{r['endpoint_distance']:.6f}")

    path = J.claim_output(OUT / f"family_fidelity_{args.scenario}.json")
    path.write_text(json.dumps({
        "scenario": args.scenario,
        "map": J.MAP,
        "floor": args.floor,
        "sub_intervals": len(rows),
        "spans_nothing": len(spans_nothing),
        "distance_min": min(dists), "distance_max": max(dists),
        "distance_median": statistics.median(dists),
        "rows": rows,
        "note": ("endpoint_distance is the mean absolute per-pixel difference between the "
                 "two endpoint frame SETS, over the whole captured pose set, on the 0-1 "
                 "scale. blend_error_one_pose is carried from the knot file for reference "
                 "and is NOT the same measurement: it is one frame at a fixed empty-road "
                 "pose. Do not form a ratio of the two."),
    }, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
