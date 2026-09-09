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

from gpu import require_cuda  # noqa: E402
import carla_jobs as J  # noqa: E402
import condition_signature as CS  # noqa: E402
import stats as ST  # noqa: E402
from run_policy import (load_policy, one_run, plate_run,  # noqa: E402
                        PREMATURE_MULTIPLE)

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
    ap.add_argument(
        "--rep-index", type=int, default=None,
        help="drive ONE repetition of every sub-interval and write it to its own "
             "artifact under results/carla/witness_reps/. The shell restarts the "
             "server between indices, so each repetition of each sub-interval gets an "
             "independent simulator (D-6) and an independent process, which ten "
             "repetitions inside one loop do not. Merge with tools/merge_witness_reps.py")
    ap.add_argument(
        "--at-witness", action="store_true",
        help="drive the EXHIBITED witness illumination of each falsified sub-interval "
             "instead of its midpoint. The default midpoint pass answers 'does the "
             "certificate flag everything'; this one answers 'is the illumination it "
             "named actually unsafe', which is the question section 10 asks")
    args = ap.parse_args()

    if args.scenario not in ("lead", "ped", "plate", "none_plate"):
        raise SystemExit(f"scenario {args.scenario!r} is not drivable")

    # The plate cells pass by NOT stopping, so their verdict column is property A and
    # their artifact carries the `_A` suffix. Everything downstream of the verdict --
    # the commit check, the midpoint/at-witness split, the agreement count -- is the same
    # question asked of a different criterion, so it is a branch and not a second script.
    plate = args.scenario in ("plate", "none_plate")
    place_plate = args.scenario == "plate"
    verdicts_path = OUT / (f"verify_{args.policy}_{args.scenario}_A.json" if plate
                           else f"verify_{args.policy}_{args.scenario}.json")
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

    # require_cuda, not is_available(): the flag is False while CARLA initialises on
    # the same device, and TRUE on a card whose kernels the installed torch does not
    # carry (sm_120 vs an sm_90 build). Both end in a silent CPU run that still prints
    # numbers. See tools/gpu.py.
    dev = require_cuda()
    # There is no plate-trained policy and there must not be: cells 5 and 6 ask whether
    # the HAZARD policy false-activates, so they load exactly the network the hazard
    # cells verify and drive. verify.py used --policy-scenario lead for the same reason.
    model, w, h = load_policy(args.policy, "lead" if plate else args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    r_req_ft = J.r_req_m(
        J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2
    ) * J.FT

    # D-9: claimed before the first run, so a crashed drive leaves no witness artifact
    # rather than an earlier one that every consumer would treat as current.
    _sfx = "_atwitness" if args.at_witness else ""
    if args.rep_index is None:
        out_path = J.claim_output(
            OUT / f"witness_{args.policy}_{args.scenario}{_sfx}.json")
    else:
        # One repetition of every sub-interval, in its own process against its own
        # freshly restarted server. The shell owns the restarts; this file only has to
        # not overwrite the other repetitions, which is D-9: a repetition that crashes
        # must leave no artifact rather than leave the previous repetition's.
        (OUT / "witness_reps").mkdir(parents=True, exist_ok=True)
        out_path = J.claim_output(
            OUT / "witness_reps" /
            f"witness_{args.policy}_{args.scenario}{_sfx}_rep{args.rep_index:02d}.json")
        if args.reps != 1:
            raise SystemExit(
                f"--rep-index drives one repetition per process; --reps is {args.reps}. "
                f"Ten repetitions inside one process is the harness this flag exists to "
                f"replace, and running both at once would report neither.")
    reps = args.reps

    carla = J.carla_module()
    client, world = J.connect(rendering=True)
    site = J.flattest_site(scenario=args.scenario)

    cells_to_drive = verdicts["cells"]
    if args.at_witness:
        # Only the falsified ones have an exhibited witness to drive.
        cells_to_drive = [c for c in verdicts["cells"]
                          if c["verdict"] == "FALSIFIED" and c.get("witness_s") is not None]
        if not cells_to_drive:
            print("  no falsified sub-interval carries an exhibited witness_s; "
                  "nothing to drive")
            return 0

    rows = []
    sig_records = []
    agree = 0
    for cell in cells_to_drive:
        if args.at_witness:
            # s runs from the sub-interval's BRIGHT knot at -1 to its DARK knot at +1:
            # tools/verify.py builds the family with the hi_alt frame as the s = -1 end.
            s = cell["witness_s"]
            mid = cell["from_deg"] + (s + 1.0) / 2.0 * (cell["to_deg"] - cell["from_deg"])
        else:
            mid = (cell["from_deg"] + cell["to_deg"]) / 2.0
        weather = world.get_weather()
        weather.sun_altitude_angle = mid
        weather.cloudiness = 10.0
        weather.precipitation = 0.0
        world.set_weather(weather)
        for _ in range(J.WEATHER_SETTLE_TICKS):
            world.tick()
        lights = "LowBeam" if mid < 5.0 else "NONE"

        if plate:
            runs = [plate_run(world, site, model, w, h, dev, J.PLATE_MPH, lights,
                              place=place_plate)
                    for _ in range(reps)]
            # ONE criterion here, and it is the standard's own: crossed the plate still
            # moving, never braked, never commanded more than 0.25 g. There is no second
            # count to keep apart, because there is no contact to avoid and no standoff
            # to hold -- the hazard cells' two counts exist because a must-brake verdict
            # must not be scored against a must-not-brake condition (F9), and here the
            # verdict IS the must-not-brake one.
            passes_protocol = sum(1 for r in runs if r["passes"])
            peaks = [r["peak_demand_mps2"] for r in runs]
            drove_ok = passes_protocol == reps
            predicted_ok = cell["verdict"] == "CERTIFIED"
            matched = drove_ok == predicted_ok
            agree += matched
            rows.append({
                "from_deg": cell["from_deg"], "to_deg": cell["to_deg"],
                "midpoint_deg": round(mid, 3), "driven_at_deg": round(mid, 3),
                "driven_at": "witness" if args.at_witness else "midpoint",
                "witness_s": cell.get("witness_s"),
                "verdict": cell["verdict"],
                **ST.rate(passes_protocol, reps),
                "passes": passes_protocol, "passes_protocol": passes_protocol,
                "of": reps,
                "braked": sum(1 for r in runs if r["braked"]),
                "exceeded_limit": sum(1 for r in runs if r["exceeded_nuisance_limit"]),
                "did_not_cross": sum(1 for r in runs if not r["crossed_plate"]),
                "peak_demand_mps2": [round(x, 4) for x in peaks],
                "worst_peak_mps2": round(max(peaks), 4),
                "worst_peak_x_limit": round(max(peaks) / runs[0]["nuisance_limit_mps2"], 4),
                "nuisance_limit_mps2": runs[0]["nuisance_limit_mps2"],
                "headlamps": lights,
                "signature": runs[0]["signature"],
                "agrees": matched,
                # EVERY field plate_run returns, not a hand-picked subset. The subset
                # this used to be dropped `plate_tiles` and `plate_covered_ft`, so the
                # trench plate's actual geometry was measured on every run and thrown
                # away at the artifact boundary -- and a partially placed plate was
                # therefore invisible to anyone reading the result. F22 named the gap as
                # "not recorded"; it was recorded and then discarded, which is worse,
                # because the fix looked like it needed a re-drive and did not.
                "runs": [dict(r) for r in runs],
            })
            sig_records.append({"sun_altitude_deg": round(mid, 3),
                                "signature": runs[0]["signature"]})
            print(f"  [{cell['from_deg']:+8.3f}, {cell['to_deg']:+8.3f}] "
                  f"at {mid:+8.3f}  {cell['verdict']:<10} "
                  f"drove {passes_protocol}/{reps}  peak {max(peaks):.3f} "
                  f"({max(peaks) / runs[0]['nuisance_limit_mps2']:.3f}x limit)  "
                  f"{'agrees' if matched else 'DISAGREES'}", flush=True)
            continue

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
        # TWO COUNTS, because they answer two different properties and conflating them
        # made a certified cell look unsound.
        #
        #   passes_protocol  PROTOCOL section 7's frozen closed-loop pass: "no contact
        #                    and standoff at least d_margin". This is what property S
        #                    composes into, so it is what a property-S verdict is scored
        #                    against.
        #   passes_no_nuisance  additionally requires the policy not to have braked
        #                    absurdly early. run_policy.py added that (PREMATURE_MULTIPLE)
        #                    and it is a sound thing to want -- a policy that stops at
        #                    300 ft has not performed AEB -- but it is a MUST-NOT-BRAKE
        #                    condition, which is property A, and property S says nothing
        #                    about it.
        #
        # Measured 2026-09-07: scoring property S against the second count reported
        # P_cont/lead's CERTIFIED [+0.779, +0.026] as a soundness violation. The run that
        # "failed" stopped 306 ft from the lead vehicle. It braked too early; it did not
        # fail to brake.
        passes_protocol = sum(
            1 for r in runs if not r["contact"] and r["standoff_ok"])
        passes = sum(
            1 for r in runs
            if not r["contact"] and r["standoff_ok"] and not r["premature"]
        )
        drove_ok = passes_protocol == args.reps
        predicted_ok = cell["verdict"] == "CERTIFIED"
        matched = drove_ok == predicted_ok
        agree += matched
        rows.append(
            {
                "from_deg": cell["from_deg"],
                "to_deg": cell["to_deg"],
                "midpoint_deg": round(mid, 3),
                "driven_at_deg": round(mid, 3),
                "driven_at": "witness" if args.at_witness else "midpoint",
                "witness_s": cell.get("witness_s"),
                "verdict": cell["verdict"],
                **ST.rate(passes_protocol, args.reps),
                "passes": passes_protocol,
                "passes_protocol": passes_protocol,
                "passes_no_nuisance": passes,
                "of": args.reps,
                "never_braked": sum(1 for r in runs if not r["braked"]),
                "contacts": sum(1 for r in runs if r["contact"]),
                "standoff_short": sum(1 for r in runs if not r["standoff_ok"]),
                "premature": sum(1 for r in runs if r["premature"]),
                # Per RUN, so the artifact can be re-scored under either criterion
                # without re-driving. Summary counts alone cannot distinguish a policy
                # that hit the target from one that stopped 300 ft early.
                "runs": [
                    {"contact": r["contact"], "standoff_ok": r["standoff_ok"],
                     "premature": r["premature"], "braked": r["braked"],
                     "min_gap_ft": r["min_gap_ft"], "rest_gap_ft": r.get("rest_gap_ft"),
                     "brake_range_ft": r["brake_range_ft"]}
                    for r in runs
                ],
                "min_gap_ft": [r["min_gap_ft"] for r in runs],
                "headlamps": lights,
                "signature": runs[0]["signature"],
                "agrees": matched,
            }
        )
        sig_records.append(
            {"sun_altitude_deg": round(mid, 3), "signature": runs[0]["signature"]})
        _nuis = "" if passes == passes_protocol else f" ({passes} w/o nuisance)"
        J.progress(
            f"{cell['from_deg']:+8.3f} to {cell['to_deg']:+8.3f}  "
            f"mid {mid:+7.3f}  predicted {cell['verdict']:<9}  "
            f"drove {ST.fmt(passes_protocol, args.reps)}{_nuis}  "
            f"{'agree' if matched else 'DISAGREE'}"
        )

    # THE ILLUMINATION AXIS THIS DRIVE ACTUALLY RENDERED, checked before the agreement
    # table is written. This is the driver that produces the study's headline -- "P_pts
    # passes both regulatory endpoints and fails 0/10 at three dusk illuminations" -- and
    # until now nothing anywhere in the repository checked that the dusk it drove was the
    # dusk the certificate named. Eleven midpoints spanning +45 to -30 deg give the check
    # real power: a sun that did not move, or moved the wrong way, cannot produce a
    # monotone brightness curve across them.
    from capture_campaign import load_uncovered  # noqa: E402
    # The at-witness pass can land several sub-intervals on the SAME rendered knot, so
    # its altitude set is not the spread the axis check is written for. Checked when the
    # pass sweeps the axis, recorded either way.
    if args.at_witness and len({r["sun_altitude_deg"] for r in sig_records}) < 3:
        illumination = CS.check_axis(sig_records, uncovered=load_uncovered())
    else:
        illumination = CS.assert_axis(sig_records, uncovered=load_uncovered())
    print(f"\n  illumination axis OK: {illumination['knots']} midpoints, span "
          f"{illumination['axis_span_mean']:.4f} of full range")

    # The model that was LOADED, not the scenario name. For the plate cells those differ
    # -- there is no P_pts_plate.pt -- and hashing a path that does not exist yields a
    # null model_sha256, which silently disables study.ledger's model-binding check.
    _prov = _provenance(str(J.REPO / "results" / "models" /
                            f"{args.policy}_{'lead' if plate else args.scenario}.pt"))
    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "rep_index": args.rep_index,
        "model_sha256": _prov.get("model_sha256"),
        "provenance": _prov,
        # D-11 is enforceable after the fact only if the artifact says which harness
        # produced it. Read from the running server and the installed package, not from
        # a constant. CARLA_DETERMINISM_PENDING.md adoption item 5.
        "determinism": J.determinism_provenance(world),
        "illumination": illumination,
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
    if plate:
        payload["criterion"] = (
            "FMVSS 127 false activation: crossed the plate still moving, never braked, "
            "and never commanded more than the standard's 0.25 g nuisance limit. This is "
            "the only scenario in the study that passes by NOT stopping.")
        payload["model_scenario"] = "lead"
        payload["plate_present"] = place_plate
    payload["driven_at"] = "witness" if args.at_witness else "midpoint"
    payload["note"] = (
        "Driven at each falsified sub-interval's EXHIBITED witness illumination -- the "
        "concrete s whose actual network output violates the property. That illumination "
        "is a rendered knot here, not a blend. The companion midpoint pass "
        "(witness_*.json) drives every sub-interval, certified ones included, because a "
        "test that only visits flagged cells cannot tell a working certificate from one "
        "that flags everything."
        if args.at_witness else payload["note"])
    path = out_path
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  certificate agrees with driving in {agree}/{len(rows)} sub-intervals")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
