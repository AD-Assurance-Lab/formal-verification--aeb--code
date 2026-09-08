# Formal verification of AEB across illuminations FMVSS 127 does not test

**Complete methodology and results.** WMU AD Assurance Lab. CARLA 0.9.16, Town01, RTX 5090.
Rebuilt end to end on 2026-09-07/08 under amendment A12 and the corrected determinism
harness; every number below was measured on that harness and nothing is carried over.

Everything here is reproducible from a committed driver. `PROTOCOL.md` is the frozen
design; where this report and that file disagree, the protocol is right. `FINDINGS.md` is
the measured record, `docs/STATE_OF_PLAY.md` is current belief, `docs/QUEUE.md` is what
happens next.

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
| False activation | Steel trench plate, 8 × 12 ft × 1 in, 50 mph — built and driven, §11 |
| Nuisance braking limit | **0.25 g**, the threshold in property A |
| Lighting conditions | Daylight; darkness lower beam; darkness upper beam |

The first two lighting conditions bound the certified interval — an interval has two ends.
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
| — cross-check | 0.486 g | the same stops read from DISTANCE rather than time |
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
decimals — so neither the hardware nor the determinism fixes are in it. A four-fold finer
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
`[+12.542, +7.715]` — 1.016 of the decision threshold for `P_pts`/ped, against ≤0.37
everywhere else covered — and PROTOCOL §4's declared repair is shorter intervals with
rendered interior endpoints. Splitting there took it to 0.268 and 0.368 (F7). The knot file
records which gate failure caused the split.

### 6.2 The renderer is not monotone in sun altitude

Measured photometrically at every knot (F6): brightness **peaks near +43°, not +60**, and
**spikes at exactly 0.000°**. Both are the renderer, not the harness, and the second is
amendment A6's horizon discontinuity seen through a completely different statistic — two
measurements sharing no code agreeing on where the sky model breaks.

## 7. Capture

The campaign drives **once** with rendering off to get a nominal state sequence, then
replays it by placing the actors, once per knot. Four scenarios — `lead`, `ped`, and their
no-target controls — at 18 knots, plus a darkness/upper-beam capture of each, filed under a
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

## 11. M4: every arm passes every regulatory test point

All three arms, both hazard scenarios, all three lighting conditions: **10/10**, Wilson
95% [0.72, 1.00], on PROTOCOL §7's frozen pass criterion. Brake onset 51.9 ft against
`r_req` 52.0, standoff 14.3 ft.

**False activation, cells 5 and 6.** All three arms, all three lighting conditions, ten
runs each on an ASTM A36 plate tiled to exactly 8.0 × 12.0 ft and approached at 50 mph:
**9 of 9 cells 10/10**, peak commanded deceleration 0.030–0.375 m/s² against the standard's
0.25 g limit of 2.453. Nobody brakes for the plate.

One defect is recorded beside the verdict rather than inside it: `P_pts3` on the pedestrian
scenario in daylight brakes at **287.6 ft** and stops 250 ft short, ten runs of ten. That
is nuisance braking — a must-NOT-brake condition, which is property A — and §7's criterion
does not fail on it.

## 12. M6: certificates over the interval

Covered sub-intervals (16 of 17; the horizon sliver is excluded):

| arm | lead certified | falsified width | ped certified | falsified width |
|---|---|---|---|---|
| `P_pts` | 4/16 | 50.32° | 4/16 | 48.27° |
| `P_pts3` | 6/16 | 43.02° | 3/16 | 43.70° |
| `P_cont` | **16/16** | 0.00° | **15/16** | 0.75° |

Those are seed 0. Over **ten matched seeds** (F16), `P_cont` beats both regulatory arms on
10 of 10 pairs, p = 0.002, ranges disjoint — while `P_pts3` and `P_pts` are
indistinguishable from each other (p = 0.45 and 0.75, ranges overlapping). The separation
is robust. The individual widths are single draws from a distribution spanning 4.5° to
57.9°, and should never be quoted alone.

**Adding the third regulatory lighting condition does not close the gap**, and over ten
seeds it does not reliably narrow it either. A policy trained on every lighting condition FMVSS 127
tests is still falsified across roughly 43° of the axis, while the continuum-trained
control certifies essentially all of it. The gap is not an artifact of having sampled two
of three points.

## 13. M7: driving the illuminations the certificate names

Two passes. **Midpoint**: every sub-interval, certified ones included, because a test that
only visits flagged cells cannot tell a working certificate from one that flags
everything. **At-witness**: the concrete `s` the certificate exhibited for each falsified
sub-interval, because §10 says *drive the witness* and the midpoint is not the witness.

| arm | agreement | contacts | premature |
|---|---|---|---|
| `P_cont` / lead | **17/17** | **0** | **0** |
| `P_cont` / ped | 15/17 | **0** | **0** |
| `P_pts3` / lead | 11/17 | 40 | 0 |
| `P_pts` / lead | 5/17 | 10 | 20 |
| `P_pts3` / ped | 5/17 | 18 | 32 |
| `P_pts` / ped | 4/17 | 0 | 40 |

**Nothing was certified and then failed**, in any cell, at either the midpoints or the
exhibited witnesses. For a safety tool that is the direction that matters.

