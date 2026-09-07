# Findings

Measured results and corrections, newest first. PROTOCOL.md section 8: a measured cell
that contradicts its expectation is a bug until proven otherwise, and findings live
here, never inside the protocol.

---

## F6 — 2026-09-07, CARLA's scene brightness is not monotone in sun altitude, and the horizon shows up twice

Found by the illumination guard ported from the steering study (NOTES section 2b), on the
first capture campaign it ever ran against. **It failed the campaign, and it was the guard
that was wrong** — but the measurement it produced is worth having, and one half of it
independently corroborates amendment A6.

### The measured curve

Mean frame brightness at capture pose 0, Town01 site 0, fixed exposure f/4.0 (A7),
headlamps below +5° per the campaign, one frame per knot:

| sun ° | +60.000 | +42.766 | +28.397 | +18.743 | +12.542 | +7.715 | +5.298 |
|---|---|---|---|---|---|---|---|
| mean | 0.5064 | **0.5282** | 0.5182 | 0.4579 | 0.4033 | 0.3366 | 0.2617 |

| sun ° | +4.198 | +3.525 | +1.891 | +1.391 | +0.779 | +0.026 | **+0.000** | −0.961 | −29.554 | −30.000 |
|---|---|---|---|---|---|---|---|---|---|---|
| mean | 0.2295 | 0.2102 | 0.1355 | 0.1082 | 0.0758 | 0.0377 | **0.0665** | 0.0496 | 0.0406 | 0.0406 |

Two things in there are not what a monotone model predicts.

**1. Brightness peaks near +43°, not at +60°.** The scene is *dimmer* with the sun near
zenith than at mid-elevation. The camera sees a large sky panel, and at 60° the sky in the
direction of travel is darker than at 43°, which more than offsets the extra road
illumination. 4.5% of the axis span.

**2. There is a spike at exactly 0.000°.** Brightness falls 0.0758 → 0.0377 approaching
the horizon, jumps to 0.0665 at zero, then resumes at 0.0496. 5.9% of the span, across a
0.026° step.

**The second one is A6 measured a second way.** A6 concluded from blend error that the
horizon is *a genuine discontinuity in the renderer's sky model, not merely a region of
high curvature*. The knot bisection independently picks out `[0.026°, 0.000°]` as the one
sub-interval that cannot meet tolerance at any width (0.0163 against a 0.01 tolerance).
The photometric signature — a different statistic, on different frames, computed by a
different tool — singles out the same sub-interval. Two measurements that share no code
agreeing on where the renderer breaks is the strongest evidence in the study that the
uncovered sliver is real and not an artifact of the bisection.

### The guard was wrong, and the repair is a magnitude test

The first version asserted that within one headlamp regime a lower sun renders a strictly
darker frame — read off A5's brightness table, which only ever covered +6° to −6°, and
extrapolated to the whole 90° axis. It is false at both ends.

Strict ordering was never the property worth asserting. Every failure this guard exists to
catch moves brightness by a LOT: a condition swap, an unsettled weather write (A4 measured
75% too bright twelve ticks in), a knot rendered at its neighbour's illumination. So the
check now bounds magnitude — no single step may run backwards by more than 12% of the axis
span, and the whole axis may not accumulate more than 25% — plus a span floor and an
extremes check. The measured axis scores 4.5% and 4.5%; rendering the +0.779° knot in
daylight would score 90%.

Inversions across a sub-interval the knot measurement itself declares uncovered are
recorded and not charged, because that declaration is the study having already measured
that the renderer is discontinuous there.

**Added at the same time, and it is the better check:** the four capture campaigns
(`lead`, `none`, `ped`, `none_ped`) render the same site at the same knots and differ only
by what stands in front of the camera. Their brightness curves must agree, and that
comparison rests on no model of the renderer at all. A knot rendered at the wrong
illumination in one campaign shows up as that campaign disagreeing with the other three at
that knot and nowhere else. `python tools/condition_signature.py` reports it and the
rebuild runs it.

### Why this is recorded rather than quietly fixed

Two of the errors in the steering follow-on programme were in the *analysis* code rather
than the experiment, and both would have inverted a conclusion. This is the same class:
a guard whose premise was an extrapolation, which would have rejected every correct
capture campaign this study will ever run. It was caught because it fired on data whose
provenance was known good, and because the numbers it printed were looked at instead of
its verdict being taken at face value.

---

