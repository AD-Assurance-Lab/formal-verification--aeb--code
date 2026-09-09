"""Per-pose verdicts over the LATCH WINDOW. The disposition PROTOCOL section 8 wants.

    python tools/latch_window.py --policy P_pts --scenario ped

**The contradiction this exists to dispose of.** Two ledger cells disagree with their
pre-registration in the same direction: cell 1 (`P_pts`/ped) was predicted to FAIL when
driven and passed 10/10 in all thirteen falsified sub-intervals, and cell 3 (`P_cont`/ped)
was predicted CERTIFIED and came back FALSIFIED over 0.753 deg. Both are property S, and
in both the certificate and the vehicle are being asked different questions.

**The quantifier structure.** Write `out(i, s)` for the network's commanded deceleration
at pose `i` under illumination `s`, and `th` for the latch threshold, which
`run_policy.BRAKE_THRESHOLD_FRACTION` and `verify.py` already share.

    property S, as PROTOCOL section 7 states it and verify.py computes it:
        FORALL i in poses_inside_r_req.  FORALL s in I.  out(i, s) >= th

    what PROTOCOL section 7's CLOSED-LOOP criterion needs:
        FORALL s in I.  EXISTS i in latch_window.  out(i, s) >= th

The controller latches once and holds full braking (`run_policy.one_run`), so a single
pose clearing the threshold early enough is the whole requirement; every pose after it is
already irrelevant, and every pose too late to stop in `d_margin` was irrelevant before it.
The first formula IMPLIES the second. The second does not imply the first. So a FALSIFIED
property S is not a prediction that the drive fails, and scoring it as one is comparing a
conjunction over 25 poses against an existential over a handful.

That is the same defect as FINDINGS F9 on a different axis. F9 was the *criterion* folding
in a property A condition; this is the *property* quantifying over more poses than the
criterion needs. Both make the certificate look wrong when it is merely answering a
stronger question.

**What this tool measures, rather than argues.** For every sub-interval it verifies each
pose in and just beyond the latch window SEPARATELY and records that pose's own verdict,
so the following sound and much tighter sufficient condition can be evaluated:

        EXISTS i in latch_window.  FORALL s in I.  out(i, s) >= th

which implies the closed-loop requirement above and is exactly one pose's certificate.
It is sufficient, not necessary -- the pose that saves the vehicle may differ with `s` --
so a sub-interval failing it is not thereby predicted to fail; it is simply not covered by
this argument.

**The window comes from the measured primitives, not from the drives.** Using the observed
stop distances to define the window and then explaining the drives with it would be
circular. `r_latch_min` is the worst measured stop at the hazard speed, which already
carries `t_lat`, plus `d_margin`. The drive-observed latch ranges are reported alongside as
a check on that arithmetic and are never used to compute it.

No simulator. Captured frames and the GPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402
import verify as V  # noqa: E402

CAPTURES = J.CAPTURES
OUT = J.REPO / "results" / "carla"


class LatchFamily(torch.nn.Module):
    """max over the latch window's poses, as one ReLU network over `s`. PROTOCOL 6.

    `Family` in verify.py maps s -> one pose's image -> one output, which gives the
    per-pose property. What the vehicle needs is the DISJUNCTION over the window:

        FORALL s.  EXISTS i in window.  out(i, s) >= th
          <=>  FORALL s.  max_i out(i, s) >= th

    and a lower bound on `max_i out(i, s)` is exactly a certificate of that. The max is
    written with ReLU so the verified network stays ReLU-only, as the standing rules
    require: max(a, b) = a + relu(b - a), chained over the window.

    One `verify.Family` per window pose, each keeping batch size 1, and the SAME student
    object in all of them -- so this is the network the ledger's verdicts and the vehicle
    both use, not a surrogate. The obvious alternative, one wide linear layer emitting
    every pose's image and reshaping to a batch of k, is wrong: auto_LiRPA treats dim 0
    as the batch and the reshape moves data across it, which dies in
    `linear.py:_bound_oneside` with `shape '[3, 96, 128]' is invalid for input of size
    73728`. The k forward passes cost k times one pose's bound and nothing else.
    """

    def __init__(self, los, his, student: torch.nn.Module):
        super().__init__()
        self.fams = torch.nn.ModuleList(
            [V.Family(lo, hi, student) for lo, hi in zip(los, his)])
        self.relu = torch.nn.ReLU()

    def forward(self, s):
        ys = [f(s) for f in self.fams]
        m = ys[0]
        for y in ys[1:]:
            m = m + self.relu(y - m)
        return m


def latch_window(braking: dict, speed_mph: float, ranges_ft) -> dict:
    """Poses at which latching still leaves d_margin at rest. From primitives only.

    `stop_ft` in braking.json is measured from the brake command to rest and already
    includes `t_lat`, so it composes with `d_margin` directly. The WORST stop is used,
    for the same reason `a_max_g_worst` is: a window sized on the median describes half
    the stops.
    """
    stops = [r["stop_ft"] for r in braking["runs"]
             if abs(r["speed_mph"] - speed_mph) < 0.5]
    if not stops:
        raise SystemExit(f"braking.json has no runs at {speed_mph} mph")
    d_margin_ft = J.D_MARGIN_M * J.FT
    r_latch_min_ft = max(stops) + d_margin_ft
    return {
        "speed_mph": speed_mph,
        "worst_stop_ft": round(max(stops), 2),
        "median_stop_ft": round(float(np.median(stops)), 2),
        "d_margin_ft": round(d_margin_ft, 2),
        "r_latch_min_ft": round(r_latch_min_ft, 2),
        "poses": [i for i, ft in enumerate(ranges_ft) if ft >= r_latch_min_ft],
        "note": ("A latch at range >= r_latch_min stops with at least d_margin to spare "
                 "on the worst measured stop. Derived from braking.json alone; the "
                 "drives are not consulted."),
    }


def main() -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from auto_LiRPA.perturbations import PerturbationLpNorm

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--scenario", default="lead", choices=["lead", "ped"])
    ap.add_argument("--method", default="alpha-CROWN")
    ap.add_argument("--max-domains", type=int, default=32)
    ap.add_argument("--min-domain-width", type=float, default=2.0 / 64)
    ap.add_argument("--beyond", type=int, default=4,
                    help="also verify this many poses INSIDE the window, so the report "
                         "shows where clearance is lost rather than only that it was")
    args = ap.parse_args()

    from gpu import require_cuda
    from capture_campaign import load_knots, load_uncovered
    from run_policy import load_policy, BRAKE_THRESHOLD_FRACTION, MODELS

    dev = require_cuda()
    model, w, h = load_policy(args.policy, args.scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    threshold = b["a_max_g_worst"] * 9.81 * BRAKE_THRESHOLD_FRACTION
    rr = J.r_req_m(J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2)

    states = json.loads((CAPTURES / f"states_{args.scenario}.json").read_text())
    ranges_m = np.array([s["range_m"] for s in states])
    ranges_ft = ranges_m * J.FT
    inside = [i for i, r in enumerate(ranges_m) if r <= rr]

    win = latch_window(b, J.HAZARD_MPH, ranges_ft)
    win["poses"] = [i for i in win["poses"] if i in inside]
    if not win["poses"]:
        raise SystemExit("empty latch window inside r_req; the primitives disagree with "
                         "the pose spacing and that is the finding, not this tool")
    probe = win["poses"] + [i for i in inside
                            if i > max(win["poses"])][:args.beyond]

    print(f"\n{args.policy} / {args.scenario}: r_req {rr * J.FT:.2f} ft, "
          f"{len(inside)} poses inside it, threshold {threshold:.3f} m/s^2")
    print(f"  latch window from primitives: range >= {win['r_latch_min_ft']} ft "
          f"-> poses {win['poses']}  (worst stop {win['worst_stop_ft']} ft "
          f"+ d_margin {win['d_margin_ft']} ft)")
    print(f"  probing poses {probe} "
          f"({', '.join(f'{ranges_ft[i]:.1f}ft' for i in probe)})\n", flush=True)

    knots, uncovered = load_knots(), load_uncovered()
    stored = {round(float(np.load(p)["sun_altitude_deg"]), 3): p
              for p in CAPTURES.glob(f"{args.scenario}_sun*.npz")}
    out_path = J.claim_output(
        OUT / f"latch_window_{args.policy}_{args.scenario}.json")

    cells = []
    for hi_alt, lo_alt in zip(knots[:-1], knots[1:]):
        t0 = time.time()
        a_imgs = np.load(stored[round(hi_alt, 3)])["images"]
        b_imgs = np.load(stored[round(lo_alt, 3)])["images"]
        per_pose = {}
        for i in probe:
            fam = V.Family(V.prepare(a_imgs[i], w, h).to(dev),
                           V.prepare(b_imgs[i], w, h).to(dev), model).to(dev).eval()
            v_i, val, w_s, n_dom = V.certify_pose(
                fam, torch.zeros(1, 1, device=dev), PerturbationLpNorm, "S",
                threshold, args.method, args.max_domains, args.min_domain_width, dev=dev)
            per_pose[str(i)] = {
                "range_ft": round(float(ranges_ft[i]), 2),
                "in_window": i in win["poses"],
                "verdict": v_i,
                "bound_mps2": round(val, 4) if val is not None else None,
                "margin_x_threshold": round(val / threshold, 4) if val is not None else None,
                "witness_s": w_s,
                "domains": n_dom,
            }
        certified_in_window = [i for i in win["poses"]
                               if per_pose[str(i)]["verdict"] == "CERTIFIED"]

        # The exact property: FORALL s. max over the window >= th. Certifying this is
        # certifying that the vehicle latches in time at EVERY illumination in the
        # sub-interval, with the saving pose allowed to differ from one illumination to
        # the next -- which is what the closed loop actually does, and what the per-pose
        # EXISTS-pose-FORALL-s condition above cannot express.
        lat = LatchFamily([V.prepare(a_imgs[i], w, h).to(dev) for i in win["poses"]],
                          [V.prepare(b_imgs[i], w, h).to(dev) for i in win["poses"]],
                          model).to(dev).eval()
        v_dis, val_dis, ws_dis, dom_dis = V.certify_pose(
            lat, torch.zeros(1, 1, device=dev), PerturbationLpNorm, "S",
            threshold, args.method, args.max_domains, args.min_domain_width, dev=dev)
        cells.append({
            "from_deg": hi_alt,
            "to_deg": lo_alt,
            "family_uncovered": any(
                abs(u["from_deg"] - hi_alt) < 1e-6 and abs(u["to_deg"] - lo_alt) < 1e-6
                for u in uncovered),
            # EXISTS pose in window. FORALL s. out >= th  -- sufficient for an on-time
            # latch everywhere in the sub-interval, and not necessary.
            "latch_guaranteed": bool(certified_in_window),
            "certified_window_poses": certified_in_window,
            "disjunction": {
                "verdict": v_dis,
                "bound_mps2": round(val_dis, 4) if val_dis is not None else None,
                "margin_x_threshold": (round(val_dis / threshold, 4)
                                       if val_dis is not None else None),
                "witness_s": ws_dis,
                "domains": dom_dis,
            },
            "deepest_certified_pose": (max([i for i in probe
                                            if per_pose[str(i)]["verdict"] == "CERTIFIED"],
                                           default=None)),
            "per_pose": per_pose,
            "seconds": round(time.time() - t0, 1),
        })
        flag = {"CERTIFIED": "LATCHES IN TIME", "FALSIFIED": "latch NOT in time",
                "UNDECIDED": "undecided"}[v_dis]
        letters = "".join("CFU"["CERTIFIED FALSIFIED UNDECIDED".split().index(
            per_pose[str(i)]["verdict"])] + ("|" if i == max(win["poses"]) else "")
            for i in probe)
        print(f"  [{hi_alt:+8.3f}, {lo_alt:+8.3f}]  {flag:<17} "
              f"{('%.3fx' % (val_dis / threshold)) if val_dis is not None else '   -':>8}"
              f"  poses {letters}  {cells[-1]['seconds']:.0f}s", flush=True)

    n_guar = sum(1 for c in cells if c["latch_guaranteed"])
    n_dis = sum(1 for c in cells if c["disjunction"]["verdict"] == "CERTIFIED")
    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "provenance": V._provenance(MODELS / f"{args.policy}_{args.scenario}.pt"),
        "threshold_mps2": round(threshold, 4),
        "r_req_ft": round(float(rr * J.FT), 2),
        "latch_window": win,
        "probed_poses": probe,
        "sub_intervals_latch_guaranteed": f"{n_guar}/{len(cells)}",
        "sub_intervals_latch_in_time": f"{n_dis}/{len(cells)}",
        "cells": cells,
        "note": ("Property S is FORALL pose FORALL s. The closed-loop criterion needs "
                 "FORALL s EXISTS pose in the latch window, which `disjunction` "
                 "certifies exactly by bounding max over the window. "
                 "`latch_guaranteed` is the weaker EXISTS pose FORALL s, kept because it "
                 "names WHICH pose carries the sub-interval when one does. It is a "
                 "DISPOSITION instrument for PROTOCOL section 8 and does not change any "
                 "committed verdict: verify.py and the ledger are untouched."),
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n  latches in time (FORALL s. max over window >= th) in "
          f"{n_dis}/{len(cells)} sub-intervals")
    print(f"  per-pose EXISTS-pose-FORALL-s holds in {n_guar}/{len(cells)}, which is the "
          f"weaker sufficient condition")
    print(f"  wrote {out_path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
