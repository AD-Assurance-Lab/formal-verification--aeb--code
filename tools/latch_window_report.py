"""Join the latch-window certificates against the drives. The disposition's evidence table.

    python tools/latch_window_report.py

`tools/latch_window.py` computes, per sub-interval, whether SOME pose in the latch window
certifies for ALL illuminations in that sub-interval -- a sound sufficient condition for
the vehicle to latch early enough to stop with `d_margin`. This joins that against what
the vehicle actually did, and asks the only question that can refute the argument:

    does any LATCH-GUARANTEED sub-interval produce a CONTACT?

If one does, the sufficient condition is not sufficient and the disposition is wrong. The
converse direction proves nothing and is not claimed: the condition is EXISTS pose FORALL
s, the vehicle needs FORALL s EXISTS pose, and a sub-interval can fail the first and still
drive clean because a different pose saves each illumination.

Written as a driver rather than run by hand, because every number it prints is quoted in
FINDINGS F17 and the standing rule is that a number in a write-up comes from a script in
the repo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
ARMS = ["P_pts", "P_cont", "P_pts3"]


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def drive_rows(policy: str, scenario: str):
    """Sub-interval -> the worst drive over the midpoint and at-witness passes."""
    rows: dict[tuple, dict] = {}
    for suffix in ("", "_atwitness"):
        d = load(OUT / f"witness_{policy}_{scenario}{suffix}.json")
        if d is None:
            continue
        for c in d["cells"]:
            k = (round(c["from_deg"], 3), round(c["to_deg"], 3))
            br = [r["brake_range_ft"] for r in c["runs"] if r.get("braked")]
            r = rows.setdefault(k, {"contacts": 0, "of": 0, "passes_protocol": 0,
                                    "premature": 0, "latest_brake_ft": None})
            r["contacts"] += c["contacts"]
            r["of"] += c["of"]
            r["passes_protocol"] += c["passes_protocol"]
            r["premature"] += c["premature"]
            if br:
                lo = min(br)
                r["latest_brake_ft"] = lo if r["latest_brake_ft"] is None else min(
                    r["latest_brake_ft"], lo)
    return rows


def main() -> int:
    summary, violations = [], []
    for policy in ARMS:
        for scenario in ("lead", "ped"):
            lw = load(OUT / f"latch_window_{policy}_{scenario}.json")
            fv = load(OUT / f"verify_{policy}_{scenario}.json")
            if lw is None or fv is None:
                print(f"  (skipping {policy}/{scenario}: "
                      f"{'no latch window' if lw is None else 'no certificate'})")
                continue
            # D-9 / F-record_cells: never join artifacts describing different networks.
            a = lw["provenance"].get("model_sha256")
            b = fv["provenance"].get("model_sha256")
            if a != b:
                raise SystemExit(
                    f"{policy}/{scenario}: latch window describes model {a} and the "
                    f"certificate describes {b}. Refusing to join them.")
            drives = drive_rows(policy, scenario)
            fv_by = {(round(c["from_deg"], 3), round(c["to_deg"], 3)): c
                     for c in fv["cells"]}
            print(f"\n== {policy} / {scenario}   "
                  f"latch guaranteed {lw['sub_intervals_latch_guaranteed']}   "
                  f"window poses {lw['latch_window']['poses']} "
                  f"(range >= {lw['latch_window']['r_latch_min_ft']} ft)")
            print(f"{'sub-interval':>22} {'FV':>10} {'latch?':>7} {'drives':>8} "
                  f"{'contact':>7} {'prem':>5} {'latest brake':>12}")
            for c in lw["cells"]:
                k = (round(c["from_deg"], 3), round(c["to_deg"], 3))
                d = drives.get(k)
                f = fv_by.get(k, {})
                # The DISJUNCTION verdict, not the weaker EXISTS-pose-FORALL-s one:
                # the disjunction is the property that claims to predict the drive, so
                # it is the one a contact refutes.
                g = c["disjunction"]["verdict"] == "CERTIFIED"
                lb = d["latest_brake_ft"] if d and d["latest_brake_ft"] is not None else None
                row = {
                    "policy": policy, "scenario": scenario,
                    "from_deg": c["from_deg"], "to_deg": c["to_deg"],
                    "family_uncovered": c["family_uncovered"],
                    "fv": f.get("verdict"),
                    "latch_in_time": g,
                    "latch_margin_x": c["disjunction"]["margin_x_threshold"],
                    "exists_pose_forall_s": c["latch_guaranteed"],
                    "drives": d["of"] if d else 0,
                    "contacts": d["contacts"] if d else None,
                    "premature": d["premature"] if d else None,
                    "latest_brake_ft": lb,
                }
                summary.append(row)
                if g and d and d["contacts"]:
                    violations.append(row)
                print(f"[{c['from_deg']:+8.3f},{c['to_deg']:+8.3f}] {str(f.get('verdict')):>10} "
                      f"{str(g):>7} {(d['of'] if d else 0):>8} "
                      f"{str(d['contacts']) if d else '-':>7} "
                      f"{str(d['premature']) if d else '-':>5} "
                      f"{(f'{lb:.1f} ft' if lb is not None else '-'):>12}")

    driven = [r for r in summary if r["drives"]]
    guar = [r for r in driven if r["latch_in_time"]]
    notg = [r for r in driven if not r["latch_in_time"]]
    contact_rows = [r for r in driven if r["contacts"]]
    print("\n" + "=" * 78)
    print(f"driven sub-intervals: {len(driven)}   "
          f"latch guaranteed {len(guar)}   not guaranteed {len(notg)}")
    print(f"sub-intervals producing a CONTACT: {len(contact_rows)}")
    for r in contact_rows:
        print(f"    {r['policy']}/{r['scenario']} [{r['from_deg']:+.3f},{r['to_deg']:+.3f}] "
              f"FV {r['fv']}  latch_in_time={r['latch_in_time']} "
              f"at {r['latch_margin_x']}x  "
              f"{r['contacts']} contacts in {r['drives']} runs")
    if violations:
        print(f"\n  REFUTED: {len(violations)} sub-interval(s) certified to latch in time "
              f"produced a CONTACT. The disjunction over the latch window is not a sound "
              f"predictor of the closed loop, and PROTOCOL section 7 must NOT be amended "
              f"to state property S that way. Margins above.")
    else:
        print("\n  No sub-interval certified to latch in time produced a contact, in any "
              "arm or scenario.")
    fv_fals_but_clean = [r for r in driven
                         if r["fv"] == "FALSIFIED" and r["latch_in_time"]
                         and not r["contacts"]]
    print(f"  FALSIFIED for property S, latch guaranteed, drove without contact: "
          f"{len(fv_fals_but_clean)} sub-intervals")

    path = J.claim_output(OUT / "latch_window_report.json")
    path.write_text(json.dumps({
        "rows": summary,
        "driven": len(driven),
        "latch_in_time_driven": len(guar),
        "contact_sub_intervals": contact_rows,
        "latch_in_time_with_contact": violations,
        "falsified_but_latch_guaranteed_and_clean": len(fv_fals_but_clean),
        "note": ("Refutation test for FINDINGS F17. `latch_in_time` is the DISJUNCTION "
                 "FORALL s EXISTS pose in the window, which is exactly what a latching "
                 "controller needs, so a sub-interval certified there that produces a "
                 "contact refutes it as a closed-loop predictor. The converse is not "
                 "claimed: a sub-interval that fails it can still drive clean, because a "
                 "vehicle can also latch OUTSIDE r_req, which is what the near-horizon "
                 "nuisance braking does."),
    }, indent=2) + "\n")
    print(f"  wrote {path.relative_to(J.REPO)}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