## F5 — 2026-09-06, the A12 rebuild: `a_max` was an integration artifact, and the safety budget was 33% too short

**This is the disposition PROTOCOL section 8 requires.** Rebuilding the primitives on the
corrected harness moved braking authority from **0.868 g to 0.505 g** at 25 mph, and
`r_req` at 25 mph with it, from **34.7 ft to 52.0 ft**. A 42% move in the one measured
number the entire safety budget is derived from is a bug until proven otherwise. It is
now measured, and the old number is the wrong one.

### What was ruled out, and what it was

A12 changed two things in `connect()` at once, and the new desktop changed a third:

| candidate | verdict |
|---|---|
| D-2, acknowledged `apply_control` | **not the cause** |
| the RTX 4070 -> RTX 5090 migration | **not the cause** |
| D-1, explicit substepping | **the cause, entirely** |

Measured by sweeping substeps with D-2 held ON and everything else fixed
(`tools/substep_convergence.py`, `results/carla/substep_convergence.json`). Before A12
this study inherited CARLA's default substepping, which at `fixed_delta_seconds = 0.05`
integrates the whole 50 ms step in **five** substeps. Setting exactly that today, on the
new GPU and through the acknowledged-control path, reproduces the published number to
four decimal places:

| substeps | step | stop | a from TIME | a from DISTANCE | disagreement |
|---|---|---|---|---|---|
| 2 | 25.00 ms | 10.6-14.9 ft | 1.77-2.07 g | 1.43-1.97 g | non-repeatable, impossible |
| 4 | 12.50 ms | 33.3 ft | 0.9867 g | 0.678 g | **+45.5%** |
| **5** | **10.00 ms** | **35.4 ft** | **0.8678 g** | **0.6233 g** | **+39.2%** |
| 8 | 6.25 ms | 37.7 ft | 0.5766 g | 0.5679 g | +1.5% |
| **16** | **3.125 ms** | **44.7 ft** | **0.5054 g** | **0.4865 g** | **+3.9%** |

`0.8678` is the value in the pre-A12 `braking.json`, to the digit. So the GPU migration
is not in it and D-2 is not in it: **the whole 42% is the integrator.**

### The old measurement was impossible on its own terms, and nothing looked

A stop has one average deceleration. Read from the time it took, the pre-A12 stop gives
0.868 g; read from the distance it covered, the same stop gives 0.623 g. Those cannot both
be true, and the 39% gap is the coarse integrator failing to resolve the brake transient.
Every guard the job had was satisfied: the deceleration was under the 1.3 g plausibility
bound that catches a vehicle driving into a junction, the twenty runs agreed with each
other to four decimals, the grade was 0.0%, and the verdict was PASS.

`job_braking` now reads every stop both ways and **fails** if they disagree by more than
10%. That check costs nothing and would have caught this on the first day of the study.

### Convergence, and why 16 substeps is the answer rather than a preference

CARLA clamps `max_substeps` to 16 and says so only in a warning line, so an arm at 32 or
64 is the 16-substep arm relabelled. The knob saturates before it can demonstrate
convergence, so the integration step was shrunk the other way instead, by reducing
`fixed_delta_seconds` at 16 substeps. **These arms are a physics check and not a study
configuration**; PROTOCOL section 1 fixes the control rate at 20 Hz and every measured
cell runs there.

