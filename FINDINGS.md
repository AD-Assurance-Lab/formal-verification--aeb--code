# Findings

Measured results and corrections, newest first. PROTOCOL.md section 8: a measured cell
that contradicts its expectation is a bug until proven otherwise, and findings live
here, never inside the protocol.

---

## F27 — 2026-09-09, one sub-interval on each map is a verdict about nothing, and the axis weights sub-intervals 200:1

The axis is bisected until the chord's midpoint error falls under an **absolute** tolerance
of 0.01. That rule has no notion of how much illumination an interval spans, so nothing
stops it producing a sub-interval across which almost nothing changes — and on both maps it
did, in the same place.

Measured on the captured frame sets, which is what `verify.py` actually bounds: the mean
absolute per-pixel distance between a sub-interval's two endpoint frame sets, over the whole
captured pose set, on the 0–1 scale.

| | Town01 | Town12 |
|---|---|---|
| sub-intervals | 17 | 20 |
| endpoint distance, smallest | **0.0000** | **0.000229** |
| endpoint distance, largest | 0.0288 | 0.046794 |
| ratio, largest to smallest | — | **204** |
| median | — | 0.021705 |
| the sub-interval that spans nothing | **[−29.554°, −30.000°]** | **[−29.539°, −30.000°]** |

**The two endpoint frame sets of that sub-interval are the same image to within the render
floor.** The family there interpolates between two copies of one frame, so its certificate
is a statement about nothing — and it still contributes a verdict to every count the study
reports. `P_cont` certifying "16/16" includes it.

### Why it exists

Both maps' darkness endpoint is −30.0° with lower beam, and by −29.5° the sun is already
far below the horizon, so the scene is lit by headlamps alone and stops changing. The
bisection reached that region, measured a chord error of 0.0041 (Town01) and 0.0043
(Town12) — which is the **render floor**, not an interpolation error, since there is
nothing to interpolate — and stopped, because the floor is under the tolerance. An absolute
stopping rule cannot tell "the chord fits well" from "there is nothing to fit".

### What follows, and what does not

- **Verdict counts over sub-intervals are not a coverage statistic.** They weight a
  sub-interval spanning 0.047 the same as one spanning 0.0002, a factor of two hundred.
  Every "certified N of M" in this study is a count of that kind, and the span belongs
  beside it.

  Checked against the Town01 certificates as published, at `town01-final`. The zero-span
  cell is **CERTIFIED in every arm**, and comfortably — margin 1.89x for `P_cont`/lead,
  1.94x for `P_cont`/ped, 1.94x for `P_pts`/lead — because bounding a family whose members
  are all one image is easy. So it inflates every certified count by exactly one, and it
  does so with a healthy-looking margin.

  The sharpest instance is the arm the paper's claim is about. **`P_pts`/lead certifies 4
  of 17 sub-intervals, and one of those four spans no illumination change at all.** A
  quarter of the certified evidence for the policy the study exists to falsify is a cell
  about nothing.
- **No verdict is asserted to be wrong.** The certificate is sound over the family it
  declares. This is about how much of the rendered axis that family represents, which is a
  different question and is the one a reader will ask.
- **This is the photometric picture only.** PROTOCOL section 4's *behavioural* in-between
  gate, in the policy's own output space, is what section 4 says decides, and it is M5. A
  sub-interval spanning no image distance will trivially pass it too, for the same reason.

### The measurement that is NOT made here

The tempting next step is a ratio of the knot file's `blend_error` to this distance, and it
would be wrong. `blend_error` is **one frame at a fixed empty-road pose** (`along=25.0`);
this distance is over the whole captured pose set with the target present. Different
populations, different variance, and a ratio of them would look rigorous and mean little. A
first pass at this finding computed exactly that ratio and reported figures up to 190
before the mismatch was noticed. The honest version needs both quantities rendered at the
same poses, which needs the simulator, and it is queued rather than guessed.

### What to do

`tools/family_fidelity.py` reports the span per sub-interval and flags any that span less
than half a grey level. Two candidate protocol changes, **neither made here** because both
change what the axis IS and that needs an amendment:

1. make the bisection tolerance relative to the endpoint distance rather than absolute;
2. refuse to create a sub-interval whose endpoint distance is under a floor, merging it
   into its neighbour instead.

---

## F26 — 2026-09-09, the capture campaign would have built a Town12 family out of Town01 endpoints

**Caught in the log, not by a check.** The A14 rebuild reached the capture stage and
printed:

    lead: 104 states x 21 knots = 2184 frames, about 2.01 GB raw
      lead_sun+60.000.npz exists, skipping

`capture_campaign.py` skipped any knot whose output file already existed. The file name is
`<scenario>_sun<altitude>.npz` and the test was `out_path.exists()` — nothing in the name
or the test carried the map, the weather, or the harness. Every capture on disk was a
**Town01** frame set from 2026-09-06 and 09-07.

### What it would have produced

Town12's re-bisected axis (F25) shares exactly three knots with Town01's:

| shared knot | what it is |
|---|---|
| **+60.000°** | **the daylight regulatory endpoint** |
| 0.000° | the horizon knot |
| **−30.000°** | **the darkness regulatory endpoint** |

**Two of the three are the regulatory endpoints** — the two rendered frames the entire
disturbance family is built between, and the two conditions FMVSS 127 tests. The rebuild
would have captured eighteen fresh Town12 knots, silently reused Town01 frames at those
three, and built a family that interpolates a Town01 daylight image to a Town01 darkness
image over Town12 poses.

Nothing errors. The manifest lists twenty-one knots, the frame counts are right, the
photometric axis check passes because the endpoints are genuinely bright and genuinely
dark, and every certificate, gate and drive downstream reads as complete. This is the same
shape as the defect that cost the sibling steering study a set of verification captures,
and the same shape as A12's: **an artifact that is wrong in a way no numeric check can
see.**

### Why the skip exists, and why it is kept

Resuming an interrupted campaign is a real need — a capture set is hours, and the skip is
what makes a crash recoverable. The defect was not the skip. It was that **a file's
existence was treated as evidence that it belonged to this campaign.**

Two guards now, and deliberately two, because the first is a directory layout and layouts
get flattened by the next person tidying up:

1. **The path carries the map.** `carla_jobs.CAPTURES` is defined once and scoped by
   `MAP`. Eleven modules had that path re-typed as a literal, which is the condition this
   repository keeps recording — a rule re-typed into each driver is a rule one driver will
   not have — and here it was eleven drivers all agreeing on the wrong thing.
2. **Every frame set carries a `harness` stamp inside the npz**: map, cloudiness, weather
   settle ticks, rules digest, `-notexturestreaming`, quality level. The resume-skip
   compares it against the harness running now and **recaptures** on a mismatch rather than
   reusing or refusing — the operator asked for this campaign, and the stale frames are not
   it. An unstamped file is a mismatch by definition, because it predates the stamp and
   there is no way to tell what made it.

The Town01 captures were moved to `results/captures/Town01/`, which is where they belong.
They are not stale and not wrong; they are a Town01 measurement, behind the `town01-final`
tag, and they are now somewhere a Town12 campaign cannot reach by accident.

### What it says about A14

A14 wrote that every measured artifact is rebuilt and that this is "an A12-scale rebuild,
entered deliberately". It was entered deliberately and the pipeline still had a path that
quietly declined to rebuild one. Declaring a rebuild does not perform one, and the only
reason this was caught is that the capture stage prints what it skips.

---

## F25 — 2026-09-09, on Town12 the disturbance family covers the whole axis: there is no uncovered sliver

The A14 rebuild re-bisected the illumination axis on the new map, at the same tolerance
and with the same metric. It comes out differently, and one of the differences removes a
caveat the study has carried since A6.

| | Town01 | Town12 |
|---|---|---|
| sub-intervals | 17 | **20** |
| **uncovered sub-intervals** | **1** | **0** |
| the horizon sliver | [+0.026°, +0.000°], blend error **0.0163** | [+0.024°, +0.000°], blend error **0.0095** |
| worst blend error, any sub-interval | — | 0.0100, at [+4.857°, +4.289°] |
| tolerance | 0.01 | 0.01 |

**Every sub-interval on Town12 is covered.** The sliver at the horizon that A6 declared
uncovered, that PROTOCOL excludes from every verdict by construction, and that F19 read as
the place where a certificate is unavailable in principle, sits at 0.0095 here — inside
tolerance, on the same metric.

### What changed, and what did not

The two axes are the same shape at the dark end and different at the bright end. Both need
one enormous step across darkness (Town01 28.593°, Town12 29.539°) and both end up with a
sliver of a few hundredths of a degree at the horizon. Where they part is daylight: Town01
opened with a 17.234° sub-interval, and Town12 needs 5.148°, 7.294°, 5.647°, 5.677° and
6.083° to hold the same tolerance. Town12's daylight scene has more in it, so a straight
line in image space between two rendered frames fits it worse and the bisection has to
split further.

That is also the likely reason the horizon sliver now passes. Town12's scene at +0.403° has
a mean brightness of 0.011 against Town01's 0.062 — this road is much darker at the horizon
— and a scene that changes less between adjacent altitudes is one a chord fits better.

### What this does NOT establish

- **Not that the horizon is coverable in general.** One road on one map, and the plausible
  mechanism is that this particular scene is darker. A6's measurement on Town01 stands as
  a measurement of Town01.
- **Not that the behavioural gate will pass.** This is the *photometric* in-between check,
  which is what the knots are bisected on. PROTOCOL section 4's *behavioural* in-between
  gate is M5 and has not run. On Town01 the photometric check passed everywhere and the
  behavioural gate then failed for `P_pts`/ped at [+12.542°, +7.715°] at 1.016, and needed
  A5's repair. The same can happen here.
- **Not a like-for-like render count.** Town12's 223 renders are a fresh full bisection;
  Town01's committed knot file records 5 because it is the *refined* artifact, produced by
  A5's repair from an earlier set. The two numbers are not comparable and neither is a
  measure of how hard the map is.

### What it costs the study, which is not nothing

Two results are about the sliver and lose their subject if it does not exist on this map:

- **F14 and QUEUE item 10, conformal coverage for the uncovered sliver.** The argument was
  that a certificate is unavailable where the family provably cannot represent reality, so
  a distribution-free coverage statement goes there instead. With no uncovered band there
  is nowhere to put it. The instrument stands; the motivating gap may not.
- **F19's reading of the sliver** as the first empirical confirmation that it cannot be
  certified. That half of F19 was already withdrawn by F24 for an unrelated reason.

Both are recorded here rather than deleted. If the behavioural gate reopens a band, they
come back.

---

## F24 — 2026-09-09, the false-activation driver ran at half the specified control rate, and it invented the plate result on both sides

**Reopens:** F19's `P_cont` half. **Disposes:** the `P_cont`/plate split left open in F22.
**Falsifies:** prediction 2 of the pre-registration addendum, which is recorded below
rather than quietly dropped.

`plate_run` ticked the world **twice per control iteration**. `J.grab_frame` at the top of
the loop calls `world.tick()` and returns the frame that tick produced; a second bare
`world.tick()` sat at the bottom. `one_run` has never had it. So the false-activation
driver — cells 5 and 6, and nothing else — ran the closed loop at **10 Hz** where
`PROTOCOL.md` section 3 fixes 20, with **7.3 ft** of quantization where section 3 states
3.7, holding each throttle command across two physics steps while the PI integral used a
one-step `dt`.

### What it did to the measurement

`P_cont` on the trench plate at +0.013°, ten repetitions, one freshly restarted server and
one process each, identical in every respect except the extra tick:

| | peak commanded deceleration | braked | verdict |
|---|---|---|---|
| **10 Hz** (as collected) | bimodal: 1.904, 1.914 and 2.605–2.618, nothing between | 8 of 10 | **2/10 pass** |
| **20 Hz** (as specified) | **1.996 – 2.176**, ten repetitions | **0 of 10** | **10/10 pass** |
| the limit | 2.4525 | | |

