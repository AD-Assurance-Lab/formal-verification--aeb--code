# PROTOCOL.md - the frozen study design

**This file is locked.** `python -m study.protocol_lock` fails if anything above the
Amendments section changes without a recorded amendment. Tagged `protocol-v1`.

It exists because study logic in this lab has been lost twice, and because many
sub-experiments will run before this one finishes. When a result and this file disagree
about what the study is, **this file is right**. Findings go in `FINDINGS.md`, current
belief goes in `CLAUDE.md` (A18), and neither may quietly redefine the design.

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
| **Repetitions** | Every closed-loop number is a verdict over at least 3 repetitions, each in its own process against its own freshly restarted server, reported with its margin. Repetitions that disagree make the cell VOID. Never a single run, and never a rate over repetitions sharing a server. See A13. |

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

**Closed-loop pass:** no contact and standoff at least `d_margin`, over at least 3
repetitions under the harness section 3 requires (A13).

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
| M2 | Harness and primitives | `a_max` and `t_lat` over >= 3 reps; contact detector validated against a deliberate collision; a perfect oracle passes every rep and a deliberately late one fails every rep |
| M3 | Expert and collection | The oracle passes every rep with standoff >= `d_margin` at both endpoints |
| M4 | Two policies | **Both policies pass both endpoints on every repetition, on both hazard scenarios.** If `P_pts` cannot pass the regulatory tests there is no story |
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
  `r_req`. **The requirement is read from the drivers, not quoted here**, because it has
  already gone stale twice: the 310 ft this line used to carry was computed from the
  pre-A12 `a_max`, and the false-activation approach actually asks `site_transform` for
  320 m of junction-free lane. See A14
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

**Large maps were not usable on the hardware A3 measured, and are usable on this one.** The
hero tag is still required and still not sufficient. A3 moved the study to Town01 on an
RTX 4070 with 12 GB; A14 moves it to Town12 on an RTX 5090 with 32 GB, on the same probe.
Read both, in that order: the first is why a large map was abandoned and the second is what
changed.

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

### A6. The illumination axis, as measured: 11 sub-intervals and one uncovered sliver

A5 said the axis must be cut. This is where, measured by bisecting for the largest step
whose midpoint blend stays within 0.01 of the render (`tools/build_family_knots.py`,
113 renders).

| from | to | step, deg | blend error |
|---|---|---|---|
| 60.00 | 29.75 | 30.25 | 0.0098 |
| 29.75 | 13.25 | 16.50 | 0.0099 |
| 13.25 | 6.18 | 7.08 | 0.0093 |
| 6.18 | 3.73 | 2.45 | 0.0096 |
| 3.73 | 2.02 | 1.71 | 0.0094 |
| 2.02 | 0.81 | 1.21 | 0.0097 |
| 0.81 | 0.14 | 0.66 | 0.0100 |
| **0.14** | **0.00** | **0.14** | **0.0386** |
| 0.00 | -3.73 | 3.73 | 0.0094 |
| -3.73 | -29.60 | 25.87 | 0.0087 |
| -29.60 | -30.00 | 0.40 | 0.0070 |

The step size collapses by more than two orders of magnitude approaching the horizon,
30.25 degrees at the top and 0.14 degrees at the bottom, then opens straight back up to
25.87 once past it. That shape is the curvature result from A5 stated quantitatively.

**One sub-interval cannot meet tolerance at any width.** The last approach step, 0.14
degrees wide, still errs at 0.0386, four times the tolerance and consistent with the
floor A5 measured. This settles the open question in A5: the horizon is a genuine
discontinuity in the renderer's sky model, not merely a region of high curvature, and no
step size fixes it.

**Consequences.**

- The certified axis is the union of the ten sub-intervals that meet tolerance. The
  sliver from 0.14 to 0.00 degrees of sun altitude is **declared uncovered**, and the
  paper must say so rather than quietly spanning it.
- Verification cost multiplies by the number of sub-intervals. Each is still a
  one-dimensional set, so branch and bound remains cheap, but the accounting in the
  cost section is per sub-interval and not per condition.