| integration step | a from distance | change |
|---|---|---|
| 3.125 ms (the study's, dt = 0.05) | 0.4864 g | |
| 1.563 ms (dt = 0.025) | 0.4801 g | -1.29% |
| 0.781 ms (dt = 0.0125) | 0.4768 g | -0.69% |

Converged: a four-fold finer integration moves the primitive by 2.0% in total, and the
last halving by 0.69%. **0.505 g is the vehicle. 0.868 g was the solver.**

*Recorded because the first version of that verdict was wrong in my own analysis code, not
in the data.* It compared raw stopping distances between arms, and the arms do not start
from identical speeds — the PI hold exits on a tolerance, so v0 lands at 25.5, 25.1 and
24.9 mph — and distance goes as v². On that variable the sweep reads 1.85% and 1.25% and
returns NOT_CONVERGED, which is the settle controller being reported as if it were the
integrator. `a = v0²/2d` divides it out. Steering-notes section 4, in this repository, on
the first try.

### What it costs the study, and what it does not

- **`r_req` at 25 mph: 34.7 ft -> 52.0 ft. At 50 mph: 114.2 ft -> 183.4 ft.** Property S
  quantifies over poses inside `r_req`, so the certified window is larger, and every
  bound, gate and witness is recomputed against it.
- **The pre-A12 study was internally consistent and still not about this vehicle.** Its
  physics braked at 0.868 g and its budget assumed 0.868 g, so its policies really did
  stop inside a 34.7 ft budget, its oracle really did pass 10/10, and its published
  "braking at 33.6 ft against r_req 34.7" really did hold. In a world whose vehicle
  dynamics CARLA's own model does not produce. That is rule D-11 stated concretely: the
  numbers are not wrong relative to each other, they are not reusable.
- **A derived budget cannot detect an error in the primitive it is derived from.** `r_req`,
  the expert label, the oracle's trigger and the closed-loop pass criterion all move
  together with `a_max`, so every consumer stayed self-consistent while the primitive was
  40% off. The oracle passed 10/10 before and passes 10/10 now, at two different physics.
  Only a check from OUTSIDE the derivation chain could see it, and the one that worked was
  the cheapest available: read one stop two ways and require the readings to agree.
- **Nothing in PROTOCOL.md above the amendment line changes.** The design, the cells, the
  properties and the expectations are untouched; `a_max` is defined there as a
  measurement, and this is that measurement taken correctly. The lock is unmoved at
  `a80d8c8dd458`.

---

## F4 — 2026-08-25, Iteration 2 verdicts: the dusk gap reappears for the pedestrian, 25.5 degrees wide

Committed at `ea1700c` BEFORE any witness drive (CARLA is lent out; the drives are
provably later). Property S over the 15 RGB sub-intervals:

- **Cell 1 (`P_pts_ped`): FALSIFIED**, as pre-registered — and the shape is stark: a
  single CONTIGUOUS falsified band from +25.899 to +0.360 deg, 25.5 degrees of dusk
  between the regulatory endpoints, certified only at the extremes (60 to 25.9 above,
  0 to −30 below). The lead campaign's falsified band was 10.8 deg; sampling only the
  test points costs the pedestrian hazard more than twice the axis.
- **Cell 3 (`P_cont_ped`): CERTIFIED** in every covered sub-interval, as
  pre-registered; the only falsification is the declared-uncovered horizon sliver.
  Cleaner than the lead campaign (no shoulder caveat).
- **Property A, `P_cont_ped`: 3/15** — the section 9 "sleeper" is live: the
  continuum-trained pedestrian policy cannot be certified quiet on an empty road
  across most of the axis, despite training with the A10 no-target control. Whether
  that surfaces as premature braking in the witness drives is exactly what M7 will
  show. `P_pts`'s property-A sweep is queued on GPU availability (no ordering
  constraint; property A has no witness drive).

M7 remains: drive the witnesses at each sub-interval midpoint once CARLA is handed
back (`tools/drive_witness.py --policy P_pts --scenario ped`, then P_cont).

---

## F3 — 2026-08-25, Iteration 2: standoff is measured AT REST, recorded before the re-run

**Written before any re-run, per PROTOCOL section 8.** The first ped M4 sweep returned
`P_pts_ped` 9/10 at darkness. The evidence says the miss is harness semantics, not the
policy: all ten runs latched at the identical brake range (33.12 ft); nine rested at
4.43 ft and one at 2.62 ft, and the only varying factor is the walker's crossing phase
against a pass criterion computed as **min separation over the whole run**. That
min-over-run coding is a lead-scenario approximation — a stationary lead's gap
decreases monotonically, so min-over-run and resting gap coincide. A crossing walker
walks PAST the stopped vehicle, so min-over-run measures the walker's path, not the
vehicle's margin. The frozen text is explicit: section 3 defines `d_margin` as
"required standoff **at rest**".

**The change:** pass requires (a) no contact at any time (unchanged, min-over-run),
and (b) separation of at least `d_margin` while the vehicle is at rest. For the lead
scenario this is identical to the old coding. It is recorded here BEFORE the M4
re-run; if `P_pts_ped` still cannot make 10/10 under the frozen semantics, M4 fails
and the protocol stops the ped study ("no story").

Also recorded: the P_pts_ped in-between gate fails only inside [0.360, 0.000] deg —
the RGB campaign's own uncoverable horizon sliver (F2), mirroring the lead pattern —
and passes at <= 0.247 everywhere covered; P_cont_ped passes everywhere (0.310).
Verify now flags any sub-interval inside the horizon band [<= 0.37, >= 0.00] deg as
`family_uncovered` for both campaigns' knot sets. The oracle harness bug F1's fix
introduced (trigger from ego centre instead of front bumper, -1.9 ft contacts) was
caught by the re-validation stage and fixed before anything was trained against it.

