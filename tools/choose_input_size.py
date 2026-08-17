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
    if not path.exists():
        raise SystemExit(f"no capture at {path}; run tools/capture_campaign.py first")
    d = np.load(path)
    images, ranges = d["images"], d["range_m"]

    b = json.loads((J.REPO / "results" / "carla" / "braking.json").read_text())
    v = J.HAZARD_MPH * J.MPH
    rr = J.r_req_m(v, b["a_max_g_worst"], b["t_lat_s_worst"] or 0.2)

    near = int(np.argmin(np.abs(ranges - rr)))
    far = int(np.argmax(ranges))
    print(f"\n{args.scenario}, sun {args.knot}")
    print(f"  r_req {rr:.1f} m; closest captured pose {ranges[near]:.1f} m (index {near})")
    print(f"  farthest pose {ranges[far]:.1f} m, used as the target-free reference\n")

    print(f"  {'input':>12}{'contrast at r_req':>20}{'contrast at far':>18}{'ratio':>8}")
    rows = []
    for w, h in CANDIDATES:
        a = downsample(images[near], w, h)
        c = downsample(images[far], w, h)
        diff = np.abs(a - c).mean()
        # A frame differs from the reference for reasons other than the target too, so
        # the useful figure is how much MORE it differs where the target is.
        band = slice(int(h * 0.35), int(h * 0.8))
        near_c = np.abs(a[band] - c[band]).mean()
        rows.append((w, h, float(diff), float(near_c)))
        print(f"  {w:5d} x {h:<4d}{near_c:20.2f}{diff:18.2f}{near_c / max(diff, 1e-6):8.2f}")

    print(
        "\n  Contrast is mean absolute difference in 0-255 units against a frame with\n"
        "  the target far away. It falls as the input shrinks; the size to choose is\n"
        "  the smallest where the target is still clearly above the background\n"
        "  difference, since every extra pixel costs the verifier ReLU neurons.\n"
    )
    (J.REPO / "results" / "carla" / f"input_size_{args.scenario}.json").write_text(
        json.dumps(
            {
                "r_req_m": round(rr, 2),
                "pose_range_m": float(ranges[near]),
                "candidates": [
                    {"w": w, "h": h, "target_band_contrast": round(nc, 3),
                     "whole_frame_contrast": round(df, 3)}
                    for w, h, df, nc in rows
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
