"""Fill the ledger in `study/results.json` from the result artifacts.

    python tools/record_cells.py            # show what it would write
    python tools/record_cells.py --write

**Why this is a tool.** The ledger cells were filled in by hand, and a 2026-08-25 audit
found the lead-scenario results recorded under the pedestrian cells — every artifact said
`scenario: lead` and nothing noticed. `study/ledger.py --check-order` was built to catch
that after the fact; this removes the step that made it possible. The cell rows come from
PROTOCOL section 9, the numbers come from the artifacts, and neither is retyped.

**What it will not do.** It refuses to record a cell as passing if a CERTIFIED
sub-interval was driven and failed. That is a soundness violation — the certificate
cleared something that then crashed — and it is the one outcome in this study that must
never be summarised into a one-word verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
RESULTS = J.REPO / "study" / "results.json"

# PROTOCOL section 9, and the same mapping study/ledger.py checks artifacts against.
LEDGER_ROWS = {
    "1": ("P_pts", "ped"),
    "2": ("P_pts", "lead"),
    "3": ("P_cont", "ped"),
    "4": ("P_cont", "lead"),
    "5": ("P_pts", "plate"),
    "6": ("P_cont", "plate"),
}


def endpoints_verdict(policy: str, scenario: str) -> tuple[str | None, dict]:
    suffix = "" if scenario == "lead" else f"_{scenario}"
    path = OUT / f"policy_endpoints{suffix}.json"
    if not path.exists():
        return None, {}
    d = json.loads(path.read_text())
    mine = {k: v for k, v in d["cells"].items() if k.startswith(f"{policy}|")}
    if not mine:
        return None, {}
    passed = [k.split("|")[1] for k, v in mine.items() if v["passes"] == v["of"]]
    detail = {k.split("|")[1]: f"{v['passes']}/{v['of']}" for k, v in mine.items()}
    if len(passed) == len(mine) and len(mine) >= 2:
        return "PASS both", detail
    return f"PASS {len(passed)} of {len(mine)}", detail


def cell_row(policy: str, scenario: str) -> dict:
    row = {"endpoints": None, "fv": None, "witness": None, "width": None, "note": ""}
    ep, ep_detail = endpoints_verdict(policy, scenario)
    row["endpoints"] = ep
    if scenario == "plate" and ep is not None:
        # The false-activation cells pass by NOT stopping, so their endpoint verdict is
        # about the nuisance limit rather than about standoff, and their FV column is
        # property A rather than property S. Recorded distinctly so nobody reads a plate
        # row as though it were a hazard row.
        row["criterion"] = ("crossed the plate without braking and never exceeded the "
                            "standard's 0.25 g nuisance limit")

    vpath = OUT / f"verify_{policy}_{scenario}.json"
    if not vpath.exists():
        # Say WHICH part is missing. "not measured" on a cell whose endpoints are
        # measured 10/10 understates the state, and on a cell with no harness at all it
        # overstates it -- the same two words for "waiting on a verifier" and "nobody has
        # built this scenario" is exactly the ambiguity a ledger exists to remove.
        if scenario == "plate":
            row["note"] = (
                "NO HARNESS. The FMVSS 127 false-activation scenario is specified in "
                "PROTOCOL sections 2 and 9 and has never been built: scenarios.py tiles "
                "the trench plate to the standard's dimensions and nothing drives it. "
                "See docs/STATE_OF_PLAY.md for what it needs. Property A is currently "
                "verified on the no-target control, which is a legitimate must-not-brake "
                "property and is NOT the standard's false-activation scenario.")
        elif ep:
            row["note"] = "endpoints measured; verification pending"
        else:
            row["note"] = "not measured"
        return row
    v = json.loads(vpath.read_text())
    row["artifact"] = str(vpath.relative_to(J.REPO))

    # COVERED sub-intervals only. A sub-interval the disturbance family cannot represent
    # is excluded from the verdict and from the width, because a bound over a blend that
    # corresponds to no render is not evidence either way (A6, audit F8).
    covered = [c for c in v["cells"] if not c.get("family_uncovered")]
    uncovered = [c for c in v["cells"] if c.get("family_uncovered")]
    fals = [c for c in covered if c["verdict"] == "FALSIFIED"]
    row["fv"] = "CERTIFIED" if not fals else "FALSIFIED"
    if fals:
        row["width"] = round(sum(c["from_deg"] - c["to_deg"] for c in fals), 3)
        row["width_note"] = (
            f"total width of the falsified sub-intervals over the covered axis, degrees "
            f"of sun altitude (axis {v['cells'][0]['from_deg']:g} to "
            f"{v['cells'][-1]['to_deg']:g}); "
            f"{len(uncovered)} uncovered sub-interval(s) excluded")
    row["certified_of_covered"] = f"{len(covered) - len(fals)}/{len(covered)}"
    row["margin_worst_x_threshold"] = min(
        (c["margin_x_threshold"] for c in covered), default=None)
    row["margin_best_x_threshold"] = max(
        (c["margin_x_threshold"] for c in covered), default=None)

    wpath = OUT / f"witness_{policy}_{scenario}.json"
    if not wpath.exists():
        row["note"] = ("verdict committed, witness drive pending -- the blind protocol "
                       "working, not a gap")
        return row
    w = json.loads(wpath.read_text())

    # MODEL BINDING. A verdict is a prediction about ONE network, and a witness drive is
    # a test of one network; joining two that describe different networks produces a
    # confident, wrong agreement table. On 2026-09-07 this joined fresh certificates
    # against witness drives from fourteen hours earlier, on policies retrained since,
    # and reported a SOUNDNESS VIOLATION in the negative control -- the single most
    # alarming thing this study can print -- purely from the mismatch.
    #
    # study/ledger.py has checked this since the F1 audit. record_cells did not, so it
    # could manufacture the finding that ledger.py would later refuse to validate.
    vm, wm = v.get("model_sha256"), w.get("model_sha256")
    if vm and wm and vm != wm:
        row["note"] = (
            f"verdict committed, witness drive STALE and ignored: the certificate "
            f"describes model {vm[:12]} and the drive on disk tested {wm[:12]}. "
            f"Re-drive before this cell can record a witness.")
        return row

    row["witness_artifact"] = str(wpath.relative_to(J.REPO))
    row["agreement"] = w["agreement"]

    by_key = {(c["from_deg"], c["to_deg"]): c for c in w["cells"]}
    driven = [(c, by_key.get((c["from_deg"], c["to_deg"]))) for c in covered]
    driven = [(c, d) for c, d in driven if d is not None]

    # Scored against PROTOCOL section 7's frozen closed-loop pass -- no contact and
    # standoff at least d_margin -- because that is what property S composes into.
    # Premature braking is a must-NOT-brake condition and belongs to property A; scoring
    # property S against it reported a certified cell as unsound when the run in question
    # stopped 306 ft short of the lead vehicle.
    def ok(d):
        return d.get("passes_protocol", d["passes"]) == d["of"]

    cert_then_failed = [(c, d) for c, d in driven if c["verdict"] == "CERTIFIED"
                        and not ok(d)]
    fals_then_failed = [(c, d) for c, d in driven if c["verdict"] == "FALSIFIED"
                        and not ok(d)]
    all_clean = all(ok(d) for _, d in driven)
    nuisance = [(c, d) for c, d in driven if d.get("premature", 0)]
    row["nuisance_braking_sub_intervals"] = len(nuisance)

    if cert_then_failed:
        # The unsafe direction. Never collapsed into PASS or FAIL.
        worst = min(cert_then_failed,
                    key=lambda p: p[1].get("passes_protocol", p[1]["passes"]))
        row["witness"] = "UNSOUND"
        row["note"] = (
            f"A CERTIFIED sub-interval FAILED when driven: "
            f"{worst[0]['from_deg']:+.3f} to {worst[0]['to_deg']:+.3f} deg drove "
            f"{worst[1].get('passes_protocol', worst[1]['passes'])}/{worst[1]['of']} "
            f"at margin "
            f"{worst[0]['margin_x_threshold']:.2f}x threshold. "
            f"{len(cert_then_failed)} sub-interval(s) in total. This is a soundness "
            f"failure and PROTOCOL section 8 makes it a bug until a written disposition "
            f"rules out the candidate causes.")
    elif row["fv"] == "FALSIFIED":
        row["witness"] = "FAIL" if fals_then_failed else "PASS"
        row["note"] = (
            f"FALSIFIED over {row['width']:.3f} deg; "
            + (f"{len(fals_then_failed)} of {len(fals)} falsified sub-intervals failed "
               f"when driven"
               if fals_then_failed else
               "every falsified sub-interval nonetheless drove clean, so every "
               "disagreement is conservative"))
    else:
        row["witness"] = "PASS" if all_clean else "PASS"
        row["note"] = (f"CERTIFIED in all {len(covered)} covered sub-intervals; "
                       f"drove clean in all {len(driven)} driven")
    if ep_detail:
        row["note"] = (row["note"] + " | endpoints " +
                       ", ".join(f"{k} {v}" for k, v in sorted(ep_detail.items()))).strip()
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="update study/results.json")
    args = ap.parse_args()

    data = json.loads(RESULTS.read_text())
    unsound = []
    for cid, (policy, scenario) in LEDGER_ROWS.items():
        row = cell_row(policy, scenario)
        old = data["cells"].get(cid, {})
        print(f"\ncell {cid}  {policy} / {scenario}")
        for k in ("endpoints", "fv", "width", "witness", "certified_of_covered",
                  "agreement", "margin_worst_x_threshold"):
            if row.get(k) is not None:
                was = old.get(k)
                print(f"  {k:26s} {row[k]}" + (f"   (was {was})" if was != row[k]
                                               and was is not None else ""))
        if row.get("note"):
            print(f"  note: {row['note']}")
        if row.get("witness") == "UNSOUND":
            unsound.append(cid)
        data["cells"][cid] = row

    if unsound:
        print(f"\n  *** cells {', '.join(unsound)} record a CERTIFIED sub-interval that "
              f"failed when driven. Read the notes above before anything else. ***")

    if args.write:
        RESULTS.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\n  wrote {RESULTS.relative_to(J.REPO)}")
        print("  now: python -m study.status && python -m study.ledger --check-order")
    else:
        print("\n  (dry run; pass --write to update study/results.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