**The continuum-trained control drives the entire axis with zero contacts and zero nuisance
stops on both scenarios.** Neither regulatory-matrix arm does.

**The at-witness pass earns its place.** `P_pts`/lead drives 0/10 with ten contacts at
+7.715°, the illumination its certificate exhibited, while the midpoint of that same
sub-interval drives clean. Across the arms, 8 of 53 driven witnesses fail the frozen
criterion and 78 contacts occur at them.

**`P_pts3` is the result nobody would have guessed from the certificates.** It certifies
*more* of the axis than `P_pts` (6/16 against 4/16 on lead) and crashes **four times as
often** when driven: 40 contacts against 10. Training against the full regulatory matrix
narrowed the certified gap and made the driving worse.

### 13a. What a FALSIFIED verdict was ever entitled to predict (F17)

Two ledger cells contradicted their pre-registration, and PROTOCOL §8 required a written
disposition before either could be written up. Both have the same cause and it is in how
the property is *stated*.

Property S is a conjunction — the bound must clear at **every** one of the 25 poses inside
`r_req`, for every illumination in the sub-interval. The controller latches once and holds
full braking, so what the closed loop needs is a disjunction: at every illumination,
**some** pose in the latch window clears. The first implies the second and not the
converse, so a FALSIFIED property S is not on its own a prediction that the drive fails.
Cell 1's `witness: expected FAIL` was reading it as one.

The **latch window** is derived from the primitives and never from the drives: the worst
measured stop at 25 mph is 44.71 ft, which already carries `t_lat`, plus `d_margin`
3.28 ft, so a latch at 47.99 ft or more stops in time — poses 79–80 on the pedestrian
approach and 79–81 on the lead one. The drives agree without having been used: latch to
rest is **37.56 ft in all 610** non-premature braking runs, against 39.10 ft of predicted
braking travel.

That disposes of cell 3 outright. `P_cont`/ped is falsified at pose 87, **36.77 ft** —
past the last range at which a latch could still meet `d_margin` — while the vehicle
latches at pose 79, 51.4 ft, in all seventeen sub-intervals including both falsified ones.
Certifying the disjunction, `P_cont` latches in time **17/17 on both scenarios**, at
1.06–2.10×.

**The obvious repair then fails, and that is the useful part.** Stating property S as the
disjunction is formally better aligned with the controller, so it should certify the same
crashes. It does not:

| | property S (conjunction) | disjunction over the latch window |
|---|---|---|
| sub-intervals driven | 102 | 102 |
| producing a contact | 9 | 9 |
| flagged by the certificate | **9 of 9** | **8 of 9** |

The miss is `P_pts`/lead over [+7.715°, +5.298°], certified to latch in time at **1.0318×**,
whose endpoint drove **10 contacts in 10 runs, 9 never braking, ending 1.93 ft inside the
lead vehicle**. On the captured frames the certificate is right — poses 79–81 give 1.568,
2.345 and 2.563 against a 2.476 threshold — and the whole approach there sits within ±5%
of the threshold, so the live-rendered drive lands on the other side of it. **The margin
does not separate them either**: four sub-intervals certified more thinly (1.0000×,
1.0033×, 1.0231×, 1.0250×) drove clean.

Requiring all twenty-five poses forces the certificate away from that knife edge, and that
is what buys the 9-of-9. §7 stays as written; the disjunction is reported beside it as the
quantity the agreement table is entitled to score against, not in place of it.

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
The gate detects a sub-interval where a blend can flip a decision in isolation — it caught
`[+12.542, +7.715]` and §4's repair fixed it — and it is *not* evidence that a certificate
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
  p = 0.002, with disjoint ranges (F16). Every *driving* number here — contacts, nuisance
  stops, agreement rates — and all of property A are seed-0 measurements, and the sweep
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
  would have cost to find by searching (`docs/QUEUE.md` item 5).

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

Ten defects. **Five were found only because a number was compared against another number
that should have matched it**, and none would have been caught by a test that checked
whether the pipeline ran.

The tenth is worth its own sentence, because it is a repeat. `docs/STATE_OF_PLAY.md`
section 1 already recorded that property A on the no-target control is *not* FMVSS 127's
false-activation scenario and must never be described as one. The harness built to fix
that then queued `none_plate` — the plate poses with the plate **removed** — which is the
same substitution one level down, in a script written the same week by someone who had
just written the warning. A rule stated in prose does not survive contact with a shell
loop; the fix is that the loop now queues `plate` and keeps `none_plate` beside it as the
control that makes a plate verdict attributable to the plate.

## 18. Reproducing this

```bash
bash scripts/bootstrap_env.sh            # builds .venv and PROVES a CUDA kernel runs
bash scripts/rebuild_all.sh              # M2 to M6, in dependency order
                                         # ... commit results/carla/verify_*.json here
bash scripts/rebuild_all.sh witness      # M7; refuses if the verdicts are uncommitted
bash scripts/rebuild_all.sh verifyA      # property A, GPU only
bash scripts/determinism_probe.sh        # D-8
python -m study.ledger --check-order     # the blind protocol, checked against git
python tools/record_cells.py --write     # the ledger, from the artifacts
python tools/make_figure.py              # PROTOCOL section 11's figure
python -m study.status
```

Figure: `docs/figures/dusk_gap.svg` and `.html`. Raw results: `results/carla/*.json`.
