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

The repetition count in `CLAUDE.md` section 3, through the amendment procedure and not
otherwise. It may not retroactively rescore any committed cell: the ledger rows stand as
measured, and a disposition explains a contradiction rather than erasing it.

If prediction 3 fails — if the `P_cont`/plate split reproduces with the same contiguous
shape under independent servers — then the shared server is exonerated, D-6 is not the
mechanism here, and the repetition count should not be reduced on this evidence.

---

# Addendum, same day: the plate cell has a named mechanism now

Written after `P_cont`/plate [+0.026°, +0.000°] was reopened as a bug rather than left
void, and **before** the confirming drive. The candidates listed in F22 were guesses. This
is not.

## The mechanism

`plate_run` ticks the world twice per control iteration. `J.grab_frame` at the top of the
loop calls `world.tick()` and returns the frame that tick produced; a second bare
`world.tick()` sat at the bottom. `one_run` has never had it. So:

- the false-activation driver ran the closed loop at **10 Hz**, where CLAUDE.md section 3
  fixes the control rate at 20 Hz and states the quantization as 3.7 ft at 50 mph. The
  real quantization was **7.3 ft**;
- the policy was evaluated on **every other rendered frame**, the intervening one being
  discarded by `grab_frame`'s stale-frame guard;
- `peak_demand_mps2` is therefore a maximum over a subsample, and near the plate the
  demand changes fast.

A sampler that skips every other frame past a sharp peak either catches it or misses it.
That is what 2.61–2.62 against 1.90–1.91 m/s² **with nothing in between** looks like, and
no continuum mechanism produces a gap with no intermediate values.

## Predicted, before the drive

1. **The cell becomes unanimous at 20 Hz.** High confidence. If it is still split, the
   double tick was not the mechanism and this addendum is wrong.
2. **It goes unanimously to FAIL, not to pass**, with peak demand at or above the higher
   mode. A 20 Hz sampler cannot miss a peak that a 10 Hz sampler sometimes catches, so the
   measured peak should rise to ≈2.6 m/s² or beyond on every repetition — meaning
   `P_cont` exceeds the nuisance limit on this sub-interval **always**, and the shared
   server's 6/10 and the restarted harness's 2/10 were both flattered by a sampler that
   kept missing the peak.
3. **`brake_range_ft` tightens.** The two values recorded were 307.68 and 271.12 ft,
   36.6 ft apart, which is five iterations at 7.3 ft. At 3.7 ft quantization the spread
   across repetitions should be a small number of 3.7 ft steps or none.

## Why it runs on Town01 and runs now

A14 moves the study to Town12 and every Town01 artifact becomes unusable. **The Town01
certificate and policies are the only place this defect can be settled**, so it is settled
before the rebuild, not after. `CARLA_MAP=Town01` exists for exactly this and for nothing
else.

## What it does not change

Nothing measured is rescored. The Town01 plate results stand as collected on the harness
that collected them, and the finding is what carries forward to Town12.

---

# Addendum: what the Town12 rebuild is expected to produce

Written 2026-09-09 at 19:00, with the capture campaign running and **before** pairing,
training, endpoints, gates or verification have produced anything. The A14 rebuild changes
the map, the site, the cloud cover and the repetition harness at once, so almost every
number will move. That is not the interesting part. What is written down here is the small
set of outcomes that would mean something has gone **wrong**, as opposed to merely
different.

## Already measured, and not predictions

The primitives came out at `a_max` 0.499 g against Town01's 0.5048, `r_req` 52.5 ft at
25 mph against 52.0, `t_lat` unchanged at 0.150 s, with the oracle and contact checks
passing. The axis re-bisected to 20 sub-intervals with **no uncovered band** (F25). Those
are results, not expectations.

## Predicted

1. **Pairing passes.** Poses are replayed from `states_<scenario>.json`, so a knot that
   differs by a tick is a capture defect and nothing about the map should produce one.
   High confidence. A pairing failure means the capture loop is not deterministic on this
   map, which would be a new defect and would stop everything.

2. **All three arms pass all three regulatory endpoints, 10/10.** Medium-high confidence,
   and this one is load-bearing: it is the setup for the whole paper. `P_pts` failing an
   endpoint on Town12 does not mean the paper is wrong, it means the policy did not train
   on this road, and the honest response is a training problem to fix rather than a result
   to report. **A study whose baseline cannot pass the regulatory test has no story**, in
   CLAUDE.md section 10's own words.

3. **The behavioural in-between gate fails somewhere.** Medium confidence, and it is the
   first thing that can contradict F25. On Town01 the photometric check passed at every
   sub-interval and the behavioural gate then failed for `P_pts`/ped at [+12.542°, +7.715°]
   at 1.016, needing A5's repair. Town12's axis has finer daylight splitting and a 29.5°
   step across darkness; the darkness step is the obvious suspect. If it fails, section 4's
   repair applies and the knots refine — that is the protocol working, not a defect.

4. **The falsified band survives, and moves.** Low confidence on the width, high on the
   existence: the study's claim is that a policy trained on the regulatory points fails
   between them, and the mechanism — a discrete training matrix — is a property of the
   training, not the road. A `P_pts` that is certified everywhere on Town12 would be the
   single most damaging outcome available and would need a written disposition before
   anything else proceeded.

5. **Zero certified-then-failed sub-intervals.** High confidence, now that F24 has removed
   the one the study had. This is the certificate's soundness and it is the claim the paper
   rests on.

6. **No void cells at M7.** Medium confidence. Three repetitions on three fresh servers
   were identical to the recorded precision on Town01 (F22), and Town12 has no reason to be
   worse. A void cell is a bug to chase, and this study's three have all been real defects.

## What would mean the rebuild itself is broken

Distinguished from a result, because after F26 the failure mode of interest is an artifact
that is wrong in a way no numeric check sees:

- any capture reusing a frame set from another campaign — the stamp now makes this loud;
- endpoint or gate numbers that reproduce Town01's **exactly**, which on a different road
  at a different cloud cover would mean something is still reading old artifacts;
- a certificate whose scope does not cover what the drives cover, in either direction.