**The 10 Hz values bracket the truth on both sides.** Neither mode was real: the low mode
sat 5% below the correct value and the high mode 20% above it, and only the high mode
crossed the nuisance limit. This is not a sampler missing a peak, which was the
pre-registered guess — it is the trajectory itself being different, because the control was
held across two physics steps. The plate was fully placed on every run, nine tiles of nine,
so the partial-placement candidate is eliminated by measurement rather than by argument.

### What it costs, and it is a headline

F19 read `P_cont` as **the only arm that brakes for the steel**: at +0.013° the plate was
said to add 22% to peak demand and carry it from 90.6% to 110.5% of the limit, the only
place in any arm where the plate changes a verdict, and therefore *"the first empirical
confirmation that the sliver cannot be certified"*.

**At the specified control rate `P_cont` does not brake on the plate at +0.013° at all.**
It peaks at 89% of the limit and crosses the plate still moving, ten times out of ten. So:

- **the study's only certified-then-failed sub-interval was a driver defect.** With it
  gone the count is zero, across every cell and every arm — which is a *stronger* result
  for the certificate than the one that was written down, not a weaker one;
- F19's `P_cont` half is withdrawn pending a re-drive, and with it section 9's "sleeper is
  awake" reading. Its `P_pts` half is untouched by this: `P_pts` commands 138% of the limit
  at +0.403° with the plate and 3.382 against 3.381 without it, and neither number depends
  on the brake latching;
- **every plate measurement in the study was collected at 10 Hz** — cells 5 and 6, F18,
  F19, and the plate figure. They stand as collected, on a driver that did not conform to
  the protocol, and they are not carried into the Town12 rebuild.

### The pre-registered prediction that failed

The addendum predicted the cell would go **unanimously to FAIL** with peaks at or above
2.6, reasoning that a 20 Hz sampler cannot miss a peak a 10 Hz sampler sometimes catches.
It went unanimously to PASS at 2.0–2.2. The reasoning assumed the extra tick subsampled an
otherwise identical trajectory; it changed the trajectory. Prediction 1 held — the cell is
unanimous — and prediction 3 held in spirit: the residual spread is two tight speed modes,
19.996 and 20.327 m/s, and the peak tracks them at 2.00 against 2.17. That bimodality is
still there and no longer crosses anything.

### Why it was found at all

Only because a repetition disagreement was treated as a bug and chased. It survived the
shared-server harness, the per-repetition restart, F22's write-up — where it was filed as
an amplifying policy and left void — and it would have survived into the paper. **A cell
whose repetitions disagree has been a bug every time in this lab**, and the three that
turned up in this study are now F21, F23 and F24. Void is where the hunt starts.

---

## F23 — 2026-09-09, CARLA's cloud layer moves under fixed weather, so "the same illumination" drifts 3.9% with elapsed simulation time

**The scene this study calls a condition is not static.** Held on the brake, camera rigid,
weather set once, exposure pinned manually, nothing else in the world: the rendered mean
brightness still wanders.

| sun altitude | mean at the 120-tick settle | range over 3,000 ticks | drift | policy demand spans |
|---|---|---|---|---|
| +0.403° (ped split cell) | 0.06209 | 0.06200 – 0.06442 | **3.85%** | **0.334 m/s²** |
| +0.013° (plate split cell) | 0.04338 | 0.04335 – 0.04486 | 3.44% | 0.273 m/s² |
| +51.383° (daylight control) | 0.51524 | 0.51276 – 0.52120 | 1.63% | 0.030 m/s² |

The curve rises for roughly 1,200–1,800 ticks and then falls back, at every altitude. That
is not a settle. Nothing converges; the scene is being modulated.

### It is the clouds, and the attribution is one flag

Every driver in this study sets `cloudiness = 10.0` beside the sun altitude. **CARLA's
cloud layer moves**, and holding the weather parameters fixed does not hold the sky still.
Re-run at +0.403° with `cloudiness = 0.0`, everything else identical:

| | cloudiness 10.0 | cloudiness 0.0 |
|---|---|---|
| drift over 3,000 ticks | 3.85% | **1.05%**, and all of it in the first 20 ticks |
| settled by | never, within 3,000 | **tick 20** |
| flat thereafter | — | 0.08% over the remaining 2,800 ticks |
| policy demand span | 0.334 m/s² | 0.114 m/s² |

`WEATHER_SETTLE_TICKS = 120` is not wrong about what it measured. Its recorded
justification is a day-to-night transition, 221 to 42.5, settled by 80 ticks and flat to
400 — a 5x change resolved to a few percent. The cloud modulation is a few percent, so it
was inside the noise of the measurement that set the constant, and it is decisive exactly
where the study's interesting cells are: at the horizon the policy's demand moves eleven
times more per unit of scene brightness than it does in daylight.

### What this costs, stated plainly

- **The illumination axis has an uncontrolled time-varying component.** Illumination is
  this study's independent variable. Two measurements of "the same" horizon illumination,
  taken a minute apart of simulated time, differ by about 2% of scene brightness, and this
  policy's brake decision is a step function across that.
- **Capture campaigns sweep the curve within one capture.** `capture_campaign.py` settles
  once and then walks its poses at 40 ticks each, so pose 1 sits near tick 120 and pose 25
  near tick 1,120 — different points of the modulation. The certificate's endpoint frames
  therefore carry a photometric gradient along the pose index that is not part of the
  declared disturbance family.
- **More repetitions make it worse, not better.** Repetitions inside one server sample
  further along the curve. This is the concrete case of the standing rule that a larger
  sample drawn through a known-bad harness measures the harness.

### What is NOT claimed

That any published verdict is wrong. Nothing here has been re-verified or re-driven at
`cloudiness = 0`, and the modulation is a few percent where the certified/uncertified
separation is a factor of two. What is claimed is that the study does not currently
control its own independent variable to better than about 2% at the horizon, and that the
gap has never been in any error budget.

**This is not a defect the `carla-determinism` package covers.** D-3 is texture-mip
streaming and D-4 is the postprocess chain; both are pinned here and both are satisfied.
This is a third mechanism, it is lab-wide, and it is written up for Zach rather than added
to a hash-locked file by a study.

---

## F22 — 2026-09-09, what ten repetitions were actually buying: three defects, no rate, and no need for ten

**Disposes:** the four split cells in `docs/PREREGISTRATION_2026-09-09.md`, and the failed
prediction 4 in that file.

`PROTOCOL.md` section 3 required every closed-loop number to be a failure rate over at
least ten repetitions with Wilson intervals. Measured across every committed artifact in
this repository (`tools/repetition_floor.py`, no simulator):

| | |
|---|---|
| cells carrying a ten-repetition count | 281 |
| unanimous | **277** |
| split | 4 |

A cell passes iff every repetition passes, so only a split cell can be sensitive to the
repetition count at all. All four splits were then re-driven with a stopped server, a
fresh launch through the determinism preflight, a new process, a new client, a new vehicle
and a new camera **before every repetition** — the harness D-6 asks for and QUEUE item 8
had open — plus two controls that were unanimous.

| cell | ten in one process | ten on ten fresh servers | cause |
|---|---|---|---|
| `P_pts` / lead [+0.779°, +0.026°] | 9/10 | **10/10** | F21 scoring defect |
| `P_pts` / lead at-witness [+0.026°, +0.000°] | 8/10 | **10/10** | F21 scoring defect |
| `P_pts3` / ped [+0.779°, +0.026°] | 2/10 | **10/10** | F23 cloud drift |
| `P_cont` / plate [+0.026°, +0.000°] | 6/10 | **2/10, still split** | the driver, F24 |
| CONTROL `P_cont` / lead [+60.000°, +42.766°] | 10/10 | 3/3 | — |
| CONTROL `P_pts3` / lead [+10.128°, +7.715°] | 0/10 | 0/3 | — |

**Not one of the four was sampling.** Two were an instrument defect, one was the simulator
moving underneath the measurement, and the fourth is open — see below, it was filed as a
marginal policy and that is a conclusion the evidence does not yet support. A Wilson
interval over any of them would have described a failure rate that does not exist.

### The three causes, separated by measurement rather than by argument

- **`P_pts3`/ped.** The ten fresh-server repetitions are bit-identical: brake at step 4,
  376.88 ft, rest at 325.50 ft, scene mean 0.06192–0.06194 every time. The ten in-process
  repetitions on a freshly restarted server reproduce the split, `PFFPFPPPPP`, and their
  scene means climb 0.06194 → 0.06251 → 0.06296 → 0.06421 as the runs accumulate. Idling
  1,000 ticks with nothing spawned reproduces both the drifted brightness (0.06425) and
  the failure, so the cause follows elapsed simulated time and not spawn churn. F23 names
  it.
- **`P_cont`/plate. CLOSED by F24, and filed wrongly twice before that.** Scene means are stable to
  3e-5 across all ten fresh-server repetitions and the cell still splits, 2/10, with peak
  demand bimodal at 1.90–1.91 against 2.61–2.62 m/s² and nothing in between. This was
  first written up as D-10 amplification and therefore VOID, and that was the wrong place
  to stop. **Under a fully enforced harness a repetition disagreement has been a BUG every
  time in this lab**, and void is where the hunt starts. A clean gap with no intermediate
  values is a discrete difference between runs, not an amplified continuum: candidates are
  a partially placed trench plate (it is built from tiles and **the per-run record does not
  carry the tile count**, so a partial placement is invisible in the artifact), the absence
  of any `brake_step` or `speed_at_brake` diagnostic in `plate_run` — the two fields that
  made F21 visible — and a one-frame offset at the start, which over a 200 m approach at
  50 mph is 1.1 m of range. **The cell is not reported until the cause is written down**;
  it also fails harder on the clean harness than the shared server said, 2/10 against
  6/10. `docs/PAPER_PLAN_2026-09-09.md` E1.
- **The two `P_pts` cells.** F21's `rest_gap_ft` defect, fixed, and both are now unanimous.

### The pre-registered prediction that failed, and its disposition

Prediction 4 said `P_pts3`/ped would stay split, on the reasoning that two runs braking at
377 ft and eight never braking is a knife-edge in the policy. It went 10/10 unanimous. The
reasoning was wrong in its subject: the knife edge is real, but what crosses it is the
scene, not the network. The prediction assumed the only thing that could vary between
repetitions was the policy, which is the assumption F23 falsifies.

Predictions 1, 2 and 3 held: both controls reproduced, both `P_pts` cells went unanimous,
and the plate cell's failures stopped being contiguous.

### What this settles about the repetition count

The ten-repetition floor came from D-7, which measured that rendering never reaches
bit-identity and inferred a repetition floor with a confidence interval. The measurement
stands and the inference does not, in this study:

- Under a per-repetition restart, repetitions of the same cell are not merely close, they
  are **identical to the recorded precision** — 10/10 at two cells and 3/3 at both
  controls, matching the sibling steering study's 0 of 48 section-pairs.
- Where they are not identical, the disagreement was a bug **three times out of four**,
  and the fourth is a void cell.
- Ten repetitions sharing a server are worse than three that do not, because they sample
  further along F23's curve while looking like a larger sample.

So the repetition count buys **detection of a split**, not precision on a rate. Three
repetitions detect the two split cells here — a 6/10 cell is visible to three repetitions
80% of the time and a 2/10 cell 53% — and, more to the point, all three causes above were
found by comparing two harnesses rather than by counting repetitions. Amendment A13
records the change; `CARLA_DETERMINISM_PENDING.md`'s open conflict with D-7 is resolved
for this repository and remains open lab-wide.

---

## F21 — 2026-09-09, the whole of M7 re-driven: 262 of 263 sub-interval drives reproduce, and the one that did not is an instrument defect

