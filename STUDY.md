# STUDY.md - the experimental design and the ledger

Read this before writing code. The design is the first artifact.

## What we are selling, and what that means for the design

The product is **the verification software**. We are indifferent to the customer's sensor
suite, to modular versus end-to-end, and to their architecture. AEB is the vehicle for the
demonstration, not the subject.

**Therefore the study is not scenario coverage.** Covering the FMVSS 127 matrix would be a
large compliance exercise that demonstrates nothing about our tool. The scenarios worth
running are the ones where verification says something a test campaign cannot.

## The selection criterion

> Choose cells where the worst case lies in the **interior** of the disturbance interval,
> not at either endpoint.

A test campaign samples endpoints. If the failure lives between them, testing structurally
cannot find it and a certificate structurally must. Everything else in the standard is a case
where testing already works, and where we would be competing on cost rather than capability.

This is not speculative. It has been measured twice in this lab: a policy trained on discrete
weather presets passed every preset it was trained on and failed between them, and certified
worst cases sat at intermediate disturbance intensity rather than at full strength.

## The claim, in one sentence

> The policy passes both regulatory test points. The certificate falsifies it without
> simulating. Driving the certificate's witness point confirms the failure the standard would
> have missed.

**The certificate hands you the one test worth running.** That is the product.

## The study in four steps

1. **Train two policies**, differing only in how the lighting axis was sampled.
   - `P_pts` sees only the **regulatory test points**: daylight, darkness lower beam,
     darkness upper beam. This is what a manufacturer optimizing against the test matrix
     actually builds, which is what makes the result matter.
   - `P_cont` sees the lighting **continuum**, densely sampled.
2. **Distill both into verifiable students.** ReLU-only, no BatchNorm or Dropout. The teacher
   is a distillation source and is never verified.
3. **Test both at the regulatory endpoints.** Expect both to pass. That is the setup.
4. **Verify both over the whole interval, and drive the witness.** Verdicts committed to git
   before any witness is driven.

**Step 4 is the contribution.** Steps 1 to 3 are infrastructure. An adequate braking policy is
enough; the claim is that verification finds what testing misses, not that our AEB is good.

## The disturbance family

Both endpoints are **rendered in the simulator at an identical camera pose**, then
interpolated:

```
x_p(s) = x_p^daylight + s ( x_p^darkness - x_p^daylight ),   s in [0,1]
```

`s = 0` and `s = 1` are two regulatory test conditions. **Every interior `s` is illumination
the standard never tests**, and that interval is the entire point of the study.

**Do not build the disturbance from an analytic photometric model.** That was measured and
failed: an analytic fog model scored R-squared 0.848 on image fidelity while driving one
policy 23.8 times harder than the real rendered condition.

The family enters the network as a prepended `nn.Linear` mapping the scalar `s` to flattened
pixels, which keeps bound propagation in `patches` mode.

## Safety budget

Every term measured in CARLA, none fitted, none modelled.

```
r_req  =  v (t_lat + dt)  +  v^2 / (2 a_max)  +  d_margin
```

- `a_max` worst measured average deceleration over >= 10 full-brake stops. Measuring rather
  than modelling removes the aerodynamic-drag question: the measurement already contains drag
  at that speed, and neglecting drag analytically is conservative for stopping distance.
- `t_lat` measured brake-command to deceleration onset.
- `dt` control period. **20 Hz**, giving 0.83 m of quantization at 60 km/h.
- `d_margin` required standoff at rest.

Hazard cells run at **40 km/h**, inside every FMVSS pedestrian band.

## The two properties

**S, must brake.** For all `s` in [0,1] and all poses with range to the conflict point
<= `r_req`, the certified **lower** bound on commanded deceleration is >= `a_max`.

**A, must not brake.** On the false-activation scenario, for all `s`, the certified **upper**
bound on commanded deceleration is <= **0.25 g (2.45 m/s^2)**. That threshold is the
standard's own. The steel trench plate is ASTM A36, 2.4 x 3.7 m x 25 mm, approached in lane
at **80 km/h**, so those cells run at 80 rather than 40.

Both are pointwise conjunctions over a window the hazard geometry defines. Neither is a mean
nor a maximum over a run.

**Why the composition is closed form.** Once braking is commanded the network leaves the
loop, so the certificate composes into standoff distance analytically. Nothing integrates
network output over time, so nothing accumulates capture error.

## Closed-loop pass criterion

No contact, and standoff >= `d_margin`, over >= 10 repetitions. Report Wilson intervals.

**Contact is inferred from bounding-box separation and kinematics, never from
`sensor.other.collision`.** Measured elsewhere in this lab: a vehicle driven into a stationary
car at 19 m/s ended 2.49 m inside a body whose contact distance is 6.06 m, and the collision
sensor reported zero events. Using it here would report that AEB never collides, in every
cell.

---

# The ledger: pre-registered expectations

**A measured cell that contradicts its expectation is a bug until proven otherwise.** It may
not be written up as a finding until a written disposition lists the candidate causes ruled
out.

Six cells. Each cell is an **interval**, `s` in [0,1], not a point.

