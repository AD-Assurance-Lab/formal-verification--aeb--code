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
  certificate's own exhibited witnesses, across 96 covered sub-intervals.
- All three arms pass all three regulatory endpoint tests 10/10.

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

Seven of ten items in `docs/QUEUE.md` are measured. The seed sweep is running. Two remain:
the trench-plate cells, which need a harness that does not exist, and the rest of the
harness hardening.

## What to read, in order

1. `PROTOCOL.md` — the frozen design. Run `python -m study.protocol_lock` first.
2. `FINDINGS.md` — newest first. F5 (the primitive) and F6 (the renderer's brightness
   curve) are the two from the rebuild.
3. `NOTES_FROM_STEERING_2026-09-06.md` — what transfers from the sibling study, including
   the guard this repo was missing.
4. `CARLA_DETERMINISM_PENDING.md` — still open on the LAP protocol; see below.
5. `docs/STUDY_REPORT.md` — carries a banner saying which of its sections still stand.

## How to run it

`bash scripts/rebuild_all.sh` is the whole study in dependency order, with a fresh
simulator before every measurement stage. It stops before M7 on purpose: the verification
verdicts must be committed to git between M6 and M7, because that ordering is the only
thing that makes a verdict a prediction, and a script that committed them for you would
turn the blind protocol into a formality.

---

## Open, in priority order

### 1. Cells 5 and 6 have no harness at all

The frozen ledger has six cells. Cells 5 and 6 — `P_pts` and `P_cont` on the FMVSS 127
false-activation scenario, a steel trench plate approached in lane at 50 mph — **are
specified and have never been built.** `tools/scenarios.py:place_trench_plate` tiles the
plate to the standard's dimensions and is validated, and nothing drives it.

Property A is currently verified on the `none` scenario, an empty road at the lead poses.
That is a legitimate must-not-brake property and it is the one that caught the position
confound (A10), but **it is not the standard's false-activation scenario** and the study
must not describe it as one.

What cells 5 and 6 need, in order:

1. **`plate` and `none_plate` capture scenarios.** `capture_campaign.nominal_states` needs
   a plate branch: place the plate with `S.place_trench_plate`, drive the approach at
   `PLATE_MPH`, and record range to the plate. `none_plate` replays those poses with the
   plate removed, the same way `none` replays `lead`. Roughly 15 minutes of simulator time
   for both at 17 knots.
2. **A must-not-brake closed-loop criterion.** `run_policy.one_run` is built around braking
   and standoff and has no notion of passing by *not* stopping. A plate run passes when
   commanded deceleration never exceeds 0.25 g and the vehicle crosses the plate at speed.
   This is new code, not a flag.
3. **`verify.py --scenario plate --property A`** for both policies, which then works
   unchanged.
4. **Witness drives** at each sub-interval midpoint, as for the hazard cells.

Estimated at three to four hours including measurement. Section 9 calls cell 6 the
sleeper: `P_cont` sees more braking data and may be the more trigger-happy, which is a
trade no single-sided test can see. That is worth doing properly rather than quickly.

### 2. The LAP protocol is still unresolved, and it is lab-wide

`CARLA_DETERMINISM_PENDING.md` records a genuine conflict: the `carla-determinism`
package's D-7 says closed-loop numbers remain rates over at least ten repetitions, and the
steering study's amendment A-4 supersedes that with three laps under a fully enforced
harness. **This study follows `PROTOCOL.md`, which says ten**, and that is the right
default while the conflict is open — resolving it needs the package's section 4 amendment
procedure and it is Zach's call, not a study's.

Note that a "lap" does not map cleanly onto AEB in any case: a lap is one traversal of all
the unique scored road, and an AEB cell is a discrete approach to a discrete hazard. What
does transfer, and is adopted: a fresh server before every measurement stage, one process
per stage, a fresh vehicle per run, the determinism preflight green on each fresh server,
and the margin reported with every verdict.

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
- **`carla-determinism` is pinned to a commit, not a tag.** The 1.1.0 API this harness
  needs is pushed but untagged. `scripts/bootstrap_env.sh` now proves the API is present
  rather than only that the package imports.
