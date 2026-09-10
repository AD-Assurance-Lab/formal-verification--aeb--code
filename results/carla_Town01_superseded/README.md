# Town01 artifacts, superseded by A14

Every measured artifact this study produced on Town01. A14 moved the study to Town12 and
says plainly that all of them are rebuilt; this directory is that instruction being
*enforced* rather than declared.

They were moved here at 03:00 on 2026-09-10, mid-rebuild, because they were about to be
read as current. `build_family_knots --refine` reads **every** `gate_inbetween_*.json` by
design — a sub-interval that fails for one policy must be split for all of them, or the
arms are certified over different axes — and ten of the twelve on disk were Town01's,
describing sub-intervals that do not exist on Town12's axis.

That is FINDINGS F26 a second time. The first was captures reusing Town01 frames at the
three knots the two axes share, including both regulatory endpoints. The shared cause is
that `results/carla/` is not scoped by map, so an artifact from the old study sits under
the exact name the new one looks for, and only the ones the rebuild happens to have reached
have been replaced. At the moment they were moved, **157 of 179 were Town01's**.

Nothing here is deleted or wrong. It is the complete Town01 study, also recoverable from
git at the `town01-final` tag. It is here so that nothing on Town12 can reach it by name.

The structural fix — scoping `results/carla/` by map the way `results/captures/` now is —
is queue item 17 and was not done mid-rebuild.
