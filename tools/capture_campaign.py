"""Capture the training and verification frames, paired across the illumination axis.

    python tools/capture_campaign.py --scenario lead --knots all
    python tools/capture_campaign.py --plan          # sizes it without capturing

Two requirements pull in opposite directions and both have to be met.

*Training* wants frames along a realistic approach. *Verification* needs frames at
**exactly** the same state at every illumination level, because the disturbance family
interpolates between them pixel by pixel; a pose that differs by one tick between two
knots is not a pair.

So this does not drive and record. It drives ONCE with rendering off to get the nominal
state sequence, then replays that sequence by PLACING the actors, once per illumination
knot. Placement was measured to reproduce a driven frame to 0.000 m and 0.007 of image
range, so replay is sound here (see results/carla/capture_check.json).

Knots come from `results/carla/family_knots.json`, measured in amendment A6.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import scenarios as S  # noqa: E402

OUT = J.REPO / "results" / "captures"
LEAD_GAP_M = 120.0
PED_GAP_M = 120.0
MIN_RANGE_M = 2.0
MAX_RANGE_M = 60.0
DISK_HEADROOM_GB = 20.0


def load_knots() -> list[float]:
    path = J.REPO / "results" / "carla" / "family_knots.json"
    if not path.exists():
        raise SystemExit("run tools/build_family_knots.py first")
    return json.loads(path.read_text())["knots_sun_altitude_deg"]


def expert_decel(range_m: float, v: float, a_max: float) -> float:
    """Ground-truth braking law. The label, and the same law the oracle uses."""
    reach = max(0.05, range_m - S.FT * 0 - 1.0)  # 1.0 m standoff, PROTOCOL section 3
    return float(min(a_max, max(0.0, v * v / (2.0 * reach))))


def nominal_states(world, site, scenario: str, speed_mph: float, a_max_g: float):
    """Drive once, rendering off, and record the states worth capturing."""
    carla = J.carla_module()
    v_target = speed_mph * J.MPH
    a_max = a_max_g * 9.81
    gap = LEAD_GAP_M if scenario == "lead" else PED_GAP_M

    tf_ego, _ = J.site_transform(world, site, along=10.0, need_m=gap + 80.0)
    tf_target, wp_target = J.site_transform(world, site, along=10.0 + gap)

    ego = target = ped = None
    states = []
    try:
        if scenario == "none":
            target = None
        elif scenario == "lead":
            bp = world.get_blueprint_library().filter("vehicle.audi.tt")[0]
            target = world.try_spawn_actor(bp, tf_target)
            if target is None:
                raise RuntimeError("lead vehicle spawn blocked")
        else:
            ped, direction = S.spawn_crossing_pedestrian(world, wp_target)

        ego = J.spawn_hero(world, tf_ego)
        yaw = math.radians(tf_ego.rotation.yaw)
        ego.set_target_velocity(
            carla.Vector3D(x=v_target * math.cos(yaw), y=v_target * math.sin(yaw), z=0.0)
        )
        ctrl = carla.WalkerControl()
        if ped is not None:
            ctrl.direction = carla.Vector3D(x=direction[0], y=direction[1], z=0.0)
            cross_m = max(0.0, 6.0 - ego.bounding_box.extent.y)
            ramp_s = 1.5 / S.WALKER_ACCEL_MPS2
            walk_s = ramp_s + max(0.0, cross_m - S.walker_lead_distance(1.5)) / 1.5

        released = False
        integral = 0.0
        other = target if target is not None else ped
        # With no target there is nothing to measure range to, so range is taken to the
        # point where the target WOULD be. That keeps the pose sequence identical to the
        # lead capture, which is the whole purpose of this control.
        for _ in range(1500):
            loc = ego.get_transform().location
            to_conflict = math.hypot(
                tf_target.location.x - loc.x, tf_target.location.y - loc.y
            ) - ego.bounding_box.extent.x
            if scenario == "lead":
                # A stationary lead sits ON the ego's line, so the straight-line gap IS
                # the longitudinal range.
                gap_m = J.separation_ft(ego, other) / J.FT
            else:
                # For a CROSSING pedestrian it is not. Straight-line distance to the
                # walker includes their lateral offset, so at "range 10.6 m" the ego was
                # only 8.7 m from the crossing point while the walker was still 6 m off
                # to the side, which is visible in the captured frames. PROTOCOL section
                # 7 says range to the CONFLICT POINT, and that is what this is.
                gap_m = to_conflict
            if ped is not None and not released:
                loc = ego.get_transform().location
                to_conflict = math.hypot(
                    tf_target.location.x - loc.x, tf_target.location.y - loc.y
                )
                if to_conflict / max(J.speed_of(ego), 0.1) <= walk_s:
                    ctrl.speed = 1.5
                    ped.apply_control(ctrl)
                    released = True

            if MIN_RANGE_M <= gap_m <= MAX_RANGE_M:
                states.append(
                    {
                        "range_m": round(gap_m, 4),
                        "ego": ego.get_transform(),
                        "other": (
                            other.get_transform()
                            if other is not None
                            else ego.get_transform()
                        ),
                        "speed_mps": round(J.speed_of(ego), 4),
                        "label_decel_mps2": round(
                            expert_decel(gap_m, J.speed_of(ego), a_max), 4
                        ),
                    }
                )
            if gap_m < MIN_RANGE_M:
                break

            err = v_target - J.speed_of(ego)
            integral = max(-20.0, min(20.0, integral + err * J.FIXED_DT))
            cmd = 0.5 * err + 0.5 * integral
            ego.apply_control(
                carla.VehicleControl(throttle=max(0.0, min(1.0, cmd)))
            )
            world.tick()
    finally:
        J.despawn(world, ego, target, ped)
    return states


def _save_states(path: Path, states) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "range_m": s["range_m"],
                    "speed_mps": s["speed_mps"],
                    "label_decel_mps2": s["label_decel_mps2"],
                    "ego": _tf_to_list(s["ego"]),
                    "other": _tf_to_list(s["other"]),
                }
                for s in states
            ],
            indent=1,
        )
        + "\n"
    )


def _tf_to_list(tf):
    return [
        tf.location.x, tf.location.y, tf.location.z,
        tf.rotation.pitch, tf.rotation.yaw, tf.rotation.roll,
    ]


def _load_states(path: Path):
    carla = J.carla_module()

    def tf(v):
        return carla.Transform(
            carla.Location(x=v[0], y=v[1], z=v[2]),
            carla.Rotation(pitch=v[3], yaw=v[4], roll=v[5]),
        )

    return [
        {**s, "ego": tf(s["ego"]), "other": tf(s["other"])}
        for s in json.loads(path.read_text())
    ]


def capture(scenario: str, knots: list[float], speed_mph: float, dry_run: bool):
    carla = J.carla_module()
    client, world = J.connect(rendering=not dry_run)
    site = J.flattest_site()
    b = json.loads((J.REPO / "results" / "carla" / "braking.json").read_text())

    spawn_tf, _ = J.site_transform(world, site, along=10.0, need_m=LEAD_GAP_M + 80.0)

    # The nominal run is saved and REUSED. It is not bit-identical across process runs:
    # two knots captured in an earlier invocation differed from the rest by 0.7 mm, and
    # while that is far below a pixel at these ranges, the pairing guarantee is the
    # entire reason for replaying rather than driving. Pairing that holds only within
    # one invocation is not a guarantee.
    OUT.mkdir(parents=True, exist_ok=True)
    # The no-target control MUST replay the lead poses, or it is not a control: the
    # whole point is to isolate what the target contributes at an identical pose.
    states_path = OUT / f"states_{'lead' if scenario == 'none' else scenario}.json"
    if states_path.exists():
        states = _load_states(states_path)
        print(f"  reusing the saved nominal run, {len(states)} states")
    elif scenario == "none":
        raise SystemExit(
            "capture --scenario lead first: the no-target control replays its poses"
        )
    else:
        states = nominal_states(world, site, scenario, speed_mph, b["a_max_g_worst"])
        _save_states(states_path, states)
    per_frame_mb = 640 * 480 * 3 / 1e6
    total_gb = len(states) * len(knots) * per_frame_mb / 1000
    print(
        f"\n{scenario}: {len(states)} states x {len(knots)} knots = "
        f"{len(states) * len(knots)} frames, about {total_gb:.2f} GB raw"
    )
    if dry_run:
        return None

    free_gb = __import__("shutil").disk_usage(J.REPO).free / 1e9
    if free_gb - total_gb < DISK_HEADROOM_GB:
        raise SystemExit(
            f"refusing: {free_gb:.0f} GB free, this needs {total_gb:.1f} GB and the "
            f"rule is to leave {DISK_HEADROOM_GB:.0f} GB headroom"
        )

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for knot in knots:
        out_path = OUT / f"{scenario}_sun{knot:+07.3f}.npz"
        if out_path.exists():
            print(f"  {out_path.name} exists, skipping")
            manifest.append({"knot": knot, "file": out_path.name, "skipped": True})
            continue
        t0 = time.time()
        w = world.get_weather()
        w.sun_altitude_angle = knot
        w.cloudiness = 10.0
        w.precipitation = 0.0
        world.set_weather(w)

        # Spawn with clearance, then PLACE. The recorded poses sit at ride height,
        # about z = 0.002, and spawning there collides with the road surface.
        ego = J.spawn_hero(world, spawn_tf)
        other = None
        cam = None
        frames = []
        try:
            if scenario == "none":
                other = None
            else:
                lifted = carla.Transform(
                    carla.Location(
                        x=states[0]["other"].location.x,
                        y=states[0]["other"].location.y,
                        z=states[0]["other"].location.z + 0.5,
                    ),
                    states[0]["other"].rotation,
                )
                bp = world.get_blueprint_library().filter(
                    "vehicle.audi.tt" if scenario == "lead" else "walker.pedestrian.*"
                )[0]
                other = world.try_spawn_actor(bp, lifted)
                if other is None:
                    raise RuntimeError(f"could not place the {scenario} target")
            images: "queue.Queue" = queue.Queue()
            cam = world.spawn_actor(
                J.rgb_camera_bp(world),
                carla.Transform(carla.Location(x=1.5, z=1.6)),
                attach_to=ego,
            )
            cam.listen(images.put)
            ego.set_light_state(
                carla.VehicleLightState(
                    carla.VehicleLightState.LowBeam
                    if knot < 5.0
                    else carla.VehicleLightState.NONE
                )
            )
            for _ in range(J.WEATHER_SETTLE_TICKS):
                J.grab_frame(world, images)

            for st in states:
                ego.set_target_velocity(carla.Vector3D(0, 0, 0))
                ego.set_target_angular_velocity(carla.Vector3D(0, 0, 0))
                ego.set_transform(st["ego"])
                if other is not None:
                    other.set_transform(st["other"])
                for _ in range(J.SETTLE_TICKS):
                    J.grab_frame(world, images)
                img = J.grab_frame(world, images)
                arr = np.frombuffer(img.raw_data, dtype=np.uint8)
                arr = arr.reshape((img.height, img.width, 4))[:, :, :3]
                frames.append(arr.copy())
        finally:
            if cam is not None:
                cam.stop()
            J.despawn(world, cam, ego, other)

        np.savez_compressed(
            out_path,
            images=np.stack(frames),
            range_m=np.array([s["range_m"] for s in states], dtype=np.float32),
            speed_mps=np.array([s["speed_mps"] for s in states], dtype=np.float32),
            label_decel_mps2=np.array(
                [s["label_decel_mps2"] for s in states], dtype=np.float32
            ),
            sun_altitude_deg=np.float32(knot),
        )
        size_mb = out_path.stat().st_size / 1e6
        print(
            f"  sun {knot:+8.3f}: {len(frames)} frames, {size_mb:6.1f} MB, "
            f"{time.time() - t0:5.1f} s",
            flush=True,
        )
        manifest.append(
            {"knot": knot, "file": out_path.name, "frames": len(frames),
             "size_mb": round(size_mb, 1)}
        )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--scenario",
        choices=["lead", "ped", "none"],
        default="lead",
        help="'none' repeats the lead poses with NO target: the control that isolates "
             "what the target contributes to a frame, and the false-activation baseline",
    )
    ap.add_argument("--speed-mph", type=float, default=J.HAZARD_MPH)
    ap.add_argument("--plan", action="store_true", help="size it, capture nothing")
    ap.add_argument("--limit-knots", type=int, default=0, help="0 means all")
    args = ap.parse_args()

    knots = load_knots()
    if args.limit_knots:
        knots = knots[: args.limit_knots]
    manifest = capture(args.scenario, knots, args.speed_mph, args.plan)
    if manifest is not None:
        path = OUT / f"manifest_{args.scenario}.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
