"""Train the two policies that differ only in how the illumination axis was sampled.

    python tools/train_policies.py --input-w 128 --input-h 96

CLAUDE.md section 5. `P_pts` sees only the regulatory test points, which is what a
manufacturer optimising against the test matrix builds. `P_cont` sees the continuum.
Architecture, recipe, epochs and data volume are identical; the ONLY difference is which
illumination knots the frames come from. That is what makes any later gap attributable
to the sampling rather than to capacity, and it is why cells 3 and 4 of the ledger exist.

Both are trained as teacher then student. The teacher is a distillation source and is
never verified. The student is ReLU-only with no BatchNorm or Dropout, because those
cause interval-bound explosion, and it is the thing the certificate is computed on.

**Engineering the gap is forbidden** (CLAUDE.md section 5). `P_pts` is trained on the
regulatory points because that is what the standard incentivises. Weakening it further
to manufacture a failure would void the result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# BEFORE torch is imported. cuBLAS reads this variable when it creates its handle, which
# happens at the first matmul, and a handle already created never re-reads it. Setting it
# in main() is too late and fails silently: torch.use_deterministic_algorithms then raises
# at the first affected kernel instead. This is the value CUDA >= 10.2 documents for a
# deterministic workspace.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu import require_cuda  # noqa: E402
import carla_jobs as J  # noqa: E402
from expert_law import label_decel  # noqa: E402

CAPTURES = J.CAPTURES
MODELS = J.MODELS

_b = json.loads((J.OUT / "braking.json").read_text())
A_MAX_MPS2 = _b["a_max_g_worst"] * 9.81
R_REQ_M = J.r_req_m(J.HAZARD_MPH * J.MPH, _b["a_max_g_worst"], _b["t_lat_s_worst"] or 0.2)

# The two regulatory lighting conditions that are ENDPOINTS of the certified interval.
REGULATORY_KNOTS = [60.0, -30.0]

# The three policies, and the ONE thing that differs between them.
#
#   P_pts   the two regulatory conditions that bound the certified interval. This is the
#           frozen section 5 comparison against P_cont and it does not move.
#   P_cont  the illumination continuum, every knot.
#   P_pts3  the regulatory MATRIX: both endpoints plus darkness with UPPER beam, which
#           FMVSS 127 tests and which P_pts has never seen. Added 2026-09-07 because
#           "what a manufacturer optimising against the test matrix builds" was being
#           represented by a policy trained on two thirds of that matrix. It is a third
#           arm rather than a redefinition of P_pts, so the existing comparison is
#           undisturbed and this one answers its own question: does the dusk gap survive
#           when the policy has seen every lighting condition the standard tests?
POLICY_ARMS = {
    "P_pts": {"knots": REGULATORY_KNOTS, "highbeam": False},
    "P_cont": {"knots": None, "highbeam": False},
    "P_pts3": {"knots": REGULATORY_KNOTS, "highbeam": True},
}


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


def load(scenario: str, knots: list[float] | None, w: int, h: int,
         highbeam: bool = False):
    """Load captures, crop to the road region, downsample, normalise.

    Loads the scenario AND the no-target control, the latter labelled zero at every
    range. Without the control, "a target is there" and "the ego is near the conflict
    point" are perfectly correlated in the training set, and the network fits the labels
    by learning position from road geometry without ever looking at the target. Measured
    before this was added: both policies commanded 2.8 to 5.1 m/s^2 on an empty road, and
    one of them exceeded the latch threshold. See amendment A10.
    """
    xs, ys, ks = [], [], []
    sources = sorted(CAPTURES.glob(f"{scenario}_sun*.npz"))
    # The A10 control must replay THIS scenario's poses, or position stays
    # informative: none replays the lead poses, none_ped the ped poses.
    ctrl = "none_ped" if scenario == "ped" else "none"
    sources += sorted(CAPTURES.glob(f"{ctrl}_sun*.npz"))
    if highbeam:
        # The upper-beam darkness capture, and its own no-target control. "{x}_sun*" does
        # not match "{x}_hb_sun*", so these only ever arrive when asked for.
        sources += sorted(CAPTURES.glob(f"{scenario}_hb_sun*.npz"))
        sources += sorted(CAPTURES.glob(f"{ctrl}_hb_sun*.npz"))
    for path in sources:
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
        # Labels are RECOMPUTED from range, not read from the capture. The law lives in
        # one place (tools/expert_law.py) so training and verification cannot drift
        # apart, and the captures stay valid when the law is corrected.
        rng = d["range_m"]
        if path.name.startswith(("none_sun", "none_ped_sun",
                                 "none_hb_sun", "none_ped_hb_sun")):
            # Nothing ahead, so nothing to brake for, at any range.
            lab = torch.zeros(len(rng), 1)
        else:
            lab = torch.tensor(
                [label_decel(float(r), R_REQ_M, A_MAX_MPS2) for r in rng]
            ).float().unsqueeze(1)
        ys.append(lab)
        ks += [knot] * len(imgs)
    if not xs:
        raise SystemExit(f"no captures for {scenario} at the requested knots")
    return torch.cat(xs), torch.cat(ys), ks


def equalise(sets):
    """Give every policy the same number of training samples.

    P_pts draws from 2 illumination knots and P_cont from 12, so without this P_cont
    sees six times the frames and any difference between them could be attributed to
    DATA VOLUME rather than to how the axis was sampled. CLAUDE.md section 5 requires
    them identical in everything except which knots the frames came from, and this is
    the part that is easy to get wrong silently.

    The smaller set is oversampled rather than the larger one truncated, so P_cont keeps
    the diversity that is the whole point of it.
    """
    target = max(len(x) for x, _, _ in sets)
    out = []
    for x, y, ks in sets:
        if len(x) < target:
            idx = torch.arange(target) % len(x)
            x, y = x[idx], y[idx]
        out.append((x, y, ks))
    return out


def make_deterministic() -> dict:
    """Pin every source of run-to-run drift inside torch, and say what was pinned.

    FINDINGS F29. Seeding torch, random and numpy is NOT enough on CUDA. Two consecutive
    trainings of P_pts at seed 0, on byte-identical frames, differed in all ten tensors
    and 77.1% of parameters, and endpoint verdicts flipped with them. The seeds were
    correct; the kernels underneath them were free to choose a different algorithm and a
    different reduction order on each run.

    Three separate mechanisms, and all three have to be closed:

      * cuDNN benchmarking picks a convolution algorithm by timing candidates on the
        first call, so the algorithm depends on what else the GPU was doing. Different
        algorithm, different summation order, different rounding.
      * Several kernels have no deterministic implementation at all unless asked.
      * cuBLAS reduction order depends on its workspace, which is why
        CUBLAS_WORKSPACE_CONFIG is set at the top of this file, before torch is
        imported.

    `use_deterministic_algorithms(True)` RAISES on an operation with no deterministic
    kernel rather than degrading quietly. That is the behaviour we want: a training run
    that cannot reproduce itself should fail, not produce a network nobody can
    re-measure.
    """
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    return {
        "use_deterministic_algorithms": True,
        "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
        "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "finding": "F29",
    }


def weights_sha256(state_dict) -> str:
    """Hash the WEIGHTS, in a fixed key order, not the file that holds them.

    A file hash also covers the container. If two trainings ever produce the same numbers
    inside a differently packed archive, a file hash calls that a difference and sends the
    next reader after a defect that is not there. This hash answers exactly the question
    F29 asks: are the two networks the same network?
    """
    h = hashlib.sha256()
    for k in sorted(state_dict):
        t = state_dict[k].detach().cpu().contiguous()
        h.update(k.encode())
        h.update(str(tuple(t.shape)).encode())
        h.update(str(t.dtype).encode())
        h.update(t.numpy().tobytes())
    return h.hexdigest()


def class_weights(y, a_max: float):
    """The step label is heavily imbalanced: only poses inside r_req are positive.

    Measured on the lead capture, about 15 of 104 poses. Unweighted MSE on a step with a
    6:1 imbalance biases the model toward never braking, which is the failure that
    matters most here.
    """
    pos = (y > a_max * 0.5).float()
    frac = float(pos.mean().clamp(1e-3, 1 - 1e-3))
    w = torch.where(pos > 0, (1 - frac) / frac, torch.ones_like(pos))
    return w / w.mean()


def fit(model, x, y, epochs: int, lr: float, dev, tag: str, teacher=None, w=None):
    model.to(dev).train()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    n = len(x)
    idx = torch.randperm(n)
    x, y = x[idx].to(dev), y[idx].to(dev)
    w = (torch.ones_like(y) if w is None else w[idx]).to(dev)
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
            loss = (w[b] * (model(x[b]) - y[b]) ** 2).mean()
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
    ap.add_argument("--seed", type=int, default=0,
                    help="seeds EVERY arm identically, so the arms are matched draws")
    ap.add_argument("--policies", nargs="+", default=list(POLICY_ARMS),
                    choices=list(POLICY_ARMS))
    ap.add_argument("--scratch", type=Path, default=None,
                    help="write the checkpoints and the report HERE instead of into "
                         "results/. For the F29 repeat test: train twice and compare, "
                         "without overwriting the study's own models.")
    ap.add_argument("--allow-nondeterministic", action="store_true",
                    help="run WITHOUT the F29 determinism pins. For measuring what they "
                         "cost, and for nothing else. The report records which was used.")
    args = ap.parse_args()

    # require_cuda, not is_available(): the flag is False while CARLA initialises on
    # the same device, and TRUE on a card whose kernels the installed torch does not
    # carry (sm_120 vs an sm_90 build). Both end in a silent CPU run that still prints
    # numbers. See tools/gpu.py.
    dev = require_cuda()
    # Seed every RNG in use: weight init and torch.randperm were nondeterministic,
    # so "retrain, re-verify, re-drive" (A10) could not be reproduced (audit F12).
    # Seeding is necessary and NOT sufficient on CUDA -- see make_deterministic and F29.
    import random as _random
    determinism = (
        {"use_deterministic_algorithms": False, "finding": "F29", "note":
         "--allow-nondeterministic: this run does not reproduce and nothing measured "
         "from it may be quoted"}
        if args.allow_nondeterministic else make_deterministic()
    )
    models_dir = args.scratch if args.scratch else MODELS
    models_dir.mkdir(parents=True, exist_ok=True)
    report = {"input": [args.input_w, args.input_h], "device": dev, "seed": args.seed,
              "determinism": determinism, "policies": {}}
    started = time.perf_counter()

    names = args.policies
    raw = [
        load(args.scenario, POLICY_ARMS[n]["knots"], args.input_w, args.input_h,
             highbeam=POLICY_ARMS[n]["highbeam"])
        for n in names
    ]
    print(f"  before equalising: {dict(zip(names, [len(x) for x, _, _ in raw]))} frames")
    balanced = equalise(raw)

    for name, (x, y, ks) in zip(names, balanced):
        # SEEDED PER ARM, with the same seed for every arm. Previously the RNG was seeded
        # once and the policies were trained in sequence, so P_cont's weight
        # initialisation and shuffling depended on how much randomness P_pts had already
        # consumed -- the arms were neither independent draws nor matched ones. CLAUDE.md
        # section 5 asks for two policies identical in everything except which knots the
        # frames came from; matched seeds are what makes that true of the initialisation
        # as well as the recipe, and they are the precondition for the seed sweep that
        # has to establish this gap is not one draw's luck.
        torch.manual_seed(args.seed)
        _random.seed(args.seed)
        np.random.seed(args.seed)
        w = class_weights(y, A_MAX_MPS2)
        print(
            f"\n{name}: {len(x)} samples from {len(set(ks))} knots, "
            f"{int((y > A_MAX_MPS2 * 0.5).sum())} braking"
        )
        teacher = fit(
            Teacher(args.input_w, args.input_h), x, y, args.epochs, args.lr, dev,
            f"{name} teacher", w=w,
        )
        student = fit(
            Student(args.input_w, args.input_h), x, y, args.epochs, args.lr, dev,
            f"{name} student", teacher=teacher, w=w,
        )
        # Seed 0 keeps the plain name, so the study's own models are untouched. A
        # non-zero seed puts the tag on the POLICY half of the name -- P_pts_s3_lead.pt --
        # so every downstream tool can address it by passing --policy P_pts_s3 and none of
        # them need to learn what a seed is.
        tag = "" if args.seed == 0 else f"_s{args.seed}"
        path = models_dir / f"{name}{tag}_{args.scenario}.pt"
        torch.save(
            {"state_dict": student.state_dict(),
             "input": [args.input_w, args.input_h],
             "seed": args.seed,
             "highbeam": POLICY_ARMS[name]["highbeam"],
             "knots": sorted(set(ks))},
            path,
        )
        with torch.no_grad():
            err = float(
                nn.functional.l1_loss(student(x.to(dev)), y.to(dev)).item()
            )
        params = sum(p.numel() for p in student.parameters())
        # The hash of the WEIGHTS, recorded beside the run that made them. This is the
        # F29 test made routine: any two trainings that claim the same seed and the same
        # frames can be compared by reading two JSON files, with no GPU and no rerun.
        wsha = weights_sha256(student.state_dict())
        print(f"  {name}: student {params} params, train MAE {err:.4f} m/s^2 -> {path.name}")
        print(f"    weights_sha256 {wsha}")
        report["policies"][name] = {
            "samples": len(x),
            "braking_samples": int((y > A_MAX_MPS2 * 0.5).sum()),
            "knots": sorted(set(ks)),
            "highbeam_condition": POLICY_ARMS[name]["highbeam"],
            "student_params": params,
            "train_mae_mps2": round(err, 4),
            "file": path.name,
            "weights_sha256": wsha,
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    report["scenario"] = args.scenario
    report["wall_seconds"] = round(time.perf_counter() - started, 1)
    report["note"] = (
        "Identical architecture, recipe, epochs and frame count. The ONLY difference is "
        "which illumination knots the frames came from. Train MAE is not a result; the "
        "result is whether each policy passes the regulatory endpoints closed loop, "
        "which is milestone M4."
    )
    # ONE FILE PER SCENARIO. This wrote a single training.json, so training lead and then
    # ped left one record describing ped and nothing at all describing lead -- while the
    # file's own name implied it covered the training. Same shape as
    # policy_endpoints{suffix}.json and gate_*{suffix}.json elsewhere here.
    suffix = "" if args.scenario == "lead" else f"_{args.scenario}"
    suffix += "" if args.seed == 0 else f"_s{args.seed}"
    path = (models_dir if args.scratch
            else J.OUT) / f"training{suffix}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n  wrote {path}  ({report['wall_seconds']:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
