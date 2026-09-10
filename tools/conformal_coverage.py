"""A distribution-free guarantee where a certificate is structurally unavailable.

    python tools/conformal_coverage.py --policy P_cont --scenario lead     # the sliver
    python tools/conformal_coverage.py --policy P_cont --from-deg 3.525 --to-deg 1.891

**The hole this fills.** Amendment A6 established that the horizon sliver cannot be
represented by the disturbance family at any width: the blend errs at 0.0163 against a 0.01
tolerance, because the renderer's sky model is discontinuous there and no step size fixes a
discontinuity. FINDINGS F6 then found the same sub-interval from a completely different
statistic. So a bound over that sub-interval quantifies over images the simulator would
never produce, and the study correctly refuses to count it as coverage.

That leaves a gap in the middle of the axis about which the study says nothing at all --
and it is not a quiet corner, it is sunset, which is exactly the region the claim is about.

**What conformal prediction gives, and what it does not.** Split conformal calibration over
illuminations drawn from the sub-interval yields, for a NEW illumination from the same
distribution, a lower bound on the commanded deceleration that holds with probability at
least 1 - alpha, with no assumption about the network, the renderer, or the distribution's
shape beyond exchangeability -- which holds here by construction, because the calibration
illuminations are drawn i.i.d. and rendered rather than blended.

It is emphatically **not** the certificate's statement. The certificate says *for all* `s`
in this sub-interval. This says *for a random* illumination from it, with probability
1 - alpha. A reader must never be allowed to confuse the two, so the artifact records the
quantifier in words and the report prints it every time.

The pairing is the point:

  covered sub-intervals    certificate, for all s, no probability attached
  the uncovered sliver     conformal, for a random s, 1 - alpha, no soundness claim
  everywhere               the two agree or they do not, and disagreement is a finding

Running it on a COVERED sub-interval as well is deliberate: where the certificate holds,
the conformal bound should be no tighter than the certified one, and if it ever is, the
certificate is not sound and that is worth knowing.
"""

from __future__ import annotations

import argparse
import json
import math
import queue
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import condition_signature as CS  # noqa: E402

OUT = J.OUT
CAPTURES = J.CAPTURES


