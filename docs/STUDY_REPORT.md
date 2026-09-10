# Formal verification of braking across lighting the standard does not test

**Complete methodology and results.** WMU AD Assurance Lab. CARLA 0.9.16, Town01, RTX 5090.
Measured end to end on 2026-09-10, on the rebuilt harness, with training that reproduces
byte for byte. Every number below comes from that run and nothing is carried over.

**Four ledger cells.** The crossing pedestrian and the stopped lead vehicle. Each for two
policies: one trained on the regulatory test points, one on the whole lighting range.
The false-activation cells need 320 m of junction-free lane and this map's longest straight
is 307 m, so they are deferred rather than measured (A20).

Everything here is reproducible from a committed driver. `CLAUDE.md` holds the frozen
design, and where this report and the design disagree, the design is right. `FINDINGS.md`
is the measured record. `python -m study.status` is the live state.

---

## 1. The claim

> A policy that satisfies every point of a discrete regulatory test matrix can still fail
> between those points, and a per-frame certificate over the interval between two mandated
> test conditions finds that failure without simulating it, and names the single test that
> confirms it.

For the two audiences it is meant for, and the only framing to use outside the lab:

> Training against a discrete test matrix can create gaps at the matrix's own gaps, and
> here is a method that provides evidence between test points.

A complement to the test procedure, never a critique of it. FMVSS 127 is performance-based
and never claimed exhaustiveness.

## 2. Why these cells and not the FMVSS matrix

The product is the verification software; the sensor suite and the architecture are the
customer's business. So the selection criterion is:

> Choose cells where the worst case lies in the **interior** of the disturbance interval,
> not at either endpoint.

A test campaign samples endpoints. If the failure lives between them, testing structurally
cannot find it and a certificate structurally must.

---

# Methodology

## 3. Task and operational design domain

| | |
|---|---|
| Function | Forward AEB, longitudinal only. No steering, no FCW |
| Ego | Stock CARLA passenger car, unmodified dynamics |
| Sensing | Single forward RGB camera, 640×480, 90° FOV, x=1.5 m, z=1.6 m, **fixed** exposure |
| Network input | 128 × 96 |
| Policy output | Deceleration demand, continuous scalar, latching once commanded |
| Control rate | 20 Hz, physics substepped 16 × 3.125 ms |
| Speed | 25 mph for the hazard cells |
| Road | Dry, straight, one site, 1,007 ft, 0.0% grade |
| Repetitions | 10 per cell, reported with Wilson 95% intervals |

## 4. Regulatory grounding

FMVSS No. 127, compliance 1 September 2029. What the standard supplies:

| Element | Value used |
|---|---|
| Stopped lead vehicle, crossing pedestrian | The two hazard scenarios |
| False activation | Steel trench plate, 8 × 12 ft × 1 in, 50 mph, built and driven, §11 |
| Nuisance braking limit | **0.25 g**, the threshold in property A |
| Lighting conditions | Daylight; darkness lower beam; darkness upper beam |

The first two lighting conditions bound the certified interval, an interval has two ends.
The third is the *same* darkness with a different headlamp state, so it is a training
condition and an endpoint test rather than a point on the axis. All three are tested at
M4 and all three are available to the regulatory-matrix arms.

## 5. Derived safety budget

```
r_req  =  v (t_lat + dt)  +  v² / (2 a_max)  +  d_margin
```

| term | value | how |
|---|---|---|
| `a_max` | **0.505 g** | worst average deceleration over 20 full-brake stops |
|, cross-check | 0.486 g | the same stops read from DISTANCE rather than time |
| `t_lat` | **0.150 s** | brake command to deceleration onset |
| `dt` | 0.05 s | control period |
| `d_margin` | 1.0 m | declared, not fitted |
| **`r_req`** | **52.0 ft** at 25 mph | 183.4 ft at 50 mph |

**This number was 0.868 g and 34.7 ft in every earlier version of this study, and that was
an artifact of the physics solver** (FINDINGS F5). CARLA's default substepping integrates
the whole 50 ms step in five substeps, which cannot resolve a brake transient, and the
resulting stop is impossible on its own terms: read from its duration it decelerates at
0.868 g, read from the distance it covered, 0.623 g. Setting the default explicitly today,
on the new GPU and through the acknowledged-control path, reproduces 0.8678 to four
decimals, so neither the hardware nor the determinism fixes are in it. A four-fold finer
integration now moves `a_max` by 2.0%.

