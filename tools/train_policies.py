"""Train the two policies that differ only in how the illumination axis was sampled.

    python tools/train_policies.py --input-w 128 --input-h 96

PROTOCOL section 5. `P_pts` sees only the regulatory test points, which is what a
manufacturer optimising against the test matrix builds. `P_cont` sees the continuum.
Architecture, recipe, epochs and data volume are identical; the ONLY difference is which
illumination knots the frames come from. That is what makes any later gap attributable
to the sampling rather than to capacity, and it is why cells 3 and 4 of the ledger exist.

Both are trained as teacher then student. The teacher is a distillation source and is
never verified. The student is ReLU-only with no BatchNorm or Dropout, because those
cause interval-bound explosion, and it is the thing the certificate is computed on.

**Engineering the gap is forbidden** (PROTOCOL section 5). `P_pts` is trained on the
regulatory points because that is what the standard incentivises. Weakening it further
to manufacture a failure would void the result.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

CAPTURES = J.REPO / "results" / "captures"
MODELS = J.REPO / "results" / "models"

# The two regulatory endpoints present in the captures. Darkness with upper beam is a
# third regulatory point and is not captured yet; see the note in the results file.
REGULATORY_KNOTS = [60.0, -30.0]


class Teacher(nn.Module):
    """PilotNet-class. Distillation source only, never verified."""

    def __init__(self, w: int, h: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 24, 5, stride=2), nn.ReLU(),
            nn.Conv2d(24, 36, 5, stride=2), nn.ReLU(),
            nn.Conv2d(36, 48, 5, stride=2), nn.ReLU(),
            nn.Conv2d(48, 64, 3), nn.ReLU(),
            nn.Conv2d(64, 64, 3), nn.ReLU(),
        )
        with torch.no_grad():
            n = self.features(torch.zeros(1, 3, h, w)).numel()
        self.head = nn.Sequential(
            nn.Flatten(), nn.Linear(n, 100), nn.ReLU(),
            nn.Linear(100, 50), nn.ReLU(),
            nn.Linear(50, 10), nn.ReLU(),
            nn.Linear(10, 1),
        )

    def forward(self, x):
        return self.head(self.features(x))


class Student(nn.Module):
    """Small, ReLU-only, no BatchNorm or Dropout. This is what gets verified."""

    def __init__(self, w: int, h: int, width: int = 16):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, width, 5, stride=2), nn.ReLU(),
            nn.Conv2d(width, width * 2, 5, stride=2), nn.ReLU(),
            nn.Conv2d(width * 2, width * 2, 3, stride=2), nn.ReLU(),
        )
        with torch.no_grad():
            n = self.features(torch.zeros(1, 3, h, w)).numel()
        self.head = nn.Sequential(
            nn.Flatten(), nn.Linear(n, 64), nn.ReLU(), nn.Linear(64, 1)
        )

    def forward(self, x):
        return self.head(self.features(x))


def load(scenario: str, knots: list[float] | None, w: int, h: int):
    """Load captures, crop to the road region, downsample, normalise."""
    xs, ys, ks = [], [], []
    for path in sorted(CAPTURES.glob(f"{scenario}_sun*.npz")):
        d = np.load(path)
        knot = float(d["sun_altitude_deg"])
        if knots is not None and not any(abs(knot - k) < 1e-3 for k in knots):
            continue
        imgs = d["images"]  # N, H, W, 3 uint8
        # The target sits ahead and near the horizon. Crop the middle band, which is
        # the same crop for every policy so it cannot advantage one of them.
        H = imgs.shape[1]
        band = imgs[:, int(H * 0.35):int(H * 0.85)]
        t = torch.from_numpy(band).permute(0, 3, 1, 2).float() / 255.0
        t = torch.nn.functional.interpolate(
            t, size=(h, w), mode="area"
        )
        xs.append(t)
        ys.append(torch.from_numpy(d["label_decel_mps2"]).float().unsqueeze(1))
        ks += [knot] * len(imgs)
    if not xs:
        raise SystemExit(f"no captures for {scenario} at the requested knots")
    return torch.cat(xs), torch.cat(ys), ks


def fit(model, x, y, epochs: int, lr: float, dev, tag: str, teacher=None):
    model.to(dev).train()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    n = len(x)
    idx = torch.randperm(n)
    x, y = x[idx].to(dev), y[idx].to(dev)
    if teacher is not None:
        teacher.eval()
        with torch.no_grad():
            y = teacher(x)  # distil onto the teacher's outputs, not the raw labels
    for ep in range(epochs):
        perm = torch.randperm(n, device=dev)
        total = 0.0
        for i in range(0, n, 32):
            b = perm[i:i + 32]
            opt.zero_grad()
            loss = loss_fn(model(x[b]), y[b])
            loss.backward()
            opt.step()
            total += loss.item() * len(b)
        if ep % 10 == 0 or ep == epochs - 1:
            print(f"    {tag} epoch {ep:3d}  mse {total / n:.5f}", flush=True)
    return model


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="lead")
    ap.add_argument("--input-w", type=int, required=True)
    ap.add_argument("--input-h", type=int, required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--lr", type=float, default=1e-3)
    args = ap.parse_args()

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    MODELS.mkdir(parents=True, exist_ok=True)
    report = {"input": [args.input_w, args.input_h], "device": dev, "policies": {}}

    for name, knots in (("P_pts", REGULATORY_KNOTS), ("P_cont", None)):
        x, y, ks = load(args.scenario, knots, args.input_w, args.input_h)
        print(f"\n{name}: {len(x)} frames from {len(set(ks))} illumination knots")
        teacher = fit(
            Teacher(args.input_w, args.input_h), x, y, args.epochs, args.lr, dev,
            f"{name} teacher",
        )
        student = fit(
            Student(args.input_w, args.input_h), x, y, args.epochs, args.lr, dev,
            f"{name} student", teacher=teacher,
        )
        path = MODELS / f"{name}_{args.scenario}.pt"
        torch.save(
            {"state_dict": student.state_dict(),
             "input": [args.input_w, args.input_h],
             "knots": sorted(set(ks))},
            path,
        )
        with torch.no_grad():
            err = float(
                nn.functional.l1_loss(student(x.to(dev)), y.to(dev)).item()
            )
        params = sum(p.numel() for p in student.parameters())
        print(f"  {name}: student {params} params, train MAE {err:.4f} m/s^2 -> {path.name}")
        report["policies"][name] = {
            "frames": len(x),
            "knots": sorted(set(ks)),
            "student_params": params,
            "train_mae_mps2": round(err, 4),
            "file": path.name,
        }

    report["note"] = (
        "Identical architecture, recipe, epochs and frame count. The ONLY difference is "
        "which illumination knots the frames came from. Train MAE is not a result; the "
        "result is whether each policy passes the regulatory endpoints closed loop, "
        "which is milestone M4."
    )
    (J.REPO / "results" / "carla" / "training.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print("\n  wrote results/carla/training.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
