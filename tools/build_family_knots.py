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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tol", type=float, default=0.01, help="normalised blend error")
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
                w.cloudiness = 10.0
                w.precipitation = 0.0
                world.set_weather(w)
                for _ in range(J.WEATHER_SETTLE_TICKS):
                    J.grab_frame(world, images)
                cache[alt] = list(memoryview(J.grab_frame(world, images).raw_data))
                renders += 1
            return cache[alt]

        def blend_error(hi: float, lo: float) -> float:
            a, b, m = render(hi), render(lo), render((hi + lo) / 2.0)
            diffs = [
                abs((a[k] + b[k]) / 2.0 - m[k])
                for k in range(0, len(a), 40)
                if k % 4 != 3
            ]
            return sum(diffs) / len(diffs) / 255.0

        knots = [DAY_ALT]
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
            knots.append(round(nxt, 3))
            cur = nxt

        payload = {
            "verdict": "MEASURED",
            "tolerance": args.tol,
            "knots_sun_altitude_deg": knots,
            "sub_intervals": len(knots) - 1,
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
        print(f"\n  {len(knots) - 1} sub-intervals, {renders} renders")
        print(f"  knots: {knots}")
        print("  wrote results/carla/family_knots.json")
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