Every witness drive in the study was run a second time, on the same committed networks
against the same committed verdicts, twelve hours apart on independently restarted
servers. `tools/rerun_compare.py` compares the two passes on the only thing D-7 permits
comparing: **whether a cell's verdict moved**, not whether its numbers did.

| | |
|---|---|
| artifacts re-driven | 21 |
| sub-interval drives compared | 263 |
| **cell verdicts that flipped** | **1** |
| artifacts whose agreement count reproduced exactly | 20 of 21 |
| the exception | `P_pts`/lead, 5/17 → 6/17 |

This is the closed-loop analogue of F20. F20 measured that the verifier reproduces its
102 verdicts with a margin floor of 0.0038 × threshold; this measures that the simulator
reproduces 262 of 263 drive verdicts, and that the 263rd is not the simulator.

### The one flip, and why it is a bug rather than a rate

`P_pts`/lead [+0.779°, +0.026°], driven at +0.403°, went 10/10 → 9/10. Nine of the ten
repetitions are identical to the pass they replace to the recorded precision — brake at
377.19 ft, rest at 325.97 ft. The tenth braked at **378.98 ft**, exactly one frame
earlier at 25 mph, and was scored a standoff failure with a null resting gap.

The standing rule is that repetitions which disagree are a bug until proven otherwise.
They were:

`one_run` records the resting gap at the TOP of its loop, guarded by `braking`, which on
that iteration still holds the value from the previous one. A run that latches the brake
and reaches the stop test **in the same iteration** therefore falls out of the loop with
`rest_gap_ft` still `None`, and `standoff_ok` is defined as `rest_gap_ft is not None and
rest_gap_ft >= d_margin`. So a vehicle that stopped **379 ft short of a stationary lead**
was recorded as having failed to hold a 3.28 ft standoff.

It can only happen when the policy latches on the loop's first iteration, before
`set_target_velocity` shows up in `get_velocity` and while the ego still reads as
stationary — which needs a nuisance brake so extreme that it fires before the vehicle has
moved. `P_pts` near the horizon brakes at 379 ft of a 52 ft required range, so it is the
one arm in the study that can reach it. Three runs of 2,764 did:
`witness_P_pts_lead` [+0.779°, +0.026°] once, and `witness_P_pts_lead_atwitness`
[+0.026°, +0.000°] twice.

**Fixed** in `tools/run_policy.py`: the resting gap is recorded on the exit path as well
as at the top of the loop, and each run now also records `brake_step`,
`speed_at_brake_mps` and `top_speed_mps`, so a run that braked before the vehicle moved is
visible in the artifact rather than only inferable from a null field.

### What it would have cost

The defect adds one to `P_pts`/lead's hazard agreement, 5/17 → 6/17, which is a number
the study reports and the paper's Table 4 carries. It survives every numeric check in the
repository: the cell is FALSIFIED either way, the drive is a nuisance brake either way,
and 9/10 with a Wilson interval of [0.596, 0.982] reads like an ordinary marginal cell.
Nothing would have found it except driving the same thing twice and refusing to average.

This is the fourth time in this repository that a defect was invisible in the statistics
and obvious in one record, and it is the reason the re-drive was worth its wall clock.

### What it does NOT excuse

Twenty of twenty-one artifacts reproduced their agreement count exactly, on a simulator
D-7 says can never render two identical frames. That is a statement about the policies as
much as the harness: per D-10 a marginal policy amplifies the render floor into a flipped
verdict, and 262 of 263 cells did not. The cells that remain sensitive are catalogued in
F22, and none of them is sensitive for a reason a larger sample would fix.

---

## F20 — 2026-09-08, the verifier has its own reproducibility floor, and it is 50x smaller than the band where the margin stops meaning anything

Re-running the property S certificates on **identical networks and identical captured
frames** — same model hashes, same knots, same branch-and-bound budget — does not
reproduce the margins bit-for-bit. alpha-CROWN's alpha optimisation runs on the GPU and
its early-stopping path is not deterministic across processes.

| | |
|---|---|
| sub-intervals recomputed | 102 |
| **verdict changes** | **0** |
| margins that moved at all | 16 of 102 |
| median relative move, among those | **0.092%** |
| largest relative move | 1.84%, on a margin of 0.109 |
| largest **absolute** move | 0.0038 × threshold |

**Nothing flipped.** Every CERTIFIED stayed certified and every FALSIFIED stayed
falsified, including the four sub-intervals whose margins sit inside F17's uninformative
band — `P_cont`/lead [+1.391°, +0.779°] at 1.0080 → 1.0079, `P_pts3`/lead
[+18.743°, +12.542°] and [+5.298°, +4.198°] unchanged to four decimals, and `P_cont`/ped
[−0.961°, −29.554°] at 1.0142 unchanged.

### Why this matters for F17

F17 measured that between about **1.00× and 1.05×** of threshold the certificate's margin
carries no information about whether the drive holds: a sub-interval certified at 1.0318×
crashed 10/10 while four thinner ones drove clean. The obvious objection is that the
margin is simply noisy at that scale, in which case F17 would be a statement about the
verifier rather than about the world.

It is not. The verifier's own floor is **0.0038 absolute**, and the band F17 identifies is
**0.05 wide** — a factor of about thirteen, and fifty times the median jitter. The margin
is stable to far finer resolution than the band in which it stops predicting. So F17's
finding is about the transfer from captured frames to a live-rendered drive, which is
where it was always located, and not about bound reproducibility.

This is the verification analogue of D-7. D-7 measured that rendering never reaches
bit-identity and therefore closed-loop numbers stay rates over repetitions; this measures
that bound computation does not either, and quantifies how much of the margin that costs.
The answer is: not enough to move a verdict, on any of 102 sub-intervals.

### How it was found

Not by looking for it. `bash scripts/rebuild_all.sh endpoints` starts at the endpoints
stage and runs **every stage after it**, so it recomputed the gates and the certificates
as well. The witness stage then refused to drive — *"verify_P_pts_lead.json is modified
since commit: an uncommitted verdict is not a prediction"* — which is the blind-protocol
guard doing exactly its job on a change nobody intended to make. The accident produced a
controlled re-run of the whole verifier, so it is recorded rather than discarded.

---

## F19 — 2026-09-08, driving the plate: one arm violates the nuisance limit for reasons that are not the plate, and one arm violates it because of the plate

**Disposes:** ledger cell 5 (witness)

The witness column for cells 5 and 6, plus the control the cells need to mean anything:
the identical 50 mph approach with **no steel on the road** (`plate_run(place=False)`).
Six drives, 17 sub-intervals each, 10 repetitions each — 1,020 runs.

| arm | plate agreement | verdict mismatches vs the control | median peak difference |
|---|---|---|---|
| `P_pts` | **17/17** | **0** of 17 | 1.06% |
| `P_pts3` | **17/17** | **0** of 17 | 5.49% |
| `P_cont` | 16/17 | **1** of 17 | 0.40% |

### `P_pts`: a real FMVSS 127 nuisance violation, 60x the worst test point, and the plate has nothing to do with it

| driven at | peak commanded deceleration | of the 2.453 limit | passed |
|---|---|---|---|
| daylight (regulatory) | 0.034 | 1.4% | 10/10 |
| darkness, lower beam (regulatory) | 0.056 | 2.3% | 10/10 |
| darkness, upper beam (regulatory) | 0.037 | 1.5% | 10/10 |
| **+0.403°** | **3.381** | **138%** | **0/10** |
| **+0.013°** | **3.053** | **124%** | **0/10** |

At all three lighting conditions the standard actually tests, this policy commands about
2% of the nuisance limit — it does essentially nothing. At an illumination **between**
them it commands **60 times more** and exceeds the limit by 38%. The certificate named
both sub-intervals and was committed before the drive.

**And it is not the plate.** With the steel removed the same two illuminations give
**3.382** and **3.055** — 0.06% and 0.09% away — and every one of the 17 pass/fail
outcomes is identical. `P_pts` brakes at 1.38x the nuisance limit on an empty road at
50 mph because of the light, and FMVSS 127's own false-activation test, run at its own
three lighting conditions, cannot see it.

That disposes cell 5's witness contradiction. The pre-registration expected PASS because
it expected CERTIFIED; the drive confirms the falsification, and the ruled-out candidate
that mattered — *the policy is responding to the steel* — is ruled out by the control at
drive level, not only in the certificate (F18).

### `P_cont`: the section 9 sleeper, awake, and it IS the plate

> **WITHDRAWN 2026-09-09, see F24.** Everything in this subsection was measured on a
> driver running at 10 Hz where PROTOCOL section 3 specifies 20. At the specified rate
> `P_cont` does not brake on the plate at +0.013°: it peaks at 2.00–2.18 m/s² against a
> 2.4525 limit and crosses the plate still moving, ten repetitions out of ten. The text
> below is left as collected, because a disposition explains a contradiction and does not
> erase it, but **nothing in it may be quoted**.

One sub-interval in 102 behaves differently with the steel there:

| `P_cont` at +0.013° | peak | of the limit | passed |
|---|---|---|---|
| plate present | **2.711** | **110.5%** | **7/10** |
| plate removed | 2.221 | 90.6% | 10/10 |

The plate adds **22%** to the peak demand — 2.221 to 2.711, measured against the control —
and carries the policy across the standard's threshold. That is false activation in the strict sense — the vehicle brakes *because of
the steel* — and `P_cont` is the only arm that does it. PROTOCOL §9 named this cell the
sleeper on the grounds that the continuum-trained policy sees more braking data and might
be the more trigger-happy, *"a trade no single-sided test can see"*. It is right, and it
took a two-sided test at an illumination the standard does not visit to see it.

### The one certified-then-failed sub-interval in the study, and where it is

That same cell is the only place in the entire study where a CERTIFIED sub-interval failed
when driven: certified at **0.9963x** of the limit, driven at **1.105x**. Two things
already on record predicted it, from different directions:

- **A6.** [+0.026°, +0.000°] is the **uncovered** sub-interval — no step size meets the
  blend tolerance across the horizon discontinuity, so a bound there quantifies over
  images the renderer does not produce, and PROTOCOL says a CERTIFIED verdict there must
  never be counted as coverage. `record_cells` excludes it, so cell 6 still reads
  *"CERTIFIED in all 16 covered sub-intervals, drove clean in all 16 driven"*. **This is
  the first direct empirical confirmation that the uncovered sliver genuinely cannot be
  certified** — until now it was an argument from the blend metric.
- **F17.** 0.9963x sits inside the band F17 measured as carrying no information: between
  about 1.00x and 1.05x of threshold the margin does not predict the drive. It did not.

Both were written down before this drive. Neither was written down *because* of it.

`docs/figures/plate_gap.svg` draws all of it: 51 bars against the limit line, with the
plate-removed control as a tick on each. `tools/make_plate_figure.py` builds it, and the
bar geometry is checked against `plate_gap_data.json` rather than trusted.

### What cells 5 and 6 establish, stated carefully

- **No arm false-activates on the trench plate at any illumination FMVSS 127 tests.** All
  nine endpoint cells, 10/10, peak 0.030–0.375 against a 2.453 limit.
- **Two of three arms violate the nuisance limit at illuminations between those tests,
  and for `P_pts` and `P_pts3` the plate is irrelevant to it** — the same violation occurs
  on empty road within 0.9%.
- **`P_cont` alone brakes for the steel**, in one sub-interval, and only there does the
  plate change a verdict. Below the limit, bar-to-control differences are run-to-run
  variation on demands two orders of magnitude under it — 0.089 against 0.011 is a 736%
  relative change and decides nothing. The only difference that means anything is one
  that crosses the line, and there is exactly one.
- The sub-interval where that happens is the one the disturbance family cannot represent,
  so the certificate cannot speak to it. The conformal guarantee (F14) is what covers that
  sliver, and this drive is what it is covering.

---

## F18 — 2026-09-08, cells 5 and 6 close: nobody false-activates on the trench plate, and the one arm that looks like it does not

