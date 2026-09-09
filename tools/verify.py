"""M6: certify each policy over each sub-interval of the illumination axis.

    python tools/verify.py --policy P_pts --scenario lead

No simulator. Runs on the captured endpoint frames and the saved model.

**The property** (PROTOCOL section 7, property S). At every pose whose range to the
conflict is at most `r_req`, and for every illumination `s` in the sub-interval, the
commanded deceleration must be at least the brake decision threshold. Below it the
closed-loop controller does not latch, so the vehicle does not brake, so it does not stop.
That is the same threshold `tools/run_policy.py` uses, deliberately: certifying a
different quantity from the one that drives the car is how a sound verifier ends up
answering the wrong question.

**How.** The disturbance enters as a single `nn.Linear` from the scalar `s` to flattened
pixels, which keeps bound propagation in patches mode, then alpha-CROWN bounds the
network output over `s` in [-1, 1] (the sub-interval's two endpoints, midpoint zero),
**with input-space branch and bound**: a domain whose bound does not decide the property
is bisected and its halves are bounded in turn.

**The branch and bound is not optional, and it was missing.** PROTOCOL section 6 has
specified "alpha-CROWN with input-space branch and bound over s" since M0, and until
2026-09-07 this file made a single `compute_bounds` call per pose over the whole
sub-interval. On a wide sub-interval that is not a certificate about the policy, it is a
report on the looseness of one interval bound. Measured on `P_cont`/lead over
[-0.961, -29.554] deg, a 28.6-degree sub-interval, worst lower bound by number of input
sub-domains:

    1 (what this file used to do)   2.2321   0.90x threshold   FALSIFIED
    2                               3.4548   1.40x threshold   CERTIFIED
    4                               4.1036   1.66x threshold   CERTIFIED
    8                               4.2932   1.73x threshold   CERTIFIED

One bisection flips it. The policy was never the problem, and a tool that answers
"unsafe" because its own bound is loose is answering a different question from the one
the study sells.

**Three outcomes, not two.** A domain that neither certifies nor yields a concrete
counterexample is UNDECIDED, and saying so is the point: the old code called that
FALSIFIED, which conflates "we exhibited an illumination where the policy does not brake"
with "our bound did not clear". FALSIFIED now requires a CONCRETE `s` whose actual network
output violates the property -- an exhibited witness, not a failure to prove. The witness
is the single frame worth driving, and driving it is M7.

**The verdicts are written before any driving.** `python -m study.ledger --check-order`
checks that against git history. That ordering is the whole reason a verdict counts as a
prediction rather than a description.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu import require_cuda  # noqa: E402
import carla_jobs as J  # noqa: E402
from run_policy import load_policy, BRAKE_THRESHOLD_FRACTION  # noqa: E402

CAPTURES = J.CAPTURES
OUT = J.REPO / "results" / "carla"


class Family(nn.Module):
    """The disturbance as one linear layer, then the student. PROTOCOL section 6."""

    def __init__(self, lo: torch.Tensor, hi: torch.Tensor, student: nn.Module):
        super().__init__()
        n = lo.numel()
        self.lin = nn.Linear(1, n)
        with torch.no_grad():
            self.lin.weight.copy_(((hi - lo).reshape(n, 1)) * 0.5)
            self.lin.bias.copy_(((lo + hi) * 0.5).reshape(n))
        self.shape = tuple(lo.shape)
        self.student = student

    def forward(self, s):
        return self.student(self.lin(s).reshape(-1, *self.shape))


def prepare(arr: np.ndarray, w: int, h: int) -> torch.Tensor:
    """Same crop and resize as training. A mismatch here is silent and fatal."""
    H = arr.shape[0]
    band = arr[int(H * 0.35):int(H * 0.85)]
    t = torch.from_numpy(np.ascontiguousarray(band)).permute(2, 0, 1)
    t = t.float().unsqueeze(0) / 255.0
    return torch.nn.functional.interpolate(t, size=(h, w), mode="area")[0]



def certify_pose(fam, s_template, ptb_cls, prop: str, threshold: float,
                 method: str, max_domains: int, min_width: float, dev=None):
    """Input-space branch and bound over `s` for ONE pose. PROTOCOL section 6.

    Returns (verdict, margin_bound, witness_s, domains_used).

      CERTIFIED  every sub-domain's bound satisfies the property. `margin_bound` is the
                 WORST bound over the sub-domains, so the reported margin is still the
                 tightest true statement about the whole sub-interval.
      FALSIFIED  a CONCRETE s was found whose actual network output violates it.
                 `witness_s` is that value. This is an exhibited counterexample.
      UNDECIDED  the budget ran out with neither. Reported honestly rather than as a
                 falsification: the difference between "the policy fails here" and "our
                 bound is loose here" is the entire credibility of the tool.
    """
    import torch as _t
    queue = [(-1.0, 1.0)]
    worst = None
    domains = 0

    def bounds_on(lo, hi):
        """One alpha-CROWN bound over the sub-domain [lo, hi] of s.

        A FRESH BoundedModule per sub-domain. Reusing one across sub-domains is the
        obvious optimisation and it is wrong: alpha-CROWN caches per-node alpha
        coefficients keyed by start node, and the second call into a reused module dies
        with KeyError '/input-23' partway through a run. Rebuilding costs little next to
        the alpha optimisation itself -- measured at 0.58 s per bound with the rebuild
        against 0.64 s with reuse -- so there is nothing to buy here anyway.
        """
        from auto_LiRPA import BoundedModule, BoundedTensor
        bm = BoundedModule(fam, s_template, device=dev)
        ptb = ptb_cls(norm=float("inf"),
                      x_L=_t.full_like(s_template, lo),
                      x_U=_t.full_like(s_template, hi))
        lb, ub = bm.compute_bounds(x=(BoundedTensor(s_template, ptb),), method=method)
        return float(lb.item()), float(ub.item())

    def concrete(lo, hi):
        """Actual outputs at concrete s. A violation here is a real counterexample.

        Sampled at the ends and the middle of the domain, which is where branch and
        bound has already concentrated the search: the domain is only split when its
        bound failed, so by the time a domain is this small the interesting s is inside
        it.
        """
        out = []
        with _t.no_grad():
            for v in (lo, (lo + hi) / 2.0, hi):
                y = float(fam(_t.full_like(s_template, v)).item())
                out.append((v, y))
        return out

    while queue:
        lo, hi = queue.pop()
        lb, ub = bounds_on(lo, hi)
        domains += 1
        satisfied = (lb >= threshold) if prop == "S" else (ub <= threshold)
        bound_val = lb if prop == "S" else ub
        if satisfied:
            worst = bound_val if worst is None else (
                min(worst, bound_val) if prop == "S" else max(worst, bound_val))
            continue
        for v, y in concrete(lo, hi):
            if (y < threshold) if prop == "S" else (y > threshold):
                return "FALSIFIED", bound_val, v, domains
        if domains >= max_domains or (hi - lo) <= min_width:
            return "UNDECIDED", bound_val, None, domains
        mid = (lo + hi) / 2.0
        queue.append((lo, mid))
        queue.append((mid, hi))
    return "CERTIFIED", worst, None, domains


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
    import warnings

    warnings.filterwarnings("ignore")
    from auto_LiRPA import BoundedModule, BoundedTensor
    from auto_LiRPA.perturbations import PerturbationLpNorm

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--scenario", default="lead", help="which captured frames to use")
    ap.add_argument(
        "--policy-scenario", default="lead",
        help="which trained policy to load. Property A evaluates the SAME policy on the "
             "no-target frames, so this stays 'lead' while --scenario is 'none'",
    )
    ap.add_argument("--method", default="alpha-CROWN")
    ap.add_argument(
        "--max-domains", type=int, default=32,
        help="input-space branch-and-bound budget per pose (PROTOCOL section 6)")
    ap.add_argument(
        "--min-domain-width", type=float, default=2.0 / 64,
        help="stop splitting below this width in s; s spans [-1, 1]")
    ap.add_argument(
        "--property", choices=["S", "A"], default="S",
        help="S: must brake inside r_req. A: must NOT brake on the false-activation "
             "scenario, upper bound at most 0.25 g, PROTOCOL section 7",
    )
    args = ap.parse_args()

    # require_cuda, not is_available(): the flag is False while CARLA initialises on
    # the same device, and TRUE on a card whose kernels the installed torch does not
    # carry (sm_120 vs an sm_90 build). Both end in a silent CPU run that still prints
    # numbers. See tools/gpu.py.
    dev = require_cuda()
    model, w, h = load_policy(args.policy, args.policy_scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    threshold = a_max * BRAKE_THRESHOLD_FRACTION
    rr = J.r_req_m(J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2)
    # ONE knot set for every scenario. This used to branch -- lead and none read
    # family_knots.json while ped read family_knots_rgb.json -- because the committed
    # lead campaign predated the three-channel fix and had to keep its own record
    # (FINDINGS F2). A12 discarded both files, so that split now certifies two
    # scenarios against two different cuts of the same axis for no reason, and the
    # ped branch reads a file build_family_knots.py no longer writes. The metric is
    # checked from the artifact's own stamp instead of from its filename.
    from capture_campaign import load_knots, load_uncovered  # noqa: E402
    knots = load_knots()
    uncovered = load_uncovered()

    # The no-target control replays the LEAD poses, so it has no states file of its own.
    states_name = {"none": "lead", "none_ped": "ped",
                   "none_plate": "plate"}.get(args.scenario, args.scenario)
    states = json.loads((CAPTURES / f"states_{states_name}.json").read_text())
    ranges = np.array([s["range_m"] for s in states])
    if args.property == "S":
        # Property S quantifies over poses INSIDE r_req and nowhere else.
        poses = [i for i, r in enumerate(ranges) if r <= rr]
    else:
        # Property A holds EVERYWHERE: with nothing in front there is no range at which
        # braking is warranted. The limit is the standard's own 0.25 g.
        poses = list(range(len(states)))
        threshold = 0.25 * 9.81
    # Standing rule 7: evidence states its own scope, recomputed from the primary data
    # and never asserted from a constant. This said "N poses inside r_req (15.85 m)" for
    # BOTH properties, and property A quantifies over every captured pose out to 60 m --
    # so every property A artifact in the repo claimed a scope 3.8x narrower than the one
    # it actually verified. The verdicts were right the whole time; only the label lied,
    # which is the version of this defect that survives longest because nothing downstream
    # disagrees with it.
    span = [round(float(ranges[poses].min()), 3), round(float(ranges[poses].max()), 3)]
    scope = {
        "poses_verified": len(poses),
        "poses_available": len(states),
        "pose_range_m": span,
        "selection": ("range <= r_req" if args.property == "S"
                      else "every captured pose, at any range"),
        "r_req_m": round(float(rr), 3),
    }
    print(
        f"\n{args.policy} / {args.scenario}: property {args.property} over "
        f"{len(poses)} of {len(states)} poses, {span[0]:.2f} to {span[1]:.2f} m "
        f"({scope['selection']}), {len(knots) - 1} sub-intervals, "
        f"threshold {threshold:.3f} m/s^2",
        flush=True,
    )

    # Claimed BEFORE any bound is computed. A crash now leaves no artifact rather than
    # the previous run's (D-9); see carla_jobs.claim_output.
    _suffix = "" if args.property == "S" else "_A"
    out_path = J.claim_output(
        OUT / f"verify_{args.policy}_{args.scenario}{_suffix}.json")

    stored = {
        round(float(np.load(p)["sun_altitude_deg"]), 3): p
        for p in CAPTURES.glob(f"{args.scenario}_sun*.npz")
    }

    cells = []
    for hi_alt, lo_alt in zip(knots[:-1], knots[1:]):
        # A6 declares the horizon sliver UNCOVERED: no step size meets the blend
        # tolerance across the discontinuity, so a bound over that blend quantifies over
        # images that do not represent rendered reality. The cell is still computed (the
        # ledger keeps its row) but carries the flag, and a CERTIFIED verdict there must
        # never be counted as coverage (audit F8).
        #
        # WHICH sub-interval that is comes from the knot measurement, not from a constant
        # here. It has been [0.143, 0.000], then [0.36, 0.00], then [0.026, 0.000] across
        # three measurements of the same axis, and the band this line used to hard-code
        # would have kept answering after the knots moved under it.
        family_uncovered = any(
            abs(u["from_deg"] - hi_alt) < 1e-6 and abs(u["to_deg"] - lo_alt) < 1e-6
            for u in uncovered)
        t0 = time.time()
        a_imgs = np.load(stored[round(hi_alt, 3)])["images"]
        b_imgs = np.load(stored[round(lo_alt, 3)])["images"]
        worst_lb = None
        witness = None
        witness_s = None
        pose_verdicts = {"CERTIFIED": 0, "FALSIFIED": 0, "UNDECIDED": 0}
        undecided_pose = None
        domains_total = 0
        for i in poses:
            lo = prepare(a_imgs[i], w, h).to(dev)
            hi = prepare(b_imgs[i], w, h).to(dev)
            fam = Family(lo, hi, model).to(dev).eval()
            s = torch.zeros(1, 1, device=dev)
            verdict_i, val, w_s, n_dom = certify_pose(
                fam, s, PerturbationLpNorm, args.property, threshold,
                args.method, args.max_domains, args.min_domain_width, dev=dev)
            pose_verdicts[verdict_i] += 1
            domains_total += n_dom
            if verdict_i == "UNDECIDED" and undecided_pose is None:
                undecided_pose = i
            # S wants the LOWEST output (does it always brake?); A wants the HIGHEST
            # (does it ever brake when it should not?). The reported margin is the worst
            # over poses, and over the sub-domains within each pose.
            if val is not None and (worst_lb is None or (
                val < worst_lb if args.property == "S" else val > worst_lb
            )):
                worst_lb, witness = val, i
                if w_s is not None:
                    witness_s = w_s
            if verdict_i == "FALSIFIED" and witness_s is None:
                witness, witness_s = i, w_s

        # A sub-interval is CERTIFIED only if every pose in it certified. One exhibited
        # counterexample falsifies it; anything else undecided leaves it UNDECIDED.
        if pose_verdicts["FALSIFIED"]:
            verdict = "FALSIFIED"
        elif pose_verdicts["UNDECIDED"]:
            verdict = "UNDECIDED"
            witness = undecided_pose if witness is None else witness
        else:
            verdict = "CERTIFIED"
        cells.append(
            {
                **({"family_uncovered": True} if family_uncovered else {}),
                "from_deg": hi_alt,
                "to_deg": lo_alt,
                "worst_bound_mps2": round(worst_lb, 4) if worst_lb is not None else None,
                "threshold_mps2": round(threshold, 4),
                "margin_x_threshold": (round(worst_lb / threshold, 4)
                                       if worst_lb is not None else None),
                "verdict": verdict,
                "poses": dict(pose_verdicts),
                "bab_domains": domains_total,
                "witness_pose": witness,
                "witness_s": witness_s,
                "witness_range_m": (round(float(ranges[witness]), 3)
                                    if witness is not None else None),
                "seconds": round(time.time() - t0, 1),
            }
        )
        _wit = ""
        if verdict == "FALSIFIED":
            _wit = (f"  witness pose {witness} at {ranges[witness]:.1f} m, "
                    f"s={witness_s:+.4f}")
        elif verdict == "UNDECIDED":
            _wit = (f"  {pose_verdicts['UNDECIDED']} pose(s) undecided at the "
                    f"{args.max_domains}-domain budget")
        print(
            f"  {hi_alt:+8.3f} to {lo_alt:+8.3f}  bound "
            f"{worst_lb if worst_lb is not None else float('nan'):8.3f}  "
            f"{(worst_lb / threshold) if worst_lb is not None else float('nan'):6.2f}x "
            f"threshold  {verdict:<9}{_wit}"
            f"  [{domains_total} domains, {time.time() - t0:.0f}s]",
            flush=True,
        )

    _prov = _provenance(str(J.REPO / "results" / "models" /
                            f"{args.policy}_{args.policy_scenario}.pt"))
    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "model_sha256": _prov.get("model_sha256"),
        "provenance": _prov,
        "property": args.property,
        "method": args.method,
        "threshold_mps2": round(threshold, 4),
        "r_req_m": round(rr, 3),
        "scope": scope,
        "poses_inside_r_req": (len(poses) if args.property == "S" else None),
        "branch_and_bound": {
            "max_domains_per_pose": args.max_domains,
            "min_domain_width": args.min_domain_width,
            "note": ("PROTOCOL section 6's input-space branch and bound. Absent from "
                     "this file until 2026-09-07, which produced FALSIFIED verdicts on "
                     "wide sub-intervals that one bisection certifies (FINDINGS F8)."),
        },
        "cells": cells,
        "falsified": [c for c in cells if c["verdict"] == "FALSIFIED"],
        "undecided": [c for c in cells if c["verdict"] == "UNDECIDED"],
        "note": (
            "Property S from PROTOCOL section 7, on the same threshold the closed-loop "
            "controller latches at. CERTIFIED means the lower bound clears it at every "
            "pose inside r_req for every illumination in the sub-interval, under "
            "input-space branch and bound. FALSIFIED means a concrete s was exhibited "
            "whose actual output violates it. UNDECIDED means neither, at the stated "
            "budget, and is reported as itself rather than as a falsification. WRITTEN "
            "BEFORE ANY DRIVING; that ordering is what makes these predictions."
        ),
    }
    path = out_path
    path.write_text(json.dumps(payload, indent=2) + "\n")
    n_bad = len(payload["falsified"])
    n_und = len(payload["undecided"])
    print(
        f"\n  {len(cells) - n_bad - n_und}/{len(cells)} sub-intervals certified, "
        f"{n_bad} falsified with an exhibited witness, {n_und} undecided"
    )
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
