"""M5: the two gates, measured on the POLICY rather than on pixels.

    python tools/gate_behavioural.py --policy P_cont

PROTOCOL sections 4 and 8 both say the check that decides is behavioural. The image
versions were run earlier and are necessary but not sufficient: an analytic fog model
once scored R-squared 0.848 on images while driving a policy 23.8 times harder than the
real condition, which is exactly why "the pixels are close" does not settle anything.

**The capture check.** Does the policy give the same answer on a frame captured by
placing the vehicle at a pose as it does driving through that pose? Verification runs on
placed frames, so if the answer differs, sound bounds on them say nothing about the car.

**The in-between check.** Does the policy respond to a BLENDED frame the way it responds
to a RENDERED frame at the same illumination? This is the one that can invalidate the
family. The certificate quantifies over the interior of each sub-interval, and the
interior is blends, so a policy that reacts differently to a blend is being certified
against a disturbance it never experiences.

Both are reported against the decision threshold, half of braking authority, because a
difference only matters if it can move the brake decision.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
from run_policy import load_policy, preprocess, BRAKE_THRESHOLD_FRACTION  # noqa: E402

CAPTURES = J.REPO / "results" / "captures"
OUT = J.REPO / "results" / "carla"
POSES_NEAR_RREQ = 20


def policy_on_array(model, arr: np.ndarray, w: int, h: int, dev) -> float:
    """Same crop and resize as training, from a stored BGR frame."""
    H = arr.shape[0]
    band = arr[int(H * 0.35):int(H * 0.85)]
    t = torch.from_numpy(np.ascontiguousarray(band)).permute(2, 0, 1)
    t = t.float().unsqueeze(0) / 255.0
    t = torch.nn.functional.interpolate(t, size=(h, w), mode="area").to(dev)
    with torch.no_grad():
        return float(model(t).item())


def capture_gate(world, site, spawn_tf, states, order, model, w, h, dev, threshold,
                 args) -> int:
    """Does the policy answer the same when PLACED at a pose as when driving through it?

    Verification runs on placed frames. If the policy's output there differs from what it
    outputs driving through the same spot, sound bounds on those frames prove nothing
    about the vehicle. The image version measured 0.007 of range; this measures the thing
    that actually decides.
    """
    carla = J.carla_module()
    import queue as _q

    driven = {}
    ego = other = cam = None
    try:
        if args.scenario == "lead":
            bp = world.get_blueprint_library().filter("vehicle.audi.tt")[0]
            first = states[0]["other"]
            other = world.try_spawn_actor(
                bp,
                carla.Transform(
                    carla.Location(x=first[0], y=first[1], z=first[2] + 0.5),
                    carla.Rotation(pitch=first[3], yaw=first[4], roll=first[5]),
                ),
            )
            tf_conflict = None
        else:
            # The ped capture gate drives the ACTUAL scenario (walker released with
            # the A9 timing) and matches poses on conflict-point range, because the
            # stored states have the walker mid-crossing at each pose.
            import scenarios as S
            from run_policy import A9_HEAD_START_M
            b = json.loads((OUT / "braking.json").read_text())
            rr = J.r_req_m(J.HAZARD_MPH * J.MPH, b["a_max_g_worst"],
                           b["t_lat_s_worst"] or 0.2)
            tf_conflict, wp_target = J.site_transform(world, site, along=10.0 + 120.0)
            other, _direction = S.spawn_crossing_pedestrian(world, wp_target)
            _pctrl = J.carla_module().WalkerControl()
            _pctrl.direction = J.carla_module().Vector3D(
                x=_direction[0], y=_direction[1], z=0.0)
            _released = False
            _cross = None  # filled after ego spawn
        ego = J.spawn_hero(world, spawn_tf)
        if args.scenario == "ped":
            _cross_m = max(0.0, 6.0 - ego.bounding_box.extent.y)
            _ramp_s = 1.5 / S.WALKER_ACCEL_MPS2
            _walk_s = _ramp_s + max(0.0, _cross_m - S.walker_lead_distance(1.5)) / 1.5
            _lead_m = rr + A9_HEAD_START_M
        images: "_q.Queue" = _q.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        wx = world.get_weather()
        wx.sun_altitude_angle = 60.0
        wx.cloudiness = 10.0
        world.set_weather(wx)
        ego.set_light_state(carla.VehicleLightState(carla.VehicleLightState.NONE))
        for _ in range(J.WEATHER_SETTLE_TICKS):
            J.grab_frame(world, images)

        target_v = args.speed_mph * J.MPH if hasattr(args, "speed_mph") else J.HAZARD_MPH * J.MPH
        yaw = math.radians(spawn_tf.rotation.yaw)
        ego.set_target_velocity(
            carla.Vector3D(x=target_v * math.cos(yaw), y=target_v * math.sin(yaw), z=0.0)
        )
        want = {int(i): states[int(i)]["range_m"] for i in order}
        integral = 0.0
        for _ in range(1500):
            img = J.grab_frame(world, images)
            if args.scenario == "lead":
                gap = J.separation_ft(ego, other) / J.FT
            else:
                loc = ego.get_transform().location
                to_conflict = math.hypot(tf_conflict.location.x - loc.x,
                                         tf_conflict.location.y - loc.y)
                gap = to_conflict - ego.bounding_box.extent.x
                if not _released and (to_conflict - _lead_m) / max(
                        J.speed_of(ego), 0.1) <= _walk_s:
                    _pctrl.speed = 1.5
                    other.apply_control(_pctrl)
                    _released = True
            for i, r in list(want.items()):
                if abs(gap - r) < 0.30 and i not in driven:
                    a = np.frombuffer(img.raw_data, dtype=np.uint8)
                    a = a.reshape((img.height, img.width, 4))[:, :, :3]
                    driven[i] = policy_on_array(model, a.copy(), w, h, dev)
            err = target_v - J.speed_of(ego)
            integral = max(-20.0, min(20.0, integral + err * J.FIXED_DT))
            cmd = 0.5 * err + 0.5 * integral
            ego.apply_control(carla.VehicleControl(throttle=max(0.0, min(1.0, cmd))))
            if gap < 3.0:
                break
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego, other)

    stored = CAPTURES / f"{args.scenario}_sun+60.000.npz"
    imgs = np.load(stored)["images"]
    diffs = []
    for i, d_driven in driven.items():
        d_placed = policy_on_array(model, imgs[i], w, h, dev)
        diffs.append(abs(d_driven - d_placed))
    if not diffs:
        print("no matched poses; the driven run never came within tolerance")
        return 1
    worst = max(diffs)
    payload = {
        "policy": args.policy,
        "gate": "capture",
        "poses_matched": len(diffs),
        "decision_threshold_mps2": round(threshold, 3),
        "max_abs_diff_mps2": round(float(worst), 4),
        "mean_abs_diff_mps2": round(float(np.mean(diffs)), 4),
        "as_fraction_of_threshold": round(float(worst) / threshold, 4),
        "verdict": "PASS" if worst / threshold < 1.0 else "FAIL",
        "note": (
            "Policy output on a PLACED frame against the same policy driving through "
            "the same spot. Verification runs on placed frames, so a large difference "
            "here means sound bounds on them say nothing about the vehicle."
        ),
    }
    _sfx = "" if args.scenario == "lead" else f"_{args.scenario}"
    (OUT / f"gate_capture_{args.policy}{_sfx}.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print(
        f"\n  capture gate: {len(diffs)} poses, worst {worst:.3f} m/s^2 = "
        f"{worst / threshold:.3f} of the decision threshold -> {payload['verdict']}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", default="P_cont")
    ap.add_argument("--scenario", default="lead")
    ap.add_argument(
        "--gate", choices=["inbetween", "capture"], default="inbetween",
        help="which of the two M5 gates to run",
    )
    args = ap.parse_args()
    if args.scenario not in ("lead", "ped"):
        raise SystemExit(f"scenario {args.scenario!r}: no gate harness")


    carla = J.carla_module()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model, w, h = load_policy(args.policy, args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    threshold = a_max * BRAKE_THRESHOLD_FRACTION
    rr = J.r_req_m(J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2)
    _kf = "family_knots.json" if args.scenario == "lead" else "family_knots_rgb.json"
    knots = json.loads((OUT / _kf).read_text())["knots_sun_altitude_deg"]

    states = json.loads((CAPTURES / f"states_{args.scenario}.json").read_text())
    ranges = np.array([s["range_m"] for s in states])
    # The poses that decide the outcome are the ones around r_req.
    order = np.argsort(np.abs(ranges - rr))[:POSES_NEAR_RREQ]
    order = np.sort(order)

    client, world = J.connect(rendering=True)
    site = J.flattest_site()
    spawn_tf, _ = J.site_transform(world, site, along=10.0, need_m=200.0)

    def render_at(alt: float, idxs) -> dict[int, np.ndarray]:
        """Render the chosen poses at one sun altitude."""
        ego = J.spawn_hero(world, spawn_tf)
        other = None
        cam = None
        frames = {}
        try:
            bp = world.get_blueprint_library().filter(
                "vehicle.audi.tt" if args.scenario == "lead" else "walker.pedestrian.*"
            )[0]
            first = states[0]["other"]
            other = world.try_spawn_actor(
                bp,
                carla.Transform(
                    carla.Location(x=first[0], y=first[1], z=first[2] + 0.5),
                    carla.Rotation(pitch=first[3], yaw=first[4], roll=first[5]),
                ),
            )
            images: "queue.Queue" = queue.Queue()
            cam = world.spawn_actor(
                J.rgb_camera_bp(world),
                carla.Transform(carla.Location(x=1.5, z=1.6)),
                attach_to=ego,
            )
            cam.listen(images.put)
            wx = world.get_weather()
            wx.sun_altitude_angle = alt
            wx.cloudiness = 10.0
            wx.precipitation = 0.0
            world.set_weather(wx)
            ego.set_light_state(
                carla.VehicleLightState(
                    carla.VehicleLightState.LowBeam
                    if alt < 5.0
                    else carla.VehicleLightState.NONE
                )
            )
            for _ in range(J.WEATHER_SETTLE_TICKS):
                J.grab_frame(world, images)

            def tf(v):
                return carla.Transform(
                    carla.Location(x=v[0], y=v[1], z=v[2]),
                    carla.Rotation(pitch=v[3], yaw=v[4], roll=v[5]),
                )

            for i in idxs:
                ego.set_target_velocity(carla.Vector3D(0, 0, 0))
                ego.set_target_angular_velocity(carla.Vector3D(0, 0, 0))
                ego.set_transform(tf(states[i]["ego"]))
                other.set_transform(tf(states[i]["other"]))
                for _ in range(J.SETTLE_TICKS):
                    J.grab_frame(world, images)
                img = J.grab_frame(world, images)
                a = np.frombuffer(img.raw_data, dtype=np.uint8)
                frames[int(i)] = a.reshape((img.height, img.width, 4))[:, :, :3].copy()
        finally:
            if cam is not None:
                cam.stop()
            J.despawn(world, cam, ego, other)
        return frames

    if args.gate == "capture":
        return capture_gate(world, site, spawn_tf, states, order, model, w, h, dev,
                            threshold, args)

    # ---- in-between check, per sub-interval -------------------------------------
    stored = {
        round(float(np.load(p)["sun_altitude_deg"]), 3): p
        for p in CAPTURES.glob(f"{args.scenario}_sun*.npz")
    }
    rows = []
    for lo, hi in zip(knots[1:], knots[:-1]):  # knots run high to low
        mid = (lo + hi) / 2.0
        J.progress(f"sub-interval {hi:+.3f} to {lo:+.3f}, midpoint {mid:+.3f}")
        rendered = render_at(mid, order)
        a_img = np.load(stored[round(hi, 3)])["images"]
        b_img = np.load(stored[round(lo, 3)])["images"]
        diffs = []
        for i in order:
            blend = (a_img[i].astype(np.float32) + b_img[i].astype(np.float32)) / 2.0
            d_blend = policy_on_array(model, blend.astype(np.uint8), w, h, dev)
            d_rend = policy_on_array(model, rendered[int(i)], w, h, dev)
            diffs.append(abs(d_blend - d_rend))
        rows.append(
            {
                "from_deg": hi,
                "to_deg": lo,
                "midpoint_deg": round(mid, 3),
                "max_abs_diff_mps2": round(float(max(diffs)), 4),
                "mean_abs_diff_mps2": round(float(np.mean(diffs)), 4),
                "as_fraction_of_threshold": round(float(max(diffs)) / threshold, 4),
            }
        )
        J.progress(
            f"  max policy difference {max(diffs):.3f} m/s^2 "
            f"= {max(diffs) / threshold:.2f} of the decision threshold"
        )

    worst = max(r["as_fraction_of_threshold"] for r in rows)
    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "decision_threshold_mps2": round(threshold, 3),
        "poses_used": len(order),
        "verdict": "PASS" if worst < 1.0 else "FAIL",
        "worst_as_fraction_of_threshold": worst,
        "sub_intervals": rows,
        "note": (
            "A blend differs from a render by this much in POLICY OUTPUT. Expressed "
            "against the decision threshold because a difference only matters if it can "
            "move the brake decision. At or above 1.0 the family's interior can flip an "
            "outcome the certificate quantifies over, and the interval is not usable as "
            "declared."
        ),
    }
    _sfx = "" if args.scenario == "lead" else f"_{args.scenario}"
    (OUT / f"gate_inbetween_{args.policy}{_sfx}.json").write_text(
        json.dumps(payload, indent=2) + "\n"
    )
    print(f"\n  worst {worst:.3f} of the decision threshold -> {payload['verdict']}")
    print(f"  wrote results/carla/gate_inbetween_{args.policy}{_sfx}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