| # | Policy | Scenario | Endpoints (test) | FV over [0,1] | Witness driven | Conf |
|---|---|---|---|---|---|---|
| 1 | P_pts | ped cross | PASS both | **FALSIFIED, interior witness** | **FAIL** | high |
| 2 | P_pts | lead stop | PASS both | FALSIFIED, interior witness | FAIL | med |
| 3 | P_cont | ped cross | PASS both | CERTIFIED | PASS | high |
| 4 | P_cont | lead stop | PASS both | CERTIFIED | PASS | high |
| 5 | P_pts | trench plate | PASS both, <= 0.25 g | CERTIFIED | PASS | low |
| 6 | P_cont | trench plate | PASS both, <= 0.25 g | CERTIFIED | PASS | **low** |

**Cell 1 is the study.** Everything else is control or contrast.

- **2** shows the effect is not specific to one hazard geometry. A stationary vehicle is
  larger and higher contrast than a pedestrian, so the interior gap may be narrower or absent,
  which is why confidence is only medium.
- **3 and 4** are the positive control. Without them, cell 1 says only that a weak policy is
  weak, rather than that the *sampling of the training axis* created the gap.
- **5 and 6** keep the must-not-brake half alive at low cost. **6 is the interesting one:**
  `P_cont` sees more braking across more conditions and may be the more trigger-happy of the
  two. A policy better on property S and worse on property A is the trade a Tier 1 needs
  quantified, and no single-sided test can see it.

## If cell 1 does not fail

Pre-registered fallback, so this is not decided after seeing the data.

If `P_pts` is robust across the whole interval, the result is a **certified absence**: proof
that no illumination between the two regulatory points defeats the policy. That is still a
sellable claim and still publishable, and it is a stronger claim than any test campaign can
make. The paper then leads on coverage rather than on discovery.

What is **not** permitted is engineering the gap. `P_pts` is trained on the regulatory points
because that is what the standard incentivizes a manufacturer to do. Reducing its training
set further, or weakening it, to manufacture a failure would invalidate the whole result.

## Iterations

**Iteration 1.** The six cells above. One lighting interval, one site.

**Iteration 2.** A second disturbance interval where the interior is also suspect: low-sun
glare between two sun altitudes. Plus a blind held-out cell declared before capture.

**Iteration 3.** Beyond the standard: fog, steam venting. Steam is an occlusion and shares a
formulation with `formal-verification--sensor-degradation--code`.

## Milestones, each with an empirical exit criterion

| | | Exit criterion |
|---|---|---|
| M0 | Specification | `r_req` written from measured primitives, both properties stated, this ledger loads and prints, expo fallback declared |
| M1 | Map survey | Site set chosen by measured geometry, not by eye. **Offline, no simulator** |
| M2 | Harness and primitives | `a_max` and `t_lat` over >= 10 reps; contact detector validated against a deliberate collision; a perfect oracle passes 10/10 and a deliberately late one fails 10/10 |
| M3 | Expert and collection | The oracle passes 10/10 with standoff >= `d_margin` at both endpoints |
| M4 | Two policies | **Both** policies pass **both** endpoints 10/10 on both hazard scenarios. If `P_pts` fails an endpoint, it is not the policy a manufacturer would ship and the study has no setup |
| M5 | Capture rig and gate | Captured deceleration demand matches driven demand below a stated threshold |
| M6 | Verification | Certified bounds over `s` in [0,1] per cell, with a witness `s` for any falsified cell. **Committed to git before M7** |
| M7 | Drive the witness | The agreement table |
| M8 | Demo and writeup | |

M4's exit criterion carries the whole design: **if `P_pts` cannot pass the regulatory tests,
there is no story**, because the point is that a policy which passes the standard is
nonetheless unsafe between its test points.

## Site selection, and why it is measurable

One large map, several sites within it, chosen by survey rather than appearance. A site
qualifies on:

- straight clear run long enough to reach steady speed and stop from 80 km/h, the
  false-activation speed
- pedestrian crossing geometry with sidewalk and walker navmesh on both sides
- lit and unlit stretches, since beam pattern is a test variable
- declared speed limits spanning the tested range

The declared limit is read from the OpenDRIVE, **not** from `get_speed_limit()`, which returns
the nearest sign prop or a 30 km/h default and disagrees with the declared limit on most
standard towns.

**Large maps segfault the server unless the ego is tagged `role_name='hero'`.** Large maps
stream tiles around the hero actor and actors in unstreamed space go dormant; attaching a
sensor to one crashes CARLA. This cost another project in this lab several weeks.

## Scope, stated rather than discovered

**On the standard.** This is a subset of FMVSS 127 and is **not a compliance demonstration**.
Not covered: lead vehicle decelerating and slower-moving, child pedestrian, crossing from the
left, pedestrian along path, pass-through false activation, forward collision warning, and
speeds above 80 km/h. The claim is about a continuum of lighting the standard does not test,
on a subset of its scenarios.

**On sensing.** Camera only. The product is sensor agnostic, so nothing here depends on the
choice, and adding radar would remove the contrast the study measures: radar is largely
invariant to illumination, so a fused policy would pass every lighting cell. Fusion is a
later question about what the radar channel provably buys, not part of this study.

**Other boundaries.** Dry road only, since the closed form assumes braking authority is
condition independent. One vehicle, stock passenger car. Interior `s` is an approximation of
intermediate illumination rather than a render the simulator would produce; the endpoints are
ground truth.
