# State of play

**Current belief, and only current belief.** `PROTOCOL.md` is the design and wins over
this file; `FINDINGS.md` is the measured record and is append-only. This file is where
someone picking the study up should start, and it is rewritten rather than appended to.

`CLAUDE.md` and `PROTOCOL.md` have both pointed at this file since M0. It did not exist
until 2026-09-07, which is the failure mode the lab keeps writing down: a rule that names
a missing artifact fails in exactly the way a satisfied rule looks.

Live state in the protocol's own terms: `python -m study.status`.

---

## Where the study is, 2026-09-08

**The A12 rebuild is complete, M0 through M7, on three policy arms.** Every number in
`docs/STUDY_REPORT.md` was measured on the corrected harness between 2026-09-07 and
2026-09-08 and nothing is carried over. `python -m study.status` is authoritative.

### The result, in five lines

- `P_cont`, the continuum-trained control, certifies **16/16** and **15/16** of the covered
  axis and drives the whole thing with **zero contacts and zero nuisance stops** on both
  hazard scenarios.
- `P_pts`, trained on the two regulatory conditions that bound the interval, is falsified
  over **50.3°** and **48.3°** and produces contacts.
- `P_pts3`, trained on **all three** conditions FMVSS 127 tests, certifies slightly more of
  the axis and **crashes four times as often** — and is falsified for property A over
  **89.2° of 90** on the pedestrian scenario, braking on an empty road at 31 of 33
  illuminations including full daylight.
- **Nothing was certified and then failed**, in any cell, at midpoints or at the
  certificate's own exhibited witnesses, across 96 covered sub-intervals. Property S
  falsified **9 of the 9** sub-intervals that produced a contact.
- Both ledger contradictions are **disposed** (F17), and the repair they suggested was
  built and **fails**: stating property S as the disjunction the controller actually needs
  catches only 8 of those 9, missing a cell it certifies at 1.03× that crashes 10/10.
- All three arms pass all three regulatory endpoint tests 10/10.
- **The ledger is 6 of 6 and every cell has all three columns.** Cells 5 and 6 say **no arm false-activates
  on the trench plate**: every property A verdict is identical with the plate present and
  removed, every bound within 0.5%, so the falsifications belong to the illumination and
  not the plate (F18). `P_cont` closes cell 6 CERTIFIED with **no margin** — 0.9825x — and
  is the loudest arm on the plate, which is the section 9 sleeper arriving.

### What the rebuild found about the instruments

Nine defects, listed with what caught each in `docs/STUDY_REPORT.md` §17. The three that
would have changed a published number:

- **`a_max` was an integration artifact** (F5). 0.868 g was CARLA's default substepping
  failing to resolve a brake transient; the correct value is 0.505 g and `r_req` is 52.0 ft,
  not 34.7.
- **The verifier had no branch and bound** (F8), which PROTOCOL §6 has specified since M0.
  Without it the negative control read 14/16 and 13/16 with false falsifications in its
  widest sub-intervals, and the study would have reported that continuum training also
  fails at dusk.
- **Property S was being scored with a property A condition** (F9), which manufactured a
  soundness violation in the negative control out of a policy braking 306 ft early.

### The queue

Ten of eleven items in `docs/QUEUE.md` are measured. Item 8's largest open piece, the
per-repetition server restart (D-6), is now built and adopted as A13. What remains of item
8 is the branch-and-bound witness search depth and the `a_max` time-versus-distance
reading, and the new open item is F23's cloud modulation.

## What to read, in order

1. `PROTOCOL.md` — the frozen design. Run `python -m study.protocol_lock` first.
2. `FINDINGS.md` — newest first. F5 through F15 are all from this rebuild; F5 (the
   primitive was a solver artifact), F8 (the verifier had no branch and bound) and F12
   (training on the whole regulatory matrix made the policy worse in both directions) are
   the three that change what the study claims.
3. `NOTES_FROM_STEERING_2026-09-06.md` — what transfers from the sibling study, including
   the guard this repo was missing.
4. `CARLA_DETERMINISM_PENDING.md` — still open on the LAP protocol; see below.
5. `docs/STUDY_REPORT.md` — the complete methodology and results, rewritten from the
   rebuilt measurements on 2026-09-08. The SUPERSEDED banner is gone.
6. `docs/QUEUE.md` — what happens next, and which of it has been measured.

## How to run it

`bash scripts/rebuild_all.sh` is the whole study in dependency order, with a fresh
simulator before every measurement stage. It stops before M7 on purpose: the verification
verdicts must be committed to git between M6 and M7, because that ordering is the only
thing that makes a verdict a prediction, and a script that committed them for you would
turn the blind protocol into a formality.

---

## Open, in priority order

### 1. Cells 5 and 6 are complete; what they found needs writing into the paper

**Closed.** Endpoints 9/9 at 10/10, certificates in (F18), witness drives in (F19):
1,020 runs across three arms with and without the plate. Two results the paper does not
yet contain:

- `P_pts` commands **2% of the nuisance limit at every lighting condition FMVSS 127 tests
  and 138% of it between them**, 60x its worst test point — and the plate is irrelevant,
  the same illumination on empty road gives 3.382 against 3.381. The standard's own
  false-activation procedure cannot see this.
- `P_cont` is the only arm that brakes **for the steel**: at +0.013° the plate adds 22%
  to peak demand and carries it from 90.6% to 110.5% of the limit — the only place in any
  arm where the plate changes a verdict. That is section 9's
  named sleeper, and it is in the A6-uncovered sliver — which is also the study's only
  certified-then-failed sub-interval, and the first empirical proof that the sliver cannot
  be certified.