The ledger has been 4 of 6 since M0. It is now **6 of 6**, and the two false-activation
cells say something the endpoint drives alone could not.

**Disposes:** ledger cell 5 (FV)

### What was measured

FMVSS 127's false-activation scenario: an ASTM A36 steel plate tiled to exactly
8.0 × 12.0 ft, approached in lane at 50 mph. Property A over the whole illumination axis
— **52 poses from 2.179 m to 59.178 m**, every captured pose at any range, against the
standard's own 0.25 g limit of 2.4525 m/s².

And the control that makes any of it attributable: `none_plate`, the identical poses with
the plate **removed**.

| arm | plate: covered certified | worst covered | uncovered sliver | **plate removed** |
|---|---|---|---|---|
| `P_cont` | **16/16** | 0.9825× | CERTIFIED 0.9963× | 16/16, worst 0.9850× |
| `P_pts3` | 15/16 | **1.3634×** | CERTIFIED 0.9974× | 15/16, worst 1.3652× |
| `P_pts` | 15/16 | **2.0872×** | FALSIFIED 3.8309× | 15/16, worst 2.0775× |

**Every verdict is identical with the plate present and with it removed, and every bound
agrees to within 0.5%.** Not one sub-interval falsifies because of the plate.

The drives agree: all nine cells — three arms across all three FMVSS lighting conditions,
ten runs each — cross the plate at 50 mph **10/10** without braking, peak commanded
deceleration 0.030 to 0.375 m/s² against the 2.453 limit.

### Cell 5's contradiction, disposed

Cell 5 pre-registered CERTIFIED and measured FALSIFIED over 0.753°, the sub-interval
[+0.779°, +0.026°], at 2.0872× the nuisance limit.

| candidate | verdict | how |
|---|---|---|
| **`P_pts` false-activates on the steel plate** | **ruled out** | the control. With the plate removed the same sub-interval falsifies at 2.0775× and the same uncovered sliver at 3.8457×, differences of 0.5% and 0.4%. The plate contributes nothing |
| an instrument defect | **ruled out** | concrete exhibited witnesses, `UNDECIDED` 0 in all seventeen, and the same tool on the same frames certifies `P_cont` 16/16 |
| the certificate covers less than the cell scopes | **ruled out** | 52 poses over 2.179–59.178 m, recomputed from `states_plate.json` and checked against the artifact's own per-cell pose counts (`tools/restate_scope.py`, 0 refused) |
| the near-horizon nuisance braking of F13 | **the cause** | it is a property of the illumination, it appears on an empty road, and it is why the axis contains illuminations at which this policy brakes at nothing at all |

So the cell is falsified and **it is not false activation**. `P_pts` brakes near sun
altitude 0 whether or not there is a steel plate in front of it, and reporting that as a
response to the plate would be exactly the attribution error the control exists to prevent.
The pre-registration expected CERTIFIED because it was reasoning about the plate; the
property is quantified over an axis that includes illuminations where this arm's behaviour
has nothing to do with the target.

### Cell 6 was the sleeper, and it is awake

PROTOCOL §9 calls cell 6 the sleeper: `P_cont` sees more braking data than the other arms
and might be the more trigger-happy, a trade no single-sided test can see. It is right,
in the direction it named and not the magnitude.

`P_cont` is the **loudest** arm on the plate at the regulatory endpoints — 0.082 to
0.375 m/s² against `P_pts3`'s 0.030–0.066 and `P_pts`'s 0.034–0.056, four to eleven times
higher — while still passing 10/10 far under the limit. And its certificate carries the
**thinnest margins of any arm**: 0.9825× on [+0.779°, +0.026°] and 0.9963× on the
uncovered sliver.

By F17 that is a band where a bare pass says nothing: between about 1.00× and 1.05× of
threshold the margin carries no information about what the vehicle does. **Cell 6 closes
as CERTIFIED with essentially no margin**, and that is the result, not a comfortable pass.
The continuum-trained policy buys its clean must-brake record with a must-not-brake budget
it very nearly spends.

### Two instrument defects found closing these cells

Both would have produced a finished-looking ledger row that said the wrong thing.

- **`record_cells` took the minimum margin for both properties.** For property S the
  dangerous end is the lowest bound; for property A it is the highest. Cell 5's worst
  covered sub-interval is at 2.0872× — a bound at twice the nuisance limit — and the
  ledger's margin column read **−0.0021**, which is not merely wrong but reassuring. Now
  property-aware, with the direction written into the row.
- **Every property A artifact misstated its own scope.** `verify.py` recorded
  `poses_inside_r_req` for both properties, and property A quantifies over every captured
  pose out to 60 m: `verify_P_cont_none_A.json` claimed "104 poses inside r_req
  (15.846 m)" for poses spanning 2.398 to 59.962 m, a scope **3.8× narrower** than the one
  verified. Every verdict was right the whole time; only the artifact's claim about itself
  was wrong, which is the version that survives longest because nothing downstream ever
  disagrees with it. `tools/restate_scope.py` rebuilds the scope from the primary data and
  checks it against each artifact's own per-cell pose counts before touching anything —
  72 artifacts restated, **0 refused**, so it is confirmed a labelling defect and not a
  measurement one.

### What is still open on these cells

The witness drives. The verdicts above are committed to git before any of them, which is
what makes them predictions. `P_pts` and `P_pts3` each have one falsified covered
sub-interval to drive, and the certified ones need driving too — a test that only visits
flagged cells cannot tell a working certificate from one that flags everything.

---

## F17 — 2026-09-08, both ledger contradictions are one quantifier — and fixing the quantifier makes the certificate worse

**This is the disposition PROTOCOL section 8 requires**, for both open contradictions. They
share a cause, it is in how the property is *stated* rather than in the certificate or the
vehicle, and it is measured rather than argued (`tools/latch_window.py`,
`tools/latch_window_report.py`). The repair it suggests was then built and **it fails**,
which is the more useful half of the finding.

**Disposes:** ledger cell 1 (witness), ledger cell 3 (FV)

| cell | pre-registered | measured |
|---|---|---|
| 1, `P_pts` / ped cross | witness **FAIL** | **PASS** 10/10 in all thirteen falsified sub-intervals, at midpoints and at the certificate's own exhibited witnesses |
| 3, `P_cont` / ped cross | FV **CERTIFIED** | **FALSIFIED** over 0.753°, the single sub-interval [+0.779°, +0.026°] |

### What was ruled out

| candidate | verdict | how |
|---|---|---|
| the drives used a different network than the verification | **not the cause** | `model_sha256` identical across certificate, both witness passes and the latch-window artifact; `record_cells.py` and `latch_window_report.py` both refuse to join across a mismatch, a check that exists because the join once manufactured a soundness violation out of one |
| the falsification is a loose bound rather than a real counterexample | **not the cause** | `certify_pose` returns FALSIFIED only when a forward pass at a concrete `s` falls below the threshold; a failed bound with no exhibited counterexample returns UNDECIDED. Both cells report `UNDECIDED: 0` in all seventeen sub-intervals |
| the drives never visited the falsifying illumination | **not the cause** | the `atwitness` pass exists for this and drove all thirteen falsified sub-intervals at their own exhibited witness `s`. All thirteen passed 10/10 |
| the criterion folds a property A condition into a property S verdict | **not the cause** | that was F9 and it is fixed: `passes_protocol` is section 7's frozen criterion, `passes_no_nuisance` is reported beside it and never inside it |
| cell 3 is one seed's draw | **explains the frequency, not the reason** | over ten matched seeds `P_cont`/ped certifies 15 or 16 of 16 — eight of ten certify all sixteen and **two of ten land on exactly this 0.753°** (F16). CERTIFIED was the right modal pre-registration and seed 0 drew the minority, which says nothing about why the sub-interval falsifies |
| **property S and the closed-loop criterion do not quantify over the same thing** | **the cause** | below, measured |

### The quantifier

Write `out(i, s)` for the network's commanded deceleration at pose `i` under illumination
`s`, and `th` for the latch threshold. `verify.py` and `run_policy.py` already share that
threshold to the digit — `a_max_g_worst × 9.81 × BRAKE_THRESHOLD_FRACTION` = 2.476 m/s² —
so this is not a mismatch of values.

    property S, as section 7 states it and verify.py computes it:
        FORALL i inside r_req.  FORALL s in I.  out(i, s) >= th

    what section 7's CLOSED-LOOP criterion needs:
        FORALL s in I.  EXISTS i in the latch window.  out(i, s) >= th

`run_policy.one_run` latches once and then holds full braking, so one pose clearing the
threshold early enough is the whole requirement: every pose after the latch is already
irrelevant, and every pose too late to stop within `d_margin` was irrelevant before it.
**The first formula implies the second; the second does not imply the first.** A FALSIFIED
property S is therefore not, on its own, a prediction that the drive fails, and cell 1's
`witness: expected FAIL` was reading it as one.

That is F9's defect on a different axis. F9 was the *criterion* silently folding in a
property A condition; this is the *property* silently quantifying over twenty-five poses
where the vehicle needs a handful. Both make the certificate look wrong when it is
answering a strictly stronger question.

### The latch window, from primitives and never from the drives

Sizing the window on the observed stops and then explaining the observed stops with it
would be circular, so it comes from `braking.json` alone: the **worst** measured stop at
25 mph is 44.71 ft, which already carries `t_lat`, plus `d_margin` 3.28 ft. A latch at
47.99 ft or more therefore stops in time. That is poses 79–80 on the pedestrian approach
and 79–81 on the lead approach, out of the twenty-five poses inside `r_req`.

The drives agree with that arithmetic without having been used to produce it: over 610
non-premature braking runs on the lead scenario the distance from latch to rest is
**37.56 ft in every single one**, against the primitive's 39.10 ft of braking travel once
its 5.61 ft of latency travel is removed — 3.9% apart, in the safe direction. The window
derived from primitives is a strict subset of the one the vehicle actually has.

### Cell 3, disposed

`P_cont`/ped is falsified at **witness pose 87, 36.77 ft** — four poses beyond the last
range at which a latch could still meet `d_margin`, and a range the vehicle occupies only
after it has already been braking for 14.6 ft. The drives say exactly that: `P_cont`/ped
latches at **pose 79, 51.4 ft, in all seventeen sub-intervals including both falsified
ones**, and comes to rest 14.25 ft from the walker against a 3.28 ft requirement.

Certifying the disjunction instead, `P_cont` **latches in time in 17 of 17 sub-intervals
on both scenarios**, at margins of 1.06× to 2.10× — including the falsified
[+0.779°, +0.026°] at 1.0634×, and including the A6-uncovered horizon sliver. The
pre-registration and the measurement were disagreeing about a pose the vehicle had
already passed under braking.

### Cell 1, disposed — and only partly explained

Of the thirteen falsified `P_pts`/ped sub-intervals, the disjunction certifies **five**,
and those five drove clean, which is what it predicts. It does not explain the other
eight, and four of those are near-horizon nuisance braking where the vehicle latches at
**384 ft** — outside `r_req` entirely, where no property quantified inside `r_req` can
speak to it at all.

What settles the cell is the direction of the disagreement rather than a complete causal
account. Across cell 1's 390 drives there is **not one contact and not one failure to
brake**; every disagreement is the certificate being more pessimistic than the vehicle.
The unsafe direction — certified and then failed — does not occur, in this cell or in any
other, and that is the property PROTOCOL section 8 is protecting.

### The repair fails, and this is the part worth keeping

The obvious conclusion is that section 7 should state property S as the disjunction, since
that is the property the vehicle actually has. **It should not.** Certifying the
disjunction across all six arms and joining it against every drive
(`tools/latch_window_report.py`):

| | property S (conjunction) | disjunction over the latch window |
|---|---|---|
| sub-intervals driven | 102 | 102 |
| sub-intervals producing a **contact** | 9 | 9 |
| of those, flagged by the certificate | **9 of 9** | **8 of 9** |

