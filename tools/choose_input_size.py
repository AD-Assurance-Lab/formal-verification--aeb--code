"""How small can the network input be before the target stops being visible?

    python tools/choose_input_size.py --scenario lead

PROTOCOL section 1 leaves the network input size open, to be fixed at M2 and recorded,
and says only that it must be larger than a lane-keeping crop because a pedestrian at
`r_req` has to survive downsampling. This measures it instead of asserting it.

Method: take the captured frame at the pose closest to `r_req`, which is the last moment
braking can still succeed and therefore the hardest frame that matters. Downsample to a
range of candidate sizes and measure how much of the target survives, as the contrast
between the target's image region and the same region in a frame captured without a
target present.

A size that cannot resolve the target at `r_req` cannot support a policy that brakes at
`r_req`, whatever it scores in training.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

CAPTURES = J.REPO / "results" / "captures"
CANDIDATES = [(64, 48), (100, 66), (128, 96), (200, 66), (200, 150), (320, 240)]


def downsample(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Area-average downsample. No dependency beyond numpy."""
    H, W = img.shape[:2]
    ys = (np.arange(h + 1) * H // h)
    xs = (np.arange(w + 1) * W // w)
    out = np.empty((h, w, img.shape[2]), dtype=np.float32)
    for j in range(h):
        for i in range(w):
            out[j, i] = img[ys[j]:ys[j + 1], xs[i]:xs[i + 1]].mean(axis=(0, 1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", choices=["lead", "ped"], default="lead")
    ap.add_argument("--knot", default="+60.000", help="sun altitude tag of the file")
    args = ap.parse_args()

    path = CAPTURES / f"{args.scenario}_sun{args.knot}.npz"
    control_path = CAPTURES / f"none_sun{args.knot}.npz"
    for p_ in (path, control_path):
        if not p_.exists():
            raise SystemExit(
                f"missing {p_.name}. Capture the scenario AND the no-target control:\n"
                "  python tools/capture_campaign.py --scenario lead\n"
                "  python tools/capture_campaign.py --scenario none"
            )
    d = np.load(path)
    ctrl = np.load(control_path)
    images, ranges = d["images"], d["range_m"]
    control = ctrl["images"]
    if len(control) != len(images):
        raise SystemExit("control and scenario have different pose counts")

    b = json.loads((J.REPO / "results" / "carla" / "braking.json").read_text())
    v = J.HAZARD_MPH * J.MPH
    rr = J.r_req_m(v, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2)

    near = int(np.argmin(np.abs(ranges - rr)))
    far = int(np.argmax(ranges))
    print(f"\n{args.scenario}, sun {args.knot}")
    print(f"  r_req {rr:.1f} m; closest captured pose {ranges[near]:.1f} m (index {near})")
    print("  control: the SAME pose with no target present\n")

    # The measure is the PEAK difference, not the mean. The control has no target at
    # all, so every difference is the target; the question is only whether it survives
    # downsampling. A mean over the whole image answers a different question, namely
    # what fraction of the frame the target occupies, and it came back flat at every
    # size because the answer is "a small one" regardless.
    print(
        f"  {'input':>12}{'peak diff':>12}{'99.9th pct':>12}"
        f"{'px over 20':>12}{'same at 60 m':>14}"
    )
    rows = []
    for w, h in CANDIDATES:
        d_near = np.abs(
            downsample(images[near], w, h) - downsample(control[near], w, h)
        )
        d_far = np.abs(
            downsample(images[far], w, h) - downsample(control[far], w, h)
        )
        peak = float(d_near.max())
        p999 = float(np.percentile(d_near, 99.9))
        over = int((d_near > 20).sum())
        rows.append((w, h, peak, p999, over, float(d_far.max())))
        print(
            f"  {w:5d} x {h:<4d}{peak:12.1f}{p999:12.1f}{over:12d}{d_far.max():14.1f}"
        )

    print(
        "\n  Every difference IS the target: the control has none. Peak difference in\n"
        "  0-255 units says whether it survives downsampling at r_req, the last moment\n"
        "  braking can still succeed. The 60 m column is the same target much further\n"
        "  away, for scale. Choose the smallest input that still resolves it, since\n"
        "  every extra pixel costs the verifier ReLU neurons.\n"
    )
    (J.REPO / "results" / "carla" / f"input_size_{args.scenario}.json").write_text(
        json.dumps(
            {
                "r_req_m": round(rr, 2),
                "pose_range_m": float(ranges[near]),
                "candidates": [
                    {"w": w, "h": h, "peak_diff": round(pk, 2),
                     "pct999": round(p9, 2), "px_over_20": ov,
                     "peak_diff_at_60m": round(fr, 2)}
                    for w, h, pk, p9, ov, fr in rows
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
