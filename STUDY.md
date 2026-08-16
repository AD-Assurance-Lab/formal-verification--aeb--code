# STUDY.md - the experimental design and the ledger

Read this before writing code. The design is the first artifact.

## The claim

> FMVSS 127 tests a finite set of discrete points. A certificate covers the continuum
> between them.

Concretely: given two trained AEB policies and no simulation, formal verification says which
regulatory lighting conditions each one is safe in, and closed-loop testing in CARLA then
agrees.

## The study in four steps

1. **Train two policies.** `P_day` on daylight only. `P_lit` across the regulatory lighting
   set (daylight, darkness lower beam, darkness upper beam).
2. **Distill both into formally verifiable students.** ReLU-only, no BatchNorm or Dropout.
   The teacher is a distillation source and is never verified.
3. **Closed-loop test both** on the FMVSS scenario set. `P_day` should fail the darkness
   conditions it never saw. `P_lit` should pass.
4. **Verify both and get the same answer without simulating.** Verdicts are committed to git
   before the corresponding closed-loop run.

**Step 4 is the contribution.** Steps 1 to 3 are infrastructure. An adequate braking policy
is enough; the claim is that verification predicts closed loop, not that our AEB is good.

## Regulatory grounding

FMVSS No. 127, compliance 1 September 2029 (2030 small volume). What the standard gives us,
and what we therefore do not have to invent:

| From the standard | How it enters the study |
|---|---|
| Pedestrian scenarios: crossing, stationary in path, walking along path | Scenario S1 |
| Lead vehicle: stopped, decelerating, slower moving | Scenario S2 (stopped) |
| **False activation: steel trench plate, pass-through** | Scenario S3. Must-not-brake is a requirement, not an extra |
| Darkness tested with **lower and upper beam** | The lighting axis |
| Stationary pedestrian 10 to 55 km/h, along-path 10 to 65 km/h | The speed sweep in iteration 2 |

## The disturbance family

Both endpoints are **rendered in the simulator at an identical camera pose**, then
interpolated:

```
x_p(s) = x_p^daylight + s ( x_p^darkness - x_p^daylight ),   s in [0,1]
```

Endpoints are two regulatory test conditions. Interior `s` is illumination the standard never
tests. **Do not build the disturbance from an analytic photometric model.** That route was
measured and failed: an analytic fog model scored R-squared 0.848 on image fidelity and drove
one policy 23.8 times harder than the real rendered condition.

The family enters the network as a prepended `nn.Linear` mapping the scalar `s` to flattened
pixels, which keeps bound propagation in `patches` mode.

## Safety budget

Every term measured in CARLA, none fitted, none modelled.

```
r_req  =  v (t_lat + dt)  +  v^2 / (2 a_max)  +  d_margin
```

- `a_max` worst measured average deceleration over >= 10 full-brake stops. Measuring it
  rather than modelling it is what removes the aerodynamic-drag question: the measurement
  already contains drag at that speed, and neglecting drag analytically is conservative for
  stopping distance in any case.
- `t_lat` measured brake-command to deceleration onset.
- `dt` control period. **20 Hz**, giving 0.83 m of quantization at 60 km/h.
- `d_margin` required standoff at rest.

Iteration 1 runs at **40 km/h**, inside every FMVSS pedestrian band.

## The two properties

**S, must brake.** For all `s` in [0,1] and all poses with range to the conflict point
<= `r_req`, the certified **lower** bound on commanded deceleration is >= `a_max`.

**A, must not brake.** On the false-activation scenarios, for all `s`, the certified
**upper** bound on commanded deceleration is <= **0.25 g (2.45 m/s^2)**. That threshold is
the standard's own, not one we chose. The steel trench plate is ASTM A36, 2.4 x 3.7 m x
25 mm, approached in lane at **80 km/h**, so the false-activation cells run at that speed
rather than at 40.

Both are pointwise conjunctions over a window the hazard geometry defines. Neither is a mean
nor a lap maximum.

**Why the composition is closed form.** Once braking is commanded the network is out of the
loop, so the certificate composes into standoff distance analytically. Nothing integrates
network output over time, so nothing accumulates capture error.

## Closed-loop pass criterion

No contact, and standoff >= `d_margin`, over >= 10 repetitions. Report Wilson intervals.