The miss is `P_pts`/lead over [+7.715°, +5.298°], **certified to latch in time at
1.0318×**, whose endpoint illumination was then driven and produced **10 contacts in 10
runs, 9 of them never braking at all, ending 1.93 ft inside the lead vehicle.**

On the captured frames the certificate is arithmetically right: at +7.715° the policy's
demand at poses 79, 80, 81 is 1.568, 2.345 and **2.563** against a 2.476 threshold, so the
window's maximum clears by 3.5% and the disjunction certifies. The whole approach at that
illumination sits within ±5% of the threshold — the demand never exceeds 2.598 at any of
the thirty-four poses examined — and the vehicle, rendering live rather than replaying
captures, lands on the other side of it.

**The margin does not rescue this.** Four sub-intervals certified more thinly than the
crashing one — at 1.0000×, 1.0033×, 1.0231× and 1.0250× — drove perfectly clean. Between
about 1.00× and 1.05× the certificate's margin carries no information about whether the
drive holds, whichever quantifier produced it.

So the conjunction is not merely conservative. Requiring all twenty-five poses forces the
certificate away from the knife edge, and **that is what buys the 9-of-9**: property S
falsified every sub-interval that produced a contact, and the property that is formally
better aligned with the controller did not. PROTOCOL section 7 stays as written, and the
recommendation to Zach is that the disjunction be reported **beside** property S as the
quantity the agreement table is entitled to score against — not in place of it.

### The connection to queue item 10

Item 10 wanted to restate the peak-versus-sustained bet as the difference between STL's
`eventually` and `always`. The same distinction arrived here on a different axis without
being looked for: property S as written is `always` over the poses inside `r_req`, the
vehicle needs `eventually` over the latch window, and both contradictions live in the gap.
The measurement adds the part the framing does not predict, which is that the weaker
operator is also the less useful one on this harness.

---

## F16 — 2026-09-08, the seed sweep: the attribution holds at p = 0.002, and one of F12's claims does not survive it

The study's central claim is an **attribution** — that the gap between the arms is
attributable to how the illumination axis was sampled — and it rested on one seed per arm.
The sibling steering study measured that this lab's training dispersion is intrinsic and
recommended n = 20 to 60 before believing a 20% effect, so an attribution at n = 1 was not
measured at all.

Nine additional seeds, every arm seeded identically at each seed so the arms are **matched
draws** differing only in which frames they saw, property S verified for all of them:
**54 verifications, 10 matched pairs including the study's own seed 0.**

### The attribution holds, and it is not close

| comparison | scenario | median Δ certified | sign test | ranges |
|---|---|---|---|---|
| `P_cont` − `P_pts` | lead | **+12.0** | 10/10, **p = 0.00195** | **disjoint** [16,16] vs [3,7] |
| `P_cont` − `P_pts` | ped | **+11.5** | 10/10, **p = 0.00195** | **disjoint** [15,16] vs [3,11] |
| `P_cont` − `P_pts3` | lead | +11.0 | 10/10, p = 0.00195 | disjoint |
| `P_cont` − `P_pts3` | ped | +10.0 | 10/10, p = 0.00195 | disjoint |

Every one of ten matched pairs goes the same way on both scenarios, at the smallest p an
exact sign test can produce at n = 10, with **no overlap between the arms' ranges at all**.
`P_cont` certifies 16 of 16 covered sub-intervals on *every* lead seed. The claim is as
strong as this design can make it and it needs no distributional assumption.

### And a claim from F12 does not survive

| comparison | scenario | median Δ | sign test | ranges |
|---|---|---|---|---|
| `P_pts3` − `P_pts` | lead | +0.5 | 5/7, p = 0.45 | **overlap** [3,7] vs [3,7] |
| `P_pts3` − `P_pts` | ped | +1.0 | 6/10, p = 0.75 | **overlap** [2,11] vs [3,11] |

F12 reported that `P_pts3` **certifies more** of the axis than `P_pts` — 6/16 against 4/16.
Over ten seeds that difference does not exist. It was one draw, and F12 is corrected.

### What the sweep says about quoting a width

`P_pts`'s falsified width ranges **4.5° to 57.9°** across seeds on the pedestrian scenario
and 12.5° to 60.0° on the lead one. The study reports 48.3° and 50.3° from seed 0, and
those are single draws from a very wide distribution.

**The separation is robust; the width is not.** A paper may say *the regulatory-points arm
is falsified over a large band and the continuum arm is not, on ten of ten matched seeds*.
It may not say *the band is 50.3° wide* without saying which seed and what the spread is.

### What has NOT been swept

Property S certified counts only. The contact counts, the property A results and every
driving number in this study are seed-0 measurements, and the sweep says nothing about
their stability. Driving ten seeds is roughly 20 hours of simulator time and is the
obvious next question.

---

## F15 — 2026-09-08, the falsification baseline: search is cheaper, unreliable, and cannot say the thing the study sells

The first thing a Tier 1 or a reviewer says to this study is *"twenty random samples would
have found that too"*, and until now the paper had no answer because it had never run the
search. `tools/falsification_baseline.py` runs three, on `P_pts`/lead, scored on PROTOCOL
section 7's frozen criterion so a nuisance stop cannot count as a find.

| method | simulator runs to first failure | searches that found anything | failing altitudes found | wall clock |
|---|---|---|---|---|
| certificate | **0** | — | maps a **50.32°** band | 6 min |
| regulatory test points | never | **0 of 1** | none | 51 s |
| uniform random over the axis | 15 (median of those that found one) | **2 of 6** | +7.90, +7.91 | 20 min |
| surrogate-guided | **20** | 1 of 1 | +7.715 | 2 min |

**Search wins on cost to first failure, and the paper should say so.** The surrogate ranks
all 18 captured illuminations offline by the policy's own predicted deceleration — free, no
simulator — drives the worst one first, and has a contact in 20 runs. That is the honest
competitor and it beats the certificate on that metric.

**Three things it does not do.**

1. **It is unreliable.** Uniform random sampling found a failure in **2 of 6 independent
   searches** inside a 100-run budget. Four practitioners out of six would have sampled the
   axis, seen nothing, and concluded the policy was fine. The certificate is not a coin
   flip.
2. **It finds a point, not a width.** All three methods between them named three
   illuminations. The certificate maps 50.32° of violating band — 56% of the axis — and
   names 12 sub-intervals.
3. **It cannot certify absence.** Nothing a sampler does produces the statement about the
   4 sub-intervals where nothing fails, and that statement is the product.

**And the regulatory points find nothing, measured rather than asserted.** The study's
entire premise is that a compliant policy hides its failure between the test conditions;
driving exactly those conditions, 0 of 1 searches found anything, which is the same 10/10
that M4 reports and is what makes the rest of the study necessary.

The comparison to make in the paper is therefore not "certificate versus search" on
cost-to-first-failure, which search wins. It is: **a surrogate search buys one illumination
for 20 runs and a two-in-six chance of buying nothing at all; the certificate buys the
whole interval for none.**

---

## F14 — 2026-09-08, the uncovered sliver gets a guarantee after all, and it separates the policies

Amendment A6 declares `[0.026°, 0.000°]` uncovered: the disturbance family cannot represent
the horizon at any width, so a certificate there would quantify over images the simulator
would never render. The study correctly refuses to count it — and until now that left it
saying **nothing at all** about a gap in the middle of the axis which is sunset, exactly
the region the claim is about.

Split conformal calibration over 40 illuminations drawn i.i.d. from the sliver and
**rendered rather than blended**, at α = 0.05, using the k = 2 order statistic:

| arm | conformal lower bound | × threshold | verdict | samples below threshold |
|---|---|---|---|---|
| `P_cont` | **4.6023 m/s²** | 1.86 | CLEARS | **0 / 40** |
| `P_pts` | **0.0517 m/s²** | 0.02 | does not clear | **40 / 40** |

**The method separates the two policies cleanly at the one place where no certificate is
available.** For an illumination drawn at random from that sliver, `P_cont` commands at
least 1.86× the brake decision threshold with 95% confidence, and `P_pts` does not command
anything at all.

**It is not the certificate's statement and must never be reported as one.** The
certificate says *for all* `s` in a sub-interval, with no probability attached. This says
*for a random* `s` from it, with probability 1 − α, and it assumes only exchangeability —
which holds by construction here, because the calibration illuminations are drawn
independently and rendered. The artifact carries that quantifier in words and the tool
prints it on every run.

The pairing is what makes it worth having:

| where | instrument | quantifier |
|---|---|---|
| the 16 covered sub-intervals | alpha-CROWN with branch and bound | for all `s`, sound |
| the uncovered sliver | split conformal | for a random `s`, 95% |

The tool refuses to produce a bound at all when n is too small for the order statistic to
exist — at α = 0.05 that is 19 calibration points — rather than returning a weaker number
that still looks like a result. Its coverage was validated by simulation before use:
0.9514 at n = 40 and 0.9489 at n = 19 against a 0.95 target.

---

## F13 — 2026-09-08, the horizon braking is illumination, not glare; and for one arm it is not the horizon at all