- Training endpoints are these knots. Rendering them once and reusing them is why this
  was measured before M3 rather than after.

Raw numbers in `results/carla/family_knots.json`.

### A7. The exposure value, and what range means for a crossing pedestrian

Both found by LOOKING at a captured frame. The statistics had said the captures were
fine.

**Exposure: f/4.0, shutter 200, ISO 100.** A4 required fixed exposure but did not pin
the values, and CARLA's defaults were kept. They are about six stops too fast for a
sunlit scene: daylight came out at mean 225 with a 5th percentile of 137, so the entire
image sat in the top 40 percent of the range and the road markings were washed out.
Swept f/1.4 through f/16:

| f-stop | 1.4 | 4.0 | 8.0 | 11 | 16 |
|---|---|---|---|---|---|
| daylight mean | 225 | **129** | 58 | 32 | 11 |
| 5th percentile | 137 | 22 | 0 | 0 | 0 |

f/4.0 uses the full range with no clipping, and night stays properly dark at mean 8 with
the target lit by the headlamps, which is the case the standard is about. A fixed
exposure cannot serve both ends of the axis equally, and it should not: that difference
is the disturbance.

**Range, for the crossing pedestrian, is to the CONFLICT POINT.** It was being measured
as the straight-line gap to the walker, which includes their lateral offset. So at a
recorded "range 10.6 m" the ego was 8.7 m from the crossing point while the walker was
still 6 m off to the side, which is plainly visible in the frame. Section 7 says range to
the conflict point, and the labels and the brake trigger now use that. The lead-vehicle
case is unaffected: a stationary lead sits on the ego's line, so the two are the same
quantity.

**Consequence.** Every capture taken before this is discarded and retaken. Roughly an
hour of simulator time, against training a policy on washed-out frames labelled against
the wrong range.

### A8. Network input size: 128 x 96, measured

Section 1 left the input size open, to be fixed and recorded. Measured against a
no-target control at the same poses, so every difference IS the target
(`tools/choose_input_size.py`):

| input | peak diff at r_req | px over 20 | peak diff at 60 m |
|---|---|---|---|
| 64 x 48 | 138.8 | 152 | 26.6 |
| 100 x 66 | 144.3 | 331 | 45.5 |
| **128 x 96** | **155.4** | **625** | **57.1** |
| 200 x 150 | 162.0 | 1613 | 87.9 |
| 320 x 240 | 165.2 | 4177 | 98.8 |

At `r_req` the target is resolvable at every candidate, peak 139 to 165 out of 255, so
that alone does not choose. What separates them is long range: the policy has to *not*
brake at 60 m as well as brake at 10.6, and the target's signature there falls from 99 to
27 as the input shrinks.

**128 x 96** keeps a peak of 57 at 60 m, five times the smallest input's margin over
nothing, and it is the size already proven tractable for the verifier: alpha-CROWN bounds
it in 13 s per pose using 1.66 GB, measured in `results/carla/verifier_feasibility.json`.
Larger inputs buy a stronger long-range signature at a cost in ReLU neurons that the
verifier pays on every pose of every cell.

Two earlier attempts at this measurement were wrong and are recorded so the method is not
repeated: comparing the near frame against a FAR frame (they differ everywhere, ratio
1.19 at every size), and comparing means over the whole image (dominated by what fraction
of the frame the target occupies, flat at every size). The peak difference against a
no-target control at the same pose is the question actually being asked.

### A9. The crossing pedestrian has to be in the path before r_req

Measured from the saved poses, not eyeballed. Timed to meet the ego at the conflict
point, the walker was still **1.70 m to the side at the closest captured pose**, outside
a vehicle whose half-width is 0.9 m. No run could have hit them, so no run was a
pedestrian test, and a policy that never braked at all would have scored a clean pass.

`r_req` is the last moment braking can still succeed, so a hazard that arrives after it
is not one the system could ever have avoided. The walker is now released early enough to
be in the path before then. Measured, varying the head start beyond `r_req`:

| head start | walker in path from | verdict |
|---|---|---|
| 0 m | 8.98 m | too late, after `r_req` = 10.57 |
| 4 m | 13.45 m | clears it by 2.9 m |
| **8 m** | **17.36 m** | clears it by 6.8 m, about 0.6 s |
| 12 m | 21.27 m | |

**8 m is used.** Four metres only just clears `r_req`, which would make the cell a test of
reaction latency rather than of whether the policy can see a pedestrian under a given
illumination, and seeing is what the study is about. Twelve gives the policy more time
than the hazard warrants.

This is a scenario parameter, declared here, and it is the same for both policies. It is
not tuned per policy and must never be.

### A10. Training must include the no-target case, or the policy learns position

Found by verifying property A, which is what property A is for.

With **nothing in front of it**, both policies command substantial braking at short range:

| range | P_pts, target | P_pts, none | P_cont, target | P_cont, none |
|---|---|---|---|---|
| 10.2 m | 8.19 | **4.51** | 8.16 | **5.08** |
| 6.9 m | 8.51 | **3.63** | 8.03 | **4.81** |
| 2.4 m | 8.39 | **2.79** | 8.32 | **4.96** |

The latch threshold is 4.26, so `P_cont` would brake on an empty road.

**The cause is the capture design, not the policies.** In the lead captures the target is
present at every pose, so "a target is there" and "the ego is near the conflict point" are
perfectly correlated. A network can fit the labels by learning position from scene cues,
the road geometry and the buildings, without ever looking at the car. Training rewarded
that and nothing penalised it.

**Consequence for what has been measured.** The certificate still predicted driving
correctly, so the METHOD result stands: verdicts committed before driving agreed 10/11 for
`P_pts`. But the claim those policies support is weaker than it appeared. A failure at
twilight may be the position cues degrading rather than the vehicle becoming invisible,
and the two cannot be separated with policies trained this way.

**The fix, using data already captured.** The `none` scenario replays the identical poses
with no target and is already captured at all 12 knots. Those frames enter training with
label 0 at every range, which makes position uninformative and forces the target to carry
the decision. Retrain, re-verify, re-drive.

**The general lesson.** Property A is not a secondary nicety next to property S. Here it
was the only thing that could detect that the policy was not solving the task at all, and
a study that verified only "does it brake in time" would have reported a clean result
about a position detector.

### A11. Property S certifies the brake DECISION threshold, not a_max, and the composition still closes

Section 7 states property S as "the certified lower bound on commanded deceleration is
at least `a_max`". The implementation (`tools/verify.py`, since M6) certifies against
the brake decision threshold instead: `a_max * 0.5`, the same latch threshold
`tools/run_policy.py` drives with. Every committed verdict in `verify_*.json` is a
certificate of that property. This amendment records the substitution rather than
leaving it as drift between the frozen text and the instrument; a 2026-08-25 audit
surfaced it as an unrecorded spec change.

**Why the certified property is the right one.** The closed loop latches: when the
commanded deceleration crosses the decision threshold, braking is commanded at full
authority and is never withdrawn (section 1). So the network's continuous output only
ever answers one question — brake or not yet — and the deceleration the vehicle then
achieves is the measured `a_max` of the platform, not the network's output value.
Requiring the certified lower bound to clear `a_max` itself would demand the network
COMMAND a number the vehicle supplies physically, a property the closed loop never
uses. The stopping-distance composition in section 7 closes exactly as written: latch
inside `r_req` at full authority is what `r_req` was derived from.

**What is given up.** A certificate at the latch threshold says braking WILL be
commanded, not that the commanded magnitude is calibrated. That is the honest
property for a latching controller, and it is the one the witness drives tested:
10/11 and 9/11 agreement are agreements about this property.

**The threshold is not tuned.** 0.5 was set in M2 with the latch design, before any
policy existed (`run_policy.py`: the observed command distribution is bimodal, and a
0.5 m/s^2 threshold latched on noise at 375 ft). It is the same constant for both
policies and both properties' harnesses, and property A's 0.25 g limit is unchanged —
it comes from the standard.

Nothing about the cells, the expectations, or any committed verdict changes; this
records what the committed verdicts already mean.

### A12. The simulator harness was wrong; every measured artifact is rebuilt

