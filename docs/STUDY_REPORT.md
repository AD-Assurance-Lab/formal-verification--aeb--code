# Formal verification of AEB across illuminations FMVSS 127 does not test

**Complete methodology and results.** WMU AD Assurance Lab. Simulated in CARLA 0.9.16,
Town01, on an RTX 4070.

Everything here is reproducible from a tool in `tools/`. The frozen design is
`PROTOCOL.md`; where this report and that file disagree, the protocol is right.

---

## 1. The claim

> A policy that satisfies every point of a discrete regulatory test matrix can still fail
> between those points, and a per-frame certificate over the interval between two mandated
> test conditions finds that failure without simulating it, and names the single test that
> confirms it.

Stated for the two audiences it is meant for, and this is the only framing to use outside
the lab:

> Training against a discrete test matrix can create gaps at the matrix's own gaps, and
> here is a method that provides evidence between test points.

This is a complement to the test procedure, never a critique of it. FMVSS 127 is
performance-based and never claimed exhaustiveness.

## 2. Why these cells and not the FMVSS matrix

The product is the verification software; the sensor suite, the architecture and modular
versus end-to-end are all the customer's business. Covering the FMVSS scenario matrix
would be a compliance exercise that demonstrates nothing about the tool. So the selection
criterion is:

> Choose cells where the worst case lies in the **interior** of the disturbance interval,
> not at either endpoint.

A test campaign samples endpoints. If the failure lives between them, testing structurally
cannot find it and a certificate structurally must. Everything else is a case where
testing already works and we would be competing on cost rather than capability.

---

# Methodology

## 3. Task and operational design domain

| | |
|---|---|
| Function | Forward AEB, longitudinal only. No steering intervention, no FCW, no driver interaction |
| Ego | Stock CARLA passenger car, unmodified dynamics |
| Sensing | Single forward RGB camera, 640×480, 90° FOV, mounted x=1.5 m, z=1.6 m |
| Network input | 128 × 96, measured (§7) |
| Policy output | Deceleration demand, continuous scalar. Latching once commanded |
| Control rate | 20 Hz |
| Speed | 25 mph for hazard cells |
| Road | Dry, straight, one site, 1,007 ft long, 0.0% grade |
| Repetitions | ≥ 10 per cell |

Excluded deliberately: wet and snow surfaces, curves, multiple simultaneous actors, and
any condition acting through vehicle dynamics rather than perception.

## 4. Regulatory grounding

FMVSS No. 127, compliance 1 September 2029 (2030 small volume). What the standard supplies,
so we do not invent it:

| Element | Value used |
|---|---|
| Stopped lead vehicle | The hazard scenario used here |
| False activation | Steel trench plate, ASTM A36, 8 × 12 ft × 1 in, approached at 50 mph |
| Nuisance braking limit | **0.25 g**, the threshold in property A |
| Lighting conditions | Daylight; darkness, lower beam. These are the certified interval's endpoints |

**Not covered, and never to be described as compliance:** lead vehicle decelerating and
slower-moving, child pedestrian, crossing from the left, pedestrian along path,
pass-through false activation, forward collision warning, speeds above 50 mph. The
crossing-pedestrian scenario is captured and validated but has no trained policy yet.

## 5. Derived safety budget

Every term measured in CARLA. None fitted, none modelled.

```
r_req  =  v (t_lat + dt)  +  v² / (2 a_max)  +  d_margin
```

| term | value | how |
|---|---|---|
| `a_max` | **0.868 g** | Worst average deceleration over 20 full-brake stops (median 0.898) |
| `t_lat` | **0.150 s** | Measured brake command to deceleration onset |
| `dt` | 0.05 s | Control period |
| `d_margin` | 1.0 m | Declared, not fitted |
| **`r_req`** | **34.7 ft** at 25 mph | |

Measuring `a_max` rather than modelling it disposes of the aerodynamic drag question
entirely: the measurement contains drag at that speed, and neglecting drag analytically is
conservative for stopping distance in any case.

