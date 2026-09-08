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

def _expected_from_protocol() -> dict:
    """Parse the ledger expectations out of the FROZEN section 9 table.

    A hard-coded duplicate lived here before: editable without tripping the
    protocol lock, which defeats the point of freezing the expectations. The
    frozen table is the single source; if it cannot be parsed, that is an error,
    not a fallback."""
    text = (REPO / "PROTOCOL.md").read_text()
    frozen, _ = lock.split_protocol(text)
    start = frozen.find("## 9. The ledger")
    section = frozen[start:]
    end = section.find("\n## ", 1)
    section = section[:end] if end != -1 else section
    out = {}
    for line in section.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 7 and cells[0].isdigit():
            cid, policy, scenario, endpoints, fv, witness, conf = cells[:7]
            fv_word = fv.split(",")[0].strip()
            out[cid] = (policy, scenario, endpoints, fv_word, witness, conf)
    if len(out) != 6:
        raise SystemExit(
            f"could not parse the 6 ledger rows from PROTOCOL section 9 (got {len(out)})")
    return out


EXPECTED = _expected_from_protocol()

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


DISPOSES = re.compile(
    r"^\*\*Disposes:\*\*(.+)$", re.MULTILINE)
DISPOSED_CELL = re.compile(r"cell\s+(\d+)\s*\((endpoints|FV|witness)\)")


def dispositions() -> dict[tuple[str, str], str]:
    """(cell, field) -> the FINDINGS heading that disposes of it.

    PROTOCOL section 8 lets a contradiction be written up once a written disposition
    lists the candidate causes ruled out. Nothing recorded that fact, so this report
    would have kept printing "do not write these up" at someone holding the finished
    disposition -- which is the failure mode this repo keeps meeting: a rule that names
    an artifact nobody made looks exactly like a rule being obeyed.

    A finding claims one by carrying a line

        **Disposes:** ledger cell 1 (witness), ledger cell 3 (FV)

    which is deliberately explicit about WHICH field, because a cell can contradict on
    the certificate and agree on the drive.
    """
    out: dict[tuple[str, str], str] = {}
    path = REPO / "FINDINGS.md"
    if not path.exists():
        return out
    heading = None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            heading = line[3:].split(" ", 1)[0].strip()
        m = DISPOSES.match(line)
        if m and heading:
            for cid, field in DISPOSED_CELL.findall(m.group(1)):
                out[(cid, field)] = heading
    return out


def contradicts(cell_id: str, measured: dict) -> list[str]:
    """EVERY field of a measured cell that disagrees with its pre-registration.

    This returned at the FIRST mismatch, which is fine until a cell contradicts on two
    fields and the first one gets a disposition: cell 5 disagreed on both the certificate
    and the drive, F18 disposed the certificate, and the drive's disagreement then had
    nothing to report it. A contradiction that hides behind a disposed one is the worst
    place for it to hide, because the row now reads as handled.
    """
    _, _, exp_end, exp_fv, exp_wit, _ = EXPECTED[cell_id]
    out = []
    for label, got, expected in (
        ("endpoints", measured.get("endpoints"), exp_end),
        ("FV", measured.get("fv"), exp_fv),
        ("witness", measured.get("witness"), exp_wit),
    ):
        if got is None:
            continue
        if not str(got).upper().startswith(expected.split(",")[0].upper()):
            out.append(f"{label}: expected {expected}, measured {got}")
    return out


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
        for bad in contradicts(cid, m):
            conflicts.append((cid, bad))

    measured = sum(1 for c in results["cells"].values() if c.get("fv") is not None)
    print(f"\n  {measured}/6 cells measured")

    if conflicts:
        disposed = dispositions()
        open_ones = []
        print("\nCONTRADICTIONS. Each is a bug until proven otherwise.")
        for cid, why in conflicts:
            where = disposed.get((cid, why.split(":", 1)[0]))
            if where:
                print(f"  cell {cid}: {why}   -- disposed, FINDINGS {where}")
            else:
                print(f"  cell {cid}: {why}")
                open_ones.append(cid)
        if open_ones:
            print(
                "\nDo not write these up as findings. A written disposition must list the\n"
                "candidate causes ruled out first. See PROTOCOL.md section 8."
            )
            return 1
        print(
            "\nEvery contradiction carries a written disposition. The ledger rows stand\n"
            "as measured -- a disposition explains a contradiction, it does not erase it."
        )
        return 0

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
