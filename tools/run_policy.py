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
# Latch at HALF of full braking authority, derived rather than picked. The label is a
# step between 0 and a_max, so anything below that is the policy saying "not yet".
# A 0.5 m/s^2 threshold latched on noise at 375 ft.
BRAKE_THRESHOLD_FRACTION = 0.5
# A policy that stops the moment it starts satisfies "no contact with standoff", but it
# has not performed AEB, it has performed a nuisance stop. Anything beyond this multiple
# of r_req counts as premature and fails the cell.
PREMATURE_MULTIPLE = 3.0


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


# A9: extra head start for the walker beyond r_req, a frozen scenario parameter.
# Must equal capture_campaign.PED_LEAD_MARGIN_M; asserted at import in main().
A9_HEAD_START_M = 8.0


def one_run(world, site, model, w, h, dev, a_max, speed_mph, lights, gap_m=120.0,
            scenario="lead", release_r_req_m=None):
    """One closed-loop run. `scenario` is 'lead' (stationary vehicle) or 'ped'
    (crossing pedestrian with the A9-timed release, range to the CONFLICT POINT)."""
    import scenarios as S
    carla = J.carla_module()
    v_target = speed_mph * J.MPH
    ego = lead = cam = None
    try:
        tf_ego, _ = J.site_transform(world, site, along=10.0, need_m=gap_m + 80.0)
        tf_lead, wp_target = J.site_transform(world, site, along=10.0 + gap_m)
        if scenario == "lead":
            bp = world.get_blueprint_library().filter("vehicle.audi.tt")[0]
            lead = world.try_spawn_actor(bp, tf_lead)
            if lead is None:
                raise RuntimeError("lead vehicle spawn blocked")
            ped_ctrl = released = None
        elif scenario == "ped":
            if release_r_req_m is None:
                raise RuntimeError("ped runs need release_r_req_m (A9 release timing)")
            lead, direction = S.spawn_crossing_pedestrian(world, wp_target)
            ped_ctrl = carla.WalkerControl()
            ped_ctrl.direction = carla.Vector3D(x=direction[0], y=direction[1], z=0.0)
            released = False
        else:
            raise RuntimeError(f"scenario {scenario!r} is not drivable")
        ego = J.spawn_hero(world, tf_ego)

        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        # The headlamps MUST match the capture, or the policy is shown a different world
        # from the one it was trained on. Measured: without this, both policies passed
        # daylight 10/10 and failed darkness 0/10 and 2/10, because every night training
        # frame was headlamp-lit and every night test frame was not.
        ego.set_light_state(
            carla.VehicleLightState(getattr(carla.VehicleLightState, lights))
        )
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
        # Release timing, mirrored from capture_campaign.nominal_states so the driven
        # scenario is the one the captures recorded (A9: in the path before r_req).
        if scenario == "ped":
            cross_m = max(0.0, 6.0 - ego.bounding_box.extent.y)
            ramp_s = 1.5 / S.WALKER_ACCEL_MPS2
            walk_s = ramp_s + max(0.0, cross_m - S.walker_lead_distance(1.5)) / 1.5
            lead_m = release_r_req_m + A9_HEAD_START_M
        min_conflict_m = 1e9
        rest_gap_ft = None
        for _ in range(1500):
            img = J.grab_frame(world, images)
            with torch.no_grad():
                demand = float(model(preprocess(img, w, h, dev)).item())

            loc = ego.get_transform().location
            to_conflict = math.hypot(
                tf_lead.location.x - loc.x, tf_lead.location.y - loc.y
            )
            min_conflict_m = min(min_conflict_m, to_conflict)
            if scenario == "ped" and not released:
                if (to_conflict - lead_m) / max(J.speed_of(ego), 0.1) <= walk_s:
                    ped_ctrl.speed = 1.5
                    lead.apply_control(ped_ctrl)
                    released = True

            sep_now = J.separation_ft(ego, lead)
            min_gap_ft = min(min_gap_ft, sep_now)
            # d_margin is "required standoff AT REST" (PROTOCOL section 3; FINDINGS
            # F3): track separation while stopped separately, because a crossing
            # walker keeps moving after the vehicle has done its job.
            if braking and J.speed_of(ego) < 0.1:
                rest_gap_ft = sep_now if rest_gap_ft is None else min(rest_gap_ft, sep_now)
            # brake_range: the lead scenario's separation IS the range; the crossing
            # scenario's range is to the CONFLICT POINT (A7).
            range_now_ft = (J.separation_ft(ego, lead) if scenario == "lead"
                            else (to_conflict - ego.bounding_box.extent.x) * J.FT)
            if not braking and demand >= a_max * BRAKE_THRESHOLD_FRACTION:
                braking = True
                demand_at_brake = round(range_now_ft, 2)
            if braking:
                # FULL braking once latched. The label is a step to a_max and the
                # certificate's property is that the commanded deceleration is at least
                # a_max inside r_req, so applying a fraction of the demand contradicts
                # both. Applying demand/a_max meant a demand of 0.5 produced 6 percent
                # braking and the vehicle coasted into the lead having "braked".
                ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            else:
                err = v_target - J.speed_of(ego)
                integral = max(-20.0, min(20.0, integral + err * J.FIXED_DT))
                cmd = 0.5 * err + 0.5 * integral
                ego.apply_control(
                    carla.VehicleControl(throttle=max(0.0, min(1.0, cmd)))
                )
            if braking and J.speed_of(ego) < 0.1:
                # For the crossing scenario, idle a moment at rest so the resting
                # standoff sees the walker actually cross; the lead target is static
                # and needs no dwell.
                if scenario == "ped":
                    for _ in range(40):
                        img2 = J.grab_frame(world, images)
                        rest_gap_ft = min(rest_gap_ft, J.separation_ft(ego, lead))
                        min_gap_ft = min(min_gap_ft, rest_gap_ft)
                break
            if min_gap_ft < -2.0:
                break
            # A non-braking ped run ends once the ego has blown through the conflict
            # point; there is nothing left to measure.
            if (scenario == "ped" and not braking and min_conflict_m < 3.0
                    and to_conflict > min_conflict_m + 20.0):
                break
        out = {
            "min_gap_ft": round(min_gap_ft, 2),
            "rest_gap_ft": None if rest_gap_ft is None else round(rest_gap_ft, 2),
            "contact": min_gap_ft <= 0.0,
            "standoff_ok": (rest_gap_ft is not None
                            and rest_gap_ft >= J.D_MARGIN_M * J.FT),
            "braked": braking,
            "brake_range_ft": demand_at_brake,
        }
        if scenario == "ped":
            out["released"] = bool(released)
        return out
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

    if args.scenario not in ("lead", "ped"):
        raise SystemExit(f"scenario {args.scenario!r} is not drivable")
    import capture_campaign as CC
    assert A9_HEAD_START_M == CC.PED_LEAD_MARGIN_M, "A9 head start drifted"
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

            r_req_m = J.r_req_m(
                args.speed_mph * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2
            )
            r_req_ft = r_req_m * J.FT
            runs = [
                one_run(world, site, model, w, h, dev, a_max, args.speed_mph, lights,
                        scenario=args.scenario, release_r_req_m=r_req_m)
                for _ in range(J.REPS)
            ]
            for r in runs:
                r["premature"] = (
                    r["brake_range_ft"] is not None
                    and r["brake_range_ft"] > r_req_ft * PREMATURE_MULTIPLE
                )
            passes = sum(
                1 for r in runs
                if not r["contact"] and r["standoff_ok"] and not r["premature"]
            )
            never = sum(1 for r in runs if not r["braked"])
            early = sum(1 for r in runs if r["premature"])
            J.progress(
                f"{pol} / {cond}: {passes}/{J.REPS} pass"
                f"{f', {never} never braked' if never else ''}"
                f"{f', {early} braked prematurely' if early else ''}"
            )
            out["cells"][f"{pol}|{cond}"] = {
                "passes": passes,
                "of": J.REPS,
                "never_braked": never,
                "premature_brakes": early,
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
    suffix = "" if args.scenario == "lead" else f"_{args.scenario}"
    path = J.REPO / "results" / "carla" / f"policy_endpoints{suffix}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
