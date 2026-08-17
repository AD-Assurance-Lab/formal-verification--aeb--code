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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRAKING = REPO / "results" / "carla" / "braking.json"
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

    results = json.loads(RESULTS.read_text())
    results["primitives"] = {
        "a_max_g": round(a_worst, 4),
        "t_lat_s": round(t_worst, 3),
        "d_margin_ft": round(D_MARGIN_M * FT, 2),
        **budget,
    }
    results["milestones"]["M2"] = {
        "state": "in_progress",
        "note": f"braking measured ({len(runs)} runs); contact detector and oracle still to do",
    }
    RESULTS.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\n  recorded in study/results.json\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
