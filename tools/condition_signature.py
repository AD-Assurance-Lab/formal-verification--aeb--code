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

**What is checked, and why it is not strict monotonicity.** The steering version
classifies into four NAMED conditions and can hard-code discriminators. Here the condition
is a continuous sun altitude, and the absolute numbers depend on the pose, the scene
content and the headlamp state, so a fixed table would be wrong the moment the capture
pose moved.

The first version of this file asserted that a lower sun always renders a darker frame.
**It fired on the first real capture campaign, and it was wrong** -- measured over
Town01's site 0 at the study's fixed exposure, CARLA's scene brightness is NOT monotone in
sun altitude (FINDINGS F6):

  * it PEAKS near +43 deg, not at +60. Mean 0.5064 at +60, 0.5282 at +42.8, 0.5182 at
    +28.4. With the sun near zenith the sky panel in view is dimmer than at mid-elevation,
    so the top of the axis turns over.
  * it SPIKES at exactly 0.000 deg. Mean falls 0.0758, 0.0377 approaching the horizon and
    jumps back to 0.0665 at zero before resuming at 0.0496. That is A6's horizon
    discontinuity, seen photometrically instead of through blend error.

Both are small -- 4.5% and 5.9% of the axis span -- and both are the renderer, not the
harness. So what is asserted is MAGNITUDE, which is what every failure this guard exists
to catch actually moves:

  1. **Span.** Brightest and darkest must differ substantially. If they do not, the
     weather writes never took effect and the family is one illumination rendered
     seventeen times.
  2. **Bounded inversion.** No single step may run backwards by more than
     MAX_INVERSION_FRAC of the span, and the total backwards movement over the whole
     axis may not exceed MAX_TOTAL_RISE_FRAC. A knot rendered at the wrong illumination
     displaces its frame by a large fraction of the span; the renderer's own wobble is
     under a sixteenth of it.
  3. **Extremes.** The brightest frame must come from the upper half of the altitude
     range and the darkest from the lower half. A reversed or scrambled axis fails here
     even if every individual step is small.
  4. **Declared discontinuities are exempt, not assumed.** An inversion that lands exactly
     on a sub-interval the knot measurement itself declares UNCOVERED is expected -- that
     declaration is A6 saying the renderer is discontinuous there. The deviation is still
     recorded; it is just not a failure.

None of this needs a reference file, which matters: a reference measured by the same tool
in the same session is a repeat, not an independent check. What IS independent is
comparing the four capture campaigns against each other, which `main()` does -- they
render the same site at the same knots, so a knot mislabelled in one campaign diverges
from the other three.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# Map-scoped, from tools/paths.py, which is stdlib-only. This module deliberately has no
# CARLA dependency -- it must run on a machine with no simulator and no carla package,
# which importing carla_jobs would break -- and it used to re-type the path for that
# reason. Re-typing a path is the defect (F26), not the cure for it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPO, CAPTURES, OUT  # noqa: E402

# Sun altitude at or above which the capture campaign leaves the headlamps off.
# Kept here rather than imported so this module has no CARLA dependency and can be run
# on an artifact long after the fact.
LAMP_THRESHOLD_DEG = 5.0

# The axis must span at least this much of full range between its brightest and darkest
# knot. Measured under the study's fixed exposure (A7, f/4.0): daylight sits near 0.53 of
# range and darkness near 0.04, so the true span is ~0.49. A tenth of that is already
# unambiguous evidence that the sun was not moving.
MIN_AXIS_SPAN = 0.05

# How far a single step may run BACKWARDS, as a fraction of the axis span. The renderer's
# own two inversions measure 4.5% and 5.9% (F6); a knot rendered one illumination away
# from its label displaces by a large fraction of the span -- rendering the +0.779 deg
# knot in daylight would show as 90%. 12% sits between them with headroom on both sides.
MAX_INVERSION_FRAC = 0.12

# ... and how much backwards movement the whole axis may accumulate. The measured axis
# totals 10.3%; a scrambled one approaches 100%, because every downward step it gets
# wrong it must climb back.
MAX_TOTAL_RISE_FRAC = 0.25


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