**Date:** 2026-08-30. **Requested by:** Zach, after the same correction in the steering study.

**What changed.** Nothing in the study DESIGN. The sections above are untouched: the
scenarios, the properties, the ledger, the gates and the primitives' definitions all
stand. What changed is the instrument, and every artifact this study produced by
*measuring* is discarded and rebuilt: the primitives, both policies, the capture campaign,
the verification verdicts, and the witness drives.

**Why.** Two defects in the CARLA harness, measured open loop in
`formal-verification--steering--code` (T06-F22) and now packaged as `carla-determinism`:

1. **`apply_control` is fire-and-forget and races `world.tick()`.** Synchronous mode
   synchronises the tick, not the command queue feeding it. The race is invisible while a
   command is unchanged, so it bites only on a step where the command CHANGES -- which for
   a braking policy is every step that matters. Measured with the feedback cut and an
   identical scripted command sequence, three repetitions finished 60 m apart. This study
   used the raw call at 16 sites.
2. **UE4 streams texture mips asynchronously**, so which mip is resident when a frame
   renders depends on load timing rather than on world state. `-notexturestreaming` cut the
   steering noise the renderer injects by 168x. This study never passed the flag.

Rule D-11 follows: data captured under a violating harness is not reusable. **It bites
hardest here of the three studies.** This study's central claim is a falsified band
BETWEEN two rendered illuminations, and the texture-streaming defect changes precisely the
frames that claim is computed from.

**What is NOT affected.** `PROTOCOL.md` above this line, and therefore the lock. The map
survey (M1) is offline geometry and stands. The committed verdicts remain in git history
at `ea1700c` and are not rewritten -- they are superseded, and the comparison between old
and rebuilt numbers is itself worth recording.

**The blind ordering survives, and must be preserved.** M7's witness drives for the
pedestrian cells had not been run, and the lead cells' were. Both are discarded. The
rebuilt sequence is unchanged: verify, commit the verdicts, then drive. A rebuilt verdict
is a prediction only if it is committed before its rebuilt witness.

**What this does not relax.** Every closed-loop number remains a rate over repetitions.
Bit-exact closed-loop replay is unreachable even on the corrected harness
(`carla-determinism` D-7: a scene where nothing moves still renders ~30 differing pixels
per frame across repetitions), so the corrections shrink the noise and name its source;
they do not remove it.

### A13. The repetition count: three, each on its own server, and a disagreement is void

**Date:** 2026-09-09. **Requested by:** Zach, on the grounds that the determinism package
has worked in the sibling steering study. **Measured here before adopting**, because the
steering result is about a lane-keeper on a lap and this is a braking policy on a discrete
approach, and the two have no reason to share a floor.

**What changed.** Section 3's repetition line, section 7's closed-loop pass, and the M2,
M3 and M4 exit criteria. Ten repetitions with Wilson intervals becomes three repetitions,
each in its own process against its own freshly restarted server, reported with the
margin, with disagreement making a cell void.

**What did NOT change.** No scenario, property, ledger cell, gate, primitive or criterion.
No already-collected number is rescored or reinterpreted: everything measured before this
date stands as collected, on the harness it was collected on, and the artifacts record
that harness. This amendment governs what is measured next.

**Why, in one line.** The repetitions were never estimating a rate, and ten of them
sharing a server are worse than three that do not.

The evidence is F22 and F23. Of 281 committed ten-repetition cells, 277 are unanimous and
4 are split. Every one of the four was re-driven with a stopped server, a fresh launch
through the determinism preflight, a new process, a new client, a new vehicle and a new
camera before every repetition, with two unanimous controls beside them. Two of the four
were an instrument defect (F21). One was the simulator moving underneath the measurement:
CARLA's cloud layer moves under fixed weather, so scene brightness at the horizon drifts
3.9% with elapsed simulated time, and repetitions inside one server sample further along
that curve the more of them you run (F23). The fourth is the policy sitting on its own
brake threshold, and it stays split on the clean harness, which under the standing rule
makes it void rather than a 20% failure rate.

