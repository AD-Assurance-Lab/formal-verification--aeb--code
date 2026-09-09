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

from gpu import require_cuda  # noqa: E402
import carla_jobs as J  # noqa: E402
import condition_signature as CS  # noqa: E402
import stats as ST  # noqa: E402
from train_policies import Student  # noqa: E402

MODELS = J.REPO / "results" / "models"
# The three lighting conditions FMVSS 127 tests, as PROTOCOL section 2 records them.
# The first two bound the certified interval; the third is the SAME darkness with a
# different headlamp state, so it is an endpoint TEST and not a point on the family's
# axis. M4 tested only the first two until 2026-09-07, which made "passes the regulatory
# test points" a claim about two thirds of the matrix.
CONDITIONS = {
    "daylight": (60.0, "NONE"),
    "darkness_lowbeam": (-30.0, "LowBeam"),
    "darkness_highbeam": (-30.0, "HighBeam"),
}
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


# FMVSS 127's nuisance braking limit, taken from the standard and not chosen (PROTOCOL
# section 2). Property A certifies the upper bound against it; this is the same number
# applied to what the vehicle actually commanded.
NUISANCE_LIMIT_MPS2 = 0.25 * 9.81


def plate_run(world, site, model, w, h, dev, speed_mph, lights, gap_m=200.0,
              place=True):
    """One false-activation run: approach a trench plate and DO NOT BRAKE.

    `place=False` runs the identical approach with NO PLATE, which is the control that
    makes a plate result attributable to the plate. Without it, a policy that brakes near
    the horizon on any road reads as false activation on steel.

    Every other scenario in this study passes by stopping. This one passes by not
    stopping, which is why it cannot be a flag on `one_run`: there is no contact to avoid,
    no standoff to hold, and the failure is the vehicle deciding to brake for a piece of
    steel lying flat on the road.

    Pass, from PROTOCOL sections 2 and 7:
      - commanded deceleration never exceeds 0.25 g, the standard's own nuisance limit
      - the vehicle crosses the plate still moving

    The policy's output is applied here exactly as it is in the hazard runs -- latched at
    the decision threshold, full authority once latched -- because the question is what
    the closed loop does, not what the network prints.
    """
    import scenarios as S
    carla = J.carla_module()
    v_target = speed_mph * J.MPH
    ego = cam = None
    plate = []
    try:
        tf_ego, _ = J.site_transform(world, site, along=10.0, need_m=gap_m + 120.0)
        tf_plate, wp_plate = J.site_transform(world, site, along=10.0 + gap_m)
        if place:
            plate, plate_info = S.place_trench_plate(world, wp_plate)
            if not plate:
                raise RuntimeError("trench plate placement blocked")
        else:
            # Same geometry, same distances, no steel. `to_plate` below is measured from
            # the placement waypoint either way, so the approach and the range at which
            # a brake would be recorded are identical.
            plate, plate_info = [], {"tiles": 0, "covered_w_ft": 0.0, "covered_l_ft": 0.0}
        ego = J.spawn_hero(world, tf_ego)

        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)), attach_to=ego)
        cam.listen(images.put)
        ego.set_light_state(
            carla.VehicleLightState(getattr(carla.VehicleLightState, lights)))
        for _ in range(J.SETTLE_TICKS):
            J.grab_frame(world, images)
        _sig = J.grab_frame(world, images)
        _arr = np.frombuffer(_sig.raw_data, dtype=np.uint8).reshape(
            (_sig.height, _sig.width, 4))[:, :, :3]
        run_signature = CS.signature(_arr)

        yaw = math.radians(tf_ego.rotation.yaw)
        ego.set_target_velocity(carla.Vector3D(
            x=v_target * math.cos(yaw), y=v_target * math.sin(yaw), z=0.0))

        braking = False
        integral = 0.0
        peak_demand = 0.0
        brake_range_ft = None
        min_speed_mps = 1e9
        crossed = False
        start_dist = None
        for _ in range(2000):
            img = J.grab_frame(world, images)
            with torch.no_grad():
                demand = float(model(preprocess(img, w, h, dev)).item())
            peak_demand = max(peak_demand, demand)

            loc = ego.get_transform().location
            to_plate = math.hypot(tf_plate.location.x - loc.x,
                                  tf_plate.location.y - loc.y)
            if start_dist is None:
                start_dist = to_plate
            if not braking and demand >= a_max_threshold(dev):
                braking = True
                brake_range_ft = round((to_plate - ego.bounding_box.extent.x) * J.FT, 2)
            if braking:
                J.apply_control(ego, carla.VehicleControl(throttle=0.0, brake=1.0))
            else:
                err = v_target - J.speed_of(ego)
                integral = max(-20.0, min(20.0, integral + err * J.FIXED_DT))
                cmd = 0.5 * err + 0.5 * integral
                J.apply_control(ego, carla.VehicleControl(
                    throttle=max(0.0, min(1.0, cmd))))
            # NO SECOND TICK. `J.grab_frame` at the top of this loop already ticks the
            # world and returns the frame that tick produced, so the `world.tick()` that
            # used to sit here made every iteration advance TWO steps -- and grab_frame
            # then silently discarded the intervening frame as stale.
            #
            # PROTOCOL section 3 fixes the control rate at 20 Hz and states the resulting
            # quantization as 3.7 ft at 50 mph. This loop was running at 10 Hz, evaluating
            # the policy on every other frame, with a quantization of 7.3 ft. `one_run`
            # has never had the extra tick, so the two hazard scenarios and the
            # false-activation scenario were not being driven at the same control rate.
            #
            # It is also the best available mechanism for the bimodality in FINDINGS F22:
            # peak_demand is a maximum over the frames the policy actually sees, and a
            # sampler that skips every other frame near a fast-changing demand either
            # catches the peak or misses it, which is what 2.61 against 1.90 m/s^2 with
            # nothing in between looks like. F24.
            if J.speed_of(ego) > 1.0:
                min_speed_mps = min(min_speed_mps, J.speed_of(ego))
            # Crossed when the plate is behind us: the distance starts growing again.
            if to_plate < 5.0:
                crossed = True
            if crossed and to_plate > 25.0:
                break
            if braking and J.speed_of(ego) < 0.1:
                break

        return {
            "signature": run_signature,
            "peak_demand_mps2": round(peak_demand, 4),
            "nuisance_limit_mps2": round(NUISANCE_LIMIT_MPS2, 4),
            "exceeded_nuisance_limit": peak_demand > NUISANCE_LIMIT_MPS2,
            "braked": braking,
            "brake_range_ft": brake_range_ft,
            "crossed_plate": crossed,
            "min_speed_mps_while_moving": (round(min_speed_mps, 3)
                                           if min_speed_mps < 1e8 else None),
            # PASS is not stopping AND not exceeding the standard's own limit.
            "passes": bool(crossed and not braking
                           and peak_demand <= NUISANCE_LIMIT_MPS2),
            "plate_present": place,
            "plate_tiles": plate_info["tiles"],
            "plate_covered_ft": [plate_info["covered_w_ft"], plate_info["covered_l_ft"]],
        }
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego, *plate)


