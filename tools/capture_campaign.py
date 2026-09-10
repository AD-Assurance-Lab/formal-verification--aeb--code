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
import condition_signature as CS  # noqa: E402
import scenarios as S  # noqa: E402

# MAP-SCOPED. Captures used to land in one flat directory keyed on scenario and sun
# altitude, and the resume-skip below tested only whether that filename existed -- so a
# campaign on a new map silently reused every frame set whose knot altitude happened to
# coincide with an old one. Measured on the A14 rebuild: Town12's axis shares exactly three
# knots with Town01's, and TWO OF THEM ARE THE REGULATORY ENDPOINTS, +60 and -30, which are
# the two frames the entire disturbance family is built between. See FINDINGS F26.
OUT = J.CAPTURES
LEAD_GAP_M = 120.0
PED_GAP_M = 120.0
# The false-activation approach is run at 50 mph per FMVSS 127, so it needs more room:
# settle distance plus r_req at that speed is about 183 ft of stopping alone.
PLATE_GAP_M = 200.0
MIN_RANGE_M = 2.0
MAX_RANGE_M = 60.0
DISK_HEADROOM_GB = 20.0
# Extra head start for the walker beyond r_req. Tuned by measurement, see A9.
PED_LEAD_MARGIN_M = 8.0


# FMVSS 127 as PROTOCOL section 2 records it tests THREE lighting conditions: daylight,
# darkness with lower beam, and darkness with upper beam. The first two are the endpoints
# of the certified interval -- an interval has two ends -- and the third is the same
# darkness with a different headlamp state, which is how tools/carla_jobs.py:job_sites has
# always treated it. So upper beam is not a knot on the sun-altitude axis; it is a
# separate capture at the darkness knot, used as a TRAINING condition and as a third
# regulatory endpoint test.
#
# Filed under a prefix the family's own globs cannot see: every consumer matches
# "{scenario}_sun*", and "{scenario}_hb_sun*" does not match it. A high-beam frame must
# never enter the disturbance family by accident -- the family interpolates absolute pixel
# values along sun altitude, and a different headlamp state at the same altitude is a
# different scene, not a point on that line.
HIGHBEAM_KNOT = -30.0


def capture_harness() -> dict:
    """What a frame set has to match to be reusable. Kept deliberately small: every field
    here is something that changes what is IN the frame, and nothing here is a timestamp
    or a path, because those differ between two legitimately identical campaigns."""
    det = J.determinism_provenance()
    return {
        "map": J.MAP,
        "cloudiness": J.CLOUDINESS,
        "weather_settle_ticks": J.WEATHER_SETTLE_TICKS,
        "rules_digest": det.get("rules_digest"),
        "notexturestreaming": det.get("notexturestreaming"),
        "quality_level": det.get("quality_level"),
    }


def stamp_mismatch(path, knot: float) -> str | None:
    """None if the frame set on disk was made by the harness running now.

    Returns a short human description of the FIRST disagreement otherwise. An unstamped
    file is a mismatch by definition: it predates F26 and there is no way to tell what
    made it."""
    try:
        z = np.load(path, allow_pickle=True)
    except Exception as exc:
        return f"unreadable: {exc}"
    if "harness" not in z:
        return "no harness stamp; predates F26"
    try:
        was = json.loads(str(z["harness"]))
    except Exception:
        return "unreadable harness stamp"
    now = capture_harness()
    for k, v in now.items():
        if v is None:
            continue                      # nothing to compare against
        if was.get(k) != v:
            return f"{k} {was.get(k)!r} -> {v!r}"
    # The altitude is in the filename, and a filename is a claim about a file. Check it
    # against what the file itself recorded.
    if "sun_altitude_deg" in z and abs(float(z["sun_altitude_deg"]) - knot) > 1e-3:
        return (f"file says sun {float(z['sun_altitude_deg']):+.3f} deg, "
                f"this knot is {knot:+.3f}")
    return None


def capture_stem(scenario: str, knot: float, highbeam: bool) -> str:
    return (f"{scenario}_hb_sun{knot:+07.3f}" if highbeam
            else f"{scenario}_sun{knot:+07.3f}")


