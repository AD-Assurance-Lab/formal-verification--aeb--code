"""Are the captured frames actually paired across the illumination axis?

    python tools/check_pairing.py

The disturbance family interpolates between two frames pixel by pixel. That is only
meaningful if the two frames are the same scene from the same place, so every knot has
to replay the identical pose sequence. This checks it rather than assuming it, which is
worth doing because it has already failed once: two knots captured in an earlier
invocation differed by 0.7 mm, small enough to be invisible and large enough to break
the guarantee the whole design rests on.

Also reports how much the image actually changes across the axis. If two knots differ by
almost nothing, there is no disturbance to certify against.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

CAPTURES = J.REPO / "results" / "captures"
POSE_TOL_M = 1e-4


def check(scenario: str) -> bool:
    files = sorted(CAPTURES.glob(f"{scenario}_sun*.npz"))
    if not files:
        print(f"{scenario}: no captures")
        return True
    ref = None
    ok = True
    knots = []
    for f in files:
        d = np.load(f)
        r = d["range_m"]
        knots.append(float(d["sun_altitude_deg"]))
        if ref is None:
            ref, ref_name = r, f.name
            continue
        if len(r) != len(ref):
            print(f"  {f.name}: {len(r)} poses, reference has {len(ref)}")
            ok = False
        elif not np.allclose(r, ref, atol=POSE_TOL_M):
            print(
                f"  {f.name}: poses differ from {ref_name} by up to "
                f"{np.abs(r - ref).max() * 1000:.2f} mm"
            )
            ok = False

    lo, hi = np.load(files[0]), np.load(files[-1])
    mid = len(ref) // 2
    spread = float(
        np.abs(lo["images"][mid].astype(np.float32) - hi["images"][mid].astype(np.float32)).mean()
    )
    print(
        f"{scenario}: {len(files)} knots ({min(knots):+.1f} to {max(knots):+.1f} deg), "
        f"{len(ref)} poses each, range {ref.max():.1f} to {ref.min():.1f} m"
    )
    print(f"  pose pairing: {'exact' if ok else 'BROKEN'}")
    print(f"  image change across the axis at mid-approach: {spread:.1f} / 255")
    if spread < 5.0:
        print("  WARNING: barely any change across the axis; nothing to certify against")
        ok = False
    return ok


def main() -> int:
    all_ok = True
    for scenario in ("lead", "ped", "none"):
        all_ok &= check(scenario)
        print()
    print("pairing check:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
