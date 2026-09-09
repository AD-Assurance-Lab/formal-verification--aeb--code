"""Why do both policies brake at 300 ft near the horizon? Altitude, or glare?

    python tools/horizon_sweep.py --policy P_cont --scenario lead
    python tools/horizon_sweep.py --policy P_cont --scenario lead --azimuth-ablation

**The observation this explains, or fails to.** Property A is falsified for BOTH policies
in the sub-intervals nearest sun altitude 0, and the witness drives show both of them
braking at 200 to 300 ft there on an empty road (FINDINGS F9). Property S is satisfied --
they brake -- so this is a must-not-brake failure and it is the section 9 sleeper arriving.

Two hypotheses, and they have different consequences for the paper:

  ILLUMINATION  the scene near sunset is genuinely hard: low contrast, long shadows, the
                target poorly separated from the road. Then the result is about
                illumination, generalises to any low-sun scene, and is the study's point.

  GLARE         the sun is in the camera's field of view and the failure is a geometric
                artifact of where it happens to sit relative to the direction of travel at
                this one site. Then the result is about THIS SITE's heading and does not
                generalise, and the paper must say so.

**The ablation separates them.** Sweep sun altitude finely through the horizon band with
nothing in front of the vehicle, recording the policy's commanded deceleration; then
repeat with the sun's AZIMUTH rotated away from the direction of travel, holding altitude
identical. If the effect survives the rotation it follows the altitude and is
illumination. If it disappears, it followed the sun into and out of frame and is glare.

FINDINGS F6 makes glare the prime suspect: scene brightness spikes at exactly 0.000 deg,
and a sky model discontinuity at the horizon is where a sun disc enters the frame.

No policy is driven here. The vehicle is placed at the captured poses and the policy's
output is read, which is cheap, exactly repeatable, and enough -- the question is what the
network does with the frame, not what the vehicle then does.
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import condition_signature as CS  # noqa: E402

OUT = J.REPO / "results" / "carla"
CAPTURES = J.REPO / "results" / "captures"

# Fine through the band the certificates and the drives both single out, coarse outside it
# so the sweep still shows what "normal" looks like.
BAND = [round(a, 3) for a in np.concatenate([
    np.array([30.0, 20.0, 12.0, 8.0]),
    np.arange(6.0, -6.0001, -0.5),
    np.array([-10.0, -20.0, -30.0]),
])]


def sweep(world, site, model, w, h, dev, states, poses, azimuth: float | None,
          lights_threshold: float = 5.0):
    carla = J.carla_module()
    import torch
    from run_policy import preprocess

    spawn_tf, _ = J.site_transform(world, site, along=10.0, need_m=200.0)
    rows = []
    for alt in BAND:
        ego = cam = None
        try:
            ego = J.spawn_hero(world, spawn_tf)
            images: "queue.Queue" = queue.Queue()
            cam = world.spawn_actor(
                J.rgb_camera_bp(world),
                carla.Transform(carla.Location(x=1.5, z=1.6)), attach_to=ego)
            cam.listen(images.put)
            wx = world.get_weather()
            wx.sun_altitude_angle = alt
            wx.cloudiness = 10.0
            wx.precipitation = 0.0
            if azimuth is not None:
                wx.sun_azimuth_angle = azimuth
            world.set_weather(wx)
            ego.set_light_state(carla.VehicleLightState(
                carla.VehicleLightState.LowBeam if alt < lights_threshold
                else carla.VehicleLightState.NONE))
            for _ in range(J.WEATHER_SETTLE_TICKS):
                J.grab_frame(world, images)

            demands, sig = [], None
            for i in poses:
                ego.set_target_velocity(carla.Vector3D(0, 0, 0))
                ego.set_target_angular_velocity(carla.Vector3D(0, 0, 0))
                ego.set_transform(states[i]["tf"])
                for _ in range(J.SETTLE_TICKS):
                    J.grab_frame(world, images)
                img = J.grab_frame(world, images)
                if sig is None:
                    arr = np.frombuffer(img.raw_data, dtype=np.uint8).reshape(
                        (img.height, img.width, 4))[:, :, :3]
                    sig = CS.signature(arr)
                with torch.no_grad():
                    demands.append(float(model(preprocess(img, w, h, dev)).item()))
        finally:
            if cam is not None:
                cam.stop()
            J.despawn(world, cam, ego)

        rows.append({
            "sun_altitude_deg": alt,
            "sun_azimuth_deg": azimuth,
            "max_demand_mps2": round(max(demands), 4),
            "mean_demand_mps2": round(float(np.mean(demands)), 4),
            "signature": sig,
        })
        J.progress(f"  sun {alt:+7.2f} az {azimuth if azimuth is not None else 'default':>7}"
                   f"  max demand {max(demands):7.3f}  mean frame {sig['mean']:.4f}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", default="P_cont")
    ap.add_argument("--scenario", default="lead", choices=["lead", "ped"])
    ap.add_argument("--azimuth-ablation", action="store_true",
                    help="also sweep with the sun rotated 90 and 180 deg in azimuth")
    ap.add_argument("--poses", type=int, default=12,
                    help="poses sampled along the approach, evenly spaced")
    args = ap.parse_args()

    from gpu import require_cuda
    from run_policy import load_policy
    carla = J.carla_module()
    dev = require_cuda()
    model, w, h = load_policy(args.policy, args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    threshold = b["a_max_g_worst"] * 9.81 * 0.5

    # The NO-TARGET poses: the question is why the policy brakes at an empty road, so the
    # road has to be empty. Same poses the property A certificates quantify over.
    raw = json.loads((CAPTURES / f"states_{args.scenario}.json").read_text())
    idx = np.linspace(0, len(raw) - 1, args.poses).astype(int).tolist()
    states = [{"tf": carla.Transform(
        carla.Location(x=s["ego"][0], y=s["ego"][1], z=s["ego"][2]),
        carla.Rotation(pitch=s["ego"][3], yaw=s["ego"][4], roll=s["ego"][5])),
        "range_m": s["range_m"]} for s in raw]

    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)
    default_az = world.get_weather().sun_azimuth_angle

    t0 = time.time()
    arms = {"default": sweep(world, site, model, w, h, dev, states, idx, None)}
    if args.azimuth_ablation:
        for label, delta in (("rot90", 90.0), ("rot180", 180.0)):
            print(f"\n  azimuth ablation: {label}")
            arms[label] = sweep(world, site, model, w, h, dev, states, idx,
                                (default_az + delta) % 360.0)

    def band_peak(rows):
        near = [r for r in rows if -6.0 <= r["sun_altitude_deg"] <= 6.0]
        far = [r for r in rows if r["sun_altitude_deg"] > 12.0]
        return {
            "peak_demand_in_band": round(max(r["max_demand_mps2"] for r in near), 4),
            "peak_at_deg": max(near, key=lambda r: r["max_demand_mps2"])["sun_altitude_deg"],
            "baseline_demand_above_12deg": round(
                max(r["max_demand_mps2"] for r in far), 4),
            "exceeds_threshold": max(r["max_demand_mps2"] for r in near) >= threshold,
        }

    summary = {k: band_peak(v) for k, v in arms.items()}
    verdict = None
    if args.azimuth_ablation:
        d = summary["default"]["peak_demand_in_band"]
        base = summary["default"]["baseline_demand_above_12deg"]
        rotated = max(summary[k]["peak_demand_in_band"] for k in ("rot90", "rot180"))
        # FIRST ask whether there is a horizon effect at all. The first version of this
        # went straight to the azimuth comparison, and on a policy that brakes on an empty
        # road at EVERY illumination it dutifully reported "illumination, not glare" --
        # true, and beside the point, because the demand above +12 deg was 4.13 against an
        # in-band peak of 4.87. Nothing was localised to the horizon to explain.
        if base >= 0.75 * d:
            verdict = (
                f"NOT A HORIZON EFFECT: the demand above +12 deg is {base:.3f} against an "
                f"in-band peak of {d:.3f}, so this policy behaves this way at every "
                f"illumination and the horizon band is not special. If it exceeds the "
                f"decision threshold it is a global must-not-brake failure, not a dusk "
                f"one, and the azimuth question does not arise.")
        elif rotated < 0.5 * d:
            verdict = ("GLARE: the horizon braking follows the sun's azimuth, so it is a "
                       "geometric artifact of this site's heading and does not generalise")
        else:
            verdict = ("ILLUMINATION: the horizon braking survives rotating the sun away "
                       "from the direction of travel, so it follows altitude and is a "
                       "property of low-sun illumination rather than of glare geometry")
        print(f"\n  in-band peak {d:.3f}, above +12 deg {base:.3f}, rotated peak "
              f"{rotated:.3f} m/s^2")
        print(f"  {verdict}")

    payload = {
        "policy": args.policy, "scenario": args.scenario,
        "brake_decision_threshold_mps2": round(threshold, 4),
        "poses_sampled": args.poses,
        "default_sun_azimuth_deg": round(default_az, 3),
        "summary": summary,
        "verdict": verdict,
        "wall_clock_s": round(time.time() - t0, 1),
        "arms": arms,
        "note": ("Placed poses on an EMPTY road, policy output read rather than driven. "
                 "Property A is falsified near the horizon for both policies and both "
                 "brake at 200-300 ft there; this asks whether that follows the sun's "
                 "altitude (illumination, generalises) or its azimuth (glare, does not)."),
    }
    suffix = "" if args.scenario == "lead" else f"_{args.scenario}"
    path = OUT / f"horizon_sweep_{args.policy}{suffix}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