def a_max_threshold(dev=None):
    """The latch threshold the closed loop uses, read from the measured primitive."""
    b = json.loads((J.REPO / "results" / "carla" / "braking.json").read_text())
    return b["a_max_g_worst"] * 9.81 * BRAKE_THRESHOLD_FRACTION


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

        # WHAT THIS RUN ACTUALLY SAW. Every artifact in this study has recorded the sun
        # altitude it ASKED for and nothing has ever recorded what was rendered, which
        # is the failure that cost the sibling steering study a set of verification
        # captures (T06-F35): the axis was swept while the camera belonged to another
        # condition, every run completed, and every number was plausible. Illumination
        # is this study's independent variable, so a drive that silently ran at the
        # wrong one does not produce a wrong number, it produces the headline.
        _sig_img = J.grab_frame(world, images)
        _arr = np.frombuffer(_sig_img.raw_data, dtype=np.uint8).reshape(
            (_sig_img.height, _sig_img.width, 4))[:, :, :3]
        run_signature = CS.signature(_arr)

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
        # The two diagnostics that separate "stopped" from "never started" (F21). The
        # loop's stop condition is `braking and speed < 0.1`, which a run that latches
        # the brake on its FIRST iteration satisfies for the wrong reason: the ego has
        # not moved yet. Recording the step index and the speed at latch makes that
        # visible in the artifact instead of only in a null rest gap.
        step = 0
        brake_step = None
        speed_at_brake = None
        top_speed = 0.0
        for step in range(1500):
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
                    J.apply_control(lead, ped_ctrl)
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
            speed_now = J.speed_of(ego)
            top_speed = max(top_speed, speed_now)
            if not braking and demand >= a_max * BRAKE_THRESHOLD_FRACTION:
                braking = True
                demand_at_brake = round(range_now_ft, 2)
                brake_step = step
                speed_at_brake = speed_now
            if braking:
                # FULL braking once latched. The label is a step to a_max and the
                # certificate's property is that the commanded deceleration is at least
                # a_max inside r_req, so applying a fraction of the demand contradicts
                # both. Applying demand/a_max meant a demand of 0.5 produced 6 percent
                # braking and the vehicle coasted into the lead having "braked".
                J.apply_control(ego, carla.VehicleControl(throttle=0.0, brake=1.0))
            else:
                err = v_target - J.speed_of(ego)
                integral = max(-20.0, min(20.0, integral + err * J.FIXED_DT))
                cmd = 0.5 * err + 0.5 * integral
                J.apply_control(ego, 
                    carla.VehicleControl(throttle=max(0.0, min(1.0, cmd)))
                )
            if braking and J.speed_of(ego) < 0.1:
                # RECORD THE RESTING GAP HERE TOO, not only at the top of the loop.
                # F21: the top-of-loop recorder reads `braking` from a PREVIOUS
                # iteration, so a run that latches the brake and reaches the stop test
                # in the SAME iteration left rest_gap_ft at None and was scored
                # standoff_ok = False -- a vehicle stopped 379 ft short of a stationary
                # lead, recorded as a standoff failure. Three runs in the study hit it,
                # all of them P_pts near the horizon, where the policy brakes so early
                # that it latches on the first iteration, before set_target_velocity has
                # shown up in get_velocity. One of them flipped a cell verdict between
                # two otherwise identical drives.
                if rest_gap_ft is None:
                    rest_gap_ft = sep_now
                else:
                    rest_gap_ft = min(rest_gap_ft, sep_now)
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
            "signature": run_signature,
            "min_gap_ft": round(min_gap_ft, 2),
            "rest_gap_ft": None if rest_gap_ft is None else round(rest_gap_ft, 2),
            "contact": min_gap_ft <= 0.0,
            "standoff_ok": (rest_gap_ft is not None
                            and rest_gap_ft >= J.D_MARGIN_M * J.FT),
            "braked": braking,
            "brake_range_ft": demand_at_brake,
            # F21 diagnostics. `brake_step` 0 with `speed_at_brake_mps` ~ 0 is the
            # degenerate run: the policy commanded full braking before the ego had
            # moved, so the "stop" is a vehicle that never started. It is a real and
            # severe nuisance brake, not a standoff failure, and the two must not be
            # scored as the same thing.
            "brake_step": brake_step,
            "speed_at_brake_mps": None if speed_at_brake is None else round(speed_at_brake, 3),
            "top_speed_mps": round(top_speed, 3),
            "steps": step + 1,
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

    if args.scenario not in ("lead", "ped", "plate"):
        raise SystemExit(f"scenario {args.scenario!r} is not drivable")
    import capture_campaign as CC
    assert A9_HEAD_START_M == CC.PED_LEAD_MARGIN_M, "A9 head start drifted"
    # From the training module's own arm list, not a literal. This read
    # ["P_pts", "P_cont"] and silently skipped P_pts3 when it was added, so the third
    # regulatory-matrix arm had certificates and gates and no M4 result at all -- and
    # "--all" reported success while covering two thirds of the policies.
    from train_policies import POLICY_ARMS
    policies = list(POLICY_ARMS) if args.all else [args.policy]
    conditions = list(CONDITIONS) if args.all else [args.condition]
    if None in policies or None in conditions:
        raise SystemExit("give --policy and --condition, or --all")

    # require_cuda, not is_available(): the flag is False while CARLA initialises on
    # the same device, and TRUE on a card whose kernels the installed torch does not
    # carry (sm_120 vs an sm_90 build). Both end in a silent CPU run that still prints
    # numbers. See tools/gpu.py.
    dev = require_cuda()
    _sfx = "" if args.scenario == "lead" else f"_{args.scenario}"
    out_path = J.claim_output(                              # D-9
        J.REPO / "results" / "carla" / f"policy_endpoints{_sfx}.json")
    b = json.loads((J.REPO / "results" / "carla" / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)

    if args.scenario == "plate":
        # Cells 5 and 6. The false-activation scenario passes by NOT stopping, so it does
        # not share the endpoint loop below: there is no contact to avoid and no standoff
        # to hold, and its speed is the standard's 50 mph rather than 25.
        out = {"scenario": "plate", "speed_mph": J.PLATE_MPH, "cells": {}}
        for pol in policies:
            model, w, h = load_policy(pol, "lead", dev)   # the hazard-trained policy
            for cond in conditions:
                alt, lights = CONDITIONS[cond]
                weather = world.get_weather()
                weather.sun_altitude_angle = alt
                weather.cloudiness = 10.0
                weather.precipitation = 0.0
                world.set_weather(weather)
                for _ in range(J.WEATHER_SETTLE_TICKS):
                    world.tick()
                runs = [plate_run(world, site, model, w, h, dev, J.PLATE_MPH, lights)
                        for _ in range(J.REPS)]
                passes = sum(1 for r in runs if r["passes"])
                J.progress(f"{pol} / {cond} / plate: {ST.fmt(passes, J.REPS)} pass "
                           f"(peak demand {max(r['peak_demand_mps2'] for r in runs):.3f} "
                           f"vs limit {NUISANCE_LIMIT_MPS2:.3f})")
                out["cells"][f"{pol}|{cond}"] = {
                    **ST.rate(passes, J.REPS),
                    "of": J.REPS,
                    "braked": sum(1 for r in runs if r["braked"]),
                    "exceeded_limit": sum(1 for r in runs if r["exceeded_nuisance_limit"]),
                    "peak_demand_mps2": max(r["peak_demand_mps2"] for r in runs),
                    "nuisance_limit_mps2": round(NUISANCE_LIMIT_MPS2, 4),
                    "sun_altitude_deg": alt, "headlamps": lights,
                    "runs": runs,
                }
        out["all_endpoints_pass"] = all(
            c["passes"] == J.REPS for c in out["cells"].values())
        out["note"] = (
            "FMVSS 127 false activation: an ASTM A36 trench plate, 8 x 12 ft x 1 in, "
            "approached in lane at 50 mph. PASS is crossing it without braking and "
            "without ever commanding more than the standard's 0.25 g nuisance limit. "
            "This is the ONLY scenario in the study that passes by not stopping.")
        path = J.claim_output(J.REPO / "results" / "carla" / "policy_endpoints_plate.json")
        path.write_text(json.dumps(out, indent=2) + "\n")
        print(f"\n  wrote {path.relative_to(J.REPO)}")
        return 0

    out = {"scenario": args.scenario, "speed_mph": args.speed_mph,
           # The harness this cell ran under. D-11 makes data from a violating harness
           # unusable, which is checkable after the fact only if the cell says which
           # harness it was (CARLA_DETERMINISM_PENDING.md item 5).
           "determinism": J.determinism_provenance(world),
           "cells": {}}
    sig_records = []
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
            # TWO COUNTS, as in drive_witness.py and for the same reason (FINDINGS F9).
            # PROTOCOL section 7 defines the closed-loop pass as "no contact and standoff
            # at least d_margin", and section 10's M4 criterion is that phrase. The
            # prematurity condition is this file's own addition, for a good reason -- a
            # policy that stops immediately has not performed AEB -- but it is a
            # must-NOT-brake condition and belongs to property A.
            #
            # This is conformance to the frozen text, not a relaxation to make a run
            # pass, and it is not allowed to bury anything: P_pts3 brakes at 287 ft in
            # daylight on the pedestrian scenario and stops 250 ft short, which is a
            # serious defect that M4 must report even though M4 does not fail on it.
            passes_protocol = sum(
                1 for r in runs if not r["contact"] and r["standoff_ok"])
            passes = sum(
                1 for r in runs
                if not r["contact"] and r["standoff_ok"] and not r["premature"]
            )
            never = sum(1 for r in runs if not r["braked"])
            early = sum(1 for r in runs if r["premature"])
            J.progress(
                f"{pol} / {cond}: {ST.fmt(passes_protocol, J.REPS)} pass"
                f"{f', {never} never braked' if never else ''}"
                f"{f', {early} braked prematurely' if early else ''}"
            )
            out["cells"][f"{pol}|{cond}"] = {
                **ST.rate(passes_protocol, J.REPS),
                "passes": passes_protocol,
                "passes_protocol": passes_protocol,
                "passes_no_nuisance": passes,
                "of": J.REPS,
                "never_braked": never,
                "premature_brakes": early,
                "min_gap_ft": [r["min_gap_ft"] for r in runs],
                "brake_range_ft": [r["brake_range_ft"] for r in runs],
                "sun_altitude_deg": alt,
                "headlamps": lights,
                "signature": runs[0]["signature"],
            }
            sig_records.append(
                {"sun_altitude_deg": alt, "headlamps": lights,
                 "signature": runs[0]["signature"]})

    # The two endpoints are the extremes of the axis, so they are the easiest place to
    # notice that the sun never moved: daylight and darkness-under-lower-beam cannot
    # render to nearly the same frame. Checked on the driver that produces M4, not on
    # the study as a whole -- the steering study's version of this rule was enforced on
    # the diagnostic path and not the authoritative one, for a whole study.
    from capture_campaign import load_uncovered  # noqa: E402
    # The axis check runs over the conditions that lie ON the family's axis. Upper beam
    # sits at the SAME sun altitude as lower beam, so including it would key two records
    # to one altitude and hand the monotonicity test a zero-degree step between two
    # different scenes. Its signature is recorded separately -- it is the only evidence
    # the high beam actually came on, and a lamp state that failed to apply looks exactly
    # like a correct run.
    on_axis = {r["sun_altitude_deg"]: r for r in sig_records
               if r["headlamps"] != "HighBeam"}
    out["illumination"] = CS.check_axis(list(on_axis.values()),
                                        uncovered=load_uncovered())
    out["illumination_highbeam"] = [
        {"sun_altitude_deg": r["sun_altitude_deg"], "signature": r["signature"]}
        for r in sig_records if r["headlamps"] == "HighBeam"]
    # Upper beam must render BRIGHTER than lower beam at the same altitude. It is the
    # same scene with more light in it, so anything else means the lamp state did not
    # take -- the failure amendment A4 found when auto-exposure made the headlamps make
    # the image darker.
    for hb in out["illumination_highbeam"]:
        lb = on_axis.get(hb["sun_altitude_deg"])
        if lb and hb["signature"]["mean"] <= lb["signature"]["mean"]:
            raise SystemExit(
                f"UPPER BEAM DID NOT TAKE at {hb['sun_altitude_deg']:+.3f} deg: it "
                f"renders {hb['signature']['mean']:.4f} against lower beam's "
                f"{lb['signature']['mean']:.4f}. More light cannot make a darker frame.")
    if not out["illumination"]["ok"] and len(on_axis) > 1:
        CS.assert_axis(list(on_axis.values()), uncovered=load_uncovered())

    out["all_endpoints_pass"] = all(
        c["passes_protocol"] == J.REPS for c in out["cells"].values())
    out["all_endpoints_pass_no_nuisance"] = all(
        c["passes_no_nuisance"] == J.REPS for c in out["cells"].values())
    # Named loudly, because an M4 that passes on the frozen criterion while a policy
    # brakes at 287 ft is a result with two halves and only one of them is the verdict.
    out["nuisance_braking_cells"] = {
        k: {"premature_of": f"{v['premature_brakes']}/{v['of']}",
            "brake_range_ft": v["brake_range_ft"][0]}
        for k, v in out["cells"].items() if v["premature_brakes"]}
    out["note"] = (
        "M4 needs every cell 10/10. A policy that cannot pass the regulatory endpoints "
        "is not the policy a manufacturer would ship, and without it the study has no "
        "setup: the claim is that a policy which SATISFIES the standard is unsafe "
        "between its test points."
    )
    path = out_path
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