## 6. The disturbance family

Both endpoints are **rendered in the simulator at an identical camera pose**, then
interpolated:

```
x_p(s) = x_p^daylight + s ( x_p^darkness − x_p^daylight ),   s ∈ [0,1]
```

`s = 0` and `s = 1` are two regulatory test conditions. Every interior `s` is illumination
the standard never tests, and that interval is the entire study.

**No analytic photometric model.** That route was measured and failed in prior lab work:
an analytic fog model scored R² 0.848 on image fidelity while driving one policy 23.8×
harder than the real rendered condition. Image fidelity is not the property that matters.

### 6.1 The interval must be cut, and where

Over the full daylight-to-darkness interval the blend is wrong by **0.243 of full range**
at the midpoint. Width is not the variable; position is. Holding the interval at 11.25°
and moving it:

| centre | +50° | +35° | +20° | **+5°** | −10° | −25° |
|---|---|---|---|---|---|---|
| blend error | 0.0025 | 0.0034 | 0.0058 | **0.1527** | 0.0076 | 0.0071 |

Only the interval crossing the horizon fails, by 20 to 60×. The cause is curvature: mean
brightness against sun altitude runs 179.7 at +6°, 120.3 at +1.5°, 79.5 at 0°, 70.4 at
−1.5°, 57.7 at −6°. Steep above, shallow below, so the second derivative peaks exactly at
sunset, and a linear blend is a second-order approximation.

Shrinking helps but floors near 0.03 straddling zero, which is a kink rather than curvature.

### 6.2 The measured knots

Bisecting for the largest step whose midpoint blend stays within 0.01 of the render, 113
renders, with a knot forced at the horizon:

**60.0, 29.75, 13.254, 6.178, 3.726, 2.016, 0.805, 0.143, 0.0, −3.727, −29.597, −30.0**

Eleven sub-intervals. Step size collapses from 30.25° at the top to 0.14° approaching the
horizon and opens back to 25.87° past it. **One sub-interval cannot meet tolerance at any
width**: the 0.14° sliver at the horizon still errs at 0.0386. It is declared **uncovered**
rather than quietly spanned.

## 7. Capture

Training wants frames along a realistic approach; verification needs frames at *exactly*
the same state at every illumination, because the family interpolates pixel by pixel. So
the campaign drives **once** with rendering off to get a nominal state sequence, then
replays that sequence by placing the actors, once per knot. Pose pairing is verified exact
(`tools/check_pairing.py`); image change across the axis is 113/255.

Three capture requirements, all measured, none of them the default:

1. **Scene lighting settles in ~80 ticks after a sun change**, not a handful. Day to night:
   104.0 at 1 tick, 74.4 at 12, 60.1 at 20, 45.2 at 40, settled 42.5 by 80. A capture 12
   ticks in reads **75% too bright**. 120 ticks are used.
2. **Fixed exposure, f/4.0, shutter 200, ISO 100**, measured by sweep. CARLA's default
   f/1.4 is ~6 stops too fast: daylight came out at mean 225 with 5th percentile 137, so
   the whole image sat in the top 40% of the range. f/4.0 gives mean 129, no clipping, and
   night stays properly dark at mean 8 with the target lit by the headlamps.
3. **Frames matched on the tick id `world.tick()` returns**, and a missing frame is an
   error. A swallowed timeout leaves the queue one frame ahead and every later image
   belongs to the previous condition.

**Network input size: 128 × 96**, measured against a no-target control at the same poses so
every difference *is* the target. At `r_req` the target is resolvable at every candidate
(peak 139–165 of 255), so that does not choose. Long range does: the policy must also *not*
brake at 60 m, and the target's signature there falls from 99 to 27 as the input shrinks.
128 × 96 keeps 57, and is the size already proven tractable for the verifier.

## 8. The two policies

Identical architecture, recipe, epochs and sample count. **The only difference is which
illumination knots the frames came from.**

