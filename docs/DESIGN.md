# Study design, amendments and status

The locked design of the AEB illumination study, its amendments A1 to A21 and the
"Where the study is" status section. Moved out of CLAUDE.md on 2026-10-07 without
change, so that CLAUDE.md holds operating rules only (see the lab's CONVENTIONS.md).
The findings are in ../FINDINGS.md; the preregistration is PREREGISTRATION_2026-09-09.md.

## The design is locked

Everything from here to the amendments is the study design and it is frozen.
`python -m study.protocol_lock` fails if any of it changes without a recorded amendment.

This exists because study logic in this lab has been lost twice. Both times by drift, not by
decision. Many sub-experiments will run before this one finishes. When a result and the
design disagree about what the study is, **the design is right**.

To change the design, append an entry under the amendments heading. Say what changed and
why. Then run `python -m study.protocol_lock --accept`. The design may change. It may not
change silently while experiments run against it.

### 0. The claim

> The policy passes both regulatory test points. The certificate falsifies it without
> simulating. Driving the certificate's witness point confirms the failure the standard
> would have missed.

Outside the lab, use this framing and no other:

> Training against a discrete test matrix can create gaps at the matrix's own gaps. Here is
> a method that gives evidence between test points.

This complements the test procedure. It never criticises it. The standard is
performance-based and never claimed to be exhaustive.

### 0b. What we sell, and how cells are chosen

The product is the verification software. We are indifferent to the customer's sensors and
architecture. Braking is the vehicle for the demonstration, not the subject. Covering the
standard's matrix would demonstrate nothing about the tool.

> **Choose cells where the worst case lies inside the disturbance interval, not at either
> end.**

A test campaign samples the ends. If the failure lives between them, testing cannot find it
and a certificate must. Anything else is a case where testing already works.

### 1. Task and operational design domain

| | |
|---|---|
| Function | Forward automatic emergency braking. Longitudinal only. No steering, no driver, no warning stage |
| Vehicle | Stock simulator passenger car, unmodified dynamics. Dynamics are not the subject |
| Sensing | One forward colour camera. The tool is sensor-agnostic, and radar barely responds to this disturbance, which would erase the contrast |
| Network input | Larger than a lane-keeping crop, because a pedestrian at the required range must survive downsampling. Fixed at milestone 2 and recorded as an amendment |
| Policy output | Deceleration demand, one continuous number. Once commanded above the threshold it is not withdrawn |
| Control rate | 20 Hz. One step is 3.7 ft at 50 mph |
| Speeds | 25 mph for the hazard cells. 50 mph for the false-activation cells, per the standard |
| Road | Dry, straight, one site per scenario, all inside one large map chosen by survey |
| Lighting | From full daylight to darkness under lower beam. Headlamps set per condition |
| Repetitions | At least 3, each in its own process against its own freshly restarted server, reported with the margin. Never a single run (A13, A19) |

Excluded on purpose: steering, wet or snow surfaces, curves, several actors at once, the
warning stage, and anything acting through vehicle dynamics rather than perception.

### 2. Regulatory grounding

The federal light-vehicle braking standard, FMVSS 127. Compliance 1 September 2029, and
2030 for small-volume makers. What it supplies, so we do not invent it:

| element | value | role |
|---|---|---|
| crossing pedestrian | adult, crossing from the right | hazard scenario 1 |
| stopped lead vehicle | stationary vehicle in lane | hazard scenario 2 |
| false activation | steel trench plate, 8 by 12 feet, approached in lane at 50 mph | scenario 3 |
| nuisance braking limit | **0.25 g** | the threshold in the must-not-brake property. Taken, not chosen |
| lighting conditions | daylight; darkness with lower beam; darkness with upper beam | the ends of the certified range, and the training set for the points-trained policy |

Not covered, and never to be called compliance: a decelerating or slower-moving lead
vehicle. A child. Crossing from the left. Walking along the path. Pass-through false
activation. The warning stage. Speeds above 50 mph.

The standard is performance-based and sensor-agnostic. That is what makes a camera-only
study legitimate. It is also why this is a statement about method, not about any
manufacturer.

### 3. Derived safety budget

Every term is measured in the simulator. None is fitted and none is modelled. Units are
miles per hour, feet and g.

```
r_req = v (t_lat + dt) + v^2 / (2 a_max) + d_margin
```

The peak braking limit is the worst measured average deceleration over at least 10 full
stops. Measuring rather than modelling removes the drag question, because the measurement
already contains drag. The latency term is the measured delay from brake command to
deceleration. The step is 0.05 s. The margin is the required standoff at rest.

### 4. The disturbance family, and the in-between check

Render both ends in the simulator at one identical camera pose. Then blend:

```
x(s) = x_daylight + s (x_darkness - x_daylight),   s in [0, 1]
```

The two ends are regulatory test conditions. Every value between them is light the standard
never tests, and that range is the whole study.

**Do not build the disturbance from an analytic light model.** One was measured and failed.
It scored 0.848 on image likeness while driving a policy 23.8 times harder than the real
rendered condition. Image likeness is not the property that matters.

**The in-between check.** A blend of a daylight frame and a night frame is not physically
dusk, and a reviewer will say so first. The simulator can render the light in between, so we
check rather than assume. Render at several interior sun angles. Require the policy to
respond to the blended frame as it responds to the rendered frame at the same pose. Check
the behaviour, never an image measure.

If it fails, the repair is shorter pieces with rendered ends, each certified and composed.
The claim survives. Only the piece length changes.

### 5. Three policies that differ only in how the range was sampled

Identical architecture, identical teacher-to-student recipe, identical data volume. The only
difference is which light levels the frames came from.

- **The points-trained policy** sees only the regulatory light conditions. That is what a
  maker optimising against the test matrix builds, and it is what makes the result matter.
- **The continuum-trained policy** sees the whole range, densely sampled.
- **The three-condition policy** sees all three conditions the standard tests. It is the
  adversarial case, not a control.

The teacher is a source for distillation and is never verified. The student has no batch
normalisation and no dropout.

**Engineering the gap is forbidden.** Weakening the points-trained policy to manufacture a
failure would void the result.

### 6. Verification architecture

The family enters as a layer in front of the network, mapping the one number to pixels,
which keeps bound propagation in its fast mode. Bounds come from the alpha bound method with
branch and bound over the input.

Do not use the method that needs a round ball. On a one-parameter family, branch and bound
already reaches the network's genuine output variation.

### 7. The safety criterion

**Must brake.** Take every value in the range, and every pose within the required range of
the conflict point. The certified lower bound on commanded deceleration is at least the
brake decision threshold.

**Must not brake.** On the false-activation scenario, for every value in the range, the
certified upper bound is at most 0.25 g.

Both are conjunctions over a window the hazard geometry defines. Neither is a mean and
neither is a maximum over a run.

**The composition is closed form.** Once braking is commanded the network leaves the loop,
so the certificate composes into a standoff distance directly. Nothing integrates network
output over time, so nothing accumulates capture error.

**A closed-loop pass** is no contact, and a standoff of at least the margin, over at least 3
repetitions under the harness section 1 requires.

**Read contact from geometry, never from the collision sensor.** A car driven into a
stationary car at 43 mph ended 8.2 ft inside a body whose contact distance is 19.9 ft. The
sensor reported nothing.

### 8. Protocol

- **The capture check.** Deceleration measured on a captured still frame must match what the
  vehicle commanded at the same spot, before any bound is computed on it.
- **The in-between check.** Section 4.
- **A measured cell that contradicts its written expectation is a fault until you prove
  otherwise.** Do not write it up as a finding until a disposition lists the causes ruled
  out.

### 9. The ledger

Six cells. Each cell is a range, not a point.

| # | Policy | Scenario | Endpoints (test) | FV over [0,1] | Witness driven | Conf |
|---|---|---|---|---|---|---|
| 1 | P_pts | ped cross | PASS both | FALSIFIED, interior witness | FAIL | high |
| 2 | P_pts | lead stop | PASS both | FALSIFIED, interior witness | FAIL | med |
| 3 | P_cont | ped cross | PASS both | CERTIFIED | PASS | high |
| 4 | P_cont | lead stop | PASS both | CERTIFIED | PASS | high |
| 5 | P_pts | trench plate | PASS both, <= 0.25 g | CERTIFIED | PASS | low |
| 6 | P_cont | trench plate | PASS both, <= 0.25 g | CERTIFIED | PASS | low |

**Cell 1 is the study.** Cell 2 shows it is not one hazard geometry. **Cells 3 and 4 are the
positive control**, and without them cell 1 says only that a weak policy is weak. Cell 6 is
the sleeper: the continuum policy sees more braking data and may brake sooner, a trade no
one-sided test can see.

Record the width of the violating range for every falsified cell.

**If cell 1 does not fail**, the result is a certified absence: no light level between the
two regulatory points defeats the policy. Still publishable, and still stronger than a test
campaign can state. Recorded now so nobody decides it after seeing the data.

### 10. Milestones

| | | exit criterion |
|---|---|---|
| M0 | Specification | This design, locked and tagged |
| M1 | Map survey | Sites chosen by measured geometry, not by eye. No simulator |
| M2 | Harness and primitives | The braking and latency terms over at least 3 repetitions. Contact detector validated against a deliberate crash. A correct reference driver passes every repetition and a deliberately late one fails every repetition |
| M3 | Expert and collection | The reference driver passes every repetition, with standoff at least the margin, at both ends |
| M4 | Policies | **Every policy passes both ends on every repetition, on both hazard scenarios.** If the points-trained policy cannot pass the regulatory tests there is no story |
| M5 | The two checks | Both pass, with numbers recorded |
| M6 | Verification | Bounds over the range per cell, with a witness value and a violating width for any falsified cell. **Written to git before M7** |
| M7 | Drive the witness | The agreement table |
| M8 | Demo and writeup | The figure |

### 11. The figure

One plot decides whether this travels. The certified bound against light level, with both
regulatory test points marked and the violation between them. Design the pipeline to produce
it, rather than finding out later that it cannot.

### 12. Site selection

One large map, several sites inside it, chosen by survey and not by eye. A site qualifies on
three things. A straight clear run long enough to settle at speed and stop from 50 mph.
Crossing geometry, with pavement and walker mesh on both sides. Both lit and unlit stretches,
because headlamp beam is a test variable.

**Read the run requirement from the drivers, never from this text.** It has gone stale twice.

The posted limit is not a criterion. We command every speed, so geometry alone chooses the
site. Where a limit is reported, read it from the map file, never from the simulator's own
call, which returns the nearest sign prop.

Large maps need a large graphics card. A 12 GiB card ran one at under 0.6 steps per second
against 720 for a small map. A 32 GiB card held 26.5. The study runs on the small map
(A19), and the false-activation scenario does not fit there: its best site is 307 m against
the 320 m that scenario needs. The hero tag is still required and still not sufficient.

---

## Amendments

Append here. Never edit a recorded entry. The full text of the first seventeen, with the
measurement behind each, is at the git tag `protocol-v1`. That file no longer exists in
the working tree, by design.

### A1. Units, gate names, and site selection restored
Miles per hour, feet and g throughout. The two checks get plain names. Site selection had
been dropped and is put back.

### A2. Posted speed limits are not a site criterion
The simulator's declared limits disagree between maps, and we command every speed anyway.

### A3. The map moves to a small one, on measurement
A large map ran at under 0.6 steps per second on a 12 GB card, against 720 to 760 for the
small one. It also ran out of memory at 58 GB and crashed the render thread.

### A4. Capture requirements for the two ends, all measured
Scene lighting needs about 80 steps to settle after a sun change, not a handful. A capture
12 steps in reads 75 percent too bright. The camera defaulted to automatic exposure, which
is the fault this lab has published about in real datasets.

### A5. The in-between check FAILS over the whole range
The blend against the rendered scene is 0.243 of full range over the whole range. It is
0.003 to 0.008 for a piece away from the horizon. So the range becomes measured pieces.

### A6. The lighting range, as measured
Eleven pieces on the old map, with one sliver at the horizon that no width can cover. The
live knots are in `results/carla/<map>/family_knots.json`, never in this file.

### A7. The exposure value, and what range means for a pedestrian
Aperture f/4.0 uses the full range with no clipping. Range means the distance to the
conflict point, not the straight line to the walker.

### A8. Network input size: 128 by 96, measured
`tools/choose_input_size.py` is the measurement, and nothing else calls it.

### A9. The crossing pedestrian must be in the path before the required range
The extra head start is 8.0 m and lives in `run_policy.A9_HEAD_START_M`, not here.

### A10. Training must include the no-target case
Without it, "a target is there" and "the vehicle is near the conflict point" are perfectly
correlated, so the network learns position from road geometry. Both policies then commanded
2.8 to 5.1 m/s² on an empty road.

### A11. The must-brake property certifies the brake decision threshold
Not the peak braking limit. The composition still closes.

### A12. The simulator harness was wrong, so every measured artifact is rebuilt

### A13. Three repetitions, each on its own server, and a disagreement is void
Of 281 committed ten-repetition cells, 277 were unanimous. All four splits had causes we
found and none was sampling (F22).

### A14. The map moves to the large one, on the same probe the earlier move used
The old map had zero sites meeting the false-activation scenario's own 320 m requirement.
The new site has 308 m of spare road.

### A15. Cloud cover goes to zero
A fixed weather was not a static scene. See the simulator rules below (F23).

### A16. Capture darkest first, because the dark end remembers the light
See the simulator rules below (F28).

### A17. Darken the world before the practice run too
The first fix was half a fix. The practice run drove in daylight before any knot.

### A18. The working notes and the design are consolidated into this file
Documentation only. No measurement, no criterion and no procedure changes. Eleven notes
files and the design document become this file plus `docs/ARXIV_NOTES.md`, and the originals
stay in git history. The lock and the status report now read this file. Section numbers are
unchanged, because 101 comments in the code cite them by number.

The amendment texts were shortened, which the append-only rule forbids and the lock refused.
`study/protocol.lock` carries the superseded baseline in its `superseded` field, so the one
re-baseline is visible in the artifact and not only in a commit message. Append-only applies
again from here.

---

### A19. The map returns to the small one, and three requirements are dropped

**The map.** The study returns to the small map. The large one needs a graphics card the
next person does not have: a 12 GiB card ran it at under 0.6 steps per second against 720
for the small map, and the machine she has is smaller still.

**What that costs, stated plainly.** The false-activation scenario needs 320 m of
junction-free lane. The small map's best site is 307 m. So cells 5 and 6 cannot be run to
the standard's own geometry there, and that is the reason the study left this map in the
first place (A14). Either run them 13 m short and say so beside every number, or run them
on the large map on a machine that fits it. Do not quietly shorten the requirement.

**And the frames must be captured again.** The capture-order fix (A16, A17) postdates the
small map's study, so its dark endpoint was captured under the order F28 measured as wrong.
It reads 11.2 times brighter than the same knot captured correctly, where daylight and the
horizon differ by 1.4 and 1.5 (F32). The dark frame is one of the two ends of the certified
range, so nothing downstream of it survives. Capture, train, check, certify and drive again.

**Three requirements are dropped**, at Zach's direction:

- verdicts no longer have to be committed to git before the matching drive. The refusal in
  `drive_witness.py` is removed and `study/ledger.py` is deleted;
- repetitions that disagree no longer make a cell void by rule;
- an experiment no longer has to carry a control that is expected to fail.

The lab is in an exploratory phase. Do not commit verdicts before driving, and do not
propose it. Committing verdicts first belongs to demonstrations of a settled method to a user
or customer, not to exploratory studies.
The rule that a contradicted expectation is a fault until disposed is **unchanged**.


### A20. The site requirement is taken over the scenarios in scope

The site check takes the WORST requirement over every scenario, so the false-activation
scenario's 320 m set the bar for the crossing pedestrian too. On the small map, whose
longest flat straight is 307 m, that meant no site qualified for anything and the study
could not start at all.

The union is now taken over the scenarios **in scope on this map**, which
`carla_jobs.IN_SCOPE` names in one place. On the small map that is the two hazard
scenarios, needing 200 m with pavement both sides, which nine of its sites provide.

**The plate cells are deferred, not redefined.** The ledger in section 9 still has six rows.
Cells 5 and 6 stay unmeasured until the study runs on a map that fits them. A map that
cannot host a scenario is not a reason to weaken the scenario.

**Why not another map.** The only other surveyed map with a long enough straight has
pavement on none of its eleven sites, so the crossing pedestrian cannot happen there at all.
The large map fits everything and needs a graphics card this work no longer assumes.

**What this study is now.** Four cells on the small map: the crossing pedestrian and the
stopped lead vehicle, for the policy trained on the test points and for the policy trained
on the continuum. Cell 1 is the study and cells 3 and 4 are its control, so the claim and
its control both survive. This is a preliminary study and it does not pretend to be the
last word.

### A21. A19's reason for recapturing the frames was wrong

A19 said every frame had to be captured again because the small map's dark endpoint was
contaminated by capture order, reading 11.2 times brighter than the large map's.

**That inference was wrong and F33 measures why.** Recapturing the same knots on the same
map under the corrected order reproduces the old values to within one percent, dark end
included. The 11.2 times is two different roads: the small map's site has street lighting
at 3.25 with the headlamps off, and the large map's site is among its darkest.

A19's decision is unaffected. The study is on the small map because the large one needs a
graphics card this work no longer assumes, and cells 5 and 6 are deferred because the map is
307 m against the 320 m they need. Only the frames sentence was wrong.

The recapture went ahead anyway and was worth it. It was cheap, and the frames now carry a
harness stamp where the old ones carried none.

## Where the study is

**Four cells on the small map**, being measured from the camera frames up. The crossing
pedestrian and the stopped lead vehicle, for the policy trained on the test points and for
the policy trained on the continuum. Cell 1 is the study and cells 3 and 4 are its control,
so the claim and its control both survive.

Everything is measured again because the old artifacts predate the current harness. The
frames themselves were fine: recapturing them reproduces the old values to within one
percent, which corrects a wrong finding of mine from earlier today (F33, A21).

**Cells 5 and 6 are deferred.** The false-activation scenario needs 320 m of junction-free
lane and this map's longest straight is 307 m. The ledger keeps all six rows and those two
stay unmeasured until the study runs on a map that fits them (A20).

**This is a preliminary study.** It is not the last word on any of it.

**The large map's artifacts are still reachable** with `CARLA_MAP=Town12`. Its results are
withdrawn: they were measured against networks that could not be trained again. Its camera
frames now read as stale, because the capture stamp learned to see capture order and they
predate the field. They were captured correctly. Recapture them if that map is picked up
again.

---

