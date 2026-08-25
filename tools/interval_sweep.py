"""How short does the disturbance interval have to be before the blend is honest?

    python tools/interval_sweep.py

PROTOCOL section 4 declares the family as a linear blend between a rendered daylight
frame and a rendered darkness frame, and says the interior must be validated against
rendered intermediate illumination rather than assumed. Measured over the full interval
the blend is wrong by 0.243 of full range at the midpoint, which is not a small error.

The recorded repair is shorter intervals with rendered interior endpoints, composed.
This measures how short: for a range of interval widths in sun altitude, it renders both
endpoints and the true midpoint, and reports how far the blend at the midpoint is from
the render.

Image space only, as in the job of the same name. A small error here is necessary and
not sufficient; the behavioural check waits for a policy.
"""

from __future__ import annotations

import json
import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

DAY_ALT, NIGHT_ALT = 60.0, -30.0
WIDTHS = [90.0, 45.0, 22.5, 11.25, 5.625]
OUT = J.REPO / "results" / "carla"


def main() -> int:
    carla = J.carla_module()
    client, world = J.connect(rendering=True)
    site = J.flattest_site()
    tf, _ = J.site_transform(world, site, along=25.0, need_m=60.0)
    ego = J.spawn_hero(world, tf)
    cam = None
    cache: dict[float, list[int]] = {}

    def render(alt: float) -> list[int]:
        alt = round(alt, 4)
        if alt in cache:
            return cache[alt]
        w = world.get_weather()
        w.sun_altitude_angle = alt
        w.cloudiness = 10.0
        w.precipitation = 0.0
        world.set_weather(w)
        for _ in range(J.WEATHER_SETTLE_TICKS):
            J.grab_frame(world, images)
        img = J.grab_frame(world, images)
        cache[alt] = list(memoryview(img.raw_data))
        return cache[alt]

    try:
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        ego.set_light_state(carla.VehicleLightState(carla.VehicleLightState.LowBeam))

        rows = []
        # Part 2 first: hold the width and move the interval, because the widths above
        # are all centred at 15 deg, so a wide one crosses the horizon and a narrow one
        # does not. Without this, "short intervals are fine" and "do not cross the
        # horizon" are the same measurement.
        for centre in (50.0, 35.0, 20.0, 5.0, -10.0, -25.0):
            width = 11.25
            hi, lo = centre + width / 2.0, centre - width / 2.0
            a, b, mid = render(hi), render(lo), render(centre)
            # All three colour channels per stride; the old stride-40 form
            # sampled blue only (audit F1).
            diffs = []
            for base in range(0, len(a) - 3, 40):
                for c in (0, 1, 2):
                    diffs.append(abs((a[base + c] + b[base + c]) / 2.0 - mid[base + c]))
            mae = sum(diffs) / len(diffs)
            rows.append(
                {
                    "kind": "fixed_width_moving_centre",
                    "width_deg": width,
                    "centre_deg": centre,
                    "crosses_horizon": lo < 0.0 < hi,
                    "mae_0_255": round(mae, 2),
                    "mae_normalised": round(mae / 255.0, 4),
                }
            )
            J.progress(
                f"centre {centre:6.1f} deg, width {width:5.2f}: "
                f"{mae:6.2f} / 255 = {mae / 255.0:.4f}"
                f"{'   (crosses horizon)' if lo < 0.0 < hi else ''}"
            )

        for width in WIDTHS:
            # One representative interval per width, centred in the full range.
            centre = (DAY_ALT + NIGHT_ALT) / 2.0
            hi, lo = centre + width / 2.0, centre - width / 2.0
            a, b, mid = render(hi), render(lo), render(centre)
            n = len(a)
            # All three colour channels per stride (audit F1).
            diffs = []
            for base in range(0, n - 3, 40):
                for c in (0, 1, 2):
                    diffs.append(abs((a[base + c] + b[base + c]) / 2.0 - mid[base + c]))
            mae = sum(diffs) / len(diffs)
            rows.append(
                {
                    "kind": "moving_width_centred_15",
                    "width_deg": width,
                    "endpoints_deg": [hi, lo],
                    "midpoint_deg": centre,
                    "mae_0_255": round(mae, 2),
                    "mae_normalised": round(mae / 255.0, 4),
                }
            )
            J.progress(
                f"width {width:6.2f} deg: blend vs rendered midpoint "
                f"{mae:6.2f} / 255 = {mae / 255.0:.4f}"
            )
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego)

    payload = {
        "verdict": "MEASURED",
        "note": (
            "Image space only. A small error is necessary and not sufficient; the "
            "behavioural check in PROTOCOL section 4 waits for a policy."
        ),
        "full_interval_deg": [DAY_ALT, NIGHT_ALT],
        "sweep": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "interval_sweep.json").write_text(json.dumps(payload, indent=2) + "\n")
    print("\n  wrote results/carla/interval_sweep.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