- **`P_pts`** — the regulatory test points only. What a manufacturer optimising against the
  test matrix builds.
- **`P_cont`** — the continuum, all 12 knots.

Teacher is PilotNet-class and never verified. Student is ReLU-only, no BatchNorm or
Dropout, 310,145 parameters. Both trained on 2,496 samples after equalising (the smaller
set is oversampled, not the larger truncated), 180 of them braking, class-weighted.

**Both training sets include the no-target control, labelled zero at every range.** Without
it, "a target is there" and "the ego is near the conflict point" are perfectly correlated
and the network learns position from road geometry instead of the target — see §12.

The expert label is a **step at `r_req`**: full braking inside, nothing outside. It has the
same shape as the property the certificate checks and introduces no parameter of its own.

## 9. Verification

The disturbance enters as a single `nn.Linear` mapping scalar `s` to flattened pixels,
which keeps bound propagation in patches mode; then alpha-CROWN over `s ∈ [−1, 1]`.

Method comparison at 128 × 96, 310k parameters: **IBP width 1294** (useless), **CROWN 0.296
in 0.8 s**, **alpha-CROWN 0.116 in 13.2 s**, peak VRAM 1.66 GB.

Two properties, both from the standard's own quantities:

- **Property S, must brake.** At every pose with range ≤ `r_req`, and for every `s` in the
  sub-interval, the certified **lower** bound on commanded deceleration ≥ the brake
  decision threshold (half of braking authority, 4.257 m/s²). 15 poses qualify.
- **Property A, must not brake.** On the no-target scenario, at **every** pose, the
  certified **upper** bound ≤ **0.25 g**. 104 poses.

The certified threshold is the same one the closed-loop controller latches at. Certifying a
different quantity from the one that drives the car is how a sound verifier ends up
answering the wrong question.

**Verdicts are committed to git before the corresponding driving.** That ordering is what
makes a verdict a prediction, and it is checkable from history.

---

# Results

## 10. Gates and harness validation

| check | result |
|---|---|
| Braking authority | 0.868 g worst of 20 runs, 0.150 s latency, on a 0.0% grade |
| Contact detector | **−1.23 ft** on a deliberate crash. Validated. Geometry, never `sensor.other.collision` |
| Oracle, lead vehicle | perfect **10/10** at 5.0 ft standoff; late **0/10** with contact at −0.3 ft |
| Oracle, crossing pedestrian | perfect **10/10**; late **0/10** |
| Expert at both endpoints | **10/10** daylight, **10/10** darkness |
| Capture gate, behavioural | 0.191 of the decision threshold |
| In-between gate, behavioural | 0.454 of the decision threshold |
| Site lighting | site 1 effectively unlit (4.6), site 3 lit (25.7) |

The oracle check is the one that matters: a harness that could not separate a correct
braking law from a deliberately late one would make every policy number meaningless.

The in-between gate at 0.454 is a pass and **not a comfortable one** — within about a
factor of two of being able to flip a brake decision. Its worst cases land in the two
sub-intervals adjacent to the horizon, exactly where §6.1 predicted from image space alone,
before any policy existed.

## 11. M4: both policies satisfy the standard

| | daylight | darkness, lower beam |
|---|---|---|
| P_pts | **10/10** | **10/10** |
| P_cont | **10/10** | **10/10** |

Braking at 33.6 ft against `r_req` 34.7, standoff 5.4–5.5 ft. This is the precondition for
the whole claim: the point is that a policy which *passes the standard* is unsafe between
its test points.

## 12. The defect that changed the study

Property A found it. With **nothing in front of them**, the first pair of policies commanded
2.8 to 5.1 m/s² at short range, and `P_cont` exceeded the 4.26 latch threshold — it would
have braked at an empty road.

The cause was the capture design, not the policies: in the lead captures the target is
present at every pose, so target presence and along-road position are perfectly correlated,
and a network can fit the labels by learning position from road geometry without ever
looking at the car.

