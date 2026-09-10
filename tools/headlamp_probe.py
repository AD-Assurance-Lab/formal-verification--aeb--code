"""What each headlamp state actually renders, at one pose, in darkness.

    python tools/headlamp_probe.py [--altitude -30.0]

The capture campaign's high-beam variant failed the axis check on Town12: at −30° the
upper-beam frames came out at 0.0095 mean against lower beam's 0.0341, and
`condition_signature` calls that a VIOLATION on the reasoning that the upper beam puts more
light into the same scene, so a frame that is not brighter means the lamp state never
applied. That reasoning caught a real defect once — amendment A4, where auto-exposure made
headlamps darken the image.

But there are two explanations for the same number and the check cannot tell them apart:

  1. the lamp state did not apply, which is A4 again;
  2. the lamp state applied perfectly and **upper beam alone is genuinely dimmer in mean
     image brightness than lower beam alone**, because low beams flood the near road that
     fills most of the frame while high beams throw a narrow bar at the far distance.

`capture_campaign` sets `VehicleLightState.HighBeam` for the upper-beam condition — high
beam ONLY, with no low beam. So explanation 2 is not exotic, it is what the code asks for.

This measures all four states at one pose so the two can be told apart. If NONE is dark,
LowBeam is bright, HighBeam is in between or dimmer, and LowBeam|HighBeam is the brightest
of all, then every lamp state applies and the check's premise is what is wrong. If nothing
moves between the states, the lamp state is not applying and A4 has recurred.

Writes `results/carla/headlamp_probe.json`. Renders only; it drives nothing and decides
nothing.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import condition_signature as CS  # noqa: E402

OUT = J.OUT


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--altitude", type=float, default=-30.0)
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--at-pose", type=int, default=None, metavar="N",
                    help="place the ego at pose N of the capture campaign's own saved "
                         "nominal run instead of an arbitrary spot on the site. Without "
                         "this the probe measures a DIFFERENT scene from the one the "
                         "capture measured, and the first run of it did exactly that: on "
                         "empty road at along=10 m high beam came out 2.16x brighter than "
                         "low beam, which is the opposite of what the captures show at "
                         "their own poses.")
    ap.add_argument("--settle", type=int, default=None, metavar="TICKS",
                    help="ticks to hold the weather before measuring, instead of "
                         "WEATHER_SETTLE_TICKS. The capture campaign reaches the darkness "
                         "knot after sweeping twenty brighter ones, and the high-beam "
                         "campaign captures it cold, so the two arrive at -30 deg with "
                         "very different amounts of simulated night behind them.")
    ap.add_argument("--save-frames", action="store_true",
                    help="write a PNG per lamp state. Look at the data, not only at the "
                         "statistics -- two defects in this study survived every numeric "
                         "check and were obvious in one frame.")
    args = ap.parse_args()
    settle = args.settle if args.settle is not None else J.WEATHER_SETTLE_TICKS

    carla = J.carla_module()
    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)

    weather = world.get_weather()
    weather.sun_altitude_angle = args.altitude
    weather.cloudiness = J.CLOUDINESS
    weather.precipitation = 0.0
    world.set_weather(weather)
    for _ in range(settle):
        world.tick()

    if args.at_pose is None:
        tf, _ = J.site_transform(world, site, along=10.0, need_m=200.0)
        where = "along=10 m, empty road"
    else:
        from capture_campaign import _load_states  # noqa: E402
        base = J.CONTROL_OF.get(args.scenario, args.scenario)
        states = _load_states(J.CAPTURES / f"states_{base}.json")
        st = states[args.at_pose]
        tf = st["ego"]
        where = (f"capture pose {args.at_pose} of {len(states)}, "
                 f"range {st.get('range_m', float('nan')):.2f} m")
    print(f"  measuring at: {where}", flush=True)
    ego = cam = None
    rows = []
    try:
        ego = J.spawn_hero(world, tf)
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(J.rgb_camera_bp(world),
                                carla.Transform(carla.Location(x=1.5, z=1.6)),
                                attach_to=ego)
        cam.listen(images.put)
        states = [
            ("NONE", carla.VehicleLightState.NONE),
            ("LowBeam", carla.VehicleLightState.LowBeam),
            ("HighBeam", carla.VehicleLightState.HighBeam),
            ("LowBeam|HighBeam",
             carla.VehicleLightState(carla.VehicleLightState.LowBeam
                                     | carla.VehicleLightState.HighBeam)),
        ]
        for name, state in states:
            ego.set_light_state(carla.VehicleLightState(state))
            # The lamp state lands on a later tick like every other write, and the frame
            # after it is the first one that can show it. Settle properly rather than
            # reading the frame next to the write.
            for _ in range(J.SETTLE_TICKS):
                J.grab_frame(world, images)
            img = J.grab_frame(world, images)
            arr = np.frombuffer(img.raw_data, dtype=np.uint8).reshape(
                (img.height, img.width, 4))[:, :, :3]
            sig = CS.signature(arr)
            if args.save_frames:
                from PIL import Image
                d = J.REPO / "results" / "frames"; d.mkdir(parents=True, exist_ok=True)
                fn = d / f"headlamp_{J.MAP}_{args.altitude:+.1f}_{name.replace('|','+')}.png"
                Image.fromarray(arr[:, :, ::-1].astype("uint8")).save(fn)
                print(f"    wrote {fn.relative_to(J.REPO)}", flush=True)
            rows.append({"lights": name, **sig})
            print(f"  {name:<18} mean {sig['mean']:.5f}  p99 {sig['p99']:.4f}  "
                  f"frac_dark {sig['frac_dark']:.4f}", flush=True)
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego)

    by = {r["lights"]: r["mean"] for r in rows}
    applied = by["LowBeam"] > by["NONE"] * 1.5      # low beam must do something at all
    both_brightest = by["LowBeam|HighBeam"] >= max(
        by["LowBeam"], by["HighBeam"]) - 1e-6
    verdict = ("LAMPS APPLY; the check's premise is wrong" if applied and both_brightest
               else "LAMPS DO NOT APPLY; A4 has recurred" if not applied
               else "INCONCLUSIVE")
    print(f"\n  {verdict}")
    print(f"  high beam alone against low beam alone: "
          f"{by['HighBeam'] / max(by['LowBeam'], 1e-9):.3f}x")

    _tag = ("" if args.at_pose is None else f"_pose{args.at_pose}") + (
        f"_settle{settle}" if settle != J.WEATHER_SETTLE_TICKS else "")
    path = J.claim_output(OUT / f"headlamp_probe{_tag}.json")
    path.write_text(json.dumps({
        "map": J.MAP, "altitude_deg": args.altitude, "scenario": args.scenario,
        "at_pose": args.at_pose, "where": where, "settle_ticks": settle,
        "cloudiness": J.CLOUDINESS,
        "states": rows,
        "low_beam_applies": bool(applied),
        "both_is_brightest": bool(both_brightest),
        "high_over_low": round(by["HighBeam"] / max(by["LowBeam"], 1e-9), 4),
        "verdict": verdict,
        "note": ("capture_campaign renders the upper-beam condition as HighBeam ALONE, "
                 "with no low beam. Mean image brightness is dominated by the near road "
                 "surface, which low beams flood and high beams do not, so high beam "
                 "alone being dimmer in mean is a geometry result rather than a defect -- "
                 "IF the lamp states apply at all, which is what this measures."),
    }, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
