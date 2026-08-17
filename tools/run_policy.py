"""Drive a trained policy in closed loop and report the pass rate.

    python tools/run_policy.py --policy P_pts --condition daylight
    python tools/run_policy.py --all          # both policies, both endpoints

This is M4's exit criterion: **both policies pass both regulatory endpoints 10/10**. If
`P_pts` cannot pass the regulatory tests it is not the policy a manufacturer would ship,
and the study has no setup, because the whole claim is that a policy which satisfies the
standard is nonetheless unsafe between its test points.

The policy sees the same crop and resolution it was trained on, reads the camera, and
outputs a deceleration demand. Braking latches once commanded, which is what the
closed-form standoff bound in PROTOCOL section 7 assumes.

Pass is no contact AND standoff at least `d_margin`, over at least 10 repetitions,
measured from bounding-box geometry and never from the collision sensor.
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
from train_policies import Student  # noqa: E402

MODELS = J.REPO / "results" / "models"
CONDITIONS = {"daylight": (60.0, "NONE"), "darkness_lowbeam": (-30.0, "LowBeam")}
BRAKE_THRESHOLD = 0.5  # m/s^2 demanded before braking latches


def load_policy(name: str, scenario: str, dev):
    path = MODELS / f"{name}_{scenario}.pt"
    if not path.exists():
        raise SystemExit(f"no trained policy at {path}; run tools/train_policies.py")
    blob = torch.load(path, map_location=dev, weights_only=False)
    w, h = blob["input"]
    model = Student(w, h).to(dev)
    model.load_state_dict(blob["state_dict"])
    model.eval()
    return model, w, h


def preprocess(img, w: int, h: int, dev):
    """Exactly the crop and resize used in training. A mismatch here is silent."""
    arr = np.frombuffer(img.raw_data, dtype=np.uint8).reshape((img.height, img.width, 4))
    band = arr[int(img.height * 0.35):int(img.height * 0.85), :, :3]
    t = torch.from_numpy(band.copy()).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    return torch.nn.functional.interpolate(t, size=(h, w), mode="area").to(dev)


def one_run(world, site, model, w, h, dev, a_max, speed_mph, gap_m=120.0):
    carla = J.carla_module()
    v_target = speed_mph * J.MPH
    ego = lead = cam = None
    try:
        tf_ego, _ = J.site_transform(world, site, along=10.0, need_m=gap_m + 80.0)
        tf_lead, _ = J.site_transform(world, site, along=10.0 + gap_m)
        bp = world.get_blueprint_library().filter("vehicle.audi.tt")[0]
        lead = world.try_spawn_actor(bp, tf_lead)
        if lead is None:
            raise RuntimeError("lead vehicle spawn blocked")
        ego = J.spawn_hero(world, tf_ego)

        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        for _ in range(J.SETTLE_TICKS):
            J.grab_frame(world, images)

        yaw = math.radians(tf_ego.rotation.yaw)
        ego.set_target_velocity(
            carla.Vector3D(x=v_target * math.cos(yaw), y=v_target * math.sin(yaw), z=0.0)
        )
        braking = False
        integral = 0.0
        min_gap_ft = 1e9
        demand_at_brake = None
        for _ in range(1500):
            img = J.grab_frame(world, images)
            with torch.no_grad():
                demand = float(model(preprocess(img, w, h, dev)).item())

            min_gap_ft = min(min_gap_ft, J.separation_ft(ego, lead))
            if not braking and demand >= BRAKE_THRESHOLD:
                braking = True
                demand_at_brake = round(J.separation_ft(ego, lead), 2)
            if braking:
                ego.apply_control(
                    carla.VehicleControl(
                        throttle=0.0, brake=float(min(1.0, max(0.0, demand / a_max)))
                    )
                )
            else:
                err = v_target - J.speed_of(ego)
                integral = max(-20.0, min(20.0, integral + err * J.FIXED_DT))
                cmd = 0.5 * err + 0.5 * integral
                ego.apply_control(
                    carla.VehicleControl(throttle=max(0.0, min(1.0, cmd)))
                )
            if braking and J.speed_of(ego) < 0.1:
                break
            if min_gap_ft < -2.0:
                break
        return {
            "min_gap_ft": round(min_gap_ft, 2),
            "contact": min_gap_ft <= 0.0,
            "standoff_ok": min_gap_ft >= J.D_MARGIN_M * J.FT,
            "braked": braking,
            "brake_range_ft": demand_at_brake,
        }
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego, lead)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", default=None)
    ap.add_argument("--condition", default=None)
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--speed-mph", type=float, default=J.HAZARD_MPH)
    args = ap.parse_args()

    policies = ["P_pts", "P_cont"] if args.all else [args.policy]
    conditions = list(CONDITIONS) if args.all else [args.condition]
    if None in policies or None in conditions:
        raise SystemExit("give --policy and --condition, or --all")

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    b = json.loads((J.REPO / "results" / "carla" / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    client, world = J.connect(rendering=True)
    site = J.flattest_site()

    out = {"scenario": args.scenario, "speed_mph": args.speed_mph, "cells": {}}
    for pol in policies:
        model, w, h = load_policy(pol, args.scenario, dev)
        for cond in conditions:
            alt, lights = CONDITIONS[cond]
            weather = world.get_weather()
            weather.sun_altitude_angle = alt
            weather.cloudiness = 10.0
            weather.precipitation = 0.0
            world.set_weather(weather)
            for _ in range(J.WEATHER_SETTLE_TICKS):
                world.tick()

            runs = [
                one_run(world, site, model, w, h, dev, a_max, args.speed_mph)
                for _ in range(J.REPS)
            ]
            passes = sum(1 for r in runs if not r["contact"] and r["standoff_ok"])
            never = sum(1 for r in runs if not r["braked"])
            J.progress(
                f"{pol} / {cond}: {passes}/{J.REPS} pass"
                f"{f', {never} never braked' if never else ''}"
            )
            out["cells"][f"{pol}|{cond}"] = {
                "passes": passes,
                "of": J.REPS,
                "never_braked": never,
                "min_gap_ft": [r["min_gap_ft"] for r in runs],
                "brake_range_ft": [r["brake_range_ft"] for r in runs],
            }

    out["all_endpoints_pass"] = all(c["passes"] == J.REPS for c in out["cells"].values())
    out["note"] = (
        "M4 needs every cell 10/10. A policy that cannot pass the regulatory endpoints "
        "is not the policy a manufacturer would ship, and without it the study has no "
        "setup: the claim is that a policy which SATISFIES the standard is unsafe "
        "between its test points."
    )
    path = J.REPO / "results" / "carla" / "policy_endpoints.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
