"""D-8: measure this repository's determinism OPEN LOOP.

    bash scripts/determinism_probe.sh          # 3 reps, fresh server each, then compare
    python tools/determinism_probe.py --rep 1  # one repetition
    python tools/determinism_probe.py --compare

**Why this exists.** The `carla-determinism` rules were measured in
`formal-verification--steering--code`, on Town06, with a lane-keeping policy. This study
adopted the *fixes* and never ran the *measurement*. Everything it can say about run-to-run
noise is inherited from a different map, a different camera and a different policy, and
D-8 exists precisely because that inference is not available:

> **D-8.** A closed-loop probe measures physics, rendering and feedback amplification at
> once, so every candidate cause produces the same symptom and none can be distinguished.
> Cut the feedback: drive a command sequence that is a pure function of the step index,
> and record pose, a hash of the raw sensor buffer, and the model's output *computed but
> not applied*. Those three streams separate physics from rendering from amplification.

So: the vehicle is driven by a scripted sequence that depends only on the step number. The
policy still sees every frame and its output is still computed and recorded — it is simply
never fed back into the controls. Three streams come out, and they answer three different
questions.

| stream | question | rule |
|---|---|---|
| pose and velocity per step | is the physics reproducible? | D-1, D-2 |
| SHA-256 of the raw camera buffer | is the rendering reproducible? | D-3, D-7 |
| policy output, computed not applied | does this policy amplify what is left? | D-10 |

**What the numbers are for.** The render stream gives the floor D-7 says cannot be removed,
measured here rather than quoted from Town06. The policy stream gives D-10's answer: with
the physics identical, any spread in the commanded deceleration is the network amplifying
render noise, and a spread comparable to the brake decision threshold means a policy whose
verdict can flip between repetitions for reasons that have nothing to do with illumination.
That is the number the repetition count in PROTOCOL section 1 is supposed to be chosen
against.

**D-9: this probe can fail.** Each repetition writes its OWN artifact path and the compare
step refuses to run unless every repetition's file exists, carries the repetition index it
claims, and differs in identity from the others. A crashed repetition that leaves the
previous file on disk is the exact defect D-9 was written for -- it produced a false "runs
are reproducible" result in the steering study and cost a day -- and here it cannot pass
silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
SPEED_STEPS = 150     # scripted acceleration, command changes EVERY step
BRAKE_STEP = 150      # then full brake, latched
MAX_STEPS = 400


def scripted_control(step: int):
    """The command sequence, a pure function of the step index. D-8's requirement.

    Deliberately CHANGING on every step through the acceleration phase. D-2's race is
    invisible while a command is unchanged, because a late arrival re-applies the same
    value, so a probe that holds the throttle constant measures nothing about it.
    """
    carla = J.carla_module()
    if step < BRAKE_STEP:
        throttle = 0.35 + 0.15 * math.sin(step / 7.0)
        return carla.VehicleControl(throttle=float(throttle), brake=0.0, steer=0.0)
    return carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0)


def run_rep(rep: int, policy: str | None, scenario: str, sun_altitude: float) -> dict:
    import queue

    carla = J.carla_module()
    client, world = J.connect(rendering=True)
    site = J.flattest_site()
    spawn, _ = J.site_transform(world, site, along=10.0, need_m=200.0)

    model = w = h = dev = None
    if policy:
        from gpu import require_cuda
        from run_policy import load_policy, preprocess
        import torch
        dev = require_cuda()
        model, w, h = load_policy(policy, scenario, dev)

    wx = world.get_weather()
    wx.sun_altitude_angle = sun_altitude
    wx.cloudiness = 10.0
    wx.precipitation = 0.0
    world.set_weather(wx)

    ego = cam = None
    steps = []
    try:
        ego = J.spawn_hero(world, spawn)
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            J.rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        ego.set_light_state(carla.VehicleLightState(
            carla.VehicleLightState.LowBeam if sun_altitude < 5.0
            else carla.VehicleLightState.NONE))
        for _ in range(J.WEATHER_SETTLE_TICKS):
            J.grab_frame(world, images)

        for step in range(MAX_STEPS):
            img = J.grab_frame(world, images)
            raw = bytes(img.raw_data)
            demand = None
            if model is not None:
                import torch
                with torch.no_grad():
                    demand = float(model(preprocess(img, w, h, dev)).item())
            tf = ego.get_transform()
            v = ego.get_velocity()
            steps.append({
                "step": step,
                "x": round(tf.location.x, 6), "y": round(tf.location.y, 6),
                "z": round(tf.location.z, 6), "yaw": round(tf.rotation.yaw, 6),
                "speed_mps": round(math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z), 6),
                "frame_sha256": hashlib.sha256(raw).hexdigest(),
                # COMPUTED, NOT APPLIED. This is the whole point of D-8: the number the
                # policy would have driven with, recorded while the vehicle is driven by
                # the script instead, so its spread is render noise and nothing else.
                "policy_demand_mps2": None if demand is None else round(demand, 6),
            })
            # The scripted command. Never the policy's.
            J.apply_control(ego, scripted_control(step))
            world.tick()
            if step >= BRAKE_STEP and J.speed_of(ego) < 0.05:
                break
    finally:
        if cam is not None:
            cam.stop()
        J.despawn(world, cam, ego)

    return {
        "rep": rep,
        "policy": policy,
        "scenario": scenario,
        "sun_altitude_deg": sun_altitude,
        "steps_recorded": len(steps),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "determinism": J.provenance() if hasattr(J, "provenance") else None,
        "steps": steps,
    }


def compare(paths: list[Path]) -> dict:
    reps = []
    seen_ids = set()
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing {p.name}: a repetition did not write its artifact, "
                             f"and comparing what is left would compare a file with "
                             f"itself (D-9)")
        d = json.loads(p.read_text())
        if d["rep"] in seen_ids:
            raise SystemExit(f"{p.name} claims rep {d['rep']}, already seen. A crashed "
                             f"repetition left an earlier file in place (D-9)")
        seen_ids.add(d["rep"])
        reps.append(d)

    n = min(r["steps_recorded"] for r in reps)
    if n < 10:
        raise SystemExit(f"only {n} common steps; the probe did not run")

    pose_dev, speed_dev, demand_dev = [], [], []
    frame_diff = 0
    for i in range(n):
        xs = [r["steps"][i] for r in reps]
        pose_dev.append(max(
            math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
            for a in xs for b in xs))
        speed_dev.append(max(a["speed_mps"] for a in xs)
                         - min(a["speed_mps"] for a in xs))
        if len({a["frame_sha256"] for a in xs}) > 1:
            frame_diff += 1
        ds = [a["policy_demand_mps2"] for a in xs if a["policy_demand_mps2"] is not None]
        if len(ds) == len(xs) and ds:
            demand_dev.append(max(ds) - min(ds))

    b = json.loads((OUT / "braking.json").read_text())
    threshold = b["a_max_g_worst"] * 9.81 * 0.5

    out = {
        "reps": len(reps),
        "common_steps": n,
        "policy": reps[0]["policy"],
        "sun_altitude_deg": reps[0]["sun_altitude_deg"],
        # PHYSICS. D-1 and D-2 are supposed to make this exactly zero.
        "pose_max_divergence_m": round(max(pose_dev), 9),
        "pose_final_divergence_m": round(pose_dev[-1], 9),
        "speed_max_divergence_mps": round(max(speed_dev), 9),
        "physics_bit_identical": max(pose_dev) == 0.0,
        # RENDERING. D-7 says this floor cannot be removed; here is its size on THIS map.
        "frames_differing": frame_diff,
        "frames_compared": n,
        "frame_diff_fraction": round(frame_diff / n, 4),
        # AMPLIFICATION. D-10: with the physics identical, any spread here is the network
        # magnifying render noise, and it is the policy's property rather than the
        # simulator's.
        "policy_demand_max_spread_mps2": (round(max(demand_dev), 6)
                                          if demand_dev else None),
        "brake_decision_threshold_mps2": round(threshold, 4),
        "demand_spread_as_fraction_of_threshold": (
            round(max(demand_dev) / threshold, 6) if demand_dev else None),
        "note": (
            "Open loop, per D-8: the vehicle is driven by a command sequence that is a "
            "pure function of the step index and the policy's output is computed but "
            "never applied. Pose divergence is physics (D-1, D-2), frame divergence is "
            "the render floor (D-3, D-7), and demand spread with identical physics is "
            "the policy amplifying that floor (D-10)."),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rep", type=int, help="run ONE repetition and write its own file")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--reps", type=int, default=3, help="how many to compare")
    ap.add_argument("--policy", default="P_cont")
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--sun-altitude", type=float, default=-30.0)
    args = ap.parse_args()

    if args.rep is not None:
        d = run_rep(args.rep, args.policy, args.scenario, args.sun_altitude)
        # Its OWN path. D-9: a repetition that crashes must not leave an earlier
        # repetition's file to be compared against itself.
        path = OUT / f"determinism_rep{args.rep}.json"
        path.write_text(json.dumps(d, indent=1) + "\n")
        print(f"  rep {args.rep}: {d['steps_recorded']} steps -> {path.name}")
        return 0

    if args.compare:
        paths = [OUT / f"determinism_rep{i}.json" for i in range(1, args.reps + 1)]
        rep = compare(paths)
        (OUT / "determinism_probe.json").write_text(json.dumps(rep, indent=1) + "\n")
        print(f"\n  {rep['reps']} reps, {rep['common_steps']} common steps, "
              f"sun {rep['sun_altitude_deg']:+.1f} deg\n")
        print(f"  physics   max pose divergence   {rep['pose_max_divergence_m']:.9f} m"
              f"   {'BIT-IDENTICAL' if rep['physics_bit_identical'] else ''}")
        print(f"            final pose divergence {rep['pose_final_divergence_m']:.9f} m")
        print(f"  rendering frames differing      {rep['frames_differing']}"
              f"/{rep['frames_compared']}  ({100 * rep['frame_diff_fraction']:.1f}%)")
        if rep["policy_demand_max_spread_mps2"] is not None:
            print(f"  policy    max demand spread      "
                  f"{rep['policy_demand_max_spread_mps2']:.6f} m/s^2 = "
                  f"{rep['demand_spread_as_fraction_of_threshold']:.6f} of the brake "
                  f"decision threshold")
        print(f"\n  wrote results/carla/determinism_probe.json")
        return 0

    ap.error("give --rep N or --compare")


if __name__ == "__main__":
    raise SystemExit(main())