Retraining with the no-target control fixed it. `P_pts` after the fix outputs **0.44, −0.02
and 0.00** on an empty road at 10.2, 6.9 and 2.4 m, where before it output 4.51, 3.63 and
2.79. With a target present it still outputs 8.4.

**A study verifying only property S would have published a clean, confident result about a
position detector.** The worst property A witness sits at 52.7 m, a range property S never
examines.

All results below are on the retrained policies.

## 13. M6: verdicts, committed before driving

Certified margin as a multiple of the decision threshold.

| sub-interval | P_pts (S) | P_cont (S) |
|---|---|---|
| +60.000 → +29.750 | 1.66 CERT | 1.73 CERT |
| +29.750 → +13.254 | 1.10 CERT | 1.62 CERT |
| +13.254 → +6.178 | **0.99 FALS** | 1.43 CERT |
| +6.178 → +3.726 | 1.17 CERT | 1.78 CERT |
| +3.726 → +2.016 | **0.75 FALS** | 1.72 CERT |
| +2.016 → +0.805 | **0.03 FALS** | **0.71 FALS** |
| +0.805 → +0.143 | **0.08 FALS** | **0.67 FALS** |
| +0.143 → +0.000 | **−0.27 FALS** | **−0.01 FALS** |
| +0.000 → −3.727 | 1.67 CERT | 1.25 CERT |
| −3.727 → −29.597 | 1.90 CERT | 1.78 CERT |
| −29.597 → −30.000 | 1.90 CERT | 1.78 CERT |

**Property S: P_pts 6/11, P_cont 8/11. Property A: P_pts 6/11, P_cont 8/11.**

Property A is falsified across the same twilight band for both policies. Combined with
property S, near the horizon the policy degrades in **both directions at once**: it fails to
brake when it should and brakes when it should not. That reading is only available because
both properties were certified.

## 14. M7: driving the illuminations the certificate names

Ten runs at each sub-interval's midpoint sun altitude, a **rendered** condition rather than
a blend, so a failure is the vehicle's and not the family's. Certified sub-intervals were
driven too — a test that only visits flagged cells cannot tell a working certificate from
one that flags everything.

| midpoint | P_pts verdict | P_pts drove | P_cont verdict | P_cont drove |
|---|---|---|---|---|
| +44.875° | CERT | 10/10 | CERT | 10/10 |
| +21.502° | CERT | 10/10 | CERT | 10/10 |
| +9.716° | FALS | **6/10** | CERT | 10/10 |
| +4.952° | CERT | 10/10 | CERT | 10/10 |
| +2.871° | FALS | 10/10 ✗ | CERT | 10/10 |
| **+1.411°** | FALS | **0/10** | FALS | 10/10 ✗ |
| **+0.474°** | FALS | **0/10** | FALS | 10/10 ✗ |
| **+0.071°** | FALS | **0/10** | FALS | 5/10 |
| −1.863° | CERT | 10/10 | CERT | 10/10 |
| −16.662° | CERT | 10/10 | CERT | 10/10 |
| −29.799° | CERT | 10/10 | CERT | 10/10 |

**Agreement: P_pts 10/11, P_cont 9/11.** The ✗ marks are disagreements.

Three findings, in order of importance.

**1. The claim holds.** `P_pts` passes both regulatory test points 10/10 and fails **0/10**
at 1.411°, 0.474° and 0.071° — illuminations the standard never tests. The certificate
named them without simulating. `P_cont`, identical but for illumination coverage, drives
10/10, 10/10 and 5/10 there. The gap is attributable to how the axis was sampled.

**2. Every disagreement is conservative.** In each of the three misses the verifier called
unsafe something that drove cleanly. **Nothing was certified and then failed.** For a safety
tool that is the correct direction to err, and it matters more than the agreement count.