Under the per-repetition restart, repetitions of a cell are identical to the recorded
precision, not merely close. So the repetition count buys DETECTION of a split rather than
precision on a rate, and a Wilson interval over three such repetitions would be an
interval on nothing.

**The conditions are not optional, and where they do not hold the answer is ten.** A clean
server restart before EVERY repetition; one process per repetition; a fresh vehicle and
camera per repetition; the determinism preflight green on each fresh server; one client
per port; and the harness recorded in the artifact. `tools/drive_witness.py --rep-index`
with `tools/merge_witness_reps.py` is the supported path; anything that drives repetitions
in a loop inside one process is the harness this amendment replaces and keeps the old
floor.

**What this does not fix, and must not be read as fixing.** F23's cloud modulation is
still there. Three repetitions on three fresh servers agree with each other because they
all sample the SAME early point of that curve, which makes them reproducible and does not
make them representative. Controlling it means either `cloudiness = 0` or a settle long
enough plus a photometric check on every capture and drive, and both change what the
conditions ARE. That is a design change, it needs its own amendment, and it is not made
here.

**Resolves** the conflict `CARLA_DETERMINISM_PENDING.md` records between D-7's
ten-repetition floor and the steering study's A-4, **for this repository only**. D-7's
measurement — that a frozen scene never renders bit-identically — is not disputed and is
not amended. What is disputed is the inference from it to a repetition floor, on the
grounds that verdict stability rather than frame identity is what the floor protected, and
that is now measured here. The package is hash-locked and lab-wide; changing D-7 needs its
section 4 procedure and is Zach's call.

### A14. The map moves from Town01 to Town12, on the same probe A3 used

**Date:** 2026-09-09. **Requested by:** Zach: the machine handles the large maps now, and
they carry more scenario options. **Measured before adopting**, with `tools/probe_memory.py`
at A3's own settings — 6 cycles, 140 ticks each, spawn/tick/destroy — because A3 is the
amendment being reversed and it deserves its own instrument.

| map | ticks/s, render off | ticks/s, render on | server memory | growth/cycle | restart to usable |
|---|---|---|---|---|---|
| Town01 | 1,418 | 444 | 3.1–3.2 GB | none | 17 s |
| **Town12** | **26.5** | **26.5** | **7.0–7.4 GB** | **none** | **29 s** |
| Town13 | 2.0 | 3.0 | 12.1–12.3 GB | +0.022 GB | 46 s |

**A3's crashes are gone.** Town13 ran six cycles flat at 12 GB with no OOM and no
RenderThread timeout, against A3's OOM kill at 58 GB resident and a segfault at 15 GB. The
hardware was the whole of that problem. What survives is throughput: Town13 is still 150x
slower than Town01 and nine times slower than Town12, and it is the only map of the three
still growing. **Town12 is the large map that is actually usable**, and Town11 has a longer
straight but a fifth of Town12's flat sites.

**And the site requirement is why this is not merely a convenience.** Re-filtering the
committed survey against what the drivers actually demand — `plate_run` asks
`site_transform` for 320 m (1,050 ft) of junction-free lane at 50 mph, `one_run` for 200 m
(656 ft) at 25 mph, both on flat road:

| map | flat sites | qualifying for the plate | qualifying for the pedestrian | longest flat straight |
|---|---|---|---|---|
| **Town01** | 9 | **0** | 5 | 1,007 ft |
| Town12 | 311 | 30 | 113 | 5,226 ft |
| Town13 | 292 | 36 | 62 | 5,077 ft |

**Town01 has no site that meets the false-activation scenario's own stated requirement.**
Its longest flat straight is 1,007 ft against the 1,050 ft the driver asks for, and the
runs complete only because `usable_run_m` measures junction-free LANE, which is a weaker
criterion than the surveyed STRAIGHT and can continue into curve. Nothing is asserted to be
wrong on that account — the driven portion, 10 m to 210 m, is inside the straight — but
cells 5 and 6 have been running with no margin on a criterion the study wrote for itself,
which is the class of defect standing rule 7 exists for.

