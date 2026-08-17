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
| **Control rate** | 20 Hz. Quantization is 3.7 ft at 50 mph. |
| **Speeds** | 25 mph for the hazard cells. 50 mph for the false-activation cells, per the standard. |
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
| False activation | Steel trench plate, ASTM A36, 8 x 12 ft x 1 in, approached in lane at 50 mph | Scenario 3 |
| Nuisance braking limit | **0.25 g** | The threshold in property A. Taken from the standard, not chosen |
| Lighting conditions | Daylight; darkness, lower beam; darkness, upper beam | Endpoints of the certified interval, and the training set for `P_pts` |
| Pedestrian speed bands | 6 to 34 mph stationary, 6 to 40 mph along path (the standard states these in km/h) | 25 mph sits inside both |

**Not covered, and never to be described as compliance.** Lead vehicle decelerating; lead
vehicle slower-moving; child pedestrian; crossing from the left; pedestrian walking along
path; pass-through false activation; forward collision warning; speeds above 50 mph.

The standard is performance-based and sensor-agnostic. That is what makes a camera-only study
legitimate, and it is also why this is a statement about method rather than about any
manufacturer's product.

## 3. Derived safety budget

Every term measured in CARLA. None fitted, none modelled. **US units throughout: mph, feet,
g.** Where the standard states a value in metric, its own number is quoted alongside.

```
r_req  =  v (t_lat + dt)  +  v^2 / (2 a_max)  +  d_margin
```

- `a_max` worst measured average deceleration over at least 10 full-brake stops, in g. Measuring
  rather than modelling removes the aerodynamic-drag question: the measurement contains drag
  at that speed, and neglecting drag analytically is conservative for stopping distance.
- `t_lat` measured brake-command to deceleration onset.
- `dt` control period, 0.05 s.
- `d_margin` required standoff at rest, in feet.

## 4. The disturbance family, and the in-between check

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

**The in-between check.** A pixel-space blend of a daylight frame and a headlamp-lit night
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
43 mph ended 8.2 ft inside a body whose contact distance is 19.9 ft, and the collision sensor
reported zero events.

## 8. Protocol

- **The capture check.** Deceleration demand measured on a captured still frame must match
  what the vehicle actually commanded at the same spot, before any bound is computed on it.
- **The in-between check.** Section 4.
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
| M5 | Capture check, in-between check | Both pass, with numbers recorded |
| M6 | Verification | Bounds over `s` in [0,1] per cell, with a witness `s` and a violating width for any falsified cell. **Committed to git before M7** |
| M7 | Drive the witness | The agreement table |
| M8 | Demo and writeup | The single figure: certified bound against `s`, with both regulatory test points marked and the violation between them |

## 11. The figure

One plot decides whether this travels: **certified bound versus `s`, with the two regulatory
test points marked and the violation sitting between them.** Design the pipeline to produce
it rather than discovering later that it cannot.

## 12. Site selection

One large map, several sites within it, chosen by survey rather than by eye. A site
qualifies on:

- straight clear run long enough to settle at speed and stop from 50 mph. The ego is
  launched at cruise speed rather than accelerated, so this is the settle distance plus
  `r_req`: about 310 ft at 50 mph, and 400 ft is used with margin
- pedestrian crossing geometry, with sidewalk and walker navmesh on both sides
- both lit and unlit stretches, since headlamp beam is a test variable
- nothing about the posted limit. CARLA's declared limits are inconsistent between maps
  and we command test speeds directly, so a road's posted number does not constrain the
  speed we run on it

Posted limits are recorded by the survey for description only. Ego speed is commanded and
other vehicles are commanded, so the site is chosen on geometry alone. Where a limit is
reported it is read from the map's OpenDRIVE file, never from `get_speed_limit()`, which
returns the nearest sign prop or a default and disagrees with the declared limit on most
towns.

**Large maps are not usable on this hardware at all.** The hero tag is still required, and
still works, but it is not sufficient. See amendment A3 for the measurement that moved this
study to Town01.

