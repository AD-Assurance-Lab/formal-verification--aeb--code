# PROTOCOL.md - the frozen study design

**This file is locked.** `python -m study.protocol_lock` fails if anything above the
Amendments section changes without a recorded amendment. Tagged `protocol-v1`.

It exists because study logic in this lab has been lost twice, and because many
sub-experiments will run before this one finishes. When a result and this file disagree
about what the study is, **this file is right**. Findings go in `FINDINGS.md`, current
belief goes in `docs/STATE_OF_PLAY.md`, and neither may quietly redefine the design.

---

## 0. The claim

> The policy passes both regulatory test points. The certificate falsifies it without
> simulating. Driving the certificate's witness point confirms the failure the standard would
> have missed.

Framing for both audiences, and the only framing to be used outside the lab:

> Training against a discrete test matrix can create gaps at the matrix's own gaps, and here
> is a method that provides evidence between test points.

This is a complement to the test procedure, never a critique of it. FMVSS 127 is
performance-based and never claimed exhaustiveness.

## 0b. What we are selling, and the selection criterion

The product is **the verification software**. We are indifferent to the customer's sensors,
to modular versus end-to-end, and to their architecture. AEB is the vehicle for the
demonstration, not the subject. Covering the FMVSS matrix would demonstrate nothing about the
tool.

> **Selection criterion: choose cells where the worst case lies in the interior of the
> disturbance interval, not at either endpoint.**

A test campaign samples endpoints. If the failure lives between them, testing structurally
cannot find it and a certificate structurally must. Everything else is a case where testing
already works and we would be competing on cost rather than capability.

---

## 1. Task and operational design domain

| | |
|---|---|
| **Function** | Forward automatic emergency braking. Longitudinal only, no steering intervention, no driver interaction, no forward collision warning. |
| **Ego** | Stock CARLA passenger car, unmodified dynamics. Vehicle dynamics are not the subject. |
| **Sensing** | Single forward RGB camera. Camera-only, because the tool is sensor-agnostic and because radar is largely invariant to the disturbance under study and would erase the contrast. |
| **Network input** | Larger than a lane-keeping crop, since a pedestrian at `r_req` must survive downsampling. The exact resolution is fixed at M2 and recorded as an amendment. |
| **Policy output** | Deceleration demand, a continuous scalar. Latching: once commanded above threshold it is not withdrawn. |
| **Control rate** | 20 Hz. Quantization is 0.83 m at 60 km/h. |
| **Speeds** | 40 km/h for the hazard cells. 80 km/h for the false-activation cells, per the standard. |
| **Road** | Dry, straight, one site per scenario, all within one large map chosen by survey. |
| **Lighting** | The interval from full daylight to darkness under lower beam. Headlamps set per condition. |
| **Repetitions** | Every closed-loop number is a failure rate over at least 10 runs, reported with Wilson intervals. Never a single run. |

**Excluded, deliberately:** steering intervention, wet or snow surfaces, curves, multiple
simultaneous actors, forward collision warning, and any condition acting through vehicle
dynamics rather than perception.

## 2. Regulatory grounding

**FMVSS No. 127**, Automatic Emergency Braking Systems for Light Vehicles. Compliance
1 September 2029, 1 September 2030 for small-volume and specialty manufacturers.

What the standard supplies, so that we do not invent it:

| Element | Value used | Role in the study |
|---|---|---|
| Crossing pedestrian scenario | Adult, crossing from the right | Hazard scenario 1 |
| Stopped lead vehicle scenario | Stationary vehicle in lane | Hazard scenario 2 |
| False activation | Steel trench plate, ASTM A36, 2.4 x 3.7 m x 25 mm, approached in lane at 80 km/h | Scenario 3 |
| Nuisance braking limit | **0.25 g (2.45 m/s^2)** | The threshold in property A. Taken from the standard, not chosen |
| Lighting conditions | Daylight; darkness, lower beam; darkness, upper beam | Endpoints of the certified interval, and the training set for `P_pts` |
| Pedestrian speed bands | 10 to 55 km/h stationary, 10 to 65 km/h along path | 40 km/h sits inside both |