def load_knots() -> list[float]:
    """The illumination knots, and proof they were measured the right way.

    FINDINGS F2: a capture campaign must use knots measured under the three-channel
    blend metric, never the blue-only one audit F1 found. That was enforced by reading
    a differently NAMED file, `family_knots_rgb.json`, which stopped working the moment
    `build_family_knots.py` was fixed -- the fixed tool writes the correct knots to
    `family_knots.json`, so the rule guarded a filename while the real artifact sat
    beside it. A12 discarded both files, so there is no longer a stale one to guard
    against; what has to be checked is the metric the file was MADE with, which the
    file now states.
    """
    path = J.OUT / "family_knots.json"
    if not path.exists():
        raise SystemExit("run tools/build_family_knots.py first (writes the knots)")
    payload = json.loads(path.read_text())
    metric = payload.get("blend_metric")
    if metric != "rgb_three_channel":
        raise SystemExit(
            f"refusing: {path.name} declares blend_metric={metric!r}, and this campaign "
            "requires 'rgb_three_channel'. A knot set bisected on the blue channel "
            "alone (audit F1) cuts the axis in the wrong places, and dusk sky is "
            "chromatic exactly where the cuts matter. Re-run "
            "tools/build_family_knots.py.")
    return payload["knots_sun_altitude_deg"]


def load_uncovered() -> list[dict]:
    """The sub-intervals the family cannot represent, as the knot measurement found them.

    A knot file written before this field existed has no way to say, so it is refused
    rather than read as "everything is covered" -- a missing coverage record must never
    default to full coverage.
    """
    path = J.OUT / "family_knots.json"
    payload = json.loads(path.read_text())
    if "sub_interval_detail" not in payload:
        raise SystemExit(
            f"{path.name} predates per-sub-interval coverage and cannot state its own "
            "scope. Re-run tools/build_family_knots.py.")
    return payload.get("uncovered", [])


def expert_decel(range_m: float, v: float, a_max: float) -> float:
    """Ground-truth braking law. The label, and the same law the oracle uses."""
    reach = max(0.05, range_m - S.FT * 0 - 1.0)  # 1.0 m standoff, PROTOCOL section 3
    return float(min(a_max, max(0.0, v * v / (2.0 * reach))))


def nominal_states(world, site, scenario: str, speed_mph: float, a_max_g: float):
    """Drive once, rendering off, and record the states worth capturing."""
    carla = J.carla_module()
    v_target = speed_mph * J.MPH
    a_max = a_max_g * 9.81
    gap = {"lead": LEAD_GAP_M, "none": LEAD_GAP_M,
           "plate": PLATE_GAP_M, "none_plate": PLATE_GAP_M}.get(scenario, PED_GAP_M)

    tf_ego, _ = J.site_transform(world, site, along=10.0, need_m=gap + 80.0)
    tf_target, wp_target = J.site_transform(world, site, along=10.0 + gap)

    ego = target = ped = None
    states = []
    try:
        if scenario in ("none", "none_plate"):
            target = None
        elif scenario == "plate":
            # FMVSS 127's false-activation target: an ASTM A36 steel trench plate,
            # 8 x 12 ft x 1 in, lying in lane. It is a STATIC PROP tiled to the
            # standard's dimensions rather than a vehicle, and the correct behaviour is
            # to drive over it without braking -- the opposite of every other scenario
            # here, which is why it needs its own closed-loop criterion in run_policy.
            plate_actors, plate_info = S.place_trench_plate(world, wp_target)
            if not plate_actors:
                raise RuntimeError("trench plate placement blocked")
            print(f"  trench plate: {plate_info['tiles']} tiles covering "
                  f"{plate_info['covered_w_ft']} x {plate_info['covered_l_ft']} ft "
                  f"against a specified {plate_info['target_w_ft']} x "
                  f"{plate_info['target_l_ft']}")
            target = None            # nothing to measure a bounding box against
            plate_ref = tf_target
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
            # The walker has to be IN the ego's path by r_req, not at the conflict point
            # later. r_req is the last moment braking can still succeed, so a hazard
            # arriving after it is not one the system could ever have avoided. Timed to
            # meet the conflict point instead, the walker was measured still 1.70 m to
            # the side at the closest captured pose, outside the vehicle: no run could
            # have hit them, so no run was a pedestrian test.
            lead_m = J.r_req_m(v_target, a_max_g, 0.15) + PED_LEAD_MARGIN_M

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
            if scenario in ("plate", "none_plate"):
                # The plate lies flat on the road with no bounding box worth measuring
                # against, so range is to its centre from the front bumper -- the same
                # quantity the conflict-point range is for the pedestrian.
                gap_m = to_conflict
            elif scenario == "lead":
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
                if (to_conflict - lead_m) / max(J.speed_of(ego), 0.1) <= walk_s:
                    ctrl.speed = 1.5
                    J.apply_control(ped, ctrl)
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
            J.apply_control(ego, 
                carla.VehicleControl(throttle=max(0.0, min(1.0, cmd)))
            )
            world.tick()
    finally:
        J.despawn(world, ego, target, ped)
    return states