def check_axis(records: list[dict], lamp_threshold: float = LAMP_THRESHOLD_DEG,
               uncovered: list[dict] | None = None) -> dict:
    """Check a whole illumination axis for the failures a per-knot label cannot show.

    `records` is [{"sun_altitude_deg": float, "signature": {...}}, ...] in any order.
    `uncovered` is the knot measurement's own list of sub-intervals the disturbance family
    cannot represent; an inversion across one of those is recorded but not a failure.
    Returns a report; `assert_axis` raises on it.
    """
    rows = sorted(records, key=lambda r: -float(r["sun_altitude_deg"]))
    means = [r["signature"]["mean"] for r in rows]
    alts = [float(r["sun_altitude_deg"]) for r in rows]
    unc = uncovered or []

    span = (max(means) - min(means)) if means else 0.0

    def _declared(a0, a1):
        """Does this step cross a sub-interval the family declares uncovered?

        OVERLAP, not equality. For a capture campaign the step IS the sub-interval, but
        the closed-loop drivers step between sub-interval MIDPOINTS, so the step that
        crosses the horizon discontinuity is a wider one that contains it.
        """
        lo, hi = min(a0, a1), max(a0, a1)
        return any(min(u["from_deg"], u["to_deg"]) <= hi
                   and max(u["from_deg"], u["to_deg"]) >= lo
                   for u in unc)

    inversions, violations, total_rise = [], [], 0.0
    for (a0, m0), (a1, m1) in zip(zip(alts, means), zip(alts[1:], means[1:])):
        # Crossing the headlamp switch is a legitimate step change in the curve, so the
        # pair that straddles it is not compared. Checking across it would fail on a
        # correct capture.
        if (a0 < lamp_threshold) != (a1 < lamp_threshold):
            continue
        rise = m1 - m0
        if rise <= 1e-9:
            continue
        frac = rise / span if span > 0 else 1.0
        total_rise += rise
        entry = {
            "from_deg": a0, "to_deg": a1, "from_mean": m0, "to_mean": m1,
            "rise": round(rise, 5), "frac_of_span": round(frac, 4),
            "declared_uncovered": _declared(a0, a1),
            "detail": (f"sun fell {a0:.3f} -> {a1:.3f} deg and the frame got BRIGHTER, "
                       f"{m0:.4f} -> {m1:.4f} ({100 * frac:.1f}% of the axis span)"),
        }
        inversions.append(entry)
        if frac > MAX_INVERSION_FRAC and not entry["declared_uncovered"]:
            violations.append(entry)

    total_frac = (total_rise / span) if span > 0 else 1.0
    # Backwards movement across a sub-interval the family already declares uncovered is
    # the renderer's measured discontinuity, not evidence about the capture.
    charged_rise = sum(i["rise"] for i in inversions if not i["declared_uncovered"])
    charged_frac = (charged_rise / span) if span > 0 else 1.0

    brightest_at = alts[means.index(max(means))]
    darkest_at = alts[means.index(min(means))]
    mid_alt = (max(alts) + min(alts)) / 2.0
    extremes_ok = brightest_at >= mid_alt and darkest_at <= mid_alt

    return {
        "knots": len(rows),
        "axis_span_mean": round(span, 5),
        "min_axis_span": MIN_AXIS_SPAN,
        "span_ok": span >= MIN_AXIS_SPAN,
        "inversions": inversions,
        "worst_inversion_frac": round(
            max((i["frac_of_span"] for i in inversions
                 if not i["declared_uncovered"]), default=0.0), 4),
        "max_inversion_frac": MAX_INVERSION_FRAC,
        "total_rise_frac": round(charged_frac, 4),
        "max_total_rise_frac": MAX_TOTAL_RISE_FRAC,
        "monotone_violations": violations,
        "monotone_ok": not violations and charged_frac <= MAX_TOTAL_RISE_FRAC,
        "brightest_at_deg": brightest_at,
        "darkest_at_deg": darkest_at,
        "extremes_ok": extremes_ok,
        "lamp_threshold_deg": lamp_threshold,
        "means_by_altitude": [
            {"sun_altitude_deg": a, "mean": m, "lamps": a < lamp_threshold}
            for a, m in zip(alts, means)
        ],
        "ok": bool(span >= MIN_AXIS_SPAN and not violations
                   and charged_frac <= MAX_TOTAL_RISE_FRAC and extremes_ok),
    }


def assert_axis(records: list[dict], lamp_threshold: float = LAMP_THRESHOLD_DEG,
                uncovered: list[dict] | None = None) -> dict:
    """Raise unless the rendered axis is physically consistent with the axis requested."""
    rep = check_axis(records, lamp_threshold, uncovered)
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
        lines.append("  " + v["detail"] +
                     f"  [limit {100 * MAX_INVERSION_FRAC:.0f}%]")
    if rep["total_rise_frac"] > MAX_TOTAL_RISE_FRAC:
        lines.append(
            f"  the axis runs backwards by {100 * rep['total_rise_frac']:.1f}% of its "
            f"own span in total, limit {100 * MAX_TOTAL_RISE_FRAC:.0f}%. That is a "
            f"scrambled axis, not a renderer wobble.")
    if not rep["extremes_ok"]:
        lines.append(
            f"  the brightest frame is at {rep['brightest_at_deg']:+.3f} deg and the "
            f"darkest at {rep['darkest_at_deg']:+.3f} deg, which is the wrong way round.")
    lines.append(
        "  Every frame captured under this axis is mislabelled. This is the failure "
        "that cost the steering study its Town04 captures (T06-F35).")
    raise RuntimeError("\n".join(lines))