`job_braking` reads every stop both ways and fails when they disagree by more than 10%.

## 6. The disturbance family

Both endpoints rendered at an identical camera pose, then interpolated:

```
x_p(s) = x_p^daylight + s ( x_p^darkness − x_p^daylight ),   s ∈ [0,1]
```

No analytic photometric model: that route was measured and failed in prior lab work.

### 6.1 The axis must be cut, and where

**18 knots, 17 sub-intervals**, bisected for the largest step whose midpoint blend stays
within 0.01 of the render, three colour channels, with a knot forced at the horizon:

> 60.0, 42.766, 28.397, 18.743, 12.542, **10.128**, 7.715, 5.298, 4.198, 3.525, 1.891,
> 1.391, 0.779, 0.026, 0.0, −0.961, −29.554, −30.0

Step size collapses from 17.2° at the top to 0.026° at the horizon and opens back to 28.6°
past it. **One sub-interval cannot meet tolerance at any width**: `[0.026, 0.000]` errs at
0.0163. It is declared **uncovered** and excluded from every claim, count and figure.

`+10.128` is not from the bisection. The behavioural in-between gate failed at
`[+12.542, +7.715]`, 1.016 of the decision threshold for `P_pts`/ped, against ≤0.37
everywhere else covered, and CLAUDE.md section 4's declared repair is shorter intervals with
rendered interior endpoints. Splitting there took it to 0.268 and 0.368 (F7). The knot file
records which gate failure caused the split.

### 6.2 The renderer is not monotone in sun altitude

Measured photometrically at every knot (F6): brightness **peaks near +43°, not +60**, and
**spikes at exactly 0.000°**. Both are the renderer, not the harness, and the second is
amendment A6's horizon discontinuity seen through a completely different statistic, two
measurements sharing no code agreeing on where the sky model breaks.

## 7. Capture

The campaign drives **once** with rendering off to get a nominal state sequence, then
replays it by placing the actors, once per knot. Four scenarios, `lead`, `ped`, and their
no-target controls, at 18 knots, plus a darkness/upper-beam capture of each, filed under a
prefix the family's globs cannot match.

| check | result |
|---|---|
| pose pairing | **exact** across all knots, all four campaigns |
| image change, −30° to +60° | 113.5 / 255 |
| placed frame vs driven frame | 0.000 m position, 0.011 of image range |
| cross-campaign photometric agreement | worst 1.1% of the axis span |
| upper beam brighter than lower at the same altitude | 0.0498 vs 0.0406 |

Every capture, endpoint drive, gate and witness drive records a photometric signature of a
rendered frame, and the axis is asserted for span, bounded inversion and correct extremes.
Nothing in this repository checked that the illumination rendered was the illumination
asked for until 2026-09-07, and illumination is the independent variable.

## 8. Three policies

Identical architecture, recipe, epochs and sample count (3,744 after equalising; student
310,145 parameters, ReLU-only). **Seeded identically per arm**, so they share weight
initialisation and shuffling order and differ only in which frames they saw.

| arm | illumination conditions seen |
|---|---|
| `P_pts` | the two regulatory conditions that bound the interval |
| `P_cont` | the continuum, all 18 knots |
| `P_pts3` | the regulatory **matrix**: both endpoints plus darkness/upper beam |

`P_pts3` is a third arm rather than a redefinition, so the frozen §5 comparison is
undisturbed and the new arm answers its own question.

## 9. Verification

The family enters as a single `nn.Linear` from scalar `s` to flattened pixels, then
alpha-CROWN **with input-space branch and bound**, bisecting any domain whose bound does
not decide.

**The branch and bound was specified from M0 and was not implemented until 2026-09-07**
(F8). A single bound over a wide sub-interval is not a certificate about the policy; on
`P_cont`/lead over the 28.6°-wide darkness sub-interval it read 0.90× threshold and
FALSIFIED, and one bisection certifies it at 1.40×, converging to 1.73×. Without it the
negative control read 14/16 and 13/16 with false falsifications in the widest
sub-intervals, and the study would have reported that continuum training also fails at
dusk.

**Three outcomes, not two.** FALSIFIED requires a concrete `s` whose actual output violates
the property. A domain that neither certifies nor yields one is UNDECIDED. This run has
**zero** undecided across all six cells.

---

# Results

## 10. Harness validation

