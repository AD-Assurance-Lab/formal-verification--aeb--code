# formal-verification--aeb--code

Automatic emergency braking under poor visibility. Owner: Zach. Demo: Novi, October 2026.

One file. It holds the study design, the amendments, current belief and every standing
rule. `docs/ARXIV_NOTES.md` is the only other notes file and it serves the paper
repository. `FINDINGS.md` is the measured record and nothing edits it after the fact.

Run `python -m study.protocol_lock` before you read any result. Run `python -m study.status`
for live numbers.

Older records name files that no longer exist. They were folded into this one on
2026-09-10 and they are all in git history. `git show 61b73d9^:<path>` recovers any of
them, and the design document is also at the tag `protocol-v1`. Do not look in `stale/`.
That directory is emptied on purpose.

A number in brackets points to a record in `FINDINGS.md`. You do not need it to follow this
file.

---

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

Writing verdicts down before driving is still the right habit. Nothing enforces it now.
The rule that a contradicted expectation is a fault until disposed is **unchanged**.


## Where the study is

**The map is the small one again**, because an 8 GiB graphics card cannot run the large
one. Everything is being measured again on it, from the camera frames up. That map's frames
predate the capture-order fix, and its dark endpoint reads 11.2 times too bright (F32,
A19).

Running now, in order: the primitives, the lighting range, the frames, training, the two
checks, then the certificates. Then the drives.

**The false-activation scenario does not fit on this map.** It needs 320 m of junction-free
lane and the best site is 307 m. Cells 5 and 6 are 13 m short of the standard's geometry.
Say so beside any number from them, or run them on a machine that fits the large map.

**The large map's artifacts are still reachable** with `CARLA_MAP=Town12`. Its results are
withdrawn: they were measured against networks that could not be trained again. Its camera
frames now read as stale, because the capture stamp learned to see capture order and they
predate the field. They were captured correctly. Recapture them if that map is picked up
again.

---

# Rules

Everything below is a measured result, not a preference. Each rule exists because breaking
it cost this lab time, and each says what it cost.

## Determinism. Do not break these

**This section is not optional and it is not advice.** The simulator and the graphics card
both produce results that look right and are not reproducible. Every rule here was measured
after a defect got past every other check.

### The training must repeat

Seeding the three random number generators is necessary. On the graphics card it is not
enough. Three things sit underneath the seeds:

- the convolution library picks an algorithm by timing it. The choice then depends on what
  else the card was doing;
- several operations have no repeatable version unless one is demanded;
- the matrix library sums in an order that follows the size of its workspace.

`tools/train_policies.py` closes all three. Set the workspace variable **before** the
machine learning library is imported. Setting it later fails quietly, and the failure
arrives much later as an error about a different kernel.

Without these, three quarters of every policy's numbers moved between two runs of one
command, and endpoint verdicts flipped with them (F29). With them, four separate runs gave
the same file, byte for byte, for 3 percent more time (F30).

The training report records a hash of the weights. Two runs that claim the same seed can be
compared by reading two small files. `--scratch DIR` trains into a folder of its own.

### Two simulator faults, and this study has not fixed them yet

Do not start the rework without talking to Zach. Another study is finishing the reference
version of the fix.

**The control command races the world step.** A fixed step lines up the step, not the queue
of commands feeding it. It only bites where the command changes, which in a closed loop is
every step. Three runs of one scripted sequence, feedback cut, finished 60 metres apart.

**The engine loads textures in the background.** Which version is in memory when a frame
renders depends on load timing, not on the state of the world. Turning texture streaming off
cut the renderer's noise by 168 times.

Neither shows up in a result. Both give trajectories that look right.

The fix is `pip install carla-determinism`. Bind the client, run the preflight, and route
every control command through it. Launch with texture streaming off and quality at Epic. Do
not turn off the post-process effects, because manual exposure lives in that chain.

Still owed here, and nothing fails if it is skipped. That is why it is written down.

1. Route every control command through one choke point.
2. Restart the server before every repetition.
3. Record the harness in every cell. Record unknown as null, never as false.
4. Make the blind-order check run on every commit.

**Frames captured under the old harness cannot be reused.** Capture them again. Do not
reweight or filter them.

### Two simulator traps that keep biting

**A read or a placement next to a write does not see that write.** Weather, spectator
transforms and sensor delivery all apply on the next step. Nothing raises an error when you
get this wrong. Never read back state you just wrote. Construct it.

**A fixed weather is not a static scene.** The cloud layer moves, so scene brightness at the
horizon drifts with elapsed simulated time and never settles. Light is this study's
independent variable, so the independent variable is what drifts. Cloud cover is now zero
(A15, F23).

Match sensor frames on the identifier the world step returns. Never swallow a missing frame.

Take the camera frames darkest first, and darken the world before the practice run. A dark
frame comes out nine times too bright if a bright frame was taken first, and it never
settles (A16, A17, F28).

## Rules that protect the result

- **A result that contradicts a written expectation is a fault until you prove otherwise.**
  Do not write it up as a finding until a disposition lists the causes you ruled out. This
  is the rule that has caught the most real defects in this study.
- **Train, test and verify over the same disturbance.** If they disagree about it, the
  comparison means nothing.
