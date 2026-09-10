"""Is the measured braking authority a property of the vehicle, or of the integrator?

    python tools/substep_convergence.py

**Why this exists.** Rebuilding the study on the corrected harness (amendment A12) moved
`a_max` from 0.868 g to 0.505 g at 25 mph -- a 42% change in the primitive the entire
safety budget is derived from. A12 changed two things at once in `connect()`:

  D-2  vehicle commands became ACKNOWLEDGED (`cd.apply_control`) instead of
       fire-and-forget, so a brake command can no longer race the tick it belongs to.
  D-1  physics substepping became EXPLICIT at 16 x 0.003125 s. Before A12 the study
       inherited CARLA's default, 10 x 0.01 s, which at `fixed_delta_seconds = 0.05`
       means the whole 50 ms step was integrated in FIVE substeps.

Either could move a braking number, and CLAUDE.md section 8 says a result that
contradicts its expectation is a bug until a written disposition rules the candidates
out. This is that disposition, run as a measurement rather than argued.

**The method is a step-size convergence study**, which is the only way to tell an
integration artifact from a vehicle property: sweep the substep count with everything
else fixed and see whether the answer settles. If stopping distance converges as the
substep shrinks, the converged value is the vehicle and the coarse value was the
integrator. If it does not converge, no substep setting is defensible and the primitive
cannot be quoted at all.

D-2 is held ON throughout, so this sweep isolates D-1. The D-2 arm is run separately and
reported alongside, because turning it off is a deliberate rule violation and must not be
something this script does by default.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.OUT / "substep_convergence.json"

# Substeps per 0.05 s step. 5 is what CARLA's default (10 x 0.01 s) actually delivers at
# this fixed_delta; 16 is what connect() sets today.
#
# 16 IS THE CEILING. CARLA prints "the number of substeps is not valid ... needs to be in
# the range [1-16]" and clamps anything larger, so an arm at 32 or 64 is not a finer
# integration, it is the 16-substep arm wearing a different label. Measured: 32 and 64
# returned 45.9 and 45.3 ft against 16's 44.7, and the whole difference is the PI settle
# leaving v0 at 25.9 / 25.6 / 25.5 mph -- a(dist) is 0.4886 / 0.4851 / 0.4865 g, one
# number three times. Those arms are not run.
SUBSTEP_COUNTS = [2, 4, 5, 8, 16]
MAX_SUBSTEPS_CARLA = 16

# Substepping saturates before it can prove convergence, so the finer physics is reached
# the other way: shrink the step being subdivided. These arms run at 16 substeps each, so
# 0.0125 s integrates at 0.78 ms against the study's 3.12 ms.
#
# This is a PHYSICS check, not a study configuration. CLAUDE.md section 1 fixes the control
# rate at 20 Hz and every measured cell runs at FIXED_DT; these arms exist only to answer
# "has the vehicle's braking stopped moving with the integrator", and the answer is quoted
# as evidence for the primitive, never substituted for it.
DT_ARMS = [0.05, 0.025, 0.0125]
REPS = 3  # a convergence sweep is a trend, not a rate; the per-cell rate is job_braking


def _set_substeps(world, n: int, dt: float = J.FIXED_DT) -> None:
    if n > MAX_SUBSTEPS_CARLA:
        raise ValueError(
            f"max_substeps={n} exceeds CARLA's ceiling of {MAX_SUBSTEPS_CARLA}; it would "
            "be clamped and the arm would silently duplicate the 16-substep arm")
    s = world.get_settings()
    s.synchronous_mode = True
    s.fixed_delta_seconds = dt
    s.substepping = True
    s.max_substeps = n
    s.max_substep_delta_time = dt / n
    s.no_rendering_mode = True
    world.apply_settings(s)
    world.tick()  # settings apply on the NEXT tick, never on the call


def _trace_stop(world, ego, spawn, target_mps: float, dt: float = J.FIXED_DT) -> dict:
    """One full-brake stop, keeping the per-tick speed trace.

    The trace is the point. `job_braking` records v0, distance and stop time, and those
    three are enough to catch an inconsistent measurement: for a stop with latency
    `t_lat` then constant deceleration, distance and time are not independent. The
    pre-A12 numbers were NOT consistent in that sense (10.8 m travelled in a 1.35 s stop
    from 11.5 m/s, where uniform deceleration gives 7.8 m), which is the first thing that
    made the old value suspect.
    """
    carla = J.carla_module()
    yaw = math.radians(spawn.rotation.yaw)
    ego.set_target_velocity(
        carla.Vector3D(x=target_mps * math.cos(yaw), y=target_mps * math.sin(yaw), z=0.0)
    )
    integral = 0.0
    for _ in range(int(J.MAX_SETTLE_TICKS * J.FIXED_DT / dt)):
        err = target_mps - J.speed_of(ego)
        integral = max(-20.0, min(20.0, integral + err * dt))
        cmd = 0.5 * err + 0.5 * integral
        J.apply_control(ego, carla.VehicleControl(
            throttle=max(0.0, min(1.0, cmd)),
            brake=max(0.0, min(1.0, -cmd * 0.2)),
        ))
        world.tick()
        if abs(err) < J.SETTLE_TOLERANCE_MPS:
            break

    v0 = J.speed_of(ego)
    start = ego.get_transform().location
    J.apply_control(ego, carla.VehicleControl(throttle=0.0, brake=1.0))

    speeds = [v0]
    ticks = 0
    while J.speed_of(ego) > 0.1 and ticks < int(600 * J.FIXED_DT / dt):
        world.tick()
        ticks += 1
        speeds.append(J.speed_of(ego))

    end = ego.get_transform().location
    dist = math.hypot(end.x - start.x, end.y - start.y)
    stop_s = ticks * dt

    # Peak deceleration over any single tick, and the deceleration implied by the
    # distance actually travelled. If the second disagrees with v0/stop_s, the run is
    # not a constant-deceleration stop and the average is hiding something.
    per_tick = [(speeds[i] - speeds[i + 1]) / dt for i in range(len(speeds) - 1)]
    onset = next((i * dt for i, a in enumerate(per_tick, 1) if a > 0.5), None)
    return {
        "v0_mps": round(v0, 4),
        "stop_m": round(dist, 4),
        "stop_s": round(stop_s, 3),
        "t_lat_s": round(onset, 3) if onset else None,
        "a_from_time_g": round(v0 / stop_s / 9.81, 4) if stop_s else None,
        # v0^2 / 2d is the deceleration the DISTANCE implies. For a clean stop these two
        # agree once latency is taken out; when they disagree the measurement is wrong.
        "a_from_dist_g": round(v0 * v0 / (2.0 * dist) / 9.81, 4) if dist > 0.1 else None,
        "a_peak_tick_g": round(max(per_tick) / 9.81, 4) if per_tick else None,
        "speeds_mps": [round(s, 4) for s in speeds],
    }


def _summarise(runs, substep_ms: float, dt_s: float) -> dict:
    return {
        "dt_s": dt_s,
        "substep_ms": round(substep_ms, 4),
        "stop_m_median": round(statistics.median(r["stop_m"] for r in runs), 4),
        "a_from_time_g_median": round(
            statistics.median(r["a_from_time_g"] for r in runs), 4),
        "a_from_dist_g_median": round(
            statistics.median(r["a_from_dist_g"] for r in runs), 4),
        "t_lat_s_worst": max((r["t_lat_s"] for r in runs if r["t_lat_s"]), default=None),
        "stop_m_spread": round(
            max(r["stop_m"] for r in runs) - min(r["stop_m"] for r in runs), 4),
        "runs": runs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--speed-mph", type=float, default=J.HAZARD_MPH)
    ap.add_argument("--reps", type=int, default=REPS)
    args = ap.parse_args()

    client, world = J.connect(rendering=False)
    site = J.flattest_site()
    spawn, _ = J.site_transform(world, site, along=10.0, need_m=160.0)
    ego = J.spawn_hero(world, spawn)

    arms = {}
    dt_arms = {}
    try:
        for n in SUBSTEP_COUNTS:
            _set_substeps(world, n)
            runs = []
            for rep in range(args.reps):
                J.reset_vehicle(world, ego, spawn)
                r = _trace_stop(world, ego, spawn, args.speed_mph * J.MPH)
                runs.append(r)
                J.progress(
                    f"{n:2d} substeps ({J.FIXED_DT / n * 1000:.2f} ms) rep {rep + 1}: "
                    f"v0 {r['v0_mps'] / J.MPH:.1f} mph, stop {r['stop_m'] * J.FT:.1f} ft "
                    f"in {r['stop_s']:.2f} s, a(time) {r['a_from_time_g']} g, "
                    f"a(dist) {r['a_from_dist_g']} g"
                )
            arms[str(n)] = _summarise(runs, substep_ms=J.FIXED_DT / n * 1000,
                                      dt_s=J.FIXED_DT)

        print()
        for dt in DT_ARMS:
            _set_substeps(world, MAX_SUBSTEPS_CARLA, dt=dt)
            runs = []
            for rep in range(args.reps):
                J.reset_vehicle(world, ego, spawn)
                r = _trace_stop(world, ego, spawn, args.speed_mph * J.MPH, dt=dt)
                runs.append(r)
                J.progress(
                    f"dt {dt * 1000:5.1f} ms x16 ({dt / 16 * 1000:.2f} ms) rep {rep + 1}: "
                    f"v0 {r['v0_mps'] / J.MPH:.1f} mph, stop {r['stop_m'] * J.FT:.1f} ft "
                    f"in {r['stop_s']:.2f} s, a(dist) {r['a_from_dist_g']} g"
                )
            dt_arms[f"{dt:g}"] = _summarise(runs, substep_ms=dt / 16 * 1000, dt_s=dt)
    finally:
        J.despawn(world, ego)
        _set_substeps(world, MAX_SUBSTEPS_CARLA)  # leave the world as connect() has it

    def _deltas(d, keys, field="a_from_dist_g_median"):
        """Convergence is judged on a(dist), NOT on raw stopping distance.

        The arms do not start from identical speeds -- the PI hold exits on a tolerance,
        so v0 lands at 25.5, 25.1 and 24.9 mph across the dt arms -- and stopping
        distance goes as v^2, so comparing distances directly reports the settle
        controller as if it were the integrator. a(dist) = v0^2 / 2d divides that out.
        The first version of this function compared distances and declared the sweep
        NOT_CONVERGED at 1.85 and 1.25 percent, where the same runs converge at 1.29
        and 0.69 on the variable that actually isolates the physics.
        """
        out = {}
        for a, b in zip(keys, keys[1:]):
            da, db = d[a][field], d[b][field]
            out[f"{a}->{b}"] = round(100.0 * (db - da) / da, 2)
        return out

    sub_keys = [str(n) for n in SUBSTEP_COUNTS]
    dt_keys = [f"{v:g}" for v in DT_ARMS]
    sub_deltas = _deltas(arms, sub_keys)
    dt_deltas = _deltas(dt_arms, dt_keys)
    sub_deltas_dist = _deltas(arms, sub_keys, "stop_m_median")
    dt_deltas_dist = _deltas(dt_arms, dt_keys, "stop_m_median")

    # The convergence question is asked of the DT sweep, because the substep knob
    # saturates at 16 before it can answer it. Converged means halving the integration
    # step no longer moves a(dist) by more than 1%.
    last_dt = dt_deltas[f"{dt_keys[-2]}->{dt_keys[-1]}"]
    converged = abs(last_dt) < 1.0

    # The self-consistency check, which is what actually condemns the old number: for a
    # stop that really is a stop, the deceleration implied by the TIME and the one
    # implied by the DISTANCE must agree. They cannot disagree by 40% unless the
    # integrator is not resolving the brake transient.
    consistency = {
        k: round(100.0 * (v["a_from_time_g_median"] - v["a_from_dist_g_median"])
                 / v["a_from_dist_g_median"], 1)
        for k, v in arms.items()
    }

    payload = {
        "speed_mph": args.speed_mph,
        "reps_per_arm": args.reps,
        "site_run_ft": site["run_ft"],
        "site_grade_pct": site.get("grade_pct"),
        "deterministic_control": True,
        "carla_max_substeps_ceiling": MAX_SUBSTEPS_CARLA,
        "scope": (
            "Substep arms run at fixed_delta_seconds = %.4f s, the study's control "
            "period. The dt arms run at 16 substeps each and are a PHYSICS convergence "
            "check only; no study cell runs at a dt other than %.4f s."
            % (J.FIXED_DT, J.FIXED_DT)
        ),
        "substep_arms": arms,
        "dt_arms": dt_arms,
        "convergence_variable": "a_from_dist_g_median (v0^2/2d, so v0 differences "
                                "between arms do not enter)",
        "pct_change_in_a_from_dist_by_substeps": sub_deltas,
        "pct_change_in_a_from_dist_by_dt": dt_deltas,
        "pct_change_in_raw_stop_distance_by_substeps": sub_deltas_dist,
        "pct_change_in_raw_stop_distance_by_dt": dt_deltas_dist,
        "a_time_vs_a_dist_pct_by_substeps": consistency,
        "converged": converged,
        "verdict": "CONVERGED" if converged else "NOT_CONVERGED",
        "note": (
            "D-2 acknowledged control is ON in every arm, so the trend is D-1 alone. "
            "a_from_time and a_from_dist are two readings of the same stop; where they "
            "disagree the integrator is not resolving the brake transient and the "
            "average deceleration is not a measurement of the vehicle."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"\n  a(dist) vs substeps: {sub_deltas}")
    print(f"  a(dist) vs dt (16 substeps): {dt_deltas}")
    print(f"  a(time) over a(dist), percent, by substeps: {consistency}")
    print(f"  verdict: {payload['verdict']}")
    print(f"  wrote {OUT.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
