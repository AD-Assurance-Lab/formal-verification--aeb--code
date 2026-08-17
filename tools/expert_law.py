"""The expert braking law. One definition, used everywhere.

PROTOCOL section 7 states the property the certificate checks: at every pose with range
to the conflict at most `r_req`, the commanded deceleration is at least `a_max`; and on
the false-activation scenario it is at most 0.25 g. The label has to be the same shape,
or the policy is trained against one specification and verified against another.

So the law is a step at `r_req`, and it introduces no parameter of its own: `r_req` is
already derived from measured primitives in section 3.

An earlier version used a continuous `v^2 / 2(r - margin)` demand. That is the classic
AEB "required deceleration", but it is never zero, so it demanded 1.06 m/s^2 at 60 m and
a policy trained on it would brake gently for the entire approach. AEB does not do that,
and the false-activation property forbids it.
"""

from __future__ import annotations


def label_decel(range_m: float, r_req_m: float, a_max_mps2: float) -> float:
    """Full braking inside r_req, nothing outside it."""
    return a_max_mps2 if range_m <= r_req_m else 0.0