def _campaign_records(manifest_path: Path) -> list[dict]:
    entries = json.loads(manifest_path.read_text())
    return [{"sun_altitude_deg": e["knot"], "signature": e["signature"]}
            for e in entries if e.get("signature")]


def _uncovered() -> list[dict]:
    path = OUT / "family_knots.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("uncovered", [])


def cross_campaign(campaigns: dict[str, list[dict]]) -> dict:
    """Compare the campaigns against each other, knot by knot.

    This is the only check here that does not rest on an assumption about the renderer.
    Campaigns that share a pose set render the same places at the same knots and differ
    only by the target in front of the camera, which occupies a small part of the frame.
    So their brightness curves must agree closely, and a knot rendered at the wrong
    illumination in ONE campaign shows up as that campaign disagreeing with its partner at
    that knot and nowhere else.

    A no-target control is expected to sit slightly brighter or darker than its scenario
    at the same knot -- there is a car or a pedestrian missing from the frame -- so the
    tolerance is on the scale of the axis, not on the scale of the difference.

    **Only WITHIN a pose group.** The premise is that the campaigns photograph the same
    places, and across pose groups they do not: the hazard scenarios put their target at
    120 m and the false-activation scenario puts its plate at 200 m, so at the same RANGE
    TO TARGET the ego is eighty metres further down the road. On Town12 that is a
    different stretch with different buildings, and the plate campaigns read 0.268 at +60
    where the hazard campaigns read 0.372 -- a 32% disagreement that is the road, not the
    illumination. Within each pose group the agreement is 0.0004.

    Comparing across groups was the original form and it passed on Town01, where the site
    is uniform enough over eighty metres that it never showed. It is not a tolerance to
    loosen; the comparison was between two different places.
    """
    names = sorted(campaigns)
    # Which campaigns share a pose set. A control replays its base scenario's poses --
    # that is what makes it a control -- so each base and its control are one group.
    groups: dict[str, list[str]] = {}
    for name in names:
        base = {"none": "lead", "none_ped": "ped", "none_plate": "plate"}.get(name, name)
        groups.setdefault(base, []).append(name)
    by_knot: dict[float, dict[str, float]] = {}
    for name in names:
        for r in campaigns[name]:
            by_knot.setdefault(round(float(r["sun_altitude_deg"]), 3), {})[name] = \
                r["signature"]["mean"]
    spans = [max(m.values()) - min(m.values())
             for m in ([{k: v for k, v in
                         ((r["sun_altitude_deg"], r["signature"]["mean"])
                          for r in campaigns[n])} for n in names])]
    span = max(spans) if spans else 1.0

    rows, worst = [], 0.0
    for alt in sorted(by_knot, reverse=True):
        # Worst disagreement WITHIN any pose group, never across them. Merging the groups
        # into one dict and taking its range would silently restore the across-group
        # comparison this exists to remove, so the spread is computed per group and the
        # worst of those is reported.
        per_group = {}
        for base, members in groups.items():
            got = {m: by_knot[alt][m] for m in members if m in by_knot[alt]}
            if len(got) > 1:
                per_group[base] = got
        if not per_group:
            continue
        spreads = {b: max(g.values()) - min(g.values()) for b, g in per_group.items()}
        worst_base = max(spreads, key=spreads.get)
        spread = spreads[worst_base]
        vals = per_group[worst_base]
        frac = spread / span if span > 0 else 1.0
        worst = max(worst, frac)
        rows.append({"sun_altitude_deg": alt, "spread": round(spread, 5),
                     "frac_of_span": round(frac, 4), "worst_pose_group": worst_base,
                     "means": {k: round(v, 5) for k, v in vals.items()},
                     "all_pose_groups": {b: {k: round(v, 5) for k, v in g.items()}
                                         for b, g in per_group.items()}})
    return {"campaigns": names, "axis_span": round(span, 5),
            "worst_disagreement_frac": round(worst, 4), "knots": rows}


