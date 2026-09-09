"""What would it have cost to find the same failures by SEARCHING instead of certifying?

    python tools/falsification_baseline.py --policy P_pts --scenario lead --method random
    python tools/falsification_baseline.py --policy P_pts --scenario lead --method surrogate
    python tools/falsification_baseline.py --compare --policy P_pts --scenario lead

**Why this exists.** The study's headline is that a certificate named the illuminations
where a compliant policy fails, without simulating them. The first thing a Tier 1 or a
reviewer will say is *"twenty random samples would have found that too"*, and right now the
paper has no answer, because it never ran the search. This is that baseline.

**It is designed to be a FAIR baseline, not a strawman.** Three methods, and the third is
the strongest thing a practitioner would actually reach for:

  regulatory  drive only the lighting conditions FMVSS 127 tests. The study's premise is
              that this finds nothing, and it is here to be the floor rather than to lose.
  random      sample sun altitude uniformly over the declared axis and drive it. Repeated
              over many search seeds, so the answer is a DISTRIBUTION of runs-to-first-
              failure rather than one lucky or unlucky number.
  surrogate   evaluate the policy on the CAPTURED frames at every knot -- free, no
              simulator -- pick the altitude whose predicted deceleration is lowest, and
              drive that. This is falsification guided by the network's own output, it
              costs almost no simulator time, and it is the honest competitor.

**What the comparison can and cannot show.** Search can find a failure; it cannot certify
absence. If the surrogate finds a failure in three runs, that is a real and useful result
for the search method and it does not touch the statement the certificate makes about the
sub-intervals where nothing fails. So this tool reports two things side by side:

  cost to first failure       where search competes, and may well win
  width of the violating band search maps a POINT; the certificate maps an INTERVAL

The second is the one the product is sold on, and it is why a cheap search result is not
an argument against the method. Reporting both is what makes the claim credible instead of
defensive.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import stats as ST  # noqa: E402

OUT = J.REPO / "results" / "carla"
CAPTURES = J.REPO / "results" / "captures"
AXIS_HI, AXIS_LO = 60.0, -30.0
REGULATORY = [60.0, -30.0]


def _cell_failed(runs) -> bool:
    """PROTOCOL section 7's frozen closed-loop pass, applied to one sampled altitude.

    No contact and standoff at least d_margin. Prematurity is deliberately NOT here: it
    is a must-not-brake condition and belongs to property A (FINDINGS F9), and a search
    baseline for property S that counted nuisance stops as finds would beat the
    certificate by finding the wrong thing.
    """
    return any(r["contact"] or not r["standoff_ok"] for r in runs)


def surrogate_ranking(policy: str, scenario: str, w: int, h: int, dev, model):
    """Rank illuminations by the policy's own output on the captured frames. No simulator.

    The cheapest possible falsifier: the network already tells you where it is least
    inclined to brake, and the frames are on disk. If a practitioner had these captures
    they would do this first, so the certificate has to beat it on something other than
    finding one failure.
    """
    import torch
    from verify import prepare
    rr = json.loads((OUT / "braking.json").read_text())
    a_max_g, t_lat = rr["a_max_g_worst"], rr["t_lat_s_worst"] or 0.2
    r_req = J.r_req_m(J.HAZARD_MPH * J.MPH, a_max_g, t_lat)
    states = json.loads((CAPTURES / f"states_{scenario}.json").read_text())
    poses = [i for i, s in enumerate(states) if s["range_m"] <= r_req]

    rows = []
    for path in sorted(CAPTURES.glob(f"{scenario}_sun*.npz")):
        d = np.load(path)
        alt = float(d["sun_altitude_deg"])
        imgs = d["images"]
        worst = None
        for i in poses:
            t = prepare(imgs[i], w, h).unsqueeze(0).to(dev)
            with torch.no_grad():
                y = float(model(t).item())
            worst = y if worst is None else min(worst, y)
        rows.append({"sun_altitude_deg": round(alt, 3), "worst_demand_mps2": round(worst, 4)})
    rows.sort(key=lambda r: r["worst_demand_mps2"])
    return rows


def drive_at(world, site, model, w, h, dev, a_max, r_req_m, scenario, alt, reps):
    from run_policy import one_run, PREMATURE_MULTIPLE
    carla = J.carla_module()
    wx = world.get_weather()
    wx.sun_altitude_angle = alt
    wx.cloudiness = 10.0
    wx.precipitation = 0.0
    world.set_weather(wx)
    for _ in range(J.WEATHER_SETTLE_TICKS):
        world.tick()
    lights = "LowBeam" if alt < 5.0 else "NONE"
    runs = [one_run(world, site, model, w, h, dev, a_max, J.HAZARD_MPH, lights,
                    scenario=scenario, release_r_req_m=r_req_m)
            for _ in range(reps)]
    for r in runs:
        r["premature"] = (r["brake_range_ft"] is not None
                          and r["brake_range_ft"] > r_req_m * J.FT * PREMATURE_MULTIPLE)
    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", default="P_pts")
    ap.add_argument("--scenario", default="lead", choices=["lead", "ped"])
    ap.add_argument("--method", choices=["regulatory", "random", "surrogate"],
                    default="random")
    ap.add_argument("--budget", type=int, default=40,
                    help="simulator RUNS the search is allowed, not samples")
    ap.add_argument("--reps", type=int, default=J.REPS,
                    help="repetitions per sampled illumination")
    ap.add_argument("--search-seeds", type=int, default=8,
                    help="independent random searches, so the answer is a distribution")
    ap.add_argument("--compare", action="store_true",
                    help="summarise whatever baselines are on disk against the certificate")
    args = ap.parse_args()

    suffix = "" if args.scenario == "lead" else f"_{args.scenario}"
    if args.compare:
        v = json.loads((OUT / f"verify_{args.policy}_{args.scenario}.json").read_text())
        covered = [c for c in v["cells"] if not c.get("family_uncovered")]
        fals = [c for c in covered if c["verdict"] == "FALSIFIED"]
        width = sum(c["from_deg"] - c["to_deg"] for c in fals)
        report = {
            "policy": args.policy, "scenario": args.scenario,
            "certificate": {
                "sub_intervals_covered": len(covered),
                "certified": len(covered) - len(fals),
                "falsified": len(fals),
                "violating_width_deg": round(width, 3),
                "axis_width_deg": AXIS_HI - AXIS_LO,
                "fraction_of_axis_falsified": round(width / (AXIS_HI - AXIS_LO), 4),
                "simulator_runs": 0,
                "note": ("The certificate quantifies over every illumination in each "
                         "covered sub-interval and uses no simulator. Its product is the "
                         "WIDTH, and the statement about the sub-intervals where nothing "
                         "fails, which no amount of sampling can produce."),
            },
            "baselines": {},
        }
        for m in ("regulatory", "random", "surrogate"):
            path = OUT / f"falsification_{m}_{args.policy}{suffix}.json"
            if path.exists():
                report["baselines"][m] = json.loads(path.read_text())["summary"]
        (OUT / f"falsification_compare_{args.policy}{suffix}.json").write_text(
            json.dumps(report, indent=2) + "\n")
        c = report["certificate"]
        print(f"\n  {args.policy} / {args.scenario}")
        print(f"    certificate   0 simulator runs, {c['certified']}/"
              f"{c['sub_intervals_covered']} sub-intervals certified, "
              f"{c['violating_width_deg']:.2f} deg of violating band mapped")
        for m, s in report["baselines"].items():
            print(f"    {m:11s}   {s.get('runs_to_first_failure')} runs to first failure"
                  f"   {s.get('altitudes_failed_count', 0)} failing altitude(s) found")
        print(f"\n  wrote falsification_compare_{args.policy}{suffix}.json")
        return 0

    from gpu import require_cuda
    from run_policy import load_policy
    dev = require_cuda()
    model, w, h = load_policy(args.policy, args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    r_req_m = J.r_req_m(J.HAZARD_MPH * J.MPH, b["a_max_g_worst"],
                        b["t_lat_s_worst"] or 0.2)

    ranking = None
    if args.method == "surrogate":
        ranking = surrogate_ranking(args.policy, args.scenario, w, h, dev, model)
        print(f"  surrogate ranked {len(ranking)} captured illuminations offline; "
              f"lowest predicted demand at {ranking[0]['sun_altitude_deg']:+.3f} deg")

    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)

    searches = []
    t0 = time.time()
    seeds = (range(args.search_seeds) if args.method == "random" else [0])
    for seed in seeds:
        rng = random.Random(1000 + seed)
        if args.method == "regulatory":
            order = list(REGULATORY)
        elif args.method == "surrogate":
            order = [r["sun_altitude_deg"] for r in ranking]
        else:
            order = [rng.uniform(AXIS_LO, AXIS_HI)
                     for _ in range(max(1, args.budget // args.reps))]

        used, first, samples = 0, None, []
        for alt in order:
            if used + args.reps > args.budget:
                break
            runs = drive_at(world, site, model, w, h, dev, a_max, r_req_m,
                            args.scenario, alt, args.reps)
            used += args.reps
            failed = _cell_failed(runs)
            n_pass = sum(1 for r in runs if not r["contact"] and r["standoff_ok"])
            samples.append({"sun_altitude_deg": round(alt, 3),
                            **ST.rate(n_pass, args.reps), "failed": failed})
            J.progress(f"  seed {seed} sun {alt:+8.3f}  {ST.fmt(n_pass, args.reps)}"
                       f"  {'FAILURE FOUND' if failed else ''}")
            if failed and first is None:
                first = used
                break
        searches.append({"seed": seed, "runs_used": used,
                         "runs_to_first_failure": first, "samples": samples})

    found = [s["runs_to_first_failure"] for s in searches
             if s["runs_to_first_failure"] is not None]
    failing_alts = sorted({round(sm["sun_altitude_deg"], 3)
                           for s in searches for sm in s["samples"] if sm["failed"]})
    summary = {
        "method": args.method,
        "budget_runs": args.budget,
        "reps_per_sample": args.reps,
        "searches": len(searches),
        "searches_that_found_a_failure": len(found),
        "runs_to_first_failure": (int(np.median(found)) if found else None),
        "runs_to_first_failure_all": found,
        "altitudes_failed": failing_alts,
        "altitudes_failed_count": len(failing_alts),
        "wall_clock_s": round(time.time() - t0, 1),
        "note": ("Search finds a POINT. The certificate states a WIDTH and covers the "
                 "sub-intervals where nothing fails, which sampling cannot do at any "
                 "budget. Cost-to-first-failure is where search competes and it may win."),
    }
    payload = {"policy": args.policy, "scenario": args.scenario,
               "summary": summary, "searches": searches}
    path = OUT / f"falsification_{args.method}_{args.policy}{suffix}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  {args.method}: {len(found)}/{len(searches)} searches found a failure; "
          f"median {summary['runs_to_first_failure']} runs")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