**Contact is inferred from bounding-box separation and kinematics, never from
`sensor.other.collision`.** Measured elsewhere in this lab: a vehicle driven into a
stationary car at 19 m/s ended 2.49 m inside a body whose contact distance is 6.06 m, and the
collision sensor reported zero events. Using it here would report that AEB never collides, in
every cell.

---

# The ledger: pre-registered expectations

**A measured cell that contradicts its expectation is a bug until proven otherwise.** It may
not be written up as a finding until a written disposition lists the candidate causes ruled
out.

Iteration 1. Two policies, one site. Hazard cells at 40 km/h, false-activation cells at
80 km/h per the standard. Sixteen cells.

| # | Model | Scenario | Lighting | FV expected | Closed loop expected | Conf | FV measured | CL measured |
|---|---|---|---|---|---|---|---|---|
| 1 | P_day | ped cross | day | CERTIFIED | PASS | high | | |
| 2 | P_day | ped cross | dark low | FALSIFIED | FAIL | high | | |
| 3 | P_day | ped cross | dark high | FALSIFIED | FAIL | med | | |
| 4 | P_day | lead stop | day | CERTIFIED | PASS | high | | |
| 5 | P_day | lead stop | dark low | FALSIFIED | FAIL | **low** | | |
| 6 | P_day | lead stop | dark high | FALSIFIED | FAIL | **low** | | |
| 7 | P_day | trench plate | day | CERTIFIED | PASS (no brake) | med | | |
| 8 | P_day | trench plate | dark low | CERTIFIED | PASS (no brake) | **low** | | |
| 9 | P_lit | ped cross | day | CERTIFIED | PASS | high | | |
| 10 | P_lit | ped cross | dark low | CERTIFIED | PASS | med | | |
| 11 | P_lit | ped cross | dark high | CERTIFIED | PASS | high | | |
| 12 | P_lit | lead stop | day | CERTIFIED | PASS | high | | |
| 13 | P_lit | lead stop | dark low | CERTIFIED | PASS | high | | |
| 14 | P_lit | lead stop | dark high | CERTIFIED | PASS | high | | |
| 15 | P_lit | trench plate | day | CERTIFIED | PASS (no brake) | **low** | | |
| 16 | P_lit | trench plate | dark low | CERTIFIED | PASS (no brake) | **low** | | |

## Where the interesting outcomes are

The four low-confidence cells are pre-registered as such, so that a surprise there is a
result rather than a retrofit.

- **5 and 6, lead vehicle in darkness.** A stationary vehicle is large, high contrast and
  carries reflectors and lamps, so `P_day` may survive darkness against a car while failing
  against a pedestrian. If cells 2 and 3 fail while 5 and 6 pass, that is the study's most
  useful industrial finding: the regulatory difficulty is the pedestrian, and it is a
  contrast and resolution problem rather than a policy problem.
- **15 and 16, false activation by the better policy.** `P_lit` sees more braking data across
  more conditions and may be the more trigger-happy of the two. A policy that is safer on
  property S and worse on property A is exactly the trade a Tier 1 needs quantified, and it
  is invisible to any single-sided test.
- **8, false activation in darkness.** Shadows and wet reflections on a steel plate at night
  are the classic nuisance-braking trigger.

## What this study does NOT cover from the standard

Iteration 1 is a deliberate subset. Stated here so the coverage claim is never overstated in
a paper or a meeting.

| In the standard | Status here |
|---|---|
| Lead vehicle **decelerating** | Not covered |
| Lead vehicle **slower moving** | Not covered |
| **Child** pedestrian, and crossing from the left | Not covered |
| Pedestrian **walking along path** | Not covered |
| **Pass-through** false activation | Not covered. Trench plate only |
| Forward collision warning requirements | Not covered. Braking only |
| Full speed range, to 100 km/h stationary lead and 145 km/h | Iteration 2 covers 20 to 60 km/h |

The claim is therefore about a subset of the FMVSS scenario set, certified over a continuum
of lighting that the standard does not test. It is not a compliance demonstration and must
never be described as one.

## Sensing: camera only in iteration 1, fusion in iteration 2