LAST_DETERMINISM = None


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


def capture(scenario: str, knots: list[float], speed_mph: float, dry_run: bool,
            highbeam: bool = False):
    carla = J.carla_module()
    client, world = J.connect(rendering=not dry_run)
    # Stashed here because `capture()` owns the world and main() writes the artifact.
    # Recorded from the live server, so the world settings are the ones the frames were
    # actually rendered under rather than the ones this file asks for.
    global LAST_DETERMINISM
    LAST_DETERMINISM = J.determinism_provenance(world)
    site = J.flattest_site(scenario=scenario)
    b = json.loads((J.OUT / "braking.json").read_text())

    spawn_tf, _ = J.site_transform(world, site, along=10.0, need_m=LEAD_GAP_M + 80.0)

    # The nominal run is saved and REUSED. It is not bit-identical across process runs:
    # two knots captured in an earlier invocation differed from the rest by 0.7 mm, and
    # while that is far below a pixel at these ranges, the pairing guarantee is the
    # entire reason for replaying rather than driving. Pairing that holds only within
    # one invocation is not a guarantee.
    OUT.mkdir(parents=True, exist_ok=True)
    # DARKEN THE WORLD BEFORE ANYTHING ELSE HAPPENS IN IT. A16 orders the knots darkest
    # first so no knot is preceded by a brighter one, and that is necessary but not
    # sufficient: CARLA starts a session in daylight, and `nominal_states` DRIVES the
    # scenario to record its poses before any knot is captured. Driving in the default
    # daylight charges the scene exactly as a bright knot does, and the first dark knot
    # then renders 9x too bright (F28) -- which is what the first attempt at A16 measured,
    # 0.0341 at -30 deg with -30 captured first.
    #
    # Setting the darkest knot here, before the nominal run and before the state loop,
    # means the session is never brighter than the darkest thing it is about to capture.
    _w = world.get_weather()
    _w.sun_altitude_angle = min(knots)
    _w.cloudiness = J.CLOUDINESS
    _w.precipitation = 0.0
    world.set_weather(_w)
    for _ in range(J.WEATHER_SETTLE_TICKS):
        world.tick()
    # The no-target control MUST replay the lead poses, or it is not a control: the
    # whole point is to isolate what the target contributes at an identical pose.
    base = J.CONTROL_OF.get(scenario, scenario)
    states_path = OUT / f"states_{base}.json"
    if states_path.exists():
        states = _load_states(states_path)
        print(f"  reusing the saved nominal run, {len(states)} states")
    elif scenario in J.CONTROL_OF:
        raise SystemExit(
            f"capture --scenario {base} first: the no-target control replays its poses"
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
    # DARKEST FIRST, always, whatever order the caller passed. FINDINGS F28: a knot
    # captured after a brighter one in the same server session renders about 9x brighter
    # at the dark end than the same knot captured on a scene that has never been bright --
    # 0.0342 against 0.0036 at -30 deg -- and it does NOT decay. Six thousand ticks of
    # simulated night leaves it at 0.0342. There are two stable states for one weather,
    # and which one a frame lands in is decided by capture order rather than by the
    # condition.
    #
    # Ascending altitude means no knot is ever preceded by a brighter one. Bright knots
    # are insensitive to what came before them (+60 reads 0.37177 after darkness against
    # 0.37138 after a full sweep), so ordering costs the bright end nothing and gives the
    # dark end a value that is a function of its own condition.
    #
    # The manifest is reordered back to the caller's order below, because the axis checks
    # and every consumer read it as an axis and an axis has a direction.
    order = sorted(knots)
    for knot in order:
        out_path = OUT / f"{capture_stem(scenario, knot, highbeam)}.npz"
        if out_path.exists():
            # Resuming an interrupted campaign is the reason this skip exists and it is a
            # real need -- a capture set is hours. But a file's EXISTENCE is not evidence
            # that it belongs to this campaign, and until F26 that was the whole test.
            # The stamp inside the file is compared against the harness now running, and a
            # mismatch RECAPTURES rather than reusing or refusing: the operator asked for
            # this campaign, and the stale frames are not it.
            stale = stamp_mismatch(out_path, knot)
            if stale:
                print(f"  {out_path.name} exists but belongs to a different campaign "
                      f"({stale}); recapturing")
            else:
                # A skipped knot still contributes its signature, read back out of the
                # npz. The axis check has to see the WHOLE axis or it sees nothing useful:
                # a campaign resumed after an interruption would otherwise check the three
                # knots it happened to redo and report success for seventeen.
                print(f"  {out_path.name} exists, skipping")
                entry = {"knot": knot, "file": out_path.name, "skipped": True}
                try:
                    z = np.load(out_path, allow_pickle=True)
                    if "signature" in z:
                        entry["signature"] = json.loads(str(z["signature"]))
                except Exception as exc:
                    print(f"    could not read its signature: {exc}")
                manifest.append(entry)
                continue
        t0 = time.time()
        w = world.get_weather()
        w.sun_altitude_angle = knot
        w.cloudiness = J.CLOUDINESS
        w.precipitation = 0.0
        world.set_weather(w)

        # Spawn with clearance, then PLACE. The recorded poses sit at ride height,
        # about z = 0.002, and spawning there collides with the road surface.
        ego = J.spawn_hero(world, spawn_tf)
        other = None
        cam = None
        frames = []
        try:
            if scenario in J.CONTROL_OF:
                other = None
            elif scenario == "plate":
                # Static, placed once, never moved between poses: it is road furniture,
                # not an actor that tracks the approach.
                S.place_trench_plate(world, J.site_transform(
                    world, site, along=10.0 + PLATE_GAP_M)[1])
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
                    carla.VehicleLightState.HighBeam if highbeam
                    else (carla.VehicleLightState.LowBeam if knot < 5.0
                          else carla.VehicleLightState.NONE)
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

        # WHAT WAS ACTUALLY RENDERED, not what was asked for. Taken at pose 0, which is
        # the same pose at every knot by construction (that pairing is the whole reason
        # this replays rather than drives), so the signatures across knots differ only
        # by illumination. Stored in the npz as well as the manifest, so a frame set can
        # be audited from itself with nothing else on disk.
        sig = CS.signature(frames[0])
        print(f"    signature: mean {sig['mean']:.4f} sigma {sig['sigma']:.4f} "
              f"p99 {sig['p99']:.4f} dark {sig['frac_dark']:.3f}", flush=True)

        np.savez_compressed(
            out_path,
            # The harness that produced these frames, inside the frames. D-11 is
            # enforceable after the fact only if the artifact says what made it, and a
            # manifest beside the file is a thing that can go missing or go stale while
            # the file survives. F26.
            harness=np.array(json.dumps(capture_harness())),
            signature=np.array(json.dumps(sig)),
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
             "size_mb": round(size_mb, 1), "signature": sig}
        )


    # THE AXIS IS CHECKED AS A WHOLE, once every knot is in. A per-knot assertion cannot
    # see the failure that matters -- a single frame is consistent with any illumination
    # you care to name, and only the axis's own shape says whether the sun moved the way
    # it was asked to. Raising here, before the manifest is written, means a campaign
    # that rendered the wrong illumination cannot leave a manifest that looks finished.
    signed = [m for m in manifest if m.get("signature")]
    if highbeam:
        # One knot, so there is no axis. The signature is still recorded -- it is the only
        # evidence that the high beam actually came on, and a lamp state that silently
        # failed to apply would otherwise look exactly like a correct capture.
        for m in signed:
            print(f"  high beam at sun {m['knot']:+.3f}: mean {m['signature']['mean']:.4f} "
                  f"p99 {m['signature']['p99']:.4f} dark {m['signature']['frac_dark']:.3f}")
        return manifest
    if len(signed) < len(manifest):
        raise SystemExit(
            f"{len(manifest) - len(signed)} of {len(manifest)} knots carry no "
            "photometric signature, so the axis cannot be checked. Those npz files "
            "predate the guard; delete them and recapture.")
    # Back into the caller's order before anything reads it as an axis.
    _pos = {round(k, 3): i for i, k in enumerate(knots)}
    manifest.sort(key=lambda e: _pos.get(round(e["knot"], 3), 0))
    rep = CS.assert_axis(fresh_records(signed), uncovered=load_uncovered())
    print(f"\n  illumination axis OK: {rep['knots']} knots, span "
          f"{rep['axis_span_mean']:.4f} of full range, worst inversion "
          f"{100 * rep['worst_inversion_frac']:.1f}% of span "
          f"(limit {100 * CS.MAX_INVERSION_FRAC:.0f}%), total "
          f"{100 * rep['total_rise_frac']:.1f}% (limit "
          f"{100 * CS.MAX_TOTAL_RISE_FRAC:.0f}%)")
    for inv in rep["inversions"]:
        print(f"    recorded: {inv['detail']}"
              + ("  [declared uncovered]" if inv["declared_uncovered"] else ""))
    return manifest


