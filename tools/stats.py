"""Confidence intervals for the rates this study reports.

PROTOCOL section 1 and `CLAUDE.md` both say every closed-loop number is a failure rate
over at least ten repetitions **reported with Wilson intervals**, and the
`carla-determinism` package says the same thing from the other direction: D-7 measured
that bit-exact closed-loop replay is unreachable, *"therefore every closed-loop number
remains a RATE over at least 10 repetitions with a confidence interval"*.

Until 2026-09-07 nothing in this repository computed one. Every rate in the study was a
bare fraction.

**Why Wilson and not the textbook interval.** The normal approximation
`p +/- z*sqrt(p(1-p)/n)` is degenerate exactly where this study's interesting cells live:
at 10/10 and 0/10 it has zero width, so a cell that passed every run would be reported as
certain, and a cell that failed every run likewise. Ten out of ten is not proof that the
rate is 1. The Wilson score interval is derived by inverting the score test rather than
assuming normality of the estimate, keeps a sensible width at the boundaries, and stays
inside [0, 1].

At n = 10 and 10 passes it gives roughly [0.72, 1.00]: a cell that passed every one of ten
runs is consistent with a true pass rate as low as 72%. That number is the honest answer
to "how much does 10/10 tell you", and it is the reason the steering study's lap protocol
argues about repetition counts at all.
"""

from __future__ import annotations

import math

# 95%, two-sided. Stated rather than passed around, because a study that quotes intervals
# at several confidence levels invites the reader to wonder which one a given number used.
Z_95 = 1.959963984540054


def wilson(passes: int, of: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, as (low, high)."""
    if of <= 0:
        return (0.0, 1.0)
    p = passes / of
    z2n = z * z / of
    centre = (p + z2n / 2.0) / (1.0 + z2n)
    half = (z / (1.0 + z2n)) * math.sqrt(p * (1.0 - p) / of + z * z / (4.0 * of * of))
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(passes: int, of: int, z: float = Z_95) -> dict:
    """The reporting form: the count, the rate, and its interval."""
    lo, hi = wilson(passes, of, z)
    return {
        "passes": passes,
        "of": of,
        "rate": round(passes / of, 4) if of else None,
        "wilson_95": [round(lo, 4), round(hi, 4)],
    }


def fmt(passes: int, of: int, z: float = Z_95) -> str:
    lo, hi = wilson(passes, of, z)
    return f"{passes}/{of} [{lo:.2f}, {hi:.2f}]"


if __name__ == "__main__":
    print("Wilson 95% intervals at the counts this study actually reports:\n")
    print(f"  {'k/n':>7s}  {'rate':>5s}  interval")
    for k, n in ((10, 10), (9, 10), (6, 10), (5, 10), (1, 10), (0, 10),
                 (30, 30), (0, 30), (60, 60)):
        lo, hi = wilson(k, n)
        print(f"  {f'{k}/{n}':>7s}  {k / n:5.2f}  [{lo:.3f}, {hi:.3f}]")
    print("\n  10/10 does not mean the rate is 1. At n = 10 it is consistent with 0.72.")
    print("  That is the whole argument about how many repetitions a cell needs.")