**3. The bound magnitude tracks severity.** A margin of 0.99 — essentially exactly on the
line — drove 6/10, an intermittent failure. Deeply negative margins drove 0/10. Comfortable
margins drove 10/10. The bound is not merely a pass/fail oracle.

## 15. Cost

| | |
|---|---|
| Certifying one policy, property S, 11 sub-intervals × 15 poses | ~15 min |
| Certifying one policy, property A, 11 sub-intervals × 104 poses | ~90 min |
| Driving one policy, 11 sub-intervals × 10 runs | ~20 min |
| Capture campaign, 3 scenarios × 12 knots × 104 poses | ~2.5 h, 1.2 GB |

The certificate's advantage here is not wall-clock. It is coverage: it quantifies over
every illumination in a declared interval, where the driven runs sample one.

---

## 16. What this does not establish

- **Simulation only.** Both the disturbances and the ground truth come from CARLA.
- **One map, one site, one speed, one vehicle, camera only, stationary lead vehicle.**
- **A subset of FMVSS 127.** This is not a compliance demonstration.
- **Both policies fail the deepest twilight.** Continuum training buys margin in the
  shoulder and little at the horizon. Near-horizon illumination looks intrinsically hard,
  not merely under-sampled. That is a weaker claim than "train on the continuum and you are
  fine" and a more credible one.
- **The 0.14° sliver at the horizon is uncovered.** The disturbance family cannot represent
  it at any width.
- **The in-between gate passes at 0.454**, within a factor of two of flipping a decision.
  That bounds how much the certificate can claim near dusk.
- **Interior `s` is an approximation** of intermediate illumination, not a render the
  simulator would produce. The endpoints are ground truth.

## 17. Defects found, and what caught them

Recorded because the pattern is more useful than any single entry. Each produced output
that looked entirely reasonable.

| defect | what it reported | caught by |
|---|---|---|
| Ego launched down the opposing lane | drove into a junction at 21 m/s, recorded as 4.94 g of braking authority, verdict PASS | physically impossible number |
| Proportional-only speed hold | every run at exactly 76% of its commanded speed | impossible number |
| `except queue.Empty: pass` | every image belonged to the previous condition | backwards result |
| 12-tick weather drain | night endpoints 75% too bright | backwards result |
| `pgrep -f` matched the launching shell | server memory a flat 0.00 GB, reading as "no leak" | implausible number |
| Camera exposure 6 stops too fast | clipping check said 0.1%, "healthy" | **looking at the image** |
| Pedestrian range measured straight-line | "10.6 m" while the walker stood 6 m to the side | **looking at the image** |
| Crossing pedestrian never entered the path | scenario could not fail; a policy that never braked would pass | **measuring the geometry** |
| Headlamps never applied in the closed loop | both policies failed darkness 0/10 and 2/10 | protocol rule: a contradiction is a bug |
| Brake threshold 0.5 m/s² against a 0/8.51 label | noise latched braking at 375 ft, then 6% braking coasted into the lead | inspecting the failure detail |
| Position confound | a clean result about a position detector | **property A** |

Five were caught by a number that was physically impossible. Three were caught only by
looking at the data rather than at summary statistics. One was caught by verifying the
property that a single-sided study would have skipped.

## 18. Reproducing this

```bash
python tools/survey_maps.py                    # choose the map, offline
python tools/carla_jobs.py --all               # primitives, gates, oracle
python tools/build_family_knots.py             # the illumination knots
python tools/capture_campaign.py --scenario lead   # then none, then ped
python tools/check_pairing.py                  # exact pose pairing
python tools/choose_input_size.py --scenario lead
python tools/train_policies.py --input-w 128 --input-h 96
python tools/run_policy.py --all               # M4
python tools/verify.py --policy P_pts --property S   # M6, before driving
python tools/verify.py --policy P_pts --scenario none --property A
python tools/drive_witness.py --policy P_pts   # M7
python -m study.status                         # the ledger
```

Figure: `docs/figures/dusk_gap.html`. Raw results: `results/carla/*.json`.
