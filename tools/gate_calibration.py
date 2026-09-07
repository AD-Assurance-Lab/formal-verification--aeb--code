"""Does the in-between gate predict when a blend-based certificate transfers to a render?

    python tools/gate_calibration.py

No simulator. Joins three artifacts this study already produces and asks a question none of
them answers alone.

**The gap being measured.** The certificate quantifies over BLENDS -- pixel interpolations
between two rendered knots. The witness drives happen at RENDERS. Nothing in between is
guaranteed, and PROTOCOL section 4 knows it: it requires the in-between check and says the
behavioural version is the one that decides. But the gate is currently used as a pass/fail
at 1.0, and a pass/fail cannot say whether a value of 0.68 is meaningfully worse than 0.16.

If the gate is a good instrument, sub-intervals with a high gate value should be where the
certificate and the drive disagree, and sub-intervals with a low one should be where they
agree. That is a testable claim about the study's own methodology and this measures it.

**What each outcome means for the paper.**

  gate predicts disagreement    the gate is a calibrated instrument, the threshold at 1.0
                                is defensible, and the paper can say how far a certificate
                                transfers as a function of a number it already computes.
  gate predicts nothing         the gate is a formality. It passes everything it is asked
                                about and tells you nothing about the risk it exists to
                                bound, and the paper should stop implying otherwise.
  disagreement everywhere       the family is the problem, not its width.

The honest version of this study reports whichever it finds. A gate that turns out to be
uninformative is a finding about the method, and it is cheaper to learn it here than from
a reviewer.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"


def _key(c):
    return (round(c["from_deg"], 6), round(c["to_deg"], 6))


def collect() -> list[dict]:
    """One row per (policy, scenario, sub-interval) that has all three artifacts."""
    from capture_campaign import load_uncovered
    unc = load_uncovered()

    def uncovered(k):
        return any(abs(u["from_deg"] - k[0]) < 1e-6 and abs(u["to_deg"] - k[1]) < 1e-6
                   for u in unc)

    rows = []
    for vpath in sorted(OUT.glob("verify_*.json")):
        stem = vpath.stem
        if stem.endswith("_A") or "_none" in stem:
            continue                                    # property A has no witness drive
        parts = stem.split("_")                         # verify_<policy>_<scenario>
        policy, scenario = parts[1], "_".join(parts[2:])
        gsuffix = "" if scenario == "lead" else f"_{scenario}"
        gpath = OUT / f"gate_inbetween_{policy}{gsuffix}.json"
        wpath = OUT / f"witness_{policy}_{scenario}.json"
        if not (gpath.exists() and wpath.exists()):
            continue
        v = json.loads(vpath.read_text())
        g = {_key(c): c for c in json.loads(gpath.read_text())["sub_intervals"]}
        w = {_key(c): c for c in json.loads(wpath.read_text())["cells"]}
        wcells = json.loads(wpath.read_text())["cells"]
        if wcells and "passes_protocol" not in wcells[0]:
            # Pre-FINDINGS-F9 artifact: its `passes` count folds in the prematurity
            # condition, which is property A. Scoring a property-S certificate against it
            # is the mismatch that manufactured a soundness violation out of a policy
            # braking too early, and it would land here as a spurious
            # "certified_then_failed". Refuse rather than analyse it.
            raise SystemExit(
                f"{wpath.name} predates the property-S/property-A split (FINDINGS F9): "
                f"it records only `passes`, which includes nuisance braking. Re-drive "
                f"with the current tools/drive_witness.py before calibrating the gate.")
        for c in v["cells"]:
            k = _key(c)
            if k not in g or k not in w:
                continue
            drove = w[k]["passes_protocol"]
            of = w[k]["of"]
            predicted_ok = c["verdict"] == "CERTIFIED"
            drove_ok = drove == of
            rows.append({
                "policy": policy, "scenario": scenario,
                "from_deg": c["from_deg"], "to_deg": c["to_deg"],
                "width_deg": round(c["from_deg"] - c["to_deg"], 4),
                "family_uncovered": uncovered(k),
                "gate": g[k]["as_fraction_of_threshold"],
                "verdict": c["verdict"],
                "margin_x_threshold": c["margin_x_threshold"],
                "drove": drove, "of": of,
                "agrees": predicted_ok == drove_ok,
                # The direction matters more than the fact. A certificate that clears
                # something which then fails is a different kind of wrong from one that
                # flags something which then drives.
                "direction": ("certified_then_failed" if predicted_ok and not drove_ok
                              else "falsified_then_drove" if not predicted_ok and drove_ok
                              else "agree"),
            })
    return rows


def point_biserial(xs, ys) -> float | None:
    """Correlation between a continuous x (the gate) and a binary y (disagreement)."""
    n = len(xs)
    if n < 4 or len(set(ys)) < 2:
        return None
    mx = sum(xs) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    if sx == 0:
        return None
    n1 = sum(ys)
    n0 = n - n1
    m1 = sum(x for x, y in zip(xs, ys) if y) / n1
    m0 = sum(x for x, y in zip(xs, ys) if not y) / n0
    return (m1 - m0) / sx * math.sqrt(n1 * n0 / (n * n))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--include-uncovered", action="store_true",
                    help="include sub-intervals the family declares uncovered. Off by "
                         "default: they are excluded from every other claim, and a "
                         "sub-interval with no coverage claim cannot test one")
    args = ap.parse_args()

    rows = collect()
    if not rows:
        raise SystemExit("no (verify, gate, witness) triples on disk yet")
    used = rows if args.include_uncovered else [r for r in rows if not r["family_uncovered"]]

    xs = [r["gate"] for r in used]
    dis = [0 if r["agrees"] else 1 for r in used]
    rpb = point_biserial(xs, dis)

    agree = [r["gate"] for r in used if r["agrees"]]
    disagree = [r["gate"] for r in used if not r["agrees"]]
    unsafe = [r for r in used if r["direction"] == "certified_then_failed"]

    def stat(v):
        if not v:
            return None
        s = sorted(v)
        return {"n": len(v), "min": round(s[0], 4), "median": round(s[len(s) // 2], 4),
                "max": round(s[-1], 4), "mean": round(sum(v) / len(v), 4)}

    payload = {
        "rows": len(used),
        "excluded_uncovered": len(rows) - len(used),
        "gate_when_certificate_and_drive_AGREE": stat(agree),
        "gate_when_they_DISAGREE": stat(disagree),
        "point_biserial_gate_vs_disagreement": (round(rpb, 4) if rpb is not None else None),
        "certified_then_failed": len(unsafe),
        "certified_then_failed_rows": unsafe,
        "interpretation": None,
        "detail": used,
    }
    if rpb is None:
        payload["interpretation"] = (
            "Not enough variation to correlate: every sub-interval agreed, or every one "
            "disagreed. The gate cannot be calibrated from this run.")
    elif rpb >= 0.3:
        payload["interpretation"] = (
            f"The gate PREDICTS disagreement (r_pb = {rpb:.2f}). Sub-intervals where the "
            f"blend moves the policy further are the ones where a blend-based certificate "
            f"fails to transfer to a rendered drive, which is what the check was built to "
            f"detect and what licenses the 1.0 threshold.")
    elif rpb <= -0.3:
        payload["interpretation"] = (
            f"The gate ANTI-predicts disagreement (r_pb = {rpb:.2f}), which is not a "
            f"result the gate's rationale can explain and should be treated as a bug "
            f"until a disposition rules out the candidates.")
    else:
        payload["interpretation"] = (
            f"The gate does NOT predict disagreement (r_pb = {rpb:.2f}). It passes "
            f"everything it is asked about and carries no information about the risk it "
            f"exists to bound. The paper should say that plainly rather than presenting "
            f"the gate as evidence the family transfers.")

    (OUT / "gate_calibration.json").write_text(json.dumps(payload, indent=2) + "\n")

    print(f"\n  {len(used)} covered sub-intervals across "
          f"{len({(r['policy'], r['scenario']) for r in used})} policy-scenario pairs")
    print(f"  gate when they agree:    {payload['gate_when_certificate_and_drive_AGREE']}")
    print(f"  gate when they disagree: {payload['gate_when_they_DISAGREE']}")
    print(f"  point-biserial r = {payload['point_biserial_gate_vs_disagreement']}")
    print(f"  certified-then-failed: {len(unsafe)}")
    print(f"\n  {payload['interpretation']}")
    print(f"\n  wrote results/carla/gate_calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