def conformal_lower_bound(scores: list[float], alpha: float) -> tuple[float, int, int]:
    """Split-conformal lower bound: P(score_new >= q) >= 1 - alpha.

    With n exchangeable calibration scores, the k-th smallest with k = floor((n+1)*alpha)
    satisfies the guarantee. k must be at least 1, so n >= 1/alpha - 1 -- at alpha = 0.05
    that is 19 calibration points, and fewer means NO valid bound rather than a weak one.
    Returning a number anyway would be the failure this study keeps writing down.
    """
    n = len(scores)
    k = math.floor((n + 1) * alpha)
    if k < 1:
        raise SystemExit(
            f"{n} calibration illuminations cannot support a {1 - alpha:.0%} bound: "
            f"floor((n+1)*alpha) = {k}, and at least 1 is needed. Use n >= "
            f"{math.ceil(1 / alpha - 1)} or a larger alpha.")
    return sorted(scores)[k - 1], k, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", default="P_cont")
    ap.add_argument("--scenario", default="lead", choices=["lead", "ped"])
    ap.add_argument("--from-deg", type=float, default=None)
    ap.add_argument("--to-deg", type=float, default=None)
    ap.add_argument("--n", type=int, default=40, help="calibration illuminations")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from capture_campaign import load_uncovered
    if args.from_deg is None or args.to_deg is None:
        unc = load_uncovered()
        if not unc:
            raise SystemExit("no uncovered sub-interval in the knot file, and no "
                             "--from-deg/--to-deg given")
        args.from_deg, args.to_deg = unc[0]["from_deg"], unc[0]["to_deg"]
        print(f"  defaulting to the declared-uncovered sub-interval "
              f"[{args.from_deg:+.3f}, {args.to_deg:+.3f}] deg")

    from gpu import require_cuda
    from run_policy import load_policy, preprocess
    import torch
    carla = J.carla_module()
    dev = require_cuda()
    model, w, h = load_policy(args.policy, args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max_g, t_lat = b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2
    threshold = a_max_g * 9.81 * 0.5
    r_req = J.r_req_m(J.HAZARD_MPH * J.MPH, a_max_g, t_lat)

    raw = json.loads((CAPTURES / f"states_{args.scenario}.json").read_text())
    poses = [i for i, s in enumerate(raw) if s["range_m"] <= r_req]
    states = [carla.Transform(
        carla.Location(x=s["ego"][0], y=s["ego"][1], z=s["ego"][2]),
        carla.Rotation(pitch=s["ego"][3], yaw=s["ego"][4], roll=s["ego"][5]))
        for s in raw]
    others = [carla.Transform(
        carla.Location(x=s["other"][0], y=s["other"][1], z=s["other"][2] + 0.5),
        carla.Rotation(pitch=s["other"][3], yaw=s["other"][4], roll=s["other"][5]))
        for s in raw]

    rng = np.random.default_rng(args.seed)
    lo, hi = min(args.from_deg, args.to_deg), max(args.from_deg, args.to_deg)
    # i.i.d. uniform draws are what makes the calibration scores exchangeable, which is
    # the only assumption the guarantee rests on. Rendered, never blended: the whole
    # reason this sub-interval has no certificate is that its blends are not real images.
    alts = sorted(rng.uniform(lo, hi, size=args.n).tolist(), reverse=True)

    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)
    spawn_tf, _ = J.site_transform(world, site, along=10.0, need_m=200.0)

    rows = []
    for alt in alts:
        ego = other = cam = None
        try:
            ego = J.spawn_hero(world, spawn_tf)
            bp = world.get_blueprint_library().filter(
                "vehicle.audi.tt" if args.scenario == "lead" else "walker.pedestrian.*")[0]
            other = world.try_spawn_actor(bp, others[0])
            images: "queue.Queue" = queue.Queue()
            cam = world.spawn_actor(J.rgb_camera_bp(world),
                                    carla.Transform(carla.Location(x=1.5, z=1.6)),
                                    attach_to=ego)
            cam.listen(images.put)
            wx = world.get_weather()
            wx.sun_altitude_angle = float(alt)
            wx.cloudiness = J.CLOUDINESS
            wx.precipitation = 0.0
            world.set_weather(wx)
            ego.set_light_state(carla.VehicleLightState(
                carla.VehicleLightState.LowBeam if alt < 5.0
                else carla.VehicleLightState.NONE))
            for _ in range(J.WEATHER_SETTLE_TICKS):
                J.grab_frame(world, images)

            worst, sig = None, None
            for i in poses:
                ego.set_target_velocity(carla.Vector3D(0, 0, 0))
                ego.set_target_angular_velocity(carla.Vector3D(0, 0, 0))
                ego.set_transform(states[i])
                if other is not None:
                    other.set_transform(others[i])
                for _ in range(J.SETTLE_TICKS):
                    J.grab_frame(world, images)
                img = J.grab_frame(world, images)
                if sig is None:
                    arr = np.frombuffer(img.raw_data, dtype=np.uint8).reshape(
                        (img.height, img.width, 4))[:, :, :3]
                    sig = CS.signature(arr)
                with torch.no_grad():
                    y = float(model(preprocess(img, w, h, dev)).item())
                worst = y if worst is None else min(worst, y)
        finally:
            if cam is not None:
                cam.stop()
            J.despawn(world, cam, ego, other)
        rows.append({"sun_altitude_deg": round(float(alt), 5),
                     "min_demand_mps2": round(worst, 5), "signature": sig})
        J.progress(f"  sun {alt:+9.5f}  min demand over {len(poses)} poses "
                   f"{worst:7.3f}  {'>= threshold' if worst >= threshold else 'BELOW'}")

    scores = [r["min_demand_mps2"] for r in rows]
    q, k, n = conformal_lower_bound(scores, args.alpha)
    empirical_below = sum(1 for s in scores if s < threshold)

    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "sub_interval_deg": [args.from_deg, args.to_deg],
        "is_declared_uncovered": any(
            abs(u["from_deg"] - args.from_deg) < 1e-6 and abs(u["to_deg"] - args.to_deg) < 1e-6
            for u in load_uncovered()),
        "n_calibration": n,
        "alpha": args.alpha,
        "order_statistic_k": k,
        "conformal_lower_bound_mps2": round(q, 5),
        "brake_decision_threshold_mps2": round(threshold, 4),
        "bound_clears_threshold": q >= threshold,
        "margin_x_threshold": round(q / threshold, 4),
        "empirical_illuminations_below_threshold": empirical_below,
        "poses_inside_r_req": len(poses),
        "quantifier": (
            f"For an illumination drawn uniformly at random from "
            f"[{min(args.from_deg, args.to_deg):+.3f}, {max(args.from_deg, args.to_deg):+.3f}] "
            f"degrees of sun altitude, the policy's minimum commanded deceleration over "
            f"the poses inside r_req is at least {q:.4f} m/s^2 with probability at least "
            f"{1 - args.alpha:.0%}. THIS IS NOT A FOR-ALL STATEMENT. The certificate "
            f"quantifies over every illumination in a sub-interval; this quantifies over "
            f"a random one and attaches a probability. They are different claims and must "
            f"never be reported as the same one."),
        "calibration": rows,
    }
    suffix = "" if args.scenario == "lead" else f"_{args.scenario}"
    tag = f"{args.from_deg:+.3f}_{args.to_deg:+.3f}".replace("+", "p").replace("-", "m")
    path = OUT / f"conformal_{args.policy}{suffix}_{tag}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"\n  n = {n}, alpha = {args.alpha}, using the k = {k} smallest score")
    print(f"  conformal lower bound {q:.4f} m/s^2 = {q / threshold:.2f}x the decision "
          f"threshold -> {'CLEARS' if q >= threshold else 'DOES NOT CLEAR'}")
    print(f"  empirically {empirical_below}/{n} sampled illuminations fell below it")
    print(f"\n  {payload['quantifier']}")
    print(f"\n  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