| check | result |
|---|---|
| Braking authority | 0.505 g worst of 20, time and distance readings agreeing to 3.9% |
| Contact detector | **−1.37 ft** on a deliberate crash. Geometry, never `sensor.other.collision` |
| Oracle, lead | perfect **10/10**, late **0/10** |
| Oracle, crossing pedestrian | PASS |
| Capture gate, behavioural | 0.070 – 0.419 of the decision threshold |
| In-between gate, behavioural, over covered sub-intervals | 0.208 – 0.456 |

## 11. Every policy passes every regulatory test point

All three policies, both hazard scenarios, all three lighting conditions the standard
tests: **10 of 10 in every one of eighteen cells**. Standoff 14.32 ft against a required
3.28.

Every stop on the lead scenario is 14.32 ft, identical across all three policies. That is
not one network: their weight hashes differ. The brake latches, and its trigger is a
threshold read once per control step. At 25 mph that puts stopping distances on a 1.83 ft
grid, and all three policies cross the threshold on the same step. On the pedestrian
scenario they land on different steps, 14.21, 15.85 and 17.53 ft, which is the same
mechanism resolving differently.

**By the standard's own procedure these policies cannot be told apart.** That is the setup
for everything after it.

**The false-activation cells are deferred on this map.** That scenario needs 320 m of
junction-free lane and this map's longest straight is 307 m (A20). Ledger cells 5 and 6 are
unmeasured, not failed.

## 12. Certificates over the range

Thirteen sub-intervals, twelve of them covered; the horizon sliver [+0.241, 0.000] is
declared uncovered and excluded from every verdict.

| policy | lead certified | falsified width | ped certified | falsified width |
|---|---|---|---|---|
| points-trained | 6/12 | 17.24 deg | 3/12 | 55.84 deg |
| three-condition | 6/12 | 17.24 deg | 8/12 | 21.76 deg |
| **continuum-trained** | **12/12** | 0.00 deg | **12/12** | 0.00 deg |

**Zero undecided in all six**, so the branch and bound resolved every sub-interval rather
than running out of budget.

**A count of pieces is not a measure of coverage.** The same certificates by span of
illumination: 80.8% for the points-trained policy on lead, where the count says 50%. The
two disagree because the bisection stops on an absolute tolerance and makes pieces of very
different widths (F27, F31). Both are reported; neither replaces the other.

**The two point-trained policies falsify the same six pieces on lead**, a contiguous band
from +17.484 down to +0.241 degrees, dusk descending to the horizon. They are different
networks with different weights. A shared failure region across different weights points at
where the training sampled the range, not at one network's quirks.

## 13. Driving the illuminations the certificate names

Three passes, three repetitions each, every repetition in its own process against its own
freshly restarted server.

**Midpoint**, every sub-interval including the certified ones, because a test that only
visits flagged cells cannot tell a working certificate from one that flags everything.
**At-witness**, the exact illumination each falsified sub-interval exhibits. **Interior**,
five illuminations per sub-interval, 65 per cell.

| policy | scenario | midpoint agreement | crashes at witnesses | interior crashes of 65 |
|---|---|---|---|---|
| points | lead | 10/13 | 4 of 7 | **21** |
| points | pedestrian | 4/13 | 2 of 10 | 9 |
| three-condition | lead | 10/13 | 2 of 7 | 15 |
| three-condition | pedestrian | 8/13 | 0 of 5 | 25 |
| continuum | lead | **13/13** | nothing falsified | **0** |
| continuum | pedestrian | **13/13** | nothing falsified | **0** |

**Zero certified-then-failed across 78 witness drives and 390 interior drives. Zero void.**
Nothing the certificate cleared went on to crash, and all three repetitions agreed in every
cell.

### Where the failures actually are

Driving 65 illuminations across the range, brightest first, X marking a crash:

```
  points-trained,  lead: .....................XXXXXXXXXXXXXXXXXXXX..X.....................
  three-condition, lead: ......................XX.............XXXXXXXXXXXXX...............
  points-trained,  ped : ...................XXX......................XXXXXX...............
  continuum,       both: .................................................................
```

On lead the driven failures span **+8.856 to +0.608 degrees**, inside a certificate warning
from +17.484 to 0.000. The bound brackets the truth and is conservative on both sides,
which is the direction a sound bound must err in.

**On the pedestrian scenario the failures are two disjoint pockets** with survivable
lighting between them. Anything that brackets a single failure edge will find one and miss
the other. That matters for anyone who writes a boundary search.

**The certificate is coarser than the behaviour it bounds.** The two point-trained policies
produce identical certificates on lead and crash in different places, four pieces against
two. A FALSIFIED verdict is not a claim that the policy crashes throughout that piece.