---

## Amendments

Changes above this line require an entry here, and a re-lock with
`python -m study.protocol_lock --accept`. Append, never edit.

### A1. US units, plain names for the two gates, and site selection restored

FMVSS 127 is a US standard, so the study reports in **mph, feet and g**. Speeds become
25 mph and 50 mph, the trench plate becomes 8 x 12 ft x 1 in, distances are in feet. Where
the standard states a number in metric its own value is quoted alongside, so nothing is
lost in conversion.

"Gate A" and "Gate F" are renamed to **the capture check** and **the in-between check**.
They were jargon that had to be looked up, in a document whose whole job is to be read.

Section 12, site selection, was in the draft and was lost when it was frozen. Restored,
including the criteria M1 is measured against and the hero-tag warning. This is the
mechanism working as intended: the omission surfaced the first time the file was edited.

Nothing about the design, the cells or the expectations changed.

### A2. Posted speed limits are not a site criterion

CARLA's declared limits are inconsistent between maps, and we command both the ego speed
and other vehicles' speeds directly, so a road's posted number does not constrain the
speed we can test on it. Section 12 now selects sites on geometry alone and records the
posted limit for description only.

The map choice was re-checked without that criterion and does not change. Town13 leads on
pedestrian sites, 401 against 303 for Town12 and 133 for Town11, and is second on braking
sites, 367 against Town11's 392. It was already the leader on geometry; speed coverage was
a supporting argument, not the deciding one.

Nothing about the design, the cells or the expectations changed.

### A3. The map moves from Town13 to Town01, on measurement

Town13 was chosen in M1 on geometry read from the OpenDRIVE, without a simulator. With the
simulator it does not work on this hardware, and the numbers are not marginal.

Same probe, same 140 ticks per cycle, rendering off (`tools/probe_memory.py`):

| | Town13 | Town01 |
|---|---|---|
| tick rate | did not finish one cycle in 231 s, so under 0.6 ticks/s | **720 to 760 ticks/s** |
| server memory over 6 cycles | see below | flat at 3.2 GB, slightly falling |
| loaded footprint | 14 to 15 GB | 3.2 to 6.4 GB |

Two crashes on Town13 before that, both the renderer rather than the physics:

- **OOM killed at 58 GB resident** during a spawn, settle, brake, destroy loop, on a 64 GB
  machine.
- **Segfault** with `GameThread timed out waiting for RenderThread after 60.00 secs`, at
  only 15 GB.

The ego was tagged `role_name='hero'` throughout, so this is not the known large-map
dormancy crash. A smoke test on Town13 passes; it is sustained work that kills it. The
hardware is an RTX 4070 with 12 GB, and the 5090 is not here yet.

Speed settles it even setting the crashes aside: at under 0.6 ticks/s the twenty-run
braking measurement alone is about two hours, and the full study is out of reach.

**Town01 instead.** The site requirement that ruled the standard towns out was wrong. It
assumed the ego accelerates up to test speed, and section 1 launches it at cruise speed.
Corrected to settle distance plus `r_req`, about 310 ft at 50 mph, Town01 offers 9
pedestrian sites and 7 braking sites with a 1,007 ft longest straight. Fewer than Town13
claimed, and enough: the study needs one site per scenario.

Nothing about the claim, the cells or the expectations changes. This is where the study
runs, not what it tests.

### A4. Capture requirements for the disturbance endpoints, all measured

The family interpolates absolute pixel values between a daylight frame and a darkness
frame at an identical pose. Three things have to be true for those endpoints to mean
anything, and none of them is the default. All three were found by capturing lighting
that came out backwards, with headlamps apparently making the road darker.

**1. Scene lighting must be allowed to settle after a sun change: 120 ticks.** Measured on
Town01, switching from day to night with the lamps off, mean image brightness against
ticks since the change:

