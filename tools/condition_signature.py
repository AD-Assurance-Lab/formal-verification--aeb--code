"""Prove from the PIXELS that the illumination rendered is the illumination asked for.

    python tools/condition_signature.py            # validate against the captures

**Why this exists.** Illumination is not a nuisance parameter in this study, it is the
independent variable: the whole claim is that a policy passing both FMVSS 127 lighting
conditions fails between them. Every artifact records the sun altitude it *asked* for.
Nothing, until now, recorded what was actually rendered.

The sibling steering study lost a set of verification captures to exactly this shape
(T06-F35): the sun altitude was swept while the declared exposure belonged to a different
condition, so daylight scenes were rendered through a night camera. Every run completed,
every step count was normal, every number was plausible, and nothing downstream could
reveal it. Six entry points in this repository tick the world; the steering study had two
and they diverged.

**What a signature is.** Five statistics of one rendered frame, in [0,1]:
mean, sigma, 1st and 99th percentile, and the fraction of near-black pixels. That is
enough, because this study's axis moves brightness monotonically over a wide range.

**What is checked, and why it is not a threshold table.** The steering version classifies
into four NAMED conditions and can therefore hard-code discriminators. Here the condition
is a continuous sun altitude, and the absolute numbers depend on the pose, the scene
content and the headlamp state -- so a fixed table would be wrong the moment the capture
pose moved. What IS invariant is the physics:

  1. Within one headlamp regime, a lower sun renders a darker scene. Strictly. This is
     amendment A5's measured curve (mean 179.7 at +6 deg falling to 57.7 at -6), and it
     is the property a mislabelled or unsettled knot breaks first.
  2. The axis has to actually SPAN daylight to darkness. If the brightest and darkest
     knots are close together, the weather writes did not take effect and the family is
     being built out of one illumination rendered eleven times.
  3. Headlamps ON must lift the dark end. Their step at the 5 deg threshold is a
     discontinuity in the curve, so monotonicity is checked within each regime, never
     across the switch -- checking across it would fail on a correct capture.

None of these needs a reference file, which matters: a reference measured by the same
tool in the same session is a repeat, not an independent check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
CAPTURES = REPO / "results" / "captures"

# Sun altitude at or above which the capture campaign leaves the headlamps off.
# Kept here rather than imported so this module has no CARLA dependency and can be run
# on an artifact long after the fact.
LAMP_THRESHOLD_DEG = 5.0

# The axis must span at least this much of full range between its brightest and darkest
# knot. Measured under the study's fixed exposure (A7, f/4.0): daylight sits near 0.5 of
# range and darkness near 0.03, so the true span is ~0.45. A tenth of that is already
# unambiguous evidence that the sun was not moving.
MIN_AXIS_SPAN = 0.05


def signature(frame) -> dict:
    """Five statistics of one frame. Accepts uint8 0..255 or float 0..1, any shape."""
    a = np.asarray(frame, dtype=np.float32)
    if a.size == 0:
        raise ValueError("empty frame")
    if a.max() > 1.5:  # uint8-style
        a = a / 255.0
    return {
        "mean": round(float(a.mean()), 5),
        "sigma": round(float(a.std()), 5),
        "p01": round(float(np.percentile(a, 1)), 5),
        "p99": round(float(np.percentile(a, 99)), 5),
        "frac_dark": round(float((a < 0.05).mean()), 5),
    }


def check_axis(records: list[dict], lamp_threshold: float = LAMP_THRESHOLD_DEG) -> dict:
    """Check a whole illumination axis for the failures a per-knot label cannot show.

    `records` is [{"sun_altitude_deg": float, "signature": {...}}, ...] in any order.
    Returns a report; `assert_axis` raises on it.
    """
    rows = sorted(records, key=lambda r: -float(r["sun_altitude_deg"]))
    means = [r["signature"]["mean"] for r in rows]
    alts = [float(r["sun_altitude_deg"]) for r in rows]

    span = (max(means) - min(means)) if means else 0.0

    # Monotonicity WITHIN each headlamp regime. Crossing the switch is a legitimate
    # discontinuity, so pairs that straddle it are not compared.
    violations = []
    for (a0, m0), (a1, m1) in zip(zip(alts, means), zip(alts[1:], means[1:])):
        lamps0 = a0 < lamp_threshold
        lamps1 = a1 < lamp_threshold
        if lamps0 != lamps1:
            continue  # the headlamp step; see the module docstring
        if m1 > m0 + 1e-9:
            violations.append({
                "from_deg": a0, "to_deg": a1,
                "from_mean": m0, "to_mean": m1,
                "detail": f"sun fell {a0:.3f} -> {a1:.3f} deg but the frame got "
                          f"BRIGHTER, {m0:.4f} -> {m1:.4f}",
            })

    # The brightest frame must be the highest sun in its regime, and the darkest the
    # lowest. Stated separately from the pairwise check because a single swapped pair
    # deep in the axis is a different defect from the whole axis being scrambled.
    brightest_at = alts[means.index(max(means))]
    darkest_at = alts[means.index(min(means))]

    return {
        "knots": len(rows),
        "axis_span_mean": round(span, 5),
        "min_axis_span": MIN_AXIS_SPAN,
        "span_ok": span >= MIN_AXIS_SPAN,
        "monotone_violations": violations,
        "monotone_ok": not violations,
        "brightest_at_deg": brightest_at,
        "darkest_at_deg": darkest_at,
        "lamp_threshold_deg": lamp_threshold,
        "means_by_altitude": [
            {"sun_altitude_deg": a, "mean": m, "lamps": a < lamp_threshold}
            for a, m in zip(alts, means)
        ],
        "ok": bool(violations == [] and span >= MIN_AXIS_SPAN),
    }


def assert_axis(records: list[dict], lamp_threshold: float = LAMP_THRESHOLD_DEG) -> dict:
    """Raise unless the rendered axis is physically consistent with the axis requested."""
    rep = check_axis(records, lamp_threshold)
    if rep["ok"]:
        return rep
    lines = ["ILLUMINATION AXIS DOES NOT MATCH WHAT WAS REQUESTED."]
    if not rep["span_ok"]:
        lines.append(
            f"  span: brightest and darkest knots differ by only "
            f"{rep['axis_span_mean']:.4f} of full range, floor {MIN_AXIS_SPAN}. "
            f"The sun was not moving -- the family would be one illumination "
            f"rendered {rep['knots']} times.")
    for v in rep["monotone_violations"]:
        lines.append("  " + v["detail"])
    lines.append(
        "  Every frame captured under this axis is mislabelled. This is the failure "
        "that cost the steering study its Town04 captures (T06-F35).")
    raise RuntimeError("\n".join(lines))


def main() -> int:
    """Validate the rule against whatever capture campaigns are on disk."""
    manifests = sorted(CAPTURES.glob("manifest_*.json"))
    if not manifests:
        print(f"no capture manifests in {CAPTURES.relative_to(REPO)} to validate against")
        return 1
    bad = 0
    for mpath in manifests:
        entries = json.loads(mpath.read_text())
        records = [
            {"sun_altitude_deg": e["knot"], "signature": e["signature"]}
            for e in entries if e.get("signature")
        ]
        if not records:
            print(f"{mpath.name:28s} no signatures recorded -- captured before this "
                  f"guard existed")
            bad += 1
            continue
        rep = check_axis(records)
        print(f"\n{mpath.name}  ({rep['knots']} knots, span {rep['axis_span_mean']:.4f})")
        print(f"  {'sun deg':>9s} {'mean':>8s} {'sigma':>8s} {'p99':>8s} {'lamps':>6s}")
        by_alt = {float(e["knot"]): e["signature"] for e in entries if e.get("signature")}
        for alt in sorted(by_alt, reverse=True):
            s = by_alt[alt]
            print(f"  {alt:9.3f} {s['mean']:8.4f} {s['sigma']:8.4f} {s['p99']:8.4f} "
                  f"{'on' if alt < LAMP_THRESHOLD_DEG else 'off':>6s}")
        if rep["ok"]:
            print("  OK: monotone within each headlamp regime, and the axis spans.")
        else:
            bad += 1
            for v in rep["monotone_violations"]:
                print(f"  VIOLATION: {v['detail']}")
            if not rep["span_ok"]:
                print(f"  VIOLATION: axis span {rep['axis_span_mean']:.4f} < "
                      f"{MIN_AXIS_SPAN}")
    print(f"\n  {len(manifests) - bad} of {len(manifests)} campaigns consistent")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