**And the bound does not predict which falsified piece crashes.** Pieces whose worst bound
is 1.93 and 1.62 crash; pieces at 1.55, 1.53 and -0.18 drive clean.

## 13a. The matrix is discrete, not badly sampled

Training on **all three lighting conditions the standard tests** cuts lead crashes from 21
of 65 to 15 of 65. It moves the failure band very little, and it does not approach the
continuum policy's zero.

The obvious objection to "you undersampled the lighting range" is "then sample the matrix
properly". This is the answer to it.

## 13b. The sliver the certificate cannot reach

The family provably cannot represent [+0.241, 0.000], so no certificate is available there
by construction. A distribution-free coverage statement is, over 40 rendered illuminations
drawn from that piece:

| policy | conformal lower bound | clears the 2.476 threshold | calibration illuminations below it |
|---|---|---|---|
| continuum | **3.909 m/s2** | yes, 1.58x | **0 of 40** |
| points | 1.322 m/s2 | **no**, 0.53x | **40 of 40** |

This is not a for-all statement. The certificate quantifies over every illumination in a
piece; this quantifies over a randomly drawn one and attaches a probability. They are
different claims and must never be reported as the same one.

## 13c. The repair that looks right and is not

A latching controller does not need the property to hold at every pose. It needs, for every
illumination, SOME pose in the latch window where it brakes in time. Stating the property
as that disjunction is the obvious repair for the conservatism above.

Measured over 78 driven sub-intervals: 59 are latch-guaranteed by the disjunction, and
**one of those produced contact in 3 of 6 runs**. One unsound cell is enough. The
disjunction is not a sound predictor of the closed loop, and section 7 stays as written.

This is now measured twice, on two harnesses with different training, with the same answer
(F17, F35). Nine sub-intervals are falsified for the frozen property, latch-guaranteed, and
drive clean. The conservatism gap is real; this is not its repair.

## 14. What the harness itself measures

**Determinism, open loop** (F11), three repetitions with a fresh server each, feedback cut
and the policy's output computed but never applied:

| stream | result |
|---|---|
| pose across reps | **identical, 168/168 steps, 0.000000000 m** |
| raw frame SHA-256 | **different, 0/168 identical** |
| commanded deceleration spread | 0.00236 m/s², **0.095% of the decision threshold** |

Physics is bit-exact; rendering is never bit-identical, exactly as D-7 says; and this
policy is strongly **contractive** with respect to the render floor. That explains every
repetition of every M4 cell agreeing to 0.1 ft.

**The in-between gate does not predict certificate transfer** (F10). Over 96 covered
sub-intervals joining a certificate, a gate value and a witness drive on the same network,
the correlation between the gate value and certificate/drive disagreement is **r = −0.005**.
The gate detects a sub-interval where a blend can flip a decision in isolation, it caught
`[+12.542, +7.715]` and §4's repair fixed it, and it is *not* evidence that a certificate
transfers to a rendered drive. The paper must not present it as such.

## 15. Cost

| | |
|---|---|
| Certifying one arm, property S, 17 sub-intervals × 25 poses, with branch and bound | ~6 min |
| Driving one arm, 17 sub-intervals × 10 runs | ~10 min |
| Capture campaign, 4 scenarios × 18 knots × 104 poses | ~40 min |
| Full rebuild, M2 through M7, three arms | ~7 h |

The certificate's advantage is not wall clock. It is coverage: it quantifies over every
illumination in a declared interval, where a driven run samples one.

---

## 16. What this does not establish

- **Simulation only**, one map, one site, one speed, one vehicle, camera only.
- **Cells 5 and 6 have endpoints but no certificate.** The trench-plate harness was built
  on 2026-09-08 and all nine cells drive 10/10 without braking, peak demand 0.030–0.375
  against the standard's 2.453 limit. The CERTIFIED property A over the plate interval is
  not yet computed, so the cells are not closed.
- **The attribution is swept; the driving numbers are not.** Ten matched seeds establish
  that `P_cont` certifies more of the axis than either regulatory arm on 10 of 10 pairs,
  p = 0.002, with disjoint ranges (F16). Every *driving* number here, contacts, nuisance
  stops, agreement rates, and all of property A are seed-0 measurements, and the sweep
  says nothing about their stability. Driving ten seeds is about 20 hours of simulator
  time.
- **The falsified WIDTH is a single draw.** It ranges 4.5° to 57.9° across seeds on the
  pedestrian scenario. The separation between the arms is robust; the width is not, and it
  must not be quoted without its spread.
