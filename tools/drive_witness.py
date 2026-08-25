"""M7: drive the illumination the certificate points at, and see if it agrees.

    python tools/drive_witness.py --policy P_pts

Reads `results/carla/verify_<policy>_<scenario>.json`, which must already be committed to
git: the verdicts are predictions only if they were written down before the driving. Then
for every sub-interval, certified and falsified alike, it drives the closed loop at that
sub-interval's midpoint sun altitude, ten repetitions, and reports the pass rate.

The midpoint is a RENDERED illumination, not a blend, so a failure there is a failure of
the vehicle and not an artefact of the family. That matters: the certificate quantifies
over blends, and the point of driving is to check the claim against something real.

Certified sub-intervals are driven too, deliberately. A test that only visits the cells
the verifier flagged cannot tell a working certificate from one that flags everything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
from run_policy import load_policy, one_run, PREMATURE_MULTIPLE  # noqa: E402

OUT = J.REPO / "results" / "carla"



def _provenance(model_path=None):
    """Attribution for result artifacts: which code, which network, when.

    The A10 retrain overwrote models and verdicts in place; without this nothing
    ties a committed verdict to the network it describes (audit F6/F12)."""
    import datetime
    import hashlib
    import subprocess
    p = {"timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    try:
        p["git_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(J.REPO), timeout=10).stdout.strip() or None
    except Exception:
        p["git_sha"] = None
    if model_path is not None:
        p["model_sha256"] = hashlib.sha256(open(model_path, "rb").read()).hexdigest()
    return p

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--reps", type=int, default=J.REPS)
    args = ap.parse_args()

    if args.scenario not in ("lead", "ped"):
        raise SystemExit(f"scenario {args.scenario!r} is not drivable")

    verdicts_path = OUT / f"verify_{args.policy}_{args.scenario}.json"
    if not verdicts_path.exists():
        raise SystemExit(f"no verdicts at {verdicts_path}; run tools/verify.py first")
    # A verdict is a prediction only if it is COMMITTED before this drive
    # (PROTOCOL section 8). The old check accepted any file on disk.
    import subprocess as _sp
    rel = str(verdicts_path.relative_to(J.REPO))
    tracked = _sp.run(["git", "ls-files", "--error-unmatch", rel],
                      capture_output=True, cwd=str(J.REPO)).returncode == 0
    dirty = _sp.run(["git", "status", "--porcelain", "--", rel],
                    capture_output=True, text=True, cwd=str(J.REPO)).stdout.strip()
    if not tracked or dirty:
        raise SystemExit(
            f"{rel} is {'untracked' if not tracked else 'modified since commit'}: "
            f"commit the verdicts first -- an uncommitted verdict is not a prediction "
            f"(PROTOCOL section 8; python -m study.ledger --check-order)")
    verdicts = json.loads(verdicts_path.read_text())

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model, w, h = load_policy(args.policy, args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    r_req_ft = J.r_req_m(
        J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2
    ) * J.FT

    carla = J.carla_module()
    client, world = J.connect(rendering=True)
    site = J.flattest_site()

    rows = []
    agree = 0
    for cell in verdicts["cells"]:
        mid = (cell["from_deg"] + cell["to_deg"]) / 2.0
        weather = world.get_weather()
        weather.sun_altitude_angle = mid
        weather.cloudiness = 10.0
        weather.precipitation = 0.0
        world.set_weather(weather)
        for _ in range(J.WEATHER_SETTLE_TICKS):
            world.tick()
        lights = "LowBeam" if mid < 5.0 else "NONE"

        runs = [
            one_run(world, site, model, w, h, dev, a_max, J.HAZARD_MPH, lights,
                    scenario=args.scenario, release_r_req_m=r_req_ft / J.FT)
            for _ in range(args.reps)
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
        drove_ok = passes == args.reps
        predicted_ok = cell["verdict"] == "CERTIFIED"
        matched = drove_ok == predicted_ok
        agree += matched
        rows.append(
            {
                "from_deg": cell["from_deg"],
                "to_deg": cell["to_deg"],
                "midpoint_deg": round(mid, 3),
                "verdict": cell["verdict"],
                "passes": passes,
                "of": args.reps,
                "never_braked": sum(1 for r in runs if not r["braked"]),
                "premature": sum(1 for r in runs if r["premature"]),
                "min_gap_ft": [r["min_gap_ft"] for r in runs],
                "agrees": matched,
            }
        )
        J.progress(
            f"{cell['from_deg']:+8.3f} to {cell['to_deg']:+8.3f}  "
            f"mid {mid:+7.3f}  predicted {cell['verdict']:<9}  "
            f"drove {passes}/{args.reps}  {'agree' if matched else 'DISAGREE'}"
        )

    _prov = _provenance(str(J.REPO / "results" / "models" /
                            f"{args.policy}_{args.scenario}.pt"))
    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "model_sha256": _prov.get("model_sha256"),
        "provenance": _prov,
        "agreement": f"{agree}/{len(rows)}",
        "cells": rows,
        "note": (
            "Driven at each sub-interval's MIDPOINT sun altitude, which is a rendered "
            "illumination and not a blend, so a failure is the vehicle's and not the "
            "family's. Certified sub-intervals are driven too: a test that only visits "
            "the flagged cells cannot tell a working certificate from one that flags "
            "everything."
        ),
    }
    path = OUT / f"witness_{args.policy}_{args.scenario}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  certificate agrees with driving in {agree}/{len(rows)} sub-intervals")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
