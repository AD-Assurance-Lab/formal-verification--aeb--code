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
network output over `s` in [-1, 1] (the sub-interval's two endpoints, midpoint zero).

A cell is CERTIFIED when the lower bound clears the threshold at every pose, and
FALSIFIED otherwise, with the worst pose reported as the witness. The witness is the
single frame worth driving, and driving it is M7.

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
import carla_jobs as J  # noqa: E402
from run_policy import load_policy, BRAKE_THRESHOLD_FRACTION  # noqa: E402

CAPTURES = J.REPO / "results" / "captures"
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
        "--property", choices=["S", "A"], default="S",
        help="S: must brake inside r_req. A: must NOT brake on the false-activation "
             "scenario, upper bound at most 0.25 g, PROTOCOL section 7",
    )
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model, w, h = load_policy(args.policy, args.policy_scenario, dev)
    b = json.loads((OUT / "braking.json").read_text())
    a_max = b["a_max_g_worst"] * 9.81
    threshold = a_max * BRAKE_THRESHOLD_FRACTION
    rr = J.r_req_m(J.HAZARD_MPH * J.MPH, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2)
    knots = json.loads((OUT / "family_knots.json").read_text())["knots_sun_altitude_deg"]

    # The no-target control replays the LEAD poses, so it has no states file of its own.
    states_name = "lead" if args.scenario == "none" else args.scenario
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
    print(
        f"\n{args.policy} / {args.scenario}: {len(poses)} poses inside r_req "
        f"({rr:.2f} m), {len(knots) - 1} sub-intervals, threshold {threshold:.3f} m/s^2",
        flush=True,
    )

    stored = {
        round(float(np.load(p)["sun_altitude_deg"]), 3): p
        for p in CAPTURES.glob(f"{args.scenario}_sun*.npz")
    }

    cells = []
    for hi_alt, lo_alt in zip(knots[:-1], knots[1:]):
        t0 = time.time()
        a_imgs = np.load(stored[round(hi_alt, 3)])["images"]
        b_imgs = np.load(stored[round(lo_alt, 3)])["images"]
        worst_lb = None
        witness = None
        for i in poses:
            lo = prepare(a_imgs[i], w, h).to(dev)
            hi = prepare(b_imgs[i], w, h).to(dev)
            fam = Family(lo, hi, model).to(dev).eval()
            s = torch.zeros(1, 1, device=dev)
            bm = BoundedModule(fam, s, device=dev)
            ptb = PerturbationLpNorm(
                norm=float("inf"),
                x_L=torch.full_like(s, -1.0),
                x_U=torch.full_like(s, 1.0),
            )
            lb, ub = bm.compute_bounds(x=(BoundedTensor(s, ptb),), method=args.method)
            # S wants the LOWEST output (does it always brake?); A wants the HIGHEST
            # (does it ever brake when it should not?).
            val = float(lb.item()) if args.property == "S" else float(ub.item())
            if worst_lb is None or (
                val < worst_lb if args.property == "S" else val > worst_lb
            ):
                worst_lb, witness = val, i
        certified = (
            worst_lb >= threshold if args.property == "S" else worst_lb <= threshold
        )
        cells.append(
            {
                "from_deg": hi_alt,
                "to_deg": lo_alt,
                "worst_bound_mps2": round(worst_lb, 4),
                "threshold_mps2": round(threshold, 4),
                "margin_x_threshold": round(worst_lb / threshold, 4),
                "verdict": "CERTIFIED" if certified else "FALSIFIED",
                "witness_pose": witness,
                "witness_range_m": round(float(ranges[witness]), 3),
                "seconds": round(time.time() - t0, 1),
            }
        )
        print(
            f"  {hi_alt:+8.3f} to {lo_alt:+8.3f}  bound {worst_lb:8.3f}  "
            f"{worst_lb / threshold:6.2f}x threshold  "
            f"{'CERTIFIED' if certified else 'FALSIFIED'}"
            f"{'' if certified else f'  witness pose {witness} at {ranges[witness]:.1f} m'}"
            f"  [{time.time() - t0:.0f}s]",
            flush=True,
        )

    payload = {
        "policy": args.policy,
        "scenario": args.scenario,
        "property": args.property,
        "method": args.method,
        "threshold_mps2": round(threshold, 4),
        "r_req_m": round(rr, 3),
        "poses_inside_r_req": len(poses),
        "cells": cells,
        "falsified": [c for c in cells if c["verdict"] == "FALSIFIED"],
        "note": (
            "Property S from PROTOCOL section 7, on the same threshold the closed-loop "
            "controller latches at. Certified means the lower bound clears it at every "
            "pose inside r_req for every illumination in the sub-interval. WRITTEN "
            "BEFORE ANY DRIVING; that ordering is what makes these predictions."
        ),
    }
    suffix = "" if args.property == "S" else "_A"
    path = OUT / f"verify_{args.policy}_{args.scenario}{suffix}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    n_bad = len(payload["falsified"])
    print(
        f"\n  {len(cells) - n_bad}/{len(cells)} sub-intervals certified, "
        f"{n_bad} falsified"
    )
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
