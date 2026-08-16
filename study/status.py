"""Where the study stands, reported in the protocol's own terms.

    python -m study.status

This is the only sanctioned answer to "where are we?". Progress that cannot be
expressed as a ledger cell, a gate or a milestone is off-ledger exploration and
belongs in FINDINGS.md, not here. Making the protocol the reporting format is what
keeps it in view: drift shows up as a status report that no longer fits its own table.

Checks the protocol lock first and refuses to report against a design that moved.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from study import protocol_lock as lock

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "study" / "results.json"

EXPECTED = {
    "1": ("P_pts",  "ped cross",    "PASS both", "FALSIFIED", "FAIL", "high"),
    "2": ("P_pts",  "lead stop",    "PASS both", "FALSIFIED", "FAIL", "med"),
    "3": ("P_cont", "ped cross",    "PASS both", "CERTIFIED", "PASS", "high"),
    "4": ("P_cont", "lead stop",    "PASS both", "CERTIFIED", "PASS", "high"),
    "5": ("P_pts",  "trench plate", "PASS both", "CERTIFIED", "PASS", "low"),
    "6": ("P_cont", "trench plate", "PASS both", "CERTIFIED", "PASS", "low"),
}

MILESTONE_NAMES = {
    "M0": "Specification, locked",
    "M1": "Map survey (offline)",
    "M2": "Harness and primitives",
    "M3": "Expert and collection",
    "M4": "Two policies pass both endpoints",
    "M5": "Capture check, in-between check",
    "M6": "Verification, verdicts committed",
    "M7": "Drive the witness",
    "M8": "Demo and writeup",
}

MARK = {"done": "[x]", "in_progress": "[~]", "todo": "[ ]", "blocked": "[!]"}


def fmt(value) -> str:
    return "-" if value is None else str(value)


def contradicts(cell_id: str, measured: dict) -> str | None:
    """A measured cell that disagrees with its pre-registered expectation."""
    _, _, exp_end, exp_fv, exp_wit, _ = EXPECTED[cell_id]
    for label, got, expected in (
        ("endpoints", measured.get("endpoints"), exp_end),
        ("FV", measured.get("fv"), exp_fv),
        ("witness", measured.get("witness"), exp_wit),
    ):
        if got is None:
            continue
        if not str(got).upper().startswith(expected.split(",")[0].upper()):
            return f"{label}: expected {expected}, measured {got}"
    return None


def main() -> int:
    text = (REPO / "PROTOCOL.md").read_text()
    frozen, amendments = lock.split_protocol(text)
    locked = lock.read_lock()
    if lock.digest(frozen) != locked["sha256"]:
        print(
            "PROTOCOL DRIFT. Refusing to report progress against a design that moved.\n"
            "Run: python -m study.protocol_lock",
            file=sys.stderr,
        )
        return 1

    n_amend = len(lock.AMENDMENT_ENTRY.findall(amendments))
    results = json.loads(RESULTS.read_text())

    print(f"\nPROTOCOL protocol-v1  {locked['sha256'][:12]}  amendments: {n_amend}")
    print("\nMilestones")
    for mid, name in MILESTONE_NAMES.items():
        m = results["milestones"].get(mid, {})
        note = f"  {m.get('note')}" if m.get("note") else ""
        print(f"  {MARK.get(m.get('state'), '[ ]')} {mid}  {name}{note}")

    print("\nGates")
    for gid, g in results["gates"].items():
        print(
            f"  {MARK.get(g.get('state'), '[ ]')} {gid:<12} "
            f"value {fmt(g.get('value')):>8}   threshold {fmt(g.get('threshold'))}"
        )

    print("\nPrimitives")
    for k, v in results["primitives"].items():
        print(f"      {k:<14} {fmt(v)}")

    print("\nLedger   (expected -> measured)")
    header = f"  {'#':<3}{'policy':<8}{'scenario':<15}{'endpoints':<22}{'FV':<26}{'witness':<16}conf"
    print(header)
    conflicts = []
    for cid, (pol, scen, exp_end, exp_fv, exp_wit, conf) in EXPECTED.items():
        m = results["cells"].get(cid, {})
        width = f" (w={m['width']})" if m.get("width") is not None else ""
        row = (
            f"  {cid:<3}{pol:<8}{scen:<15}"
            f"{exp_end + ' -> ' + fmt(m.get('endpoints')):<22}"
            f"{exp_fv + ' -> ' + fmt(m.get('fv')) + width:<26}"
            f"{exp_wit + ' -> ' + fmt(m.get('witness')):<16}{conf}"
        )
        print(row)
        bad = contradicts(cid, m)
        if bad:
            conflicts.append((cid, bad))

    measured = sum(1 for c in results["cells"].values() if c.get("fv") is not None)
    print(f"\n  {measured}/6 cells measured")

    if conflicts:
        print("\nCONTRADICTIONS. Each is a bug until proven otherwise.")
        for cid, why in conflicts:
            print(f"  cell {cid}: {why}")
        print(
            "\nDo not write these up as findings. A written disposition must list the\n"
            "candidate causes ruled out first. See PROTOCOL.md section 8."
        )
        return 1

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
