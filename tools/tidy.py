"""A tidy pass. Run it before pushing anything you want other people to read.

    python tools/tidy.py

This repository is public and is a proof of concept, so the bar is "an outsider can
follow it", not "production". This reports the handful of things that actually make a
small research repo unreadable. It never deletes anything.

Anything it flags that you want gone goes in `stale/`, which is git-ignored. Nothing is
lost by doing that: if the file was ever committed it stays in git history forever.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIG_FILE_KB = 500
LONG_FILE_LINES = 400


def git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def section(title: str, lines: list[str], good: str) -> bool:
    print(f"\n{title}")
    if not lines:
        print(f"  {good}")
        return True
    for line in lines:
        print(f"  {line}")
    return False


def main() -> int:
    clean = True

    clean &= section(
        "Uncommitted work",
        git("status", "--short"),
        "working tree clean",
    )

    unpushed = git("log", "--oneline", "@{u}..HEAD") if git("remote") else []
    clean &= section(
        "Not yet on GitHub",
        unpushed,
        "everything is pushed",
    )

    stale = REPO / "stale"
    parked = [str(p.relative_to(REPO)) for p in stale.rglob("*") if p.is_file()]
    section(
        "Parked in stale/ (git-ignored, delete when you have looked at them)",
        parked,
        "nothing parked",
    )

    tracked = git("ls-files")
    big = []
    long_files = []
    for rel in tracked:
        p = REPO / rel
        if not p.is_file():
            continue
        kb = p.stat().st_size / 1024
        if kb > BIG_FILE_KB:
            big.append(f"{rel}  {kb:.0f} KB")
        if p.suffix in {".py", ".md"}:
            n = len(p.read_text(errors="ignore").splitlines())
            if n > LONG_FILE_LINES:
                long_files.append(f"{rel}  {n} lines")
    clean &= section(
        f"Tracked files over {BIG_FILE_KB} KB (should data be here at all?)",
        big,
        "nothing oversized",
    )
    section(
        f"Files over {LONG_FILE_LINES} lines (fine, but check they still read well)",
        long_files,
        "nothing unusually long",
    )

    marks = []
    for rel in tracked:
        p = REPO / rel
        if p.suffix != ".py" or not p.is_file():
            continue
        if rel == "tools/tidy.py":
            continue  # this file necessarily contains the words it searches for
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if any(m in line for m in ("TODO", "FIXME", "XXX", "HACK")):
                marks.append(f"{rel}:{i}  {line.strip()[:70]}")
    section(
        "Loose ends in code",
        marks,
        "no TODO or FIXME markers",
    )

    orphans = []
    for rel in tracked:
        if not rel.endswith(".py") or rel.endswith("__init__.py"):
            continue
        stem = Path(rel).stem
        hits = git("grep", "-l", stem, "--", "*.py", "*.md")
        if len([h for h in hits if h != rel]) == 0:
            orphans.append(f"{rel}  (nothing else mentions it)")
    section(
        "Possibly dead code",
        orphans,
        "every module is referenced somewhere",
    )

    print(
        "\nBefore pushing something public, the two that matter are an unclean tree and\n"
        "unpushed commits. The rest is judgement.\n"
    )
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