**Not covered, and never to be described as compliance.** Lead vehicle decelerating; lead
vehicle slower-moving; child pedestrian; crossing from the left; pedestrian walking along
path; pass-through false activation; forward collision warning; speeds above 80 km/h.

The standard is performance-based and sensor-agnostic. That is what makes a camera-only study
legitimate, and it is also why this is a statement about method rather than about any
manufacturer's product.

## 3. Derived safety budget

Every term measured in CARLA. None fitted, none modelled.

```
r_req  =  v (t_lat + dt)  +  v^2 / (2 a_max)  +  d_margin
```

- `a_max` worst measured average deceleration over at least 10 full-brake stops. Measuring
  rather than modelling removes the aerodynamic-drag question: the measurement contains drag
  at that speed, and neglecting drag analytically is conservative for stopping distance.
- `t_lat` measured brake-command to deceleration onset.
- `dt` control period, 0.05 s.
- `d_margin` required standoff at rest.

## 4. The disturbance family, and the gate that validates it

Both endpoints are **rendered in the simulator at an identical camera pose**, then
interpolated:

```
x_p(s) = x_p^daylight + s ( x_p^darkness - x_p^daylight ),   s in [0,1]
```

`s = 0` and `s = 1` are two regulatory test conditions. Every interior `s` is illumination the
standard never tests, and that interval is the entire study.

**Do not build the disturbance from an analytic photometric model.** Measured and failed: an
analytic fog model scored R-squared 0.848 on image fidelity while driving one policy 23.8
times harder than the real rendered condition. Image fidelity is not the property that
matters.

**Gate F, family validity.** A pixel-space blend of a daylight frame and a headlamp-lit night
frame is not physically dusk, and a reviewer will say so first. Because CARLA can render
intermediate illumination, we validate rather than assume: render at several interior sun
altitudes and require that the policy's response to the interpolated frame matches its
response to the rendered frame at matched poses, **behaviorally, not by image metric**.

If the interpolation fails that check, the repair is shorter intervals with rendered
interior endpoints (daylight to dusk, dusk to darkness), each certified separately and
composed. The claim survives; only the interval length changes.

## 5. Two policies differing only in axis sampling

Identical architecture, identical teacher-to-student distillation recipe, identical data
volume. **The only difference is how the lighting axis was sampled.**

- **`P_pts`** sees only the three regulatory lighting points. This is what a manufacturer
  optimizing against the test matrix builds, which is what makes the result matter.
- **`P_cont`** sees the lighting continuum, densely sampled.

The teacher is a distillation source and is never verified. The student is ReLU-only, no
BatchNorm, no Dropout.

**Engineering the gap is forbidden.** `P_pts` is trained on the regulatory points because
that is what the standard incentivizes. Weakening it further to manufacture a failure voids
the result.

## 6. Verification architecture

The family enters as a prepended `nn.Linear` mapping the scalar `s` to flattened pixels,
which keeps bound propagation in `patches` mode. Bounds by **alpha-CROWN with input-space
branch and bound** over `s`.

Not SDP-CROWN: it requires an L2 ball, and on a one-parameter family branch and bound
converges to the network's genuine output variation, leaving no looseness to remove.

## 7. The safety criterion

**Property S, must brake.** For all `s` in [0,1] and all poses with range to the conflict
point at most `r_req`, the certified **lower** bound on commanded deceleration is at least
`a_max`.

**Property A, must not brake.** On the false-activation scenario, for all `s`, the certified
**upper** bound on commanded deceleration is at most 0.25 g.

Both are pointwise conjunctions over a window the hazard geometry defines. Neither is a mean
nor a maximum over a run.

**Why the composition is closed form.** Once braking is commanded the network leaves the
loop, so the certificate composes into standoff distance analytically. Nothing integrates
network output over time, so nothing accumulates capture error.

