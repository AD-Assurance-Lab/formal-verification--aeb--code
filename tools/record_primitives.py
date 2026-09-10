"""Turn the braking measurement into the safety budget, and record it.

    python tools/record_primitives.py

Reads results/carla/braking.json, computes r_req at each test speed per PROTOCOL
section 3, and writes the numbers into study/results.json so `python -m study.status`
reports them.

The worst measured deceleration is used, not the median. A budget built on the median
is a budget that is wrong half the time.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPO, OUT  # noqa: E402

BRAKING = OUT / "braking.json"
RESULTS = REPO / "study" / "results.json"

G = 9.81
MPH = 0.44704
FT = 3.280839895
FIXED_DT = 0.05
D_MARGIN_M = 1.0  # declared, not fitted
SPEEDS_MPH = (25.0, 50.0)


def r_req_m(v_mps: float, a_max_g: float, t_lat_s: float) -> float:
    return v_mps * (t_lat_s + FIXED_DT) + v_mps**2 / (2.0 * a_max_g * G) + D_MARGIN_M


def main() -> int:
    if not BRAKING.exists():
        print("No braking measurement yet. Run: python tools/carla_jobs.py --job braking")
        return 1
    b = json.loads(BRAKING.read_text())
    runs = [r for r in b.get("runs", []) if r.get("a_avg_g")]
    if not runs:
        print("braking.json has no usable runs")
        return 1

    by_speed: dict[float, list[dict]] = {}
    for r in runs:
        by_speed.setdefault(r["speed_mph"], []).append(r)

    print(f"\n{len(runs)} braking runs on a {b.get('site_run_ft', '?')} ft straight\n")
    print(f"  {'speed':>7} {'n':>3} {'a worst':>9} {'a median':>9} {'spread':>8} {'t_lat':>7} {'grade':>7}")
    for speed in sorted(by_speed):
        rs = by_speed[speed]
        accels = [r["a_avg_g"] for r in rs]
        lats = [r["t_lat_s"] for r in rs if r.get("t_lat_s")]
        grades = [r["grade_pct"] for r in rs if r.get("grade_pct") is not None]
        print(
            f"  {speed:6.0f}m {len(rs):3d} {min(accels):9.4f} "
            f"{statistics.median(accels):9.4f} "
            f"{max(accels) - min(accels):8.4f} "
            f"{(max(lats) if lats else 0):7.3f} "
            f"{(statistics.median(grades) if grades else 0):7.2f}"
        )

    a_worst = min(r["a_avg_g"] for r in runs)
    t_worst = max((r["t_lat_s"] for r in runs if r.get("t_lat_s")), default=0.2)

    print(f"\n  a_max = {a_worst:.4f} g (worst of {len(runs)}), t_lat = {t_worst:.3f} s")
    print(f"  d_margin = {D_MARGIN_M} m ({D_MARGIN_M * FT:.1f} ft), declared not fitted\n")
    print(f"  {'speed':>7} {'r_req':>10} {'r_req':>10}")
    budget = {}
    for mph in SPEEDS_MPH:
        rr = r_req_m(mph * MPH, a_worst, t_worst)
        budget[f"r_req_ft_at_{mph:g}mph"] = round(rr * FT, 1)
        print(f"  {mph:6.0f}m {rr:9.1f} m {rr * FT:9.1f} ft")

    # The SAME stops read from the distance they covered. PROTOCOL section 3 defines
    # a_max from the stop TIME and that stays the primitive; this is the consistency
    # check that condemned the pre-A12 value, where the two readings differed by 39%
    # because a five-substep integrator could not resolve the brake transient (F5). It
    # belongs in the recorded block, not only in braking.json, because study.status is
    # where anyone looks and a budget whose two readings disagree is not a budget.
    a_dist = b.get("a_from_dist_g_worst")
    disagree = (abs(a_worst - a_dist) / a_worst) if a_dist else None
    if disagree is not None and disagree > 0.10:
        print(f"\n  REFUSING: a_max from time is {a_worst:.4f} g and from distance "
              f"{a_dist:.4f} g, {disagree * 100:.1f}% apart. One stop has one average "
              f"deceleration; if these disagree the integrator is not resolving the stop "
              f"and neither number describes the vehicle (FINDINGS F5).")
        return 1

    results = json.loads(RESULTS.read_text())
    prev = results.get("primitives", {})
    results["primitives"] = {
        "a_max_g": round(a_worst, 4),
        "a_max_g_from_distance": round(a_dist, 4) if a_dist else None,
        "t_lat_s": round(t_worst, 3),
        "d_margin_ft": round(D_MARGIN_M * FT, 2),
        **budget,
        # Not derivable from braking.json: they are the network's input geometry, set by
        # training, and they are reported here because every certificate is a statement
        # about images of exactly this size. Carried forward rather than defaulted, so
        # this tool cannot silently drop a field a later hand-edit added -- which is how
        # three of them went missing from the committed block in the first place.
        "input_w": prev.get("input_w"),
        "input_h": prev.get("input_h"),
        "_note": ("a_max is read from the stop TIME, as PROTOCOL section 3 defines it; "
                  "a_max_g_from_distance reads the same stops from the distance covered "
                  "and is the consistency check that condemned the pre-A12 value "
                  "(FINDINGS F5)."),
    }
    # M2 covers the primitives AND the contact detector AND both oracles, so this tool
    # is not entitled to set its state: it knows about one of the three. It used to
    # stamp "in_progress, contact detector and oracle still to do" unconditionally,
    # which silently reopened a finished milestone every time the budget was recomputed.
    RESULTS.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\n  recorded in study/results.json (M2's state is carla_jobs' to set, "
          f"not this tool's)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