def main() -> int:
    """Validate the axis of every capture campaign on disk, and cross-check them."""
    manifests = sorted(CAPTURES.glob("manifest_*.json"))
    if not manifests:
        print(f"no capture manifests in {CAPTURES.relative_to(REPO)} to validate against")
        return 1
    unc = _uncovered()
    bad = 0
    campaigns = {}
    # The upper-beam captures are ONE knot at a different headlamp state. They are not an
    # axis -- the span check would fail on a single point -- and they are not comparable
    # to the low-beam campaigns at the same altitude, because more light is supposed to
    # make a different frame. Held out of both checks and given their own, which is the
    # one that matters for them: upper beam must render BRIGHTER than lower beam at the
    # same altitude, or the lamp state never took.
    hb = [m for m in manifests if m.stem.endswith("_hb")]
    manifests = [m for m in manifests if not m.stem.endswith("_hb")]
    for mpath in manifests:
        name = mpath.stem.replace("manifest_", "")
        records = _campaign_records(mpath)
        if not records:
            print(f"{mpath.name:28s} no signatures recorded -- captured before this "
                  f"guard existed")
            bad += 1
            continue
        campaigns[name] = records
        rep = check_axis(records, uncovered=unc)
        print(f"\n{mpath.name}  ({rep['knots']} knots, span "
              f"{rep['axis_span_mean']:.4f}, worst inversion "
              f"{100 * rep['worst_inversion_frac']:.1f}% of span)")
        print(f"  {'sun deg':>9s} {'mean':>8s} {'sigma':>8s} {'p99':>8s} {'lamps':>6s}")
        for r in sorted(records, key=lambda r: -r["sun_altitude_deg"]):
            s = r["signature"]
            print(f"  {r['sun_altitude_deg']:9.3f} {s['mean']:8.4f} {s['sigma']:8.4f} "
                  f"{s['p99']:8.4f} "
                  f"{'on' if r['sun_altitude_deg'] < LAMP_THRESHOLD_DEG else 'off':>6s}")
        for inv in rep["inversions"]:
            print(f"  recorded: {inv['detail']}"
                  + ("  [declared uncovered]" if inv["declared_uncovered"] else ""))
        if rep["ok"]:
            print("  OK")
        else:
            bad += 1
            for v in rep["monotone_violations"]:
                print(f"  VIOLATION: {v['detail']}")
            if not rep["span_ok"]:
                print(f"  VIOLATION: axis span {rep['axis_span_mean']:.4f} < "
                      f"{MIN_AXIS_SPAN}")
            if not rep["extremes_ok"]:
                print("  VIOLATION: brightest and darkest are the wrong way round")

    if len(campaigns) > 1:
        cc = cross_campaign(campaigns)
        print(f"\ncross-campaign agreement ({', '.join(cc['campaigns'])})")
        print(f"  worst per-knot disagreement: "
              f"{100 * cc['worst_disagreement_frac']:.1f}% of the axis span")
        for r in sorted(cc["knots"], key=lambda r: -r["frac_of_span"])[:3]:
            print(f"    {r['sun_altitude_deg']:+8.3f} deg  spread {r['spread']:.4f}  "
                  f"{', '.join(f'{k}={v:.4f}' for k, v in sorted(r['means'].items()))}")
        if cc["worst_disagreement_frac"] > 0.15:
            print("  VIOLATION: campaigns rendering the same knot disagree by more than "
                  "15% of the axis span. They differ only by the target in front of the "
                  "camera, which cannot do that.")
            bad += 1
        (CAPTURES / "cross_campaign.json").write_text(json.dumps(cc, indent=1) + "\n")
        print(f"  wrote {(CAPTURES / 'cross_campaign.json').relative_to(REPO)}")

    for mpath in hb:
        scen = mpath.stem.replace("manifest_", "").removesuffix("_hb")
        recs = _campaign_records(mpath)
        base = campaigns.get(scen, [])
        print(f"\n{mpath.name}  (upper beam, {len(recs)} knot)")
        for r in recs:
            alt = r["sun_altitude_deg"]
            low = next((b for b in base
                        if abs(b["sun_altitude_deg"] - alt) < 1e-6), None)
            hi_m = r["signature"]["mean"]
            if low is None:
                print(f"  {alt:+8.3f} upper {hi_m:.4f}  (no lower-beam capture to "
                      f"compare against)")
                continue
            lo_m = low["signature"]["mean"]
            ok = hi_m > lo_m
            print(f"  {alt:+8.3f} upper {hi_m:.4f} vs lower {lo_m:.4f}  "
                  f"{'OK, brighter' if ok else 'VIOLATION, not brighter'}")
            if not ok:
                print("  VIOLATION: the upper beam is supposed to put MORE light into "
                      "the same scene. A frame that is not brighter means the lamp "
                      "state never applied -- amendment A4's auto-exposure failure made "
                      "headlamps darken the image and read as perfectly normal.")
                bad += 1

    total = len(manifests) + len(hb)
    print(f"\n  {total - bad} of {total} campaigns consistent")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