**What this costs.** Every measured artifact. Primitives, expert, captures, all three
policies, both gates, every certificate and every drive are Town01 measurements and none of
them transfers: the disturbance family is built from frames captured at poses on a specific
road. This is an A12-scale rebuild and it is entered deliberately, not discovered halfway
through.

**What it does not change.** The claim, the properties, the ledger cells, the criterion,
the primitives' definitions, or the expectations. Where the study runs, not what it tests —
the same sentence A3 ends on.

**Ordering that follows from it, and is not optional.** F23 is undecided and the whole
capture campaign is about to be re-run. Deciding `cloudiness` AFTER recapturing means
capturing twice, so F23's decision comes first and is now nearly free. Likewise the
false-activation instrumentation gap in FINDINGS F22 is fixed before the plate is driven
again, or the rebuild reproduces an invisible failure mode on a new map.

### A15. Cloud cover goes to zero, because a fixed weather was not a static scene

**Date:** 2026-09-09. **Requested by:** the measurement, and taken now because A14 is about
to re-run every capture and deciding this afterwards means capturing twice.

**What changed.** Every driver set `cloudiness = 10.0` beside the sun altitude. It is now a
single constant, `carla_jobs.CLOUDINESS`, and its value is **0.0**. Nothing else about the
conditions changes: the sun-altitude axis, the headlamp states, the three regulatory
lighting conditions and the endpoints are all as section 2 defines them.

**Why.** FINDINGS F23. CARLA's cloud layer moves even though the weather parameters are
held fixed, so "the same illumination" is a function of elapsed simulated time. Measured
with the vehicle held on the brake, camera rigid, exposure pinned manually and nothing else
in the world, on both maps, at three altitudes, 3,000 ticks each. The lighting transient
after `set_weather` is over by about tick 120, so the existing settle is adequate and is
not changed. What is left after it is the cloud wander:

| | residual after the settle, cloudiness 10.0 | cloudiness 0.0 |
|---|---|---|
| Town12, +0.403° | 0.00076 | **0.00035** |
| Town12, +0.013° | 0.00062 | **0.00031** |
| Town12, +51.383° (daylight) | 0.00048 | 0.00048 |
| Town01, +0.403° | 0.00038 | **0.00019** |

**The clouds double the residual at the horizon and change nothing in daylight**, and the
horizon is where every interesting cell in this study lives. On Town01 that wander was
enough to move a policy across its brake threshold: the same sub-interval produced eight
pedestrian contacts on a warm server and none at all on ten fresh ones (F22).

**What it costs.** Nothing that A14 was not already spending. Every capture is being redone
for the map move, so this is free now and would have cost the whole campaign twice later.
That is the entire reason it is decided today rather than after the rebuild.

**What it narrows.** The ODD. `cloudiness = 0` is a clear sky, where 10.0 was a nearly
clear one, and the study should say so rather than imply cloud cover was tested. FMVSS 127
does not specify cloud cover, and the disturbance family is parameterised on sun altitude,
so removing an uncontrolled second illumination variable makes the axis the thing the
family claims it is. Cloud cover as a disturbance axis in its own right is journal work,
and it would need the family rebuilt around it.

**What it does not fix.** The residual at the horizon is halved, not removed: 0.00035 at
+0.403° on Town12 is still there and is still unmodelled. It is now small enough to sit
below the transient, and it is recorded here so that a future cell sitting on a knife edge
is read against a known floor rather than against an assumption of zero.

### A16. Capture darkest first, because the dark end remembers the light

**Date:** 2026-09-09. **Requested by:** the measurement, during the A14 rebuild's capture
stage, which stopped on the illumination check rather than producing this quietly.

**What changed.** `capture_campaign` renders the knots in ascending sun altitude whatever
order it is handed, and reorders the manifest back to the axis's own direction before
anything reads it. Nothing else: not the knots, not the conditions, not the endpoints, not
the scenarios.

**Why.** FINDINGS F28. At the same site, pose, camera, exposure, lights and weather, the
−30° darkness knot renders at **0.0036** on a scene that has never been bright and
**0.0342** when a bright knot was captured before it in the same server session — 9.4x —
and it does not decay: 4,200 ticks of daylight, then 6,000 ticks of night, and it is still
0.0342. The scene has two stable states for one weather and capture order picks between
them.

