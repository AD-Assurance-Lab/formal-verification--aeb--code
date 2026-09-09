"""One repetition, one process, one freshly restarted server. The harness the
repetition count is conditional on.

    python tools/repetition_probe.py --policy P_cont --scenario plate \
        --from-deg 0.026 --to-deg 0.0 --rep 3
    python tools/repetition_probe.py --report

**What this exists to settle.** `tools/drive_witness.py` drives ten repetitions of every
sub-interval inside one process against one server, which is what makes ten repetitions
look like ten independent trials when they are not: they share a simulator whose state
accumulates, and D-6 says restart before every measurement. Across the 281 committed
ten-repetition cells in this repository, 277 are unanimous and 4 are split -- and none of
the four looks like sampling. Two trace to a scoring defect (F21). One is a bimodal
brake-latch: two runs brake at 377 ft and pass, eight never brake at all and hit the
pedestrian. The fourth, `P_cont` on the trench plate in the uncovered sliver, brakes over
the nuisance limit on runs 0-3 and sails through on runs 4-9, with peak demand stepping
down from ~2.7 to ~2.1 m/s^2 between run 3 and run 4. A step in run INDEX inside a shared
server is the D-6 signature, and it is load-bearing: that cell is the study's only
certified-then-failed sub-interval (F19).

So the question this probe asks is not "what is the failure rate". It is: **does the split
survive when each repetition gets its own server and its own process?** If it does not,
the split was the harness and ten repetitions were measuring it. If it does, the cell is
genuinely marginal, which under the standing rule makes it VOID rather than a rate.

**Each repetition writes its own artifact** (D-9). A repetition that crashes leaves no
file rather than leaving the previous repetition's, which is the defect that once produced
a false "runs are reproducible" result in this lab.

The driven illumination is recomputed from the committed verdicts file with the same
arithmetic `drive_witness.py` uses, and then checked against what the witness artifact
says it drove. Reading it out of the witness artifact would be trusting an artifact's own
claim about itself, which standing rule 7 forbids; computing it and never checking would
let the probe drive a different condition and still look finished.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu import require_cuda  # noqa: E402
import carla_jobs as J  # noqa: E402
from run_policy import load_policy, one_run, plate_run, PREMATURE_MULTIPLE  # noqa: E402

OUT = J.REPO / "results" / "carla"
PROBE = OUT / "repprobe"


def cell_key(from_deg: float, to_deg: float) -> str:
    return f"{from_deg:+.3f}_{to_deg:+.3f}".replace("+", "p").replace("-", "m")


def artifact_name(policy: str, scenario: str, at_witness: bool) -> str:
    return f"witness_{policy}_{scenario}{'_atwitness' if at_witness else ''}"


def driven_altitude(cell: dict, at_witness: bool) -> float:
    """The same arithmetic drive_witness.py uses, and it is not allowed to drift.

    s runs from the sub-interval's BRIGHT knot at -1 to its DARK knot at +1, which is how
    tools/verify.py builds the family."""
    if at_witness:
        s = cell["witness_s"]
        return cell["from_deg"] + (s + 1.0) / 2.0 * (cell["to_deg"] - cell["from_deg"])
    return (cell["from_deg"] + cell["to_deg"]) / 2.0


def drive_one(args) -> int:
    plate = args.scenario in ("plate", "none_plate")
    place_plate = args.scenario == "plate"
    verdicts_path = OUT / (f"verify_{args.policy}_{args.scenario}_A.json" if plate
                           else f"verify_{args.policy}_{args.scenario}.json")
    if not verdicts_path.exists():
        raise SystemExit(f"no verdicts at {verdicts_path}")
    verdicts = json.loads(verdicts_path.read_text())

    match = [c for c in verdicts["cells"]
             if abs(c["from_deg"] - args.from_deg) < 1e-6
             and abs(c["to_deg"] - args.to_deg) < 1e-6]
    if len(match) != 1:
        raise SystemExit(
            f"[{args.from_deg}, {args.to_deg}] matches {len(match)} sub-intervals in "
            f"{verdicts_path.name}; it must match exactly one")
    cell = match[0]
    if args.at_witness and cell.get("witness_s") is None:
        raise SystemExit("--at-witness needs an exhibited witness_s on this sub-interval")
    mid = driven_altitude(cell, args.at_witness)

    # Two-sided: the probe must drive the illumination the ten-repetition drive drove, or
    # the comparison is between two different experiments. Checked against the committed
    # witness artifact rather than assumed.
    ref_path = OUT / f"{artifact_name(args.policy, args.scenario, args.at_witness)}.json"
    ref_cell = None
    if ref_path.exists():
        for c in json.loads(ref_path.read_text())["cells"]:
            if (abs(c["from_deg"] - args.from_deg) < 1e-6
                    and abs(c["to_deg"] - args.to_deg) < 1e-6):
                ref_cell = c
        if ref_cell is not None and abs(ref_cell["driven_at_deg"] - round(mid, 3)) > 1e-3:
            raise SystemExit(
                f"this probe would drive {mid:+.3f} deg and {ref_path.name} says the "
                f"ten-repetition drive used {ref_cell['driven_at_deg']:+.3f} deg. One of "
                f"the two is not the experiment it claims to be.")

    dev = require_cuda()
    model, w, h = load_policy(args.policy, "lead" if plate else args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    r_req_ft = J.r_req_m(
        J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2) * J.FT

    key = cell_key(args.from_deg, args.to_deg)
    PROBE.mkdir(parents=True, exist_ok=True)
    out_path = J.claim_output(
        PROBE / f"{artifact_name(args.policy, args.scenario, args.at_witness)}"
                f"_{key}_rep{args.rep:02d}.json")

    client, world = J.connect(rendering=True)
    site = J.flattest_site()
    weather = world.get_weather()
    weather.sun_altitude_angle = mid
    weather.cloudiness = 10.0
    weather.precipitation = 0.0
    world.set_weather(weather)
    for _ in range(J.WEATHER_SETTLE_TICKS):
        world.tick()
    lights = "LowBeam" if mid < 5.0 else "NONE"

    if plate:
        run = plate_run(world, site, model, w, h, dev, J.PLATE_MPH, lights,
                        place=place_plate)
        passed = run["passes"]
    else:
        run = one_run(world, site, model, w, h, dev, a_max, J.HAZARD_MPH, lights,
                      scenario=args.scenario, release_r_req_m=r_req_ft / J.FT)
        run["premature"] = (run["brake_range_ft"] is not None
                            and run["brake_range_ft"] > r_req_ft * PREMATURE_MULTIPLE)
        # PROTOCOL section 7's frozen closed-loop pass, and only that. The nuisance
        # condition is property A and is recorded beside the verdict, never inside it.
        passed = (not run["contact"]) and run["standoff_ok"]
        run["passes"] = passed

    record = {
        "policy": args.policy,
        "scenario": args.scenario,
        "driven_at": "witness" if args.at_witness else "midpoint",
        "from_deg": args.from_deg,
        "to_deg": args.to_deg,
        "driven_at_deg": round(mid, 3),
        "rep": args.rep,
        "verdict": cell["verdict"],
        "passes": bool(passed),
        "headlamps": lights,
        # One server per repetition is the whole point, so the artifact has to be able to
        # prove it: a probe that silently reused a warm server would look exactly like a
        # probe that did not.
        "server_age_s": None,
        "run": run,
        "determinism": J.determinism_provenance(world),
        "provenance": {"git_sha": _git_sha(), "reference_artifact": ref_path.name},
    }
    record["server_age_s"] = record["determinism"].get("server_age_s")
    out_path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"  rep {args.rep:02d}  [{args.from_deg:+.3f},{args.to_deg:+.3f}] "
          f"at {mid:+.3f}  {'PASS' if passed else 'FAIL'}  "
          f"server age {record['server_age_s']}s  -> {out_path.name}", flush=True)
    return 0


def _git_sha():
    import subprocess
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                       cwd=str(J.REPO))
    return r.stdout.strip() or None


def report() -> int:
    """Aggregate the per-repetition artifacts and compare against the shared-server run.

    Reports the two numbers the amendment turns on: whether the probe agrees with the
    ten-repetition verdict, and whether the probe's own repetitions agree with each
    other. A split under this harness is a VOID cell; a split that disappears under it
    was the harness."""
    from math import comb
    groups: dict[tuple, list] = {}
    for p in sorted(PROBE.glob("*.json")):
        r = json.loads(p.read_text())
        groups.setdefault(
            (r["policy"], r["scenario"], r["driven_at"], r["from_deg"], r["to_deg"]),
            []).append(r)

    rows = []
    for k, recs in sorted(groups.items()):
        policy, scenario, driven_at, from_deg, to_deg = k
        recs.sort(key=lambda r: r["rep"])
        n = len(recs)
        p = sum(1 for r in recs if r["passes"])
        ages = [r.get("server_age_s") for r in recs if r.get("server_age_s") is not None]
        ref_name = artifact_name(policy, scenario, driven_at == "witness")
        ref = OUT / f"{ref_name}.json"
        ref_p = ref_n = None
        if ref.exists():
            for c in json.loads(ref.read_text())["cells"]:
                if (abs(c["from_deg"] - from_deg) < 1e-6
                        and abs(c["to_deg"] - to_deg) < 1e-6):
                    ref_p, ref_n = c.get("passes_protocol"), c.get("of")
        # The chance a k-repetition draw from the shared-server cell would have shown the
        # split at all. It is the detection power the repetition count actually buys.
        detect = None
        if ref_p is not None and ref_n and 0 < ref_p < ref_n:
            same = (comb(ref_p, n) if ref_p >= n else 0) + (
                comb(ref_n - ref_p, n) if ref_n - ref_p >= n else 0)
            detect = round(1.0 - same / comb(ref_n, n), 4)
        rows.append({
            "policy": policy, "scenario": scenario, "driven_at": driven_at,
            "from_deg": from_deg, "to_deg": to_deg,
            "verdict": recs[0]["verdict"],
            "probe_passes": p, "probe_of": n,
            "probe_unanimous": p in (0, n),
            "shared_server_passes": ref_p, "shared_server_of": ref_n,
            "shared_server_unanimous": None if ref_p is None else ref_p in (0, ref_n),
            "verdict_agrees": None if ref_p is None else (p == n) == (ref_p == ref_n),
            "prob_a_run_of_n_shows_the_split": detect,
            "server_age_s": {"min": min(ages), "max": max(ages)} if ages else None,
            "per_rep": [{"rep": r["rep"], "passes": r["passes"],
                         **({"peak_demand_mps2": r["run"].get("peak_demand_mps2"),
                             "braked": r["run"].get("braked")}
                            if scenario in ("plate", "none_plate") else
                            {"min_gap_ft": r["run"].get("min_gap_ft"),
                             "rest_gap_ft": r["run"].get("rest_gap_ft"),
                             "brake_range_ft": r["run"].get("brake_range_ft"),
                             "brake_step": r["run"].get("brake_step"),
                             "speed_at_brake_mps": r["run"].get("speed_at_brake_mps")})}
                        for r in recs],
        })
        mark = "" if row_ok(rows[-1]) else "   SPLIT UNDER PER-REPETITION RESTART"
        print(f"  {policy:<7} {scenario:<11} {driven_at:<9} "
              f"[{from_deg:+8.3f},{to_deg:+8.3f}]  probe {p}/{n}   "
              f"shared server {ref_p}/{ref_n}{mark}")

    path = J.claim_output(OUT / "repetition_probe.json")
    path.write_text(json.dumps({
        "cells": rows,
        "note": ("Each repetition ran in its own process against its own freshly "
                 "restarted server (D-6), which is the harness the repetition floor is "
                 "conditional on. A cell whose repetitions disagree here is VOID under "
                 "the standing rule, not a rate; a cell that was split on the shared "
                 "server and is unanimous here was measuring the server."),
    }, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


def row_ok(row) -> bool:
    return bool(row["probe_unanimous"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true",
                    help="aggregate the per-repetition artifacts; needs no simulator")
    ap.add_argument("--policy")
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--from-deg", type=float)
    ap.add_argument("--to-deg", type=float)
    ap.add_argument("--rep", type=int)
    ap.add_argument("--at-witness", action="store_true")
    args = ap.parse_args()
    if args.report:
        return report()
    if args.scenario not in ("lead", "ped", "plate", "none_plate"):
        raise SystemExit(f"scenario {args.scenario!r} is not drivable")
    for req in ("policy", "from_deg", "to_deg", "rep"):
        if getattr(args, req) is None:
            raise SystemExit(f"--{req.replace('_', '-')} is required to drive")
    return drive_one(args)


if __name__ == "__main__":
    raise SystemExit(main())