---

## F2 — 2026-08-25 re-measurements: the committed campaign survives its own audit

The four measurements the F1 audit demanded, all run on a fresh server:

- **P_pts capture gate: PASS at 0.260** of the decision threshold (P_cont was 0.191).
- **P_pts in-between gate: passes at 0.578 worst over the covered sub-intervals, and
  fails at 1.074 in exactly one place — the [0.143, 0.000] deg sliver A6 already
  declared uncovered.** That cell is FALSIFIED in the committed verdicts, drove 0/10
  at a RENDERED midpoint (independent of blend validity), and is excluded from the
  coverage claim. So the gate failure confirms the A5/A6 horizon discontinuity at the
  behavioural level rather than weakening any committed cell: every certified P_pts
  cell now has a passing behavioural gate, closing audit item F10.
- **Re-bisection under the corrected three-channel metric**
  (`results/carla/family_knots_rgb.json`): 15 sub-intervals against the campaign's
  11, and the uncoverable horizon band widens from [0.143, 0.000] (blue-only error
  0.0386) to **[0.36, 0.00] at error 0.0164**. The committed campaign's knots stand
  as its record — PROTOCOL section 4 makes the behavioural check the deciding one,
  and it passes for both policies everywhere the family claims coverage — but any
  FUTURE capture campaign must use the RGB knots and the wider exclusion.
- **Sites re-measured with the fixed-exposure camera** (audit F2's defect): street
  lighting site 1 = 0.23, site 3 = 9.86 (auto-exposed values were 4.55 / 25.71). The
  A4 conclusion — site 1 effectively unlit, site 3 lit — is unchanged; the old
  numeric values should not be quoted.

Amendment A11 (same day) records the certified property as the brake decision
threshold, which is what every committed verdict already meant.

---

## F1 — 2026-08-25 audit: results were filed under the wrong ledger cells, and five measurement defects found

A four-way audit (CARLA/capture handling, protocol-integrity tooling, paper–code
consistency, citation verification) found and fixed:

- **The lead-scenario results were recorded under the ped-cross cells (1/3).** Every
  artifact is `scenario: lead`; refiled to cells 2/4 with artifact bindings, and
  `python -m study.ledger --check-order` (new) now cross-checks each cell's artifact
  scenario/policy against the frozen row, verifies the verdict's *content* was
  committed before its witness drive (first-add checking would credit the A10
  retrain's overwrites with pre-retrain dates), and requires the violating width on
  falsified cells (cell 2: 10.802° of the 90° axis).
- **Every blend-error and brightness number was sampled from the BLUE channel only**
  (stride-40/64 over BGRA with a dead alpha guard). Fixed to all three channels in
  `build_family_knots`, `interval_sweep`, `carla_jobs` (in-between, capture-check,
  sites, expert samplers). **Consequence: the A5/A6 tables and the knots in
  `family_knots.json` were blue-only measurements; re-measure the knots before
  Iteration 2 trains against them.** The behavioural gate (full-RGB, policy-output
  space) partially backstops the committed result, but it was only run on P_cont.
- `job_sites` used an auto-exposure camera (the A4 defect); the lit/unlit numbers
  quoted in A4 were not absolute photometry. Fixed to the fixed-exposure camera;
  re-measure before anything relies on them again.
- `run_policy`/`drive_witness`/`gate_behavioural` silently drove the lead geometry
  for any `--scenario`; they now refuse anything but `lead` until the pedestrian
  harness exists. `job_pedestrian`'s oracle trigger used walker distance instead of
  conflict-point range (A7); fixed.
- Training now seeds every RNG, and verify/witness artifacts record git SHA,
  timestamp, and the model's sha256, so a committed verdict is tied to the network
  it describes. `drive_witness` refuses to run against uncommitted or modified
  verdicts. `protocol_lock` now hashes each amendment (append-only is enforced, and
  `--accept` is no longer pre-authorized by a stale counter). The A6 uncovered
  sliver is flagged `family_uncovered` in verify output.

Open questions for the study lead: the `a_max/2` verification threshold vs frozen
section 7's `a_max` (needs an amendment or a code change), and the knot re-measurement
above.
