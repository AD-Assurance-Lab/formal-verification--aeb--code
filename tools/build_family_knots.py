"""Where to cut the illumination axis, measured rather than guessed.

    python tools/build_family_knots.py [--tol 0.01]

Amendment A5 established that the linear blend in PROTOCOL section 4 is only faithful
over sub-intervals, and that the limit is curvature near the horizon rather than width.
This turns that into the actual knot points: the largest steps whose midpoint blend stays
within tolerance of the render, walking from daylight down to darkness.

A knot is forced at sun altitude 0. Straddling intervals floor near 0.03 error however
short they are, which is a kink rather than curvature, and no step size fixes a kink.

Image space, like everything else about the family so far. The behavioural check that
decides is in PROTOCOL section 4 and waits for a policy. What this gives is the set of
endpoints to render for training and verification, so that work is not done twice.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

DAY_ALT, NIGHT_ALT = 60.0, -30.0
HORIZON = 0.0
MIN_STEP = 0.5
MAX_STEP = 60.0


def failing_sub_intervals() -> list[dict]:
    """Covered sub-intervals where the BEHAVIOURAL in-between gate failed.

    PROTOCOL section 4: the check that decides is behavioural, not the image metric this
    file bisects on. A sub-interval can sit comfortably inside the image tolerance and
    still move a policy's brake decision, and when it does, section 4's repair is
    "shorter intervals with rendered interior endpoints ... the claim survives; only the
    interval length changes". That is what --refine does.

    Read from every gate artifact, because the knot set is shared: a sub-interval that
    fails for ONE policy is split for all of them, or the two policies are certified over
    different axes and cease to be comparable.
    """
    from capture_campaign import load_uncovered
    unc = load_uncovered()

    def covered(r):
        return not any(abs(u["from_deg"] - r["from_deg"]) < 1e-6
                       and abs(u["to_deg"] - r["to_deg"]) < 1e-6 for u in unc)

    out: dict[tuple, dict] = {}
    for path in sorted((J.REPO / "results" / "carla").glob("gate_inbetween_*.json")):
        d = json.loads(path.read_text())
        # Derived from the per-sub-interval rows rather than read from a summary field.
        # The field is newer than some artifacts, and a gate run that predates it would
        # otherwise look like a gate that passed -- which is the failure mode this study
        # keeps writing down.
        failing = [r for r in d["sub_intervals"]
                   if r["as_fraction_of_threshold"] >= 1.0 and covered(r)]
        for r in failing:
            key = (round(r["from_deg"], 6), round(r["to_deg"], 6))
            prev = out.get(key)
            if prev is None or r["as_fraction_of_threshold"] > prev["worst"]:
                out[key] = {"from_deg": r["from_deg"], "to_deg": r["to_deg"],
                            "worst": r["as_fraction_of_threshold"],
                            "policy": d["policy"], "scenario": d.get("scenario", "lead")}
    return sorted(out.values(), key=lambda r: -r["from_deg"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tol", type=float, default=0.01, help="normalised blend error")
    ap.add_argument(
        "--refine", action="store_true",
        help="do not re-bisect. Split the sub-intervals the BEHAVIOURAL in-between gate "
             "failed, at their midpoints, and re-measure the halves. PROTOCOL section 4's "
             "repair, applied to the sub-intervals that actually need it")
    args = ap.parse_args()

    carla = J.carla_module()
    client, world = J.connect(rendering=True)
    site = J.flattest_site()
    tf, _ = J.site_transform(world, site, along=25.0, need_m=60.0)
    ego = J.spawn_hero(world, tf)
    cam = None
    cache: dict[float, list[int]] = {}
    renders = 0

    try:
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        ego.set_light_state(carla.VehicleLightState(carla.VehicleLightState.LowBeam))

        def render(alt: float) -> list[int]:
            nonlocal renders
            alt = round(alt, 3)
            if alt not in cache:
                w = world.get_weather()
                w.sun_altitude_angle = alt
                w.cloudiness = J.CLOUDINESS
                w.precipitation = 0.0
                world.set_weather(w)
                for _ in range(J.WEATHER_SETTLE_TICKS):
                    J.grab_frame(world, images)
                cache[alt] = list(memoryview(J.grab_frame(world, images).raw_data))
                renders += 1
            return cache[alt]

        def blend_error(hi: float, lo: float) -> float:
            a, b, m = render(hi), render(lo), render((hi + lo) / 2.0)
            # BGRA buffer: sample all three colour channels per stride. The old
            # form strided by 40 (divisible by 4) with a dead alpha guard, so it
            # measured the BLUE channel only -- dusk sky is chromatic exactly
            # where the axis is cut (audit F1; knots need re-measuring under this).
            diffs = [
                abs((a[base + c] + b[base + c]) / 2.0 - m[base + c])
                for base in range(0, len(a) - 3, 40)
                for c in (0, 1, 2)
            ]
            return sum(diffs) / len(diffs) / 255.0

        if args.refine:
            failing = failing_sub_intervals()
            if not failing:
                print("\n  no covered sub-interval failed the behavioural gate; "
                      "nothing to refine")
                return 0
            prev = json.loads(
                (J.REPO / "results" / "carla" / "family_knots.json").read_text())
            knots = list(prev["knots_sun_altitude_deg"])
            detail = list(prev["sub_interval_detail"])
            splits = []
            for f in failing:
                mid = round((f["from_deg"] + f["to_deg"]) / 2.0, 3)
                if any(abs(k - mid) < 1e-6 for k in knots):
                    continue
                J.progress(
                    f"splitting {f['from_deg']:+.3f} -> {f['to_deg']:+.3f} at {mid:+.3f} "
                    f"({f['policy']}/{f['scenario']} gate failed at "
                    f"{f['worst']:.3f} of the decision threshold)")
                e_hi = blend_error(f["from_deg"], mid)
                e_lo = blend_error(mid, f["to_deg"])
                J.progress(f"    halves blend at {e_hi:.4f} and {e_lo:.4f} "
                           f"(tolerance {args.tol})")
                knots.append(mid)
                knots = sorted(set(knots), reverse=True)
                detail = [d for d in detail
                          if not (abs(d["from_deg"] - f["from_deg"]) < 1e-6
                                  and abs(d["to_deg"] - f["to_deg"]) < 1e-6)]
                for a, b, e in ((f["from_deg"], mid, e_hi), (mid, f["to_deg"], e_lo)):
                    detail.append({
                        "from_deg": round(a, 3), "to_deg": round(b, 3),
                        "step_deg": round(a - b, 3), "blend_error": round(e, 4),
                        "covered": bool(e <= args.tol),
                        "split_from": [f["from_deg"], f["to_deg"]],
                        "split_because": (
                            f"{f['policy']}/{f['scenario']} in-between gate failed at "
                            f"{f['worst']:.3f} of the decision threshold"),
                    })
                splits.append({**f, "midpoint_deg": mid,
                               "blend_error_upper": round(e_hi, 4),
                               "blend_error_lower": round(e_lo, 4)})
            detail.sort(key=lambda d: -d["from_deg"])
            payload = {
                "verdict": "MEASURED",
                "blend_metric": "rgb_three_channel",
                "tolerance": args.tol,
                "knots_sun_altitude_deg": knots,
                "sub_intervals": len(knots) - 1,
                "sub_interval_detail": detail,
                "uncovered": [d for d in detail if not d["covered"]],
                "refined_from": prev.get("knots_sun_altitude_deg"),
                "refinements": splits,
                "renders_used": renders,
                "note": (
                    "Refined from a previous knot set by PROTOCOL section 4's repair: a "
                    "sub-interval whose BEHAVIOURAL in-between gate failed is split at "
                    "its midpoint, which becomes a rendered endpoint. The image blend "
                    "metric had already accepted it; the behavioural check is the one "
                    "that decides. Capture the new knot before re-gating."),
            }
            (J.REPO / "results" / "carla" / "family_knots.json").write_text(
                json.dumps(payload, indent=2) + "\n")
            print(f"\n  {len(splits)} sub-interval(s) split, now "
                  f"{len(knots) - 1} sub-intervals, {renders} renders")
            print(f"  knots: {knots}")
            print("  wrote results/carla/family_knots.json")
            return 0

        knots = [DAY_ALT]
        detail = []
        cur = DAY_ALT
        while cur > NIGHT_ALT:
            floor_at = HORIZON if cur > HORIZON else NIGHT_ALT
            # Largest acceptable step, by bisection, never stepping past the next knot.
            lo_step, hi_step = MIN_STEP, min(MAX_STEP, cur - floor_at)
            if hi_step <= MIN_STEP:
                nxt = floor_at
            else:
                best = None
                for _ in range(6):
                    mid_step = (lo_step + hi_step) / 2.0
                    if blend_error(cur, cur - mid_step) <= args.tol:
                        best = mid_step
                        lo_step = mid_step
                    else:
                        hi_step = mid_step
                nxt = cur - (best if best else MIN_STEP)
                if nxt < floor_at:
                    nxt = floor_at
            err = blend_error(cur, nxt)
            J.progress(
                f"knot {cur:7.2f} -> {nxt:7.2f}  step {cur - nxt:6.2f} deg  "
                f"error {err:.4f}"
            )
            # EACH SUB-INTERVAL DECLARES ITS OWN COVERAGE. A6 found one step at the
            # horizon that cannot meet tolerance at any width, and downstream tools were
            # deciding which step that was from a hard-coded altitude band (verify.py:
            # `hi_alt <= 0.37 and lo_alt >= -0.001`) copied from the measurement current
            # at the time. The band moved when the knots were re-measured -- 0.143 in the
            # first campaign, 0.36 under the corrected three-channel metric, 0.026 on the
            # rebuilt harness -- and a constant that no longer matches the knot file does
            # not fail, it silently reclassifies a sub-interval. Coverage is a property of
            # the measurement, so the measurement records it.
            detail.append({
                "from_deg": round(cur, 3),
                "to_deg": round(nxt, 3),
                "step_deg": round(cur - nxt, 3),
                "blend_error": round(err, 4),
                "covered": bool(err <= args.tol),
            })
            knots.append(round(nxt, 3))
            cur = nxt

        payload = {
            "verdict": "MEASURED",
            # The artifact states which metric produced it, because the study has
            # already been burned by a knot set that did not. Audit F1 found every
            # blend error sampled from the BLUE channel alone (stride 40 over a BGRA
            # buffer), and the file it wrote was indistinguishable from a correct one.
            # Consumers require this field rather than trusting the filename.
            "blend_metric": "rgb_three_channel",
            "tolerance": args.tol,
            "knots_sun_altitude_deg": knots,
            "sub_intervals": len(knots) - 1,
            "sub_interval_detail": detail,
            "uncovered": [d for d in detail if not d["covered"]],
            "renders_used": renders,
            "note": (
                "Endpoints to render for training and verification. A knot is forced at "
                "the horizon because straddling intervals floor near 0.03 error at any "
                "width, which is a kink and not curvature. Image space; the behavioural "
                "check in PROTOCOL section 4 still decides."
            ),
        }
        (J.REPO / "results" / "carla" / "family_knots.json").write_text(
            json.dumps(payload, indent=2) + "\n"
        )
        bad = [d for d in detail if not d["covered"]]
        print(f"\n  {len(knots) - 1} sub-intervals, {renders} renders")
        print(f"  knots: {knots}")
        for d in bad:
            print(f"  UNCOVERED: {d['from_deg']:+.3f} to {d['to_deg']:+.3f} "
                  f"({d['step_deg']:.3f} deg) errs at {d['blend_error']:.4f} against a "
                  f"{args.tol} tolerance -- declared uncovered, never quietly spanned")
        print("  wrote results/carla/family_knots.json")
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