**Closed-loop pass:** no contact and standoff at least `d_margin`, over at least 10
repetitions.

**Contact is inferred from bounding-box separation and kinematics, never from
`sensor.other.collision`.** Measured in this lab: a vehicle driven into a stationary car at
19 m/s ended 2.49 m inside a body whose contact distance is 6.06 m, and the collision sensor
reported zero events.

## 8. Protocol

- **Gate A, surrogate validity.** Captured deceleration demand must match driven demand below
  a stated threshold before any bound is computed on captured frames.
- **Gate F, family validity.** Section 4.
- **Verdicts are committed to git before the corresponding closed-loop run.** That is what
  makes a verdict a prediction.
- **A measured cell that contradicts its pre-registered expectation is a bug until proven
  otherwise.** It may not be written up as a finding until a written disposition lists the
  candidate causes ruled out.
- **Keep the negative control alive.** If `P_cont` also fails, or `P_pts` also certifies, stop
  and debug rather than narrating it.

## 9. The ledger

Six cells. Each cell is an **interval**, `s` in [0,1], not a point.

| # | Policy | Scenario | Endpoints (test) | FV over [0,1] | Witness driven | Conf |
|---|---|---|---|---|---|---|
| 1 | P_pts | ped cross | PASS both | FALSIFIED, interior witness | FAIL | high |
| 2 | P_pts | lead stop | PASS both | FALSIFIED, interior witness | FAIL | med |
| 3 | P_cont | ped cross | PASS both | CERTIFIED | PASS | high |
| 4 | P_cont | lead stop | PASS both | CERTIFIED | PASS | high |
| 5 | P_pts | trench plate | PASS both, <= 0.25 g | CERTIFIED | PASS | low |
| 6 | P_cont | trench plate | PASS both, <= 0.25 g | CERTIFIED | PASS | low |

**Cell 1 is the study.** 2 shows it is not one hazard geometry. **3 and 4 are the positive
control**, and without them cell 1 says only that a weak policy is weak. 6 is the sleeper:
`P_cont` sees more braking data and may be the more trigger-happy, which is a trade no
single-sided test can see.

**Also recorded per falsified cell: the width of the violating interval in `s`.** Both
audiences will ask how wide the gap is and what a test campaign would have had to sample to
find it.

**If cell 1 does not fail**, the result is a certified absence: proof that no illumination
between the two regulatory points defeats the policy. Still publishable, still a stronger
claim than a test campaign can make, and the paper leads on coverage rather than discovery.
This fallback is recorded now so it is not decided after seeing data.

## 10. Milestones and exit criteria

| | | Exit criterion |
|---|---|---|
| M0 | Specification | This file, locked and tagged |
| M1 | Map survey | Site set chosen by measured geometry, not by eye. Offline, no simulator |
| M2 | Harness and primitives | `a_max` and `t_lat` over >= 10 reps; contact detector validated against a deliberate collision; a perfect oracle passes 10/10 and a deliberately late one fails 10/10 |
| M3 | Expert and collection | The oracle passes 10/10 with standoff >= `d_margin` at both endpoints |
| M4 | Two policies | **Both policies pass both endpoints 10/10 on both hazard scenarios.** If `P_pts` cannot pass the regulatory tests there is no story |
| M5 | Gates A and F | Both pass, with numbers recorded |
| M6 | Verification | Bounds over `s` in [0,1] per cell, with a witness `s` and a violating width for any falsified cell. **Committed to git before M7** |
| M7 | Drive the witness | The agreement table |
| M8 | Demo and writeup | The single figure: certified bound against `s`, with both regulatory test points marked and the violation between them |

## 11. The figure

One plot decides whether this travels: **certified bound versus `s`, with the two regulatory
test points marked and the violation sitting between them.** Design the pipeline to produce
it rather than discovering later that it cannot.

---

## Amendments

Changes above this line require an entry here, and a re-lock with
`python -m study.protocol_lock --accept`. Append, never edit.

*(none yet)*