Darkness is one of the two endpoints the disturbance family is built between and one of the
three lighting conditions FMVSS 127 tests. A study whose endpoint frame depends on how many
knots preceded it does not control its own independent variable.

**Why ordering rather than a fresh server per knot.** Both work and they agree — 0.00360
ordered against 0.00362 on a fresh server. Ordering is free; a server per knot is about
four and a half hours of recapture per campaign set. Bright knots are insensitive to what
preceded them (+60° reads 0.37177 after darkness against 0.37138 after a full descending
sweep), so ascending order costs the bright end nothing.

**Which state is correct.** Neither is more physically faithful — a night scene is not
brighter for having been day earlier. What decides it is that 0.0036 is reproducible from a
defined initial condition and 0.0342 depends on the number of preceding knots, their pose
counts and the machine's speed. That is the same argument A13 made about repetitions:
prefer the measurement that is a function of the condition.

**What it invalidates.** Every capture taken in descending order, which is every capture
this study has ever made, on both maps. The Town12 set is discarded and recaptured under
this amendment. The Town01 set stays where it is, behind `town01-final`, unexamined for this
effect and not to be reused.

**It also repairs a guard rather than relaxing one.** With the dark knot clean the upper
beam reads 0.0095 against the lower beam's 0.0036, so amendment A4's check — more light in
the same scene cannot darken it — passes for the reason it was written for. The check was
correct; the frame it was reading was not.

### A17. A16 was half a fix: the nominal run drives in daylight before any knot is captured

**Date:** 2026-09-09, an hour after A16. **Requested by:** the measurement that A16's own
change failed to produce.

**Why this is a new entry and not an edit to A16.** Amendments are append-only and
`study.protocol_lock` refused the edit, which is the guard doing its job. A16 is left
exactly as it was written, including the part of it that turned out to be insufficient.

**What A16 got right.** Capture darkest first. No knot is then preceded by a brighter one,
and bright knots are insensitive to what came before them.

**What it missed.** Ordering the knots is necessary and not sufficient. `nominal_states`
**drives the scenario to record its poses before any knot is captured**, and CARLA starts a
session in daylight, so the nominal run charges the scene exactly as a bright knot does.
Measured: with A16's ordering in place and nothing else, the `lead` campaign still captured
−30° at **0.0341**, the contaminated value.

It looked correct in testing because the campaigns used to check it were `none`, which
replays saved poses and never drives. The scenario that drives is the one that breaks it.

**What changed.** `capture()` sets the weather to `min(knots)` before the nominal run and
before the state loop, so the session is never brighter than the darkest thing it is about
to capture. With both halves in place the `lead` campaign captures −30° at **0.0036** and
+60° at 0.3718, matching every other measurement of that knot.

**And it removes the argument for the expensive alternative.** A16 preferred ordering over a
fresh server per knot on cost. That comparison was wrong in the same way: a fresh server
also starts in daylight and would have needed the darkening step too, so it never bought
anything ordering does not.

### A18. The working notes are consolidated into `CLAUDE.md`

**Documentation only. No measurement, no criterion and no procedure changes.** It is
recorded as an amendment because the sentence it edits sits in the frozen part of this
file, and the only sanctioned way to edit that is here.

**What changed.** Section 0 said current belief goes in `docs/STATE_OF_PLAY.md`. Eleven
working notes files, 1,891 lines, were rewritten in Simplified Technical English and
consolidated into `CLAUDE.md`. One file is kept, `docs/ARXIV_NOTES.md`, for the paper
repository. The originals are in `stale/notes_folded_into_claude_2026-09-10/` and in git
history.

So current belief now goes in `CLAUDE.md`, and live numbers come from
`python -m study.status`, which reads the artifacts rather than any prose.

**Why an amendment rather than a stub.** A rule that names a missing file fails in exactly
the way a satisfied rule looks. This repository has written that down four times. Leaving
`docs/STATE_OF_PLAY.md` as a redirect would keep section 0 literally true and make it
misleading, which is the same defect wearing a better hat.
