"""How long the rendered scene takes to stop changing after the sun is moved.

    python tools/lighting_settle.py --altitude 0.403 --ticks 2000 --every 20

One process, one freshly restarted server, one altitude. The vehicle and camera are
spawned once and held still, nothing else is in the world, and the scene's photometric
signature and the policy's deceleration demand are recorded every `--every` ticks. The
output is a convergence curve for a scene in which **nothing is supposed to be changing**.

## Why this exists

`PROTOCOL.md` sets `WEATHER_SETTLE_TICKS = 120`, six seconds of simulated time, on the
reasoning that `world.set_weather()` applies on the next tick and a few frames of margin
covers it. The write does apply on the next tick. What was never measured is how long the
RENDERED CONSEQUENCE of that write takes to settle.

Measured 2026-09-09 while chasing why four ten-repetition cells split. At sun altitude
+0.403° the scene's mean brightness climbs from 0.06194 to about 0.0643, a rise of 3.8%,
over roughly the first fifty seconds of simulated time after the weather is set -- long
after the 120-tick settle has returned. A run that starts at the settle sees a different
scene from a run that starts a minute later, and at this illumination `P_pts3` brakes on
one and not the other, which is a contact against a crossing pedestrian.

That is why ten repetitions inside one process split and ten repetitions on ten fresh
servers did not: the shared-server repetitions sampled different points of this curve,
and the fresh-server repetitions all sampled the same early point of it. Neither harness
was noisy. They were measuring a scene that was still changing.

The 1000-idle-tick control separates the two candidate causes: idling with nothing
spawned reproduces the drift, so it follows elapsed simulated time and not the
spawn/despawn churn of successive runs.

## What the curve is for

The settle is correct when the signature has stopped moving, and "stopped" has to be a
measured threshold rather than a number someone liked. The report gives, per altitude, the
first tick at which the signature stays inside a band for the rest of the sweep -- so
`WEATHER_SETTLE_TICKS` can be set from the measurement instead of from an assumption, and
so a future change of map, camera or quality level can be rechecked rather than trusted.

Run one altitude per process on a fresh server. Two altitudes in one process would have
the second one starting from wherever the first left off, which is the confound this is
here to measure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu import require_cuda  # noqa: E402
import carla_jobs as J  # noqa: E402
import condition_signature as CS  # noqa: E402
from run_policy import load_policy, preprocess  # noqa: E402

OUT = J.REPO / "results" / "carla"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--altitude", type=float, required=True)
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--every", type=int, default=20)
    ap.add_argument("--policy", default="P_pts3")
    ap.add_argument("--scenario", default="ped")
    ap.add_argument("--cloudiness", type=float, default=None,
                    help="defaults to the study's own J.CLOUDINESS, which A15 sets to 0.0 "
                         "because CARLA's cloud layer MOVES under fixed weather (F23). "
                         "Pass a value to sweep it; this tool is how that was measured.")
    ap.add_argument("--band", type=float, default=0.002,
                    help="RELATIVE band, kept for continuity. Misleading on a dark scene: "
                         "0.2%% of a mean of 0.011 is 2.2e-5, finer than the renderer's "
                         "own floor, so a scene that settles perfectly reads as never "
                         "settling. Judge on --band-abs.")
    ap.add_argument("--band-abs", type=float, default=0.0005,
                    help="ABSOLUTE band on the 0-1 image scale, and the one to read. "
                         "0.0005 is about an eighth of a grey level at 8 bits, which is "
                         "below anything the policy resolves and above the render floor. "
                         "A relative band cannot be used across a 15x range of scene "
                         "brightness, which is what the horizon-to-daylight axis is.")
    args = ap.parse_args()
    if args.cloudiness is None:
        args.cloudiness = J.CLOUDINESS

    carla = J.carla_module()
    dev = require_cuda()
    model, w, h = load_policy(args.policy, args.scenario, dev)

    # The map is in the name. The Town01 curves are committed and the Town12 ones are a
    # different measurement of a different road, and a file that overwrote the other would
    # leave the repository holding one curve labelled as both.
    tag = f"{J.MAP}_{args.altitude:+.3f}".replace("+", "p").replace("-", "m").replace(".", "_")
    tag += f"_cloud{args.cloudiness:g}"   # always in the name; the study's value changed
    out_path = J.claim_output(OUT / f"lighting_settle_{tag}.json")

    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)
    weather = world.get_weather()
    weather.sun_altitude_angle = args.altitude
    weather.cloudiness = args.cloudiness
    weather.precipitation = 0.0
    world.set_weather(weather)

    tf_ego, _ = J.site_transform(world, site, along=10.0, need_m=200.0)
    ego = cam = None
    samples = []
    try:
        ego = J.spawn_hero(world, tf_ego)
        ego.set_light_state(carla.VehicleLightState(
            getattr(carla.VehicleLightState,
                    "LowBeam" if args.altitude < 5.0 else "NONE")))
        import queue
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)), attach_to=ego)
        cam.listen(images.put)
        # The vehicle is held on the brake and never moves, so every frame in the sweep
        # is the same geometry under the same manually pinned exposure. Anything that
        # moves in this series is the renderer or the lighting, and nothing else.
        for t in range(args.ticks + 1):
            J.apply_control(ego, carla.VehicleControl(throttle=0.0, brake=1.0))
            img = J.grab_frame(world, images)
            if t % args.every:
                continue
            arr = np.frombuffer(img.raw_data, dtype=np.uint8).reshape(
                (img.height, img.width, 4))[:, :, :3]
            with torch.no_grad():
                demand = float(model(preprocess(img, w, h, dev)).item())
            samples.append({"tick": t, "demand_mps2": round(demand, 6),
                            **{k: v for k, v in CS.signature(arr).items()}})
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego)

    means = [s["mean"] for s in samples]
    final = means[-1]

    def settle_tick(tol: float, relative: bool) -> int:
        """First tick after which every later sample stays inside `tol`.

        Read from the END backwards, so a curve that wanders back out later cannot be
        called settled."""
        for i in range(len(samples) - 1, -1, -1):
            d = abs(means[i] - final)
            if (d / max(final, 1e-9) if relative else d) > tol:
                return samples[min(i + 1, len(samples) - 1)]["tick"]
        return samples[0]["tick"]

    settled_at = settle_tick(args.band_abs, relative=False)
    settled_at_rel = settle_tick(args.band, relative=True)
    # What is left AFTER the settle, which is the number the cloudiness decision turns on.
    # The transient before it is removed by settling longer; this is not.
    post = [m for m, sm in zip(means, samples) if sm["tick"] >= settled_at]
    post_drift = (max(post) - min(post)) if post else 0.0

    demands = [s["demand_mps2"] for s in samples]
    payload = {
        "altitude_deg": args.altitude,
        "cloudiness": args.cloudiness,
        "policy": args.policy, "scenario": args.scenario,
        "ticks": args.ticks, "every": args.every, "band": args.band,
        "settle_ticks_in_protocol": J.WEATHER_SETTLE_TICKS,
        "mean_at_protocol_settle": next(
            (s["mean"] for s in samples if s["tick"] >= J.WEATHER_SETTLE_TICKS), None),
        "mean_final": final,
        "mean_min": min(means), "mean_max": max(means),
        "drift_frac_of_final": round((max(means) - min(means)) / max(final, 1e-9), 5),
        "band_abs": args.band_abs,
        "settled_at_tick": settled_at,
        "settled_at_tick_relative_band": settled_at_rel,
        "post_settle_drift": round(post_drift, 6),
        "settled_within_protocol_settle": settled_at <= J.WEATHER_SETTLE_TICKS,
        "demand_min": round(min(demands), 6), "demand_max": round(max(demands), 6),
        "demand_range": round(max(demands) - min(demands), 6),
        "samples": samples,
        "note": ("Nothing in this scene moves: the vehicle is held on the brake, the "
                 "camera is rigid, the weather is fixed and the exposure is pinned "
                 "manually. Any movement in the signature is the renderer or the "
                 "lighting still converging on the weather that was set before it."),
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  altitude {args.altitude:+.3f}: mean {means[0]:.5f} -> {final:.5f} "
          f"({payload['drift_frac_of_final'] * 100:.2f}% of final), settled at tick "
          f"{settled_at} against a {J.WEATHER_SETTLE_TICKS}-tick settle; demand spans "
          f"{payload['demand_range']:.4f} m/s^2")
    print(f"  wrote {out_path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