Production AEB is camera plus radar. FMVSS 127 is performance based and sensor agnostic, so
the standard does not require either. Iteration 1 is camera only, for a scientific reason
rather than a convenient one.

**Radar is largely invariant to the disturbance we are certifying.** Darkness and fog degrade
the camera and not the radar, so a fused policy would likely pass every lighting cell and the
study would have no contrast to measure. Establishing where the *camera channel* provably
fails is the logically prior question, and it is the input to the fusion decision that
industry is currently spending money on: thermal, radar, or more camera.

**Iteration 2 adds a third policy, `P_fused`, and this is where the study gets its strongest
commercial artifact:** a certificate that says the camera-only policy is falsified in
darkness and the fused policy is certified **quantifies formally what the radar channel
buys**. That is a claim a Tier 1 selling fusion ECUs can use, and no test campaign produces
it because a test samples conditions rather than covering them.

Two things to design before that, not during:

- Radar adds few input dimensions (range, range rate, azimuth per detection), so it barely
  grows the verified set. The cost is in the fusion architecture staying ReLU-only.
- **CARLA radar is idealized.** No multipath, no clutter, no ghost targets, and those are
  precisely what causes real phantom braking. A fusion result from idealized radar overstates
  the benefit, and that has to be stated as a validity threat or measured against a
  degradation model, not left implicit.

## Iterations

**Iteration 1.** The sixteen cells above. Separable on purpose: if the lead-vehicle rows
certify and the pedestrian rows are resolution-bound, the vehicle result publishes and the
pedestrian rows become stated future work.

**Iteration 2.** Speed sweep across the FMVSS bands (20, 40, 60 km/h) on whatever worked,
plus a blind held-out lighting level declared before capture.

**Iteration 3.** Beyond the standard, which is where certification adds what testing cannot:
fog, glare, steam venting. Steam is an occlusion and shares a formulation with
`formal-verification--sensor-degradation--code`.

## Milestones, each with an empirical exit criterion

| | | Exit criterion |
|---|---|---|
| M0 | Specification | `r_req` written from measured primitives, both properties stated, this ledger loads and prints, expo fallback declared |
| M1 | Map survey | Site set chosen by measured geometry, not by eye. **Offline, no simulator** |
| M2 | Harness and primitives | `a_max` and `t_lat` over >= 10 reps; contact detector validated against a deliberate collision; a perfect oracle passes 10/10 and a deliberately late one fails 10/10 |
| M3 | Expert and collection | The oracle passes 10/10 with standoff >= `d_margin` in every lighting condition |
| M4 | Two policies | `P_day` passes daylight 10/10, `P_lit` passes all trained conditions 10/10, and `P_day` FAILS darkness. If the negative control passes, stop: there is no contrast to study |
| M5 | Capture rig and gate | Captured deceleration demand matches driven demand below a stated threshold |
| M6 | Verification | A certified onset range per cell, verdicts committed to git before M7 |
| M7 | Closed loop and blind cell | The agreement table, with at least one held-out condition declared before capture |
| M8 | Demo and writeup | |

## Site selection, and why it is measurable

One large map, several sites within it, chosen by survey rather than appearance. A site
qualifies on:

- straight clear run long enough to reach steady speed and stop from 65 km/h, roughly 150 to
  200 m
- pedestrian crossing geometry with sidewalk and walker navmesh on both sides
- lit and unlit stretches, since beam pattern is a test variable
- declared speed limits spanning 10 to 65 km/h

The declared limit is read from the OpenDRIVE, **not** from `get_speed_limit()`, which
returns the nearest sign prop or a 30 km/h default and disagrees with the declared limit on
most standard towns.

**Large maps segfault the server unless the ego is tagged `role_name='hero'`.** Large maps
stream tiles around the hero actor and actors in unstreamed space go dormant; attaching a
sensor to one crashes CARLA. This cost another project in this lab several weeks.

## Scope boundaries, stated rather than discovered

- **Dry road only.** The closed form assumes braking authority is condition independent,
  which holds for visibility disturbances and fails for wet or snow. Friction coupling is the
  winter-dataset follow-on.
- **One vehicle**, stock passenger car. Vehicle dynamics are not the story here.
- **Interior `s` is an approximation** of intermediate illumination, not a render the
  simulator would produce. Endpoints are ground truth.