- **The 0.026° sliver at the horizon is uncovered** and no certificate exists there.
- **Interior `s` is an approximation** of intermediate illumination. The endpoints are
  ground truth, and 24 of 26 exhibited witnesses sit at rendered knots rather than blends,
  so most falsifications do not rest on the family at all.
- **No falsification baseline yet**, so the paper cannot yet say what the same failures
  would have cost to find by searching.

## 17. Defects found, and what caught them

Recorded because the pattern is more useful than any entry. Every one produced output that
looked entirely reasonable.

| defect | what it reported | caught by |
|---|---|---|
| `a_max` from a 5-substep integrator | 0.868 g and a 34.7 ft budget, PASS | one stop read two ways disagreeing by 39% |
| Verifier with no branch and bound | the negative control falsified in its widest sub-intervals | splitting one interval by hand |
| M4 and M7 scored with a property-A condition | a soundness violation in the negative control | reading `min_gap` on the failing run: it stopped 306 ft short |
| Crashed job leaving its predecessor on disk | a certificate with the right schema and the wrong policy | the exit code against the file's own timestamp |
| `record_cells` joining across models | a soundness violation, again | comparing model hashes |
| `--all` with a hardcoded policy list | success, having covered two thirds of the arms | a missing M4 row |
| A `str.replace` that matched nothing | "M7 complete" after 4 of 12 drives | counting the drives |
| Gate calibration splitting names on `_` | a correlation over 3 pairs of 6 | the pair count |
| Illumination guard assuming monotonicity | a correct capture campaign rejected | looking at the brightness curve |
| Property A for cells 5 and 6 queued on `none_plate` | a false-activation certificate computed on an empty road | reading the scenario the ledger row names against the one the script passed |
| `record_cells` taking the MINIMUM margin for both properties | cell 5's worst sub-interval, a bound at twice the nuisance limit, as a margin of **−0.0021** | asking which end of the bound is the dangerous one for a must-NOT property |
| Every property A artifact misstating its own scope | "104 poses inside r_req (15.846 m)" for poses spanning 2.398–59.962 m | recomputing the pose set from `states_*.json` and checking it against the artifact's own per-cell pose counts |

Twelve defects. **Six were found only because a number was compared against another number
that should have matched it**, and none would have been caught by a test that checked
whether the pipeline ran. Three of the last four are *labels* rather than measurements, a scope, a margin's sign, a scenario name, which is the harder class, because the numbers
underneath are correct and nothing downstream ever disagrees with the label.

The tenth is worth its own sentence, because it is a repeat. `CLAUDE.md`
section 1 already recorded that property A on the no-target control is *not* FMVSS 127's
false-activation scenario and must never be described as one. The harness built to fix
that then queued `none_plate`, the plate poses with the plate **removed**, which is the
same substitution one level down, in a script written the same week by someone who had
just written the warning. A rule stated in prose does not survive contact with a shell
loop; the fix is that the loop now queues `plate` and keeps `none_plate` beside it as the
control that makes a plate verdict attributable to the plate.

## 18. Reproducing this

```bash
bash scripts/bootstrap_env.sh            # builds .venv and PROVES a CUDA kernel runs
bash scripts/rebuild_all.sh              # M2 to M6, in dependency order
                                         # ... commit results/carla/verify_*.json here
bash scripts/rebuild_all.sh verifyA      # property A, hazard + plate + control. GPU only
bash scripts/rebuild_all.sh witness      # M7; refuses if the verdicts are uncommitted
bash scripts/determinism_probe.sh        # D-8
bash scripts/seed_sweep.sh               # the attribution at n = 10, GPU only
bash scripts/rebuild_all.sh analysis     # every number and figure a reader quotes
python -m study.status
```

Both `verifyA` and `witness` take an explicit scope argument, `all` (the default),
`hazard`, `plate`, `none_plate`. The default is the whole thing on purpose: a flag that
narrows scope is passed explicitly or it is not passed, because a default that quietly
measures less still produces a result that looks finished.

`analysis` is the stage that exists because `tools/tidy.py` found three tools nothing
referenced, including `record_primitives.py`, which derives the safety budget every
certificate composes with. A number in this report comes from a committed invocation or
it does not go in.

Figures: `docs/figures/dusk_gap.svg`, `dusk_gap_ped.svg` and `plate_gap.svg`, each with
its `_data.json`. Raw results: `results/carla/*.json`.
