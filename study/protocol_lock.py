"""The protocol is locked. This is what notices when it is not.

    python -m study.protocol_lock            check, and print the ledger
    python -m study.protocol_lock --accept   re-lock after a recorded amendment

Everything in PROTOCOL.md above the "## Amendments" heading is frozen. Changing it
without appending an amendment is the failure mode this guards: study logic in this
lab has been lost twice, and it was lost by drift rather than by decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROTOCOL = REPO / "PROTOCOL.md"
LOCK = REPO / "study" / "protocol.lock"

AMENDMENTS_HEADING = "## Amendments"
AMENDMENT_ENTRY = re.compile(r"^### A\d+\b", re.MULTILINE)


def split_protocol(text: str) -> tuple[str, str]:
    """Frozen part, amendments part."""
    idx = text.find(AMENDMENTS_HEADING)
    if idx == -1:
        raise SystemExit(f"PROTOCOL.md has no '{AMENDMENTS_HEADING}' heading.")
    return text[:idx], text[idx:]


def digest(frozen: str) -> str:
    # Normalise line endings and trailing whitespace so a reformat is not a change.
    lines = [line.rstrip() for line in frozen.replace("\r\n", "\n").split("\n")]
    return hashlib.sha256("\n".join(lines).strip().encode()).hexdigest()


def read_lock() -> dict:
    if not LOCK.exists():
        raise SystemExit("study/protocol.lock is missing. The protocol was never locked.")
    return json.loads(LOCK.read_text())


def write_lock(sha: str, amendments: int, note: str) -> None:
    LOCK.write_text(
        json.dumps(
            {"sha256": sha, "amendments": amendments, "note": note},
            indent=2,
        )
        + "\n"
    )


def print_ledger(frozen: str) -> None:
    """Echo the ledger table so the design is in front of you, not one file away."""
    start = frozen.find("## 9. The ledger")
    if start == -1:
        return
    section = frozen[start:]
    end = section.find("\n## ", 1)  # stop before the next top-level heading
    if end != -1:
        section = section[:end]
    rows = [
        line
        for line in section.split("\n")
        if line.startswith("| ") and not line.startswith("|---")
    ]
    print("\nThe ledger, from PROTOCOL.md section 9:\n")
    for row in rows:
        print("  " + row)
    print(
        "\nA measured cell that contradicts its expectation is a bug until proven"
        "\notherwise. It is not a finding until a written disposition lists the"
        "\ncandidate causes ruled out.\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--accept",
        action="store_true",
        help="re-lock to the current text, permitted only when a new amendment is present",
    )
    ap.add_argument("--quiet", action="store_true", help="suppress the ledger")
    args = ap.parse_args()

    text = PROTOCOL.read_text()
    frozen, amendments_text = split_protocol(text)
    sha = digest(frozen)
    count = len(AMENDMENT_ENTRY.findall(amendments_text))
    lock = read_lock()

    unchanged = sha == lock["sha256"]
    new_amendment = count > lock["amendments"]

    if args.accept:
        if unchanged:
            print("Protocol unchanged. Nothing to re-lock.")
            return 0
        if not new_amendment:
            print(
                "REFUSED. The protocol changed but no new amendment was appended.\n"
                f"  amendments recorded: {lock['amendments']}, found: {count}\n"
                "Append an '### A<n>' entry under '## Amendments' saying what changed\n"
                "and why, then run --accept again.",
                file=sys.stderr,
            )
            return 2
        write_lock(sha, count, f"re-locked at amendment A{count}")
        print(f"Re-locked at amendment A{count}.")
        return 0

    if unchanged:
        print(f"Protocol locked and intact ({sha[:12]}, {count} amendments).")
        if not args.quiet:
            print_ledger(frozen)
        return 0

    print(
        "PROTOCOL DRIFT.\n"
        f"  locked:  {lock['sha256'][:12]}\n"
        f"  current: {sha[:12]}\n",
        file=sys.stderr,
    )
    if new_amendment:
        print(
            "An amendment is present. If the change is intended, run:\n"
            "  python -m study.protocol_lock --accept",
            file=sys.stderr,
        )
    else:
        print(
            "No new amendment. Either revert the change, or append an '### A<n>' entry\n"
            "under '## Amendments' saying what changed and why, then --accept.\n\n"
            "This is the guard, not an obstacle. The design is allowed to change; it is\n"
            "not allowed to change silently while experiments are running against it.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