**The scenario substitution happened twice and both times in the safe-looking direction.**
Property A was originally verified only on `none`, an empty road at the lead poses — a
legitimate must-not-brake property, the one that caught the position confound (A10), and
**not** the standard's false-activation scenario. The harness written to fix that then
queued `none_plate`, which is the plate poses with the plate **removed** — the same
substitution one level down. `scripts/rebuild_all.sh` now queues `plate` (the standard's
scenario) and keeps `none_plate` beside it as the control that makes a plate verdict
attributable to the plate, and the stage takes an explicit scope argument rather than
silently covering less.

Section 9 calls cell 6 the sleeper: `P_cont` sees more braking data and may be the more
trigger-happy. **The endpoint drives support that**, in the only place a single-sided test
could not see it — `P_cont` peaks at 0.082–0.375 m/s² on the plate against `P_pts3`'s
0.030–0.066 and `P_pts`'s 0.034–0.056, four to eleven times higher, though every arm is far
under the 2.453 limit and all nine cells pass 10/10. The certificate then puts `P_cont` at
0.98–1.00x of the limit on the two near-horizon sub-intervals, the thinnest margins of any
arm, which by F17 is a band where a bare pass says nothing.

### 2. The repetition count is settled here, and the reason is not the one anyone expected

**Closed for this repository, 2026-09-09, by amendment A13.** Three repetitions, each in
its own process against its own freshly restarted server, reported with the margin, and
repetitions that disagree make the cell **void**. The path is
`scripts/drive_witness_reps.sh`, validated end to end against a committed ten-repetition
cell: same verdicts, no void cells, ninety seconds.

It was not adopted from the steering study. It was measured here, and the measurement
found three things the ten-repetition floor had been hiding (F22):

- Of 281 committed ten-repetition cells, **277 are unanimous and 4 are split**, and not
  one of the four is a draw from a rate.
- Two of the four were an instrument defect (F21). One is the policy on its own brake
  threshold, and it stays split on the clean harness, so it is **void** — and it fails
  harder there, 2/10 rather than the shared server's 6/10.
- The fourth was the simulator moving underneath the measurement, which is F23 and is the
  finding with the longest reach.

**F23: CARLA's cloud layer moves under fixed weather.** Every driver here sets
`cloudiness = 10.0` beside the sun altitude, and the cloud layer drifts, so scene
brightness at the horizon wanders **3.9% with elapsed simulated time** and never settles
inside 3,000 ticks. At `cloudiness = 0.0` the same scene settles by tick 20 and holds to
0.08%. The 120-tick settle is not wrong about what it measured — a day-to-night
transition — it is blind to a few-percent modulation that is decisive exactly where this
study's interesting cells are.

**That is still open and it is bigger than the repetition count.** Three fresh servers
agree with each other because they all sample the same early point of that curve, which
makes them reproducible and not representative. `capture_campaign.py` settles once and
then walks its poses, so a single capture sweeps the curve along its own pose index.
Controlling it means `cloudiness = 0` or a much longer settle plus a photometric check,
and both change what the conditions ARE. That needs its own amendment and it is Zach's
call. Nothing published is asserted to be wrong; what is asserted is that the study does
not currently control its independent variable to better than about 2% at the horizon.

### 3. What the rebuild costs the paper

`formal-verification--aeb--arxiv` has a complete 9-page draft whose measured numbers all
come from the superseded harness — `34.7 ft`, `33.58 ft` brake onset, `6/11` and `8/11`
certified, and the eleven-row Table 4 that its STATUS file calls "the whole study on one
page". Every one of those changes. Nothing there should be regenerated by hand; that
repository's `figures/make_data.py` is the only sanctioned path from these results into
it, and it needs re-running against the rebuilt artifacts.

---

## Standing traps, specific to this repository

Written where they will be read, because each has cost real time here.

- **A read or a placement issued next to a write does not see that write.** Weather,
  spectator transforms and sensor delivery all apply on the next tick, and nothing errors.
- **The illumination guard bounds magnitude, not ordering.** CARLA's scene brightness is
  not monotone in sun altitude (F6). Do not re-tighten it to strict monotonicity; it will
  reject every correct capture campaign.
- **`a_max` has two readings and they must agree.** If a future harness change moves them
  apart, the integrator is not resolving the stop and neither number describes the vehicle.
- **The knot file states its own coverage and its own metric.** Read those fields; do not
  re-derive which sub-interval is uncovered from an altitude band, which has already moved
  three times.
- **A certificate at 1.0x is not a prediction this harness can cash.** Between about
  1.00x and 1.05x of threshold the margin carries no information about whether the drive
  holds: a sub-interval certified at 1.0318x crashed 10/10 while four thinner ones drove
  clean (F17). Report the margin, and do not read a bare pass near the threshold as one.
- **A "fixed" weather is not a static scene.** `cloudiness = 10.0` leaves a moving cloud
  layer, so the same sun altitude renders 3.9% brighter or darker depending on how long
  the server has been ticking (F23). Repetitions inside one process sample that curve;
  repetitions on fresh servers all sample its first few ticks. Neither is the converged
  scene, and there is no converged scene while the clouds are on.
- **`carla-determinism` is pinned to a commit, not a tag.** The 1.1.0 API this harness
  needs is pushed but untagged. `scripts/bootstrap_env.sh` now proves the API is present
  rather than only that the package imports.