def fresh_records(manifest_entries):
    return [{"sun_altitude_deg": m["knot"], "signature": m["signature"]}
            for m in manifest_entries]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--scenario",
        # DERIVED, not listed. A scenario this accepts but SCENARIO_SITE does not know
        # stops the run at site selection -- which is what happened to 'none' and
        # 'none_ped' -- and a scenario SCENARIO_SITE knows but this rejects is
        # unreachable. Two lists of the same thing is one list too many.
        choices=[k for k in J.SCENARIO_SITE if k != "any"],
        default="lead",
        help="'none' repeats the lead poses with NO target; 'none_ped' repeats the "
             "ped poses the same way. The control isolates what the target contributes "
             "to a frame (A10) and is the false-activation baseline for property A",
    )
    ap.add_argument("--speed-mph", type=float, default=None,
                    help="defaults to 25 mph for the hazard scenarios and 50 for the "
                         "trench plate, which is the speed FMVSS 127 approaches it at")
    ap.add_argument("--plan", action="store_true", help="size it, capture nothing")
    ap.add_argument("--limit-knots", type=int, default=0, help="0 means all")
    ap.add_argument(
        "--highbeam", action="store_true",
        help="capture the darkness knot with UPPER beam. FMVSS 127's third lighting "
             "condition: same illumination, different headlamp state, so it is a "
             "training condition and an endpoint test rather than a point on the axis")
    args = ap.parse_args()

    if args.speed_mph is None:
        args.speed_mph = (J.PLATE_MPH if args.scenario in ("plate", "none_plate")
                          else J.HAZARD_MPH)
    knots = load_knots()
    if args.highbeam:
        knots = [k for k in knots if abs(k - HIGHBEAM_KNOT) < 1e-6]
        if not knots:
            raise SystemExit(
                f"the knot set has no point at {HIGHBEAM_KNOT} deg, so there is no "
                "darkness endpoint to capture with the upper beam")
    elif args.limit_knots:
        knots = knots[: args.limit_knots]
    manifest = capture(args.scenario, knots, args.speed_mph, args.plan, args.highbeam)
    if manifest is not None:
        suffix = "_hb" if args.highbeam else ""
        path = OUT / f"manifest_{args.scenario}{suffix}.json"
        # A LIST with a sidecar, not a dict: condition_signature.py reads this file as a
        # list of entries and wrapping it would break the photometric cross-check, which
        # is the one illumination check resting on no assumption about the renderer.
        # D-11 is about captured data above all -- training images taken with texture
        # streaming on carry mip variation an evaluation will never show -- so the frames
        # need their harness recorded even though the manifest cannot hold it.
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        dpath = OUT / f"determinism_{args.scenario}{suffix}.json"
        dpath.write_text(json.dumps({
            "manifest": path.name,
            "knots": len(manifest),
            "determinism": LAST_DETERMINISM,
        }, indent=2) + "\n")
        print(f"  wrote {dpath.relative_to(J.REPO)}")
        print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