Queue item 9 asked whether the near-horizon nuisance braking follows the sun's ALTITUDE
(illumination, generalises, the study's point) or its AZIMUTH (glare, an artifact of this
site's heading, does not generalise). F6's brightness spike at exactly 0.000° made glare
the prime suspect. `tools/horizon_sweep.py` sweeps the band on an EMPTY road reading the
policy's commanded deceleration, then repeats it with the sun rotated 90° and 180° at
identical altitude.

**It is illumination.** Rotating the sun out of the direction of travel does not remove the
effect — it makes it slightly worse. For `P_cont`/lead:

| arm | peak in the ±6° band | above +12° | at |
|---|---|---|---|
| default azimuth | 0.335 | 0.159 | +5.5° |
| rotated 90° | 0.690 | 0.045 | +1.0° |
| rotated 180° | 0.586 | 0.031 | +1.0° |

The band is 2 to 15× the out-of-band baseline and the ordering is unchanged by azimuth, so
the effect is a property of low-sun illumination and generalises. `P_cont` never comes
close to the 2.476 m/s² decision threshold, which is why it has zero nuisance stops in the
drives and 16/16 on property A.

### For `P_pts3` on the pedestrian scenario it is not a horizon effect at all

The same sweep on the arm that IS falsified for property A over 89.22°:

| sun altitude | +30° | +12° | +5° | +1° | 0° | −3° | −30° |
|---|---|---|---|---|---|---|---|
| max demand, empty road | **4.130** | **3.145** | **3.351** | 2.425 | **3.334** | **4.730** | **4.869** |

**31 of 33 sampled illuminations exceed the decision threshold, including full daylight.**
The demand above +12° is 4.130 against an in-band peak of 4.866. There is nothing localised
to the horizon to explain: this policy brakes on an empty road essentially everywhere, and
the two altitudes that do *not* trigger it (+1.0° and +0.5°) are the exception.

This is amendment A10's position confound returning in a policy that HAS the no-target
control in its training set. A10 fixed it by adding `none`-scenario frames labelled zero at
every range; `P_pts3` has them, sees three lighting conditions rather than two, and brakes
at an empty road anyway. Whatever the third condition bought at the endpoints, it did not
buy the ability to tell a pedestrian from a road.

### The tool told me the wrong thing first, and the fix is recorded

The verdict logic went straight to the azimuth comparison and reported "ILLUMINATION, not
glare" for `P_pts3` — literally true, and beside the point, because there was no horizon
localisation to attribute to anything. A question of the form *"is this effect A or B"*
cannot be asked before establishing that the effect exists. The tool now checks whether the
in-band peak is meaningfully above the out-of-band baseline first, and says
**NOT A HORIZON EFFECT** when it is not.

---

## F12 — 2026-09-08, training on the whole regulatory matrix made the policy worse in BOTH directions

`P_pts3` was added to answer the cheapest question that could have sunk this study: does
the dusk gap close when the policy has seen every lighting condition FMVSS 127 tests? It
does not. It is worse than that.

`P_pts3` is trained on all three regulatory lighting conditions — daylight, darkness with
lower beam, darkness with upper beam — against `P_pts`'s two. Identical architecture,
recipe, sample count after equalising, and the same seed. It passes **all three** regulatory
endpoint tests, on both hazard scenarios, 10/10, on PROTOCOL section 7's frozen criterion.

Then:

| | `P_pts` (2 conditions) | `P_pts3` (all 3) | `P_cont` (continuum) |
|---|---|---|---|
| property S certified, lead | 4/16 | **6/16** | 16/16 |
| property S certified, ped | 4/16 | **3/16** | 15/16 |
| property S falsified width, lead | 50.32° | **43.02°** | 0° |
| property A certified, empty road | 14/16 | **16/16** | 16/16 |
| property A certified, ped poses | 12/16 | **1/16** | 15/16 |
| property A falsified width, ped poses | 2.83° | **89.22°** | 0.75° |
| contacts when driven, lead | 10 | **40** | **0** |
| contacts + nuisance stops, ped | 0 + 40 | 18 + 32 | **0 + 0** |

**It crashes four times as often** — 40 contacts against 10 when the certificate's own
witnesses are driven.

> **Corrected 2026-09-08 by the seed sweep (F16).** This finding originally also said
> `P_pts3` *certifies more of the axis* than `P_pts`, on 6/16 against 4/16 at one seed.
> Over ten matched seeds that difference is **not there**: median +0.5 and +1.0
> sub-intervals, sign test p = 0.45 and 0.75, and the two arms' ranges overlap completely.
> The certified-count comparison between the two regulatory arms was one draw. The
> contact count and the property A result below are single-seed measurements too and are
> labelled as such; only the `P_cont` comparison has been swept.

**And on the pedestrian scenario it is falsified for property A across 89.22° of a 90°
axis** (one seed; property A has not been swept). One sub-interval of sixteen survives. That is the certificate saying this policy
will brake on an empty road at essentially every illumination, and the drives exhibit
exactly that: it brakes at 287.6 ft in daylight and stops 250 ft short of the pedestrian,
ten runs of ten.

### Why this matters more than the original result

The study's claim was that training against a discrete test matrix creates gaps at the
matrix's own gaps. The obvious objection is *"then sample the matrix properly"*. `P_pts3`
samples it properly — every lighting condition the standard names — and comes out failing
in **both** directions at once: it does not brake when it should across 43° of the axis,
and it brakes when it should not across 89°.

Adding a third training condition did not interpolate between the conditions. It bought
margin at the endpoints the standard checks and lost the road between and around them.

**This is only visible because both properties were verified.** A study that checked only
must-brake would have reported `P_pts3` as the better regulatory arm — it certifies more
sub-intervals than `P_pts` — and shipped a policy that stops dead 250 ft from a pedestrian
in broad daylight. PROTOCOL section 9 calls property A's cells "the sleeper"; this is the
sleeper, and it is louder than the cell it was written about.

### The direction of every disagreement is still safe

Across all six cells, both drive passes, and every one of 96 covered sub-intervals:
**nothing was certified and then failed.** Every certificate/drive disagreement in this
study is the verifier calling unsafe something that drove cleanly.

---

## F11 — 2026-09-08, D-8 measured here at last: physics bit-exact, rendering never, and this policy does not amplify

Rule D-8 says determinism must be measured OPEN LOOP, and this study had never done it —
it adopted the `carla-determinism` fixes and inherited every claim about run-to-run noise
from the steering study's Town06 branch, a different map, a different camera and a
lane-keeping policy. `tools/determinism_probe.py` cuts the feedback: the vehicle is driven
by a command sequence that is a pure function of the step index, deliberately changing on
every step through the acceleration phase, while the policy sees every frame and its
output is computed and recorded but never applied.

Three repetitions, a fresh server before each, 168 steps, `P_cont`/lead at −30° with lower
beam:

| stream | result | rule |
|---|---|---|
| pose across reps | **identical, 168 of 168 steps, 0.000000000 m** | D-1, D-2 |
| raw frame SHA-256 | **different, 0 of 168 identical** | D-3, D-7 |
| commanded deceleration, computed not applied | max spread **0.00236 m/s²**, median 0.00013 | D-10 |

**The physics is bit-exact.** Acknowledged control and explicit substepping deliver exactly
what they promise on this map and this vehicle. That is now measured here rather than
assumed from Town06.

**The rendering is never bit-identical**, in exactly the way D-7 says it cannot be, and
that rule's repetition floor is not in dispute.

**This policy does not amplify the render floor, and that is the number the study needed.**
D-10 says amplification is a property of the policy: in the steering study a 2.6e-6
steering perturbation grew to 7.6 ft of cross-track error over 349 steps, so run-to-run
spread there was a stability-margin measurement. Here, with the physics bit-exact and only
the render floor left, the commanded deceleration moves by **0.095% of the brake decision
threshold** at its worst. The AEB policy is strongly contractive with respect to the noise
the simulator cannot remove.

That explains something the study had been reporting without understanding: every
repetition of every M4 cell agreeing to 0.1 ft. It is not the harness being suspiciously
quiet, it is a contractive policy on bit-exact physics.

**What it does NOT license.** This is an open-loop measurement, and the closed loop
latches: once the demand crosses the threshold, braking is commanded at full authority and
never withdrawn. A demand perturbation of 0.0024 m/s² can only matter if it moves which
STEP the crossing happens on, and at 20 Hz and 11 m/s a step is 0.56 m. So the bound on
the closed-loop consequence is one control step, not zero — small, but not nothing, and it
is why the repetition count stays where PROTOCOL section 1 puts it.

**Recorded for the D-7 versus A-4 question, and not acted on.** `CARLA_DETERMINISM_PENDING`
flags an unresolved conflict between D-7's floor of ten repetitions and the steering
study's amendment A-4, which cut it to three on a fully enforced harness. This is the
AEB-specific datum that argument has been missing: the policy whose marginality motivated
the floor is not this policy. Resolving it still needs the package's section 4 amendment
procedure and it is Zach's call, not a study's.

---

## F10 — 2026-09-08, the in-between gate carries no information about the risk it exists to bound

PROTOCOL section 4 requires the in-between check and says the behavioural version is the
one that decides whether the disturbance family may be used at all. The certificate
quantifies over BLENDS; the witness drives happen at RENDERS; the gate is what stands
between them, and the study has been using it as a pass/fail at 1.0.

**It does not predict anything.** Over 96 covered sub-intervals — three arms, two hazard
scenarios, each joining a certificate, a gate value and a witness drive on the same
network:

| | n | min | median | max | mean |
|---|---|---|---|---|---|
| gate where certificate and drive AGREE | 54 | 0.021 | 0.110 | 0.341 | 0.125 |
| gate where they DISAGREE | 42 | 0.021 | 0.079 | 0.456 | 0.124 |

Point-biserial correlation between the gate value and disagreement: **r = −0.005**. The
two distributions are indistinguishable. A sub-interval where the blend moves the policy
four times as far as another is no more likely to be one where a blend-based certificate
fails to transfer to a rendered drive.

**What this does and does not license.** It does not say the family is unsound: no
sub-interval anywhere in those 96 was certified and then failed. It says the gate is not
evidence *for* the family, and the paper must stop implying that it is. Passing the
in-between check at 0.16 rather than 0.68 is not a statement about how far a certificate
transfers, because transfer is uncorrelated with the number.

The check still has one job it demonstrably does: it caught `[+12.542, +7.715]` at 1.016
and PROTOCOL section 4's repair fixed it (F7). Detecting a sub-interval where the blend
can flip a decision *in isolation* is worth having. Predicting where the certificate and
the vehicle will disagree is a different claim and the gate does not support it.

**Two instrument defects found while getting this number**, both silent under-coverage of
exactly the kind this study keeps finding:

- The tool parsed `verify_<policy>_<scenario>.json` by splitting on `_`, and every policy
  name contains one. `verify_P_pts_lead` parsed as policy `P`, scenario `pts_lead`; the
  gate path built from that does not exist, the pair was skipped by a `continue`, and the
  tool reported a correlation over whatever happened to survive — 3 pairs of 6. Now parsed
  against the known arm names.
- Run against pre-F9 witness artifacts it happily produced r = 0.14 and four
  "certified then failed" rows, both artifacts of scoring property S against a count that
  folds in nuisance braking. It now refuses artifacts that predate the split.

---

## F9 — 2026-09-07, the agreement table was scoring property S against a property A condition

M7's first pass reported a **CERTIFIED sub-interval that failed when driven** — `P_cont`
on the lead scenario, `[+0.779, +0.026]`, certified at 1.08x, drove 9/10. That is the
unsafe direction and the one outcome this study must never wave through, so
`tools/record_cells.py` refuses to summarise it and PROTOCOL section 8 requires a
disposition. Here it is, and the certificate is not at fault.

**The run that "failed" stopped 306 ft from the lead vehicle.** It did not fail to brake;
it braked absurdly early. Classifying every failing drive in the first pass:

| driven at | verdict | passed | contacts | premature | min gap |
|---|---|---|---|---|---|
| P_pts/lead **+8.921°** | FALSIFIED | 0/10 | **10** | 0 | **−1.93 ft** |
| P_pts/lead +0.403° | FALSIFIED | 0/10 | 0 | 10 | ≥ 306 ft |
| P_pts/lead +0.013° | FALSIFIED | 0/10 | 0 | 10 | ≥ 306 ft |
| P_pts/ped +1.085° | FALSIFIED | 0/10 | 0 | 10 | ≥ 306 ft |
| P_pts/ped +0.403° | FALSIFIED | 0/10 | 0 | 10 | ≥ 306 ft |
| P_pts/ped +0.013° | FALSIFIED | 0/10 | 0 | 10 | ≥ 306 ft |
| P_cont/lead +0.403° | CERTIFIED | 9/10 | 0 | 1 | 306 ft on that run |
| P_cont/lead +0.013° | CERTIFIED | 0/10 | 0 | 10 | ≥ 306 ft |

**Exactly one is a must-brake failure**: `P_pts`/lead at +8.921°, where the vehicle ended
**1.93 ft inside** the lead vehicle, on all ten runs, in the sub-interval the certificate
falsified at 0.03x. Every other failing drive is nuisance braking near the horizon.

### The criterion, and where the drift came from

PROTOCOL section 7 states the closed-loop pass in full: *"no contact and standoff at least
`d_margin`, over at least 10 repetitions."* `tools/run_policy.py` adds a third condition,
`PREMATURE_MULTIPLE`, on the reasoning that *"a policy that stops the moment it starts
satisfies 'no contact with standoff', but it has not performed AEB, it has performed a
nuisance stop"*. That reasoning is right and the condition is worth having. **It is also a
must-NOT-brake condition, which is property A, and property S says nothing about it.**

Scoring a property-S verdict against a pass criterion that silently includes a property-A
condition is comparing two different quantities, and here it manufactured a soundness
violation out of a policy braking too early. This is the trap the steering study wrote
down as its section 7: *check what your criterion quantifies over, and make the comparison
cover the same set*.

**The fix is to report both, not to drop either.** `drive_witness.py` now records
`passes_protocol` (section 7's frozen criterion, which is what a property-S verdict is
scored against), `passes_no_nuisance` (with the prematurity condition), and the per-run
contact / standoff / premature / brake-range detail, so the artifact can be re-scored
under either criterion without re-driving. Summary counts alone cannot tell a policy that
hit the target from one that stopped 300 ft early, and for two nights running that was the
difference between a clean result and a soundness violation.

### What it says about the study, beyond the bookkeeping

The near-horizon behaviour of BOTH policies is nuisance braking, not failure to brake.
That is a property A phenomenon and it is the sleeper PROTOCOL section 9 names: *"6 is the
sleeper: `P_cont` sees more braking data and may be the more trigger-happy, which is a
trade no single-sided test can see."* The property S certificates say the policies brake
in time; the drives say that near the horizon they brake at 300 ft. Both are true, and
only running both properties makes the pair visible.

---

## F8 — 2026-09-07, the verifier was not doing branch and bound, and it cost the negative control

`PROTOCOL.md` section 6 has said "Bounds by **alpha-CROWN with input-space branch and
bound** over `s`" since M0. `tools/verify.py` made a single `compute_bounds` call per pose
over the whole sub-interval and never split anything. On a wide sub-interval that is not a
certificate about the policy; it is a report on how loose one interval bound is.

Measured on `P_cont`/lead over `[-0.961, -29.554]`, the 28.6-degree darkness sub-interval,
worst lower bound against the number of input sub-domains:

| sub-domains | worst lower bound | × threshold | verdict |
|---|---|---|---|
| **1** (what the file did) | 2.2321 | **0.90** | FALSIFIED |
| 2 | 3.4548 | 1.40 | CERTIFIED |
| 4 | 4.1036 | 1.66 | CERTIFIED |
| 8 | 4.2932 | 1.73 | CERTIFIED |

**One bisection flips it**, and the bound converges to about 1.73x. The policy was never
the problem.

### What it would have cost the study

Without branch and bound the four property-S cells read `P_pts` 5/16 and 3/16, `P_cont`
14/16 and 13/16. **The negative control was falsified in two sub-intervals of each
scenario**, and both were the widest ones — `[-0.961, -29.554]` at 0.90x and 0.25x, and
`[+0.779, +0.026]`. PROTOCOL section 8 says exactly what to do about that: *"Keep the
negative control alive. If `P_cont` also fails, or `P_pts` also certifies, stop and debug
rather than narrating it."* The finding underneath that instruction is that a study which
narrates it would have published "continuum training also fails at dusk" on the strength
of its own verifier being loose over a 28-degree interval.

With branch and bound: **`P_cont` is 16/16 on both scenarios**, and the contrast with
`P_pts` is attributable to axis sampling alone, which is the entire design of the ledger.

### Three outcomes, not two

FALSIFIED now requires a **concrete `s` whose actual network output violates the
property** — an exhibited counterexample. A domain that neither certifies nor produces one
within the branch-and-bound budget is **UNDECIDED** and is reported as itself.

The old code called that FALSIFIED, which merges "we exhibited an illumination where this
policy does not brake in time" with "our bound did not clear". For a tool whose product is
the sentence *here is the certified envelope*, that distinction is the entire credibility
of the result, and it is the difference between the two readings of the anticipated
reviewer challenge *"the verifier just flags everything"*. This run has **zero** undecided
sub-intervals across all four cells.

Worth recording for the write-up: **24 of the 26 exhibited witnesses sit at s = ±1**,
which is a rendered knot rather than an interpolated interior point, so almost every
falsification in this study is a claim about an illumination the simulator actually
rendered and does not depend on the blend being faithful. The two exceptions are both in
`P_pts`/lead — `[+18.743, +12.542]` and `[+0.779, +0.026]`, each at s = 0 — where the
sub-interval's endpoints satisfy the property and an interior blend does not. Those two
DO rest on the family, and the in-between gate is what licenses them: 0.156 and 0.123 of
the decision threshold at those sub-intervals.

That the rest land on knots is partly a property of the search — the concrete check samples
a domain at its ends and middle, so an endpoint violation is found first — and they remain
real counterexamples at real rendered illuminations.

### An implementation note that will otherwise be rediscovered

A fresh `BoundedModule` is built **per sub-domain**. Reusing one across sub-domains is the
obvious optimisation, and alpha-CROWN dies partway through a run with
`KeyError: '/input-23'` when its per-node alpha cache is carried across perturbation
regions. Measured, rebuilding costs 0.58 s per bound against 0.64 s with reuse, so there
was nothing to buy.

---

## F7 — 2026-09-07, the in-between gate failed at a covered sub-interval, and section 4's repair worked

The behavioural in-between check is the one PROTOCOL section 4 says decides whether the
disturbance family is usable: does the policy answer a **blended** frame the way it answers
a **rendered** frame at the same illumination? The certificate quantifies over the blends,
so a sub-interval that fails this is one where a bound is not a statement about the vehicle.

On the rebuilt axis it failed at a **covered** sub-interval, which is new — F2's failures
were all inside the horizon sliver that is excluded from the coverage claim by design:

| sub-interval | P_pts/ped | P_cont/ped | P_pts/lead | P_cont/lead |
|---|---|---|---|---|
| **[+12.542, +7.715]** | **1.016** | **0.848** | 0.123 | 0.114 |
| every other covered sub-interval | ≤ 0.37 | ≤ 0.24 | ≤ 0.24 | ≤ 0.22 |

Not noise: both policies see it, at three to five times their next-worst sub-interval. It
is also the widest sub-interval in the region where brightness falls fastest, just above
the 5-degree headlamp switch.

**Section 4's declared repair is "shorter intervals with rendered interior endpoints ...
the claim survives; only the interval length changes."** Unlike the horizon sliver, which
A6 established is a genuine kink no width fixes, this is a width problem. Splitting
`[+12.542, +7.715]` at `+10.128`:

| | before | after |
|---|---|---|
| P_pts / ped | 1.016 | **0.268** and **0.368** |
| P_pts / lead | 0.123 | 0.032 and 0.156 |
| image blend error | 0.0097 | 0.0082 and 0.0095 |

All four gates then pass over the covered axis, worst 0.156 / 0.222 / 0.506 / 0.678.

`tools/build_family_knots.py --refine` is that repair as a committed tool: it reads the
behavioural gate artifacts, splits every covered sub-interval that failed, re-measures both
halves against the image tolerance, and records in the knot file which gate failure caused
each split. **The split is applied to the shared axis, not per policy** — a sub-interval
that fails for one policy is split for both, or the two are certified over different axes
and stop being comparable, and that comparison is the whole study.

### Two defects that let a failing exit criterion look like a passing one

- `gate_behavioural.py` **returned 0 whatever the verdict**, so `scripts/rebuild_all.sh`
  walked from a failed M5 straight into verification. It now returns non-zero on FAIL.
- It judged the verdict on the worst sub-interval **including the uncovered sliver**, so
  two policies whose covered axis was fine at 0.123 and 0.222 were both labelled FAIL. A
  gate about the coverage claim cannot be failed by a sub-interval excluded from that
  claim. Both the covered worst and the failing covered rows are now in the artifact.

---

## F6 — 2026-09-07, CARLA's scene brightness is not monotone in sun altitude, and the horizon shows up twice

Found by the illumination guard ported from the steering study (NOTES section 2b), on the
first capture campaign it ever ran against. **It failed the campaign, and it was the guard
that was wrong** — but the measurement it produced is worth having, and one half of it
independently corroborates amendment A6.

### The measured curve

Mean frame brightness at capture pose 0, Town01 site 0, fixed exposure f/4.0 (A7),
headlamps below +5° per the campaign, one frame per knot:

| sun ° | +60.000 | +42.766 | +28.397 | +18.743 | +12.542 | +7.715 | +5.298 |
|---|---|---|---|---|---|---|---|
| mean | 0.5064 | **0.5282** | 0.5182 | 0.4579 | 0.4033 | 0.3366 | 0.2617 |

| sun ° | +4.198 | +3.525 | +1.891 | +1.391 | +0.779 | +0.026 | **+0.000** | −0.961 | −29.554 | −30.000 |
|---|---|---|---|---|---|---|---|---|---|---|
| mean | 0.2295 | 0.2102 | 0.1355 | 0.1082 | 0.0758 | 0.0377 | **0.0665** | 0.0496 | 0.0406 | 0.0406 |

Two things in there are not what a monotone model predicts.

**1. Brightness peaks near +43°, not at +60°.** The scene is *dimmer* with the sun near
zenith than at mid-elevation. The camera sees a large sky panel, and at 60° the sky in the
direction of travel is darker than at 43°, which more than offsets the extra road
illumination. 4.5% of the axis span.

**2. There is a spike at exactly 0.000°.** Brightness falls 0.0758 → 0.0377 approaching
the horizon, jumps to 0.0665 at zero, then resumes at 0.0496. 5.9% of the span, across a
0.026° step.

**The second one is A6 measured a second way.** A6 concluded from blend error that the
horizon is *a genuine discontinuity in the renderer's sky model, not merely a region of
high curvature*. The knot bisection independently picks out `[0.026°, 0.000°]` as the one
sub-interval that cannot meet tolerance at any width (0.0163 against a 0.01 tolerance).
The photometric signature — a different statistic, on different frames, computed by a
different tool — singles out the same sub-interval. Two measurements that share no code
agreeing on where the renderer breaks is the strongest evidence in the study that the
uncovered sliver is real and not an artifact of the bisection.

### The guard was wrong, and the repair is a magnitude test

The first version asserted that within one headlamp regime a lower sun renders a strictly
darker frame — read off A5's brightness table, which only ever covered +6° to −6°, and
extrapolated to the whole 90° axis. It is false at both ends.

Strict ordering was never the property worth asserting. Every failure this guard exists to
catch moves brightness by a LOT: a condition swap, an unsettled weather write (A4 measured
75% too bright twelve ticks in), a knot rendered at its neighbour's illumination. So the
check now bounds magnitude — no single step may run backwards by more than 12% of the axis
span, and the whole axis may not accumulate more than 25% — plus a span floor and an
extremes check. The measured axis scores 4.5% and 4.5%; rendering the +0.779° knot in
daylight would score 90%.

Inversions across a sub-interval the knot measurement itself declares uncovered are
recorded and not charged, because that declaration is the study having already measured
that the renderer is discontinuous there.

**Added at the same time, and it is the better check:** the four capture campaigns
(`lead`, `none`, `ped`, `none_ped`) render the same site at the same knots and differ only
by what stands in front of the camera. Their brightness curves must agree, and that
comparison rests on no model of the renderer at all. A knot rendered at the wrong
illumination in one campaign shows up as that campaign disagreeing with the other three at
that knot and nowhere else. `python tools/condition_signature.py` reports it and the
rebuild runs it.

### Why this is recorded rather than quietly fixed

Two of the errors in the steering follow-on programme were in the *analysis* code rather
than the experiment, and both would have inverted a conclusion. This is the same class:
a guard whose premise was an extrapolation, which would have rejected every correct
capture campaign this study will ever run. It was caught because it fired on data whose
provenance was known good, and because the numbers it printed were looked at instead of
its verdict being taken at face value.

---

## F5 — 2026-09-06, the A12 rebuild: `a_max` was an integration artifact, and the safety budget was 33% too short

**This is the disposition PROTOCOL section 8 requires.** Rebuilding the primitives on the
corrected harness moved braking authority from **0.868 g to 0.505 g** at 25 mph, and
`r_req` at 25 mph with it, from **34.7 ft to 52.0 ft**. A 42% move in the one measured
number the entire safety budget is derived from is a bug until proven otherwise. It is
now measured, and the old number is the wrong one.

### What was ruled out, and what it was

A12 changed two things in `connect()` at once, and the new desktop changed a third:

| candidate | verdict |
|---|---|
| D-2, acknowledged `apply_control` | **not the cause** |
| the RTX 4070 -> RTX 5090 migration | **not the cause** |
| D-1, explicit substepping | **the cause, entirely** |

Measured by sweeping substeps with D-2 held ON and everything else fixed
(`tools/substep_convergence.py`, `results/carla/substep_convergence.json`). Before A12
this study inherited CARLA's default substepping, which at `fixed_delta_seconds = 0.05`
integrates the whole 50 ms step in **five** substeps. Setting exactly that today, on the
new GPU and through the acknowledged-control path, reproduces the published number to
four decimal places:

| substeps | step | stop | a from TIME | a from DISTANCE | disagreement |
|---|---|---|---|---|---|
| 2 | 25.00 ms | 10.6-14.9 ft | 1.77-2.07 g | 1.43-1.97 g | non-repeatable, impossible |
| 4 | 12.50 ms | 33.3 ft | 0.9867 g | 0.678 g | **+45.5%** |
| **5** | **10.00 ms** | **35.4 ft** | **0.8678 g** | **0.6233 g** | **+39.2%** |
| 8 | 6.25 ms | 37.7 ft | 0.5766 g | 0.5679 g | +1.5% |
| **16** | **3.125 ms** | **44.7 ft** | **0.5054 g** | **0.4865 g** | **+3.9%** |

`0.8678` is the value in the pre-A12 `braking.json`, to the digit. So the GPU migration
is not in it and D-2 is not in it: **the whole 42% is the integrator.**

### The old measurement was impossible on its own terms, and nothing looked

A stop has one average deceleration. Read from the time it took, the pre-A12 stop gives
0.868 g; read from the distance it covered, the same stop gives 0.623 g. Those cannot both
be true, and the 39% gap is the coarse integrator failing to resolve the brake transient.
Every guard the job had was satisfied: the deceleration was under the 1.3 g plausibility
bound that catches a vehicle driving into a junction, the twenty runs agreed with each
other to four decimals, the grade was 0.0%, and the verdict was PASS.

`job_braking` now reads every stop both ways and **fails** if they disagree by more than
10%. That check costs nothing and would have caught this on the first day of the study.

### Convergence, and why 16 substeps is the answer rather than a preference

CARLA clamps `max_substeps` to 16 and says so only in a warning line, so an arm at 32 or
64 is the 16-substep arm relabelled. The knob saturates before it can demonstrate
convergence, so the integration step was shrunk the other way instead, by reducing
`fixed_delta_seconds` at 16 substeps. **These arms are a physics check and not a study
configuration**; PROTOCOL section 1 fixes the control rate at 20 Hz and every measured
cell runs there.

| integration step | a from distance | change |
|---|---|---|
| 3.125 ms (the study's, dt = 0.05) | 0.4864 g | |
| 1.563 ms (dt = 0.025) | 0.4801 g | -1.29% |
| 0.781 ms (dt = 0.0125) | 0.4768 g | -0.69% |

Converged: a four-fold finer integration moves the primitive by 2.0% in total, and the
last halving by 0.69%. **0.505 g is the vehicle. 0.868 g was the solver.**

*Recorded because the first version of that verdict was wrong in my own analysis code, not
in the data.* It compared raw stopping distances between arms, and the arms do not start
from identical speeds — the PI hold exits on a tolerance, so v0 lands at 25.5, 25.1 and
24.9 mph — and distance goes as v². On that variable the sweep reads 1.85% and 1.25% and
returns NOT_CONVERGED, which is the settle controller being reported as if it were the
integrator. `a = v0²/2d` divides it out. Steering-notes section 4, in this repository, on
the first try.

### What it costs the study, and what it does not

- **`r_req` at 25 mph: 34.7 ft -> 52.0 ft. At 50 mph: 114.2 ft -> 183.4 ft.** Property S
  quantifies over poses inside `r_req`, so the certified window is larger, and every
  bound, gate and witness is recomputed against it.
- **The pre-A12 study was internally consistent and still not about this vehicle.** Its
  physics braked at 0.868 g and its budget assumed 0.868 g, so its policies really did
  stop inside a 34.7 ft budget, its oracle really did pass 10/10, and its published
  "braking at 33.6 ft against r_req 34.7" really did hold. In a world whose vehicle
  dynamics CARLA's own model does not produce. That is rule D-11 stated concretely: the
  numbers are not wrong relative to each other, they are not reusable.
- **A derived budget cannot detect an error in the primitive it is derived from.** `r_req`,
  the expert label, the oracle's trigger and the closed-loop pass criterion all move
  together with `a_max`, so every consumer stayed self-consistent while the primitive was
  40% off. The oracle passed 10/10 before and passes 10/10 now, at two different physics.
  Only a check from OUTSIDE the derivation chain could see it, and the one that worked was
  the cheapest available: read one stop two ways and require the readings to agree.
- **Nothing in PROTOCOL.md above the amendment line changes.** The design, the cells, the
  properties and the expectations are untouched; `a_max` is defined there as a
  measurement, and this is that measurement taken correctly. The lock is unmoved at
  `a80d8c8dd458`.

---

## F4 — 2026-08-25, Iteration 2 verdicts: the dusk gap reappears for the pedestrian, 25.5 degrees wide

Committed at `ea1700c` BEFORE any witness drive (CARLA is lent out; the drives are
provably later). Property S over the 15 RGB sub-intervals:

- **Cell 1 (`P_pts_ped`): FALSIFIED**, as pre-registered — and the shape is stark: a
  single CONTIGUOUS falsified band from +25.899 to +0.360 deg, 25.5 degrees of dusk
  between the regulatory endpoints, certified only at the extremes (60 to 25.9 above,
  0 to −30 below). The lead campaign's falsified band was 10.8 deg; sampling only the
  test points costs the pedestrian hazard more than twice the axis.
- **Cell 3 (`P_cont_ped`): CERTIFIED** in every covered sub-interval, as
  pre-registered; the only falsification is the declared-uncovered horizon sliver.
  Cleaner than the lead campaign (no shoulder caveat).
- **Property A, `P_cont_ped`: 3/15** — the section 9 "sleeper" is live: the
  continuum-trained pedestrian policy cannot be certified quiet on an empty road
  across most of the axis, despite training with the A10 no-target control. Whether
  that surfaces as premature braking in the witness drives is exactly what M7 will
  show. `P_pts`'s property-A sweep is queued on GPU availability (no ordering
  constraint; property A has no witness drive).

M7 remains: drive the witnesses at each sub-interval midpoint once CARLA is handed
back (`tools/drive_witness.py --policy P_pts --scenario ped`, then P_cont).

---

## F3 — 2026-08-25, Iteration 2: standoff is measured AT REST, recorded before the re-run

**Written before any re-run, per PROTOCOL section 8.** The first ped M4 sweep returned
`P_pts_ped` 9/10 at darkness. The evidence says the miss is harness semantics, not the
policy: all ten runs latched at the identical brake range (33.12 ft); nine rested at
4.43 ft and one at 2.62 ft, and the only varying factor is the walker's crossing phase
against a pass criterion computed as **min separation over the whole run**. That
min-over-run coding is a lead-scenario approximation — a stationary lead's gap
decreases monotonically, so min-over-run and resting gap coincide. A crossing walker
walks PAST the stopped vehicle, so min-over-run measures the walker's path, not the
vehicle's margin. The frozen text is explicit: section 3 defines `d_margin` as
"required standoff **at rest**".

**The change:** pass requires (a) no contact at any time (unchanged, min-over-run),
and (b) separation of at least `d_margin` while the vehicle is at rest. For the lead
scenario this is identical to the old coding. It is recorded here BEFORE the M4
re-run; if `P_pts_ped` still cannot make 10/10 under the frozen semantics, M4 fails
and the protocol stops the ped study ("no story").

Also recorded: the P_pts_ped in-between gate fails only inside [0.360, 0.000] deg —
the RGB campaign's own uncoverable horizon sliver (F2), mirroring the lead pattern —
and passes at <= 0.247 everywhere covered; P_cont_ped passes everywhere (0.310).
Verify now flags any sub-interval inside the horizon band [<= 0.37, >= 0.00] deg as
`family_uncovered` for both campaigns' knot sets. The oracle harness bug F1's fix
introduced (trigger from ego centre instead of front bumper, -1.9 ft contacts) was
caught by the re-validation stage and fixed before anything was trained against it.

---

## F2 — 2026-08-25 re-measurements: the committed campaign survives its own audit

The four measurements the F1 audit demanded, all run on a fresh server:

- **P_pts capture gate: PASS at 0.260** of the decision threshold (P_cont was 0.191).
- **P_pts in-between gate: passes at 0.578 worst over the covered sub-intervals, and
  fails at 1.074 in exactly one place — the [0.143, 0.000] deg sliver A6 already
  declared uncovered.** That cell is FALSIFIED in the committed verdicts, drove 0/10
  at a RENDERED midpoint (independent of blend validity), and is excluded from the
  coverage claim. So the gate failure confirms the A5/A6 horizon discontinuity at the
  behavioural level rather than weakening any committed cell: every certified P_pts
  cell now has a passing behavioural gate, closing audit item F10.
- **Re-bisection under the corrected three-channel metric**
  (`results/carla/family_knots_rgb.json`): 15 sub-intervals against the campaign's
  11, and the uncoverable horizon band widens from [0.143, 0.000] (blue-only error
  0.0386) to **[0.36, 0.00] at error 0.0164**. The committed campaign's knots stand
  as its record — PROTOCOL section 4 makes the behavioural check the deciding one,
  and it passes for both policies everywhere the family claims coverage — but any
  FUTURE capture campaign must use the RGB knots and the wider exclusion.
- **Sites re-measured with the fixed-exposure camera** (audit F2's defect): street
  lighting site 1 = 0.23, site 3 = 9.86 (auto-exposed values were 4.55 / 25.71). The
  A4 conclusion — site 1 effectively unlit, site 3 lit — is unchanged; the old
  numeric values should not be quoted.

Amendment A11 (same day) records the certified property as the brake decision
threshold, which is what every committed verdict already meant.

---

## F1 — 2026-08-25 audit: results were filed under the wrong ledger cells, and five measurement defects found

A four-way audit (CARLA/capture handling, protocol-integrity tooling, paper–code
consistency, citation verification) found and fixed:

- **The lead-scenario results were recorded under the ped-cross cells (1/3).** Every
  artifact is `scenario: lead`; refiled to cells 2/4 with artifact bindings, and
  `python -m study.ledger --check-order` (new) now cross-checks each cell's artifact
  scenario/policy against the frozen row, verifies the verdict's *content* was
  committed before its witness drive (first-add checking would credit the A10
  retrain's overwrites with pre-retrain dates), and requires the violating width on
  falsified cells (cell 2: 10.802° of the 90° axis).
- **Every blend-error and brightness number was sampled from the BLUE channel only**
  (stride-40/64 over BGRA with a dead alpha guard). Fixed to all three channels in
  `build_family_knots`, `interval_sweep`, `carla_jobs` (in-between, capture-check,
  sites, expert samplers). **Consequence: the A5/A6 tables and the knots in
  `family_knots.json` were blue-only measurements; re-measure the knots before
  Iteration 2 trains against them.** The behavioural gate (full-RGB, policy-output
  space) partially backstops the committed result, but it was only run on P_cont.
- `job_sites` used an auto-exposure camera (the A4 defect); the lit/unlit numbers
  quoted in A4 were not absolute photometry. Fixed to the fixed-exposure camera;
  re-measure before anything relies on them again.
- `run_policy`/`drive_witness`/`gate_behavioural` silently drove the lead geometry
  for any `--scenario`; they now refuse anything but `lead` until the pedestrian
  harness exists. `job_pedestrian`'s oracle trigger used walker distance instead of
  conflict-point range (A7); fixed.
- Training now seeds every RNG, and verify/witness artifacts record git SHA,
  timestamp, and the model's sha256, so a committed verdict is tied to the network
  it describes. `drive_witness` refuses to run against uncommitted or modified
  verdicts. `protocol_lock` now hashes each amendment (append-only is enforced, and
  `--accept` is no longer pre-authorized by a stale counter). The A6 uncovered
  sliver is flagged `family_uncovered` in verify output.

Open questions for the study lead: the `a_max/2` verification threshold vs frozen
section 7's `a_max` (needs an amendment or a code change), and the knot re-measurement
above.