- **Read contact from geometry, never from the collision sensor.** A car driven into a
  stationary car at 43 mph ended 8.2 ft inside a body whose contact distance is 19.9 ft.
  The sensor reported nothing.
- **Certify against the closed-loop tolerance, not a per-frame corridor.** In the steering
  study the per-frame corridor was about 3.4 times too permissive, and a vehicle left the
  road with every frame inside it.
- **Never trade experimental quality for speed.** No processor fallback, no lowered
  simulator quality, no cut training. Warn Zach before a run longer than 1 hour.

## Every path is named once, and carries the map

`tools/paths.py` names the frames folder, the results folder and the models folder. It
imports nothing but the standard library, so the tools that must run without a simulator can
share it. Do not type a path out again. That is the fault, not the cure.

Files from an old map used to sit under the exact names the new tools ask for, and nothing
raised an error. That happened four times in one night.

## A count of pieces is not a measure of coverage

The lighting range is cut until the middle of a piece is close enough to the straight line
across it. The rule uses a fixed distance, so it can make a piece across which the scene
does not change at all.

On clean frames, 8 of the 29 pieces span nothing. Two of those are 7.4 degrees of sun angle
wide, because below about 14 degrees under the horizon only the headlamps light the road.
Width in degrees and distance in light disagree, and they disagree most at the dark end
(F27, F31).

Report the distance in light beside every verdict. `tools/family_fidelity.py` measures it
and needs no simulator.

## The statistic is a hypothesis

The working expectation is that the peak is the correct statistic for braking, because the
hazard is one event. For lane keeping the peak was wrong, because that threshold described a
sustained error.

This is the scientific bet of the repository. Test it blind. If it fails, the failure is the
result.

## Working in this repository

This is a public repository and a proof of concept. The bar is that an outsider can follow
it. It is not production quality. Try things. Do not leave the wreckage behind.

- Delete nothing in anger. Move it to `stale/`, which git ignores. Zach inspects it and
  empties it, often the same day, so never write a pointer INTO `stale/`. Point at git
  history instead. Anything ever committed is recoverable from there.
- Run `python tools/tidy.py` before you push anything meant to be read. It never deletes.
- Push often. GitHub is the backup.
- Keep `README.md` honest about what runs without a simulator. Most readers have none.
- Do not add continuous integration, formatters or linters.
- `tools/headlamp_probe.py` and `tools/choose_input_size.py` are kept although nothing calls
  them, and the hygiene report flags them. They are how anyone would check the headlamp
  beams and the network input size again.

## If your graphics card is smaller than the lab machine's

Everything measured here ran on a 32 GiB card. Two numbers decide what fits, and both are
measured rather than guessed.

| what | needs |
|---|---|
| the simulator, large map, at Epic quality | about 7.4 GiB, and it leaks to about 10.5 GiB over a long session |
| one bound computation | 3.3 to 8.3 GiB, depending on the policy and how much the sub-interval branches |

They never need to fit at the same time. Verification runs with the simulator stopped, and
the pipeline stops it for you.

**On an 8 GiB card**, one bound computation at its worst case does not fit. The pipeline now
reads the card and runs them one at a time, and says so. The widest sub-intervals may still
run out of memory. That is a fact about the card, not a fault in the run. Two honest
responses: verify the narrow sub-intervals and say which ones you could not reach, or borrow
the big machine for the verification stage only.

**The map is the harder problem.** The study moved off large maps once already. A 12 GiB
card ran a large map at under 0.6 steps per second, against 720 for a small one (A3). It
moved back only when a 32 GiB card held 26.5 steps per second (A14). An 8 GiB card is below
the card that failed the first time.

So on a small card, expect to work on the small map, `CARLA_MAP=Town01`, which is what that
variable exists for. The complete study is on that map anyway, at the tag `town01-final`.
Everything except the false-activation test fits there. That scenario needs 320 m of
junction-free lane and the small map has none, which is the whole reason for the move.

**What does not care about the card.** Training takes about 75 seconds for all three
policies. Every check that needs no simulator runs anywhere, including the lighting range
measurement and the whole of `study/`.

**Do not lower the simulator quality to make something fit.** Below Epic the rendering
measured far worse. Manual exposure lives inside the post-process chain, so turning that off
measured about 2000 times worse. A run that does not fit is a run that does not fit.

## The simulator is shared

- Book it. Zach, three students and another project want the same machine.
- Relaunch the server before every measurement run. It leaks about 10.5 GiB over 11 hours.
- Use the non-default port on the lab machine. Check before you assume 2000.
- Detach long runs with `setsid nohup`. The harness kills foreground jobs.
- One client at a time. A second script asking for the world just times out, and that looks
  exactly like a dead server.
- A pattern kill matches your own command line. Use bracket patterns or process numbers.
- `grep` and `tail` both buffer. Use `--line-buffered`, and never pipe a job you want to
  watch, or a healthy run looks stalled.
- Look at the data, not only at the statistics. Two faults passed every numeric check and
  were obvious in one frame. One was an exposure six stops too fast, which the clipping
  check called healthy. One was a pedestrian measured at 10.6 m who stood 6 m to the side.
  Export a frame and open it.