| ticks | 1 | 12 | 20 | 40 | 80 | 150 | 400 |
|---|---|---|---|---|---|---|---|
| mean | 104.0 | 74.4 | 60.1 | 45.2 | 42.6 | 42.6 | 42.5 |

Settled value is 42.5. A capture 12 ticks after the change reads **75 percent too bright**.
Twelve ticks is what "weather applies on the next tick, so drain a few frames" leads you
to, and it is not enough by an order of magnitude. 120 is used, with margin over the
measured 80.

**2. The camera must use fixed exposure.** CARLA's default `exposure_mode` is `histogram`,
which is auto-exposure. This lab has published that ACDC is unusable partly because it is
auto-exposed and absolute photometry is gone; the same objection applies to our own
captures, and more sharply, because the family interpolates absolute values. Cameras are
built with `exposure_mode=manual` and fixed shutter, iso and fstop.

**3. Frames are matched on the id `world.tick()` returns, and a missing frame is an
error.** A `except queue.Empty: pass` leaves the queue one frame ahead, and every image
after it belongs to the previous condition. Already in this repository's notes; still
written, still cost a full set of captures.

With all three in place the captures are physical, dark < low beam < high beam at every
site, where before they were monotonically backwards.

**Site lighting, resolved.** Section 12 asks for lit and unlit stretches and says the
survey cannot answer it. Measured at night with the lamps off: site 1 (758 ft) reads 4.5
and is effectively unlit, site 3 (736 ft) reads 25.7 and is lit. Both are available.

Nothing about the claim, the cells or the expectations changes.

### A5. The in-between check FAILS over the full interval, and why

This is the first result that bears on whether the family in section 4 is sound, and it
is negative over the interval as declared.

**Over the full daylight-to-darkness interval the blend is wrong by 0.243 of full range
at the midpoint.** That is a quarter of the dynamic range, not a rounding error. The
recorded repair in section 4 is shorter intervals with rendered interior endpoints, and
that repair works, but not for the reason it was written down.

**Width is not the variable. Position is.** Holding the width at 11.25 degrees of sun
altitude and moving the interval:

| centre | +50 | +35 | +20 | **+5** | -10 | -25 |
|---|---|---|---|---|---|---|
| blend error | 0.0025 | 0.0034 | 0.0058 | **0.1527** | 0.0076 | 0.0071 |

Only the interval crossing the horizon fails, by twenty to sixty times. The 90 and 45
degree intervals failed because they span sunrise, not because they are wide.

**The cause is curvature, concentrated at the horizon.** Mean brightness against sun
altitude: 179.7 at +6, 151.1 at +3, 120.3 at +1.5, 96.4 at +0.75, 79.5 at 0, 74.8 at
-0.75, 70.4 at -1.5, 62.7 at -3, 57.7 at -6. Steep above, shallow below, so the second
derivative peaks right where the sun sets. A linear blend is exactly a second-order
approximation, so it fails precisely there.

**Shrinking helps but does not fully rescue the twilight band.** Intervals straddling
zero: 0.1083 at 6 degrees wide, 0.0646 at 3, 0.0368 at 1.5, 0.0298 at 0.75. It flattens
out near 0.03 rather than going to zero, which suggests a genuine kink at the horizon and
not merely curvature.

**Consequences for the study.**

- The daylight-to-darkness axis may not be one blended interval. It is composed of
  sub-intervals, split at the horizon.
- Away from roughly -3 to +12 degrees, an 11 degree sub-interval blends to within 0.008
  and needs no special care.
- Inside that band the sub-intervals must be short, and even then about 0.03 of error
  remains at the horizon itself. That band is dusk, which is exactly the untested region
  the study's claim is about, so this is on the critical path rather than off it.
- **This is image space.** Section 4 is explicit that the check which decides is
  behavioural. A 0.03 image error may or may not move a policy's output, and that is not
  knowable until there is a policy. Recorded now because it changes how the family is
  built, and building it wrong first would waste the training.

Measured with `tools/interval_sweep.py`; raw numbers in
`results/carla/interval_sweep.json`.
