# Pre-registration: the split cells under a per-repetition restart

Written 2026-09-09, **while `scripts/probe_split_cells.sh` is running and before any of
its artifacts have been read.** Two repetitions of the first cell had already been written
to disk when this was committed; neither was opened, and this file is committed ahead of
all forty-four others. The study's own rule is that a result contradicting a
pre-registered expectation is a bug until proven otherwise, and that a verdict is a
prediction only if it was written down first. That rule has so far been applied to
verification verdicts. It applies here too: the whole point of this probe is to decide
whether an instrument is measuring the world or itself, and an expectation formed after
seeing the answer cannot decide that.

## The question

`tools/repetition_floor.py`, run on this repository's committed artifacts, finds **277 of
281** ten-repetition cells unanimous and **4 split**. A cell passes iff every repetition
passes, so only a split cell can be sensitive to the repetition count at all.

None of the four looks like a draw from a rate:

| cell | p/n | repetitions in run order |
|---|---|---|
| `P_cont` / plate [+0.026°, +0.000°] | 6/10 | `FFFFPPPPPP` |
| `P_pts3` / ped [+0.779°, +0.026°] | 2/10 | `PFFFFFFFFP` |
| `P_pts` / lead [+0.779°, +0.026°] | 9/10 | `PPPPPFPPPP` |
| `P_pts` / lead, at-witness [+0.026°, +0.000°] | 8/10 | `PPFPFPPPPP` |

All ten repetitions of a cell share one process and one server, which is what D-6 forbids
and what `docs/QUEUE.md` item 8 still has open. The probe drives each of the four again,
plus two controls that were unanimous, with **a stopped server, a fresh launch through the
determinism preflight, a new process, a new client, a new vehicle and a new camera before
every single repetition**.

## What is predicted, and how confident

1. **Controls reproduce.** `P_cont`/lead [+60.000°, +42.766°] passes 3/3 and
   `P_pts3`/lead [+10.128°, +7.715°] passes 0/3. High confidence. Without this the probe
   cannot distinguish "the split went away" from "this probe cannot see a split".

2. **The two `P_pts` cells become unanimous 10/10.** High confidence, because the
   mechanism is identified and fixed: F21's `rest_gap_ft` defect scored a vehicle stopped
   379 ft short as a standoff failure, it accounts for exactly the three failing
   repetitions in those two cells, and `tools/run_policy.py` now records the resting gap
   on the loop's exit path. If either cell is still split, the F21 disposition is wrong
   and F21 must be reopened.

3. **`P_cont`/plate [+0.026°, +0.000°] does not reproduce `FFFFPPPPPP`.** Medium
   confidence on the specific outcome, high confidence on the structure: four contiguous
   failures at the head of a run sequence, with peak demand stepping from ~2.7 to
   ~2.1 m/s² between repetition 3 and repetition 4, is a step in run INDEX and not in
   anything the study varies. The prediction is that under a per-repetition restart the
   failing repetitions are **not contiguous**; whether the cell lands unanimous PASS,
   unanimous FAIL or split is deliberately not predicted, because the mechanism is not
   identified yet.

   **This cell is load-bearing.** It is the study's only certified-then-failed
   sub-interval and F19 reads it as the first empirical confirmation that the A6
   uncovered sliver cannot be certified. If the failures were the server, F19's headline
   claim is confounded and has to be restated. That is the single most damaging thing this
   probe could find, which is why it runs first.

4. **`P_pts3`/ped [+0.779°, +0.026°] stays split.** Medium-high confidence. The two
   passing repetitions brake at 377 ft and the eight failing ones never brake at all, so
   the outcome is a knife-edge on whether the brake latches, not a spread around a mean.
   Under the standing rule a cell that is still split is **VOID**, not a 20% failure rate,
   and it should be reported as void.

## What the answer is allowed to change

The repetition count in `PROTOCOL.md` section 3, through the amendment procedure and not
otherwise. It may not retroactively rescore any committed cell: the ledger rows stand as
measured, and a disposition explains a contradiction rather than erasing it.

If prediction 3 fails — if the `P_cont`/plate split reproduces with the same contiguous
shape under independent servers — then the shared server is exonerated, D-6 is not the
mechanism here, and the repetition count should not be reduced on this evidence.
