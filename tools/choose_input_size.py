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

    print(f"  {'input':>12}{'target signal':>16}{'scene noise':>14}{'ratio':>8}")
    rows = []
    for w, h in CANDIDATES:
        with_t = downsample(images[near], w, h)
        without = downsample(control[near], w, h)
        signal = float(np.abs(with_t - without).mean())
        # At the farthest pose the target is 60 m away and contributes almost nothing,
        # so the same difference there is the floor: rendering noise and whatever else
        # separates the two runs. The ratio is what says the target is visible at all.
        noise = float(
            np.abs(
                downsample(images[far], w, h) - downsample(control[far], w, h)
            ).mean()
        )
        rows.append((w, h, noise, signal))
        print(f"  {w:5d} x {h:<4d}{signal:16.3f}{noise:14.3f}{signal / max(noise, 1e-6):8.2f}")

    print(
        "\n  Signal is the mean absolute difference, in 0-255 units, between the frame\n"
        "  at r_req and the SAME pose with no target. Noise is that difference at the\n"
        "  farthest pose, where the target contributes almost nothing. Choose the\n"
        "  smallest input whose ratio is comfortably above 1, since every extra pixel\n"
        "  costs the verifier ReLU neurons.\n"
    )
    (J.REPO / "results" / "carla" / f"input_size_{args.scenario}.json").write_text(
        json.dumps(
            {
                "r_req_m": round(rr, 2),
                "pose_range_m": float(ranges[near]),
                "candidates": [
                    {"w": w, "h": h, "target_signal": round(sig, 4),
                     "scene_noise": round(noi, 4),
                     "ratio": round(sig / max(noi, 1e-6), 3)}
                    for w, h, noi, sig in rows
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
