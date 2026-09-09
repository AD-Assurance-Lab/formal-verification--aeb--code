# The AEB paper against the finished steering paper: outline, experiments, and what to drop

Written 2026-09-09, after the steering preprint was finished. `docs/PAPER_OUTLINE.md` is
the locked outline and this does not replace it; this maps the steering paper's actual
section structure onto it, and turns the difference into a list of experiments.

**The correction this is built on.** A disagreement between repetitions under a fully
enforced harness has been a **bug** every time it has occurred in this lab. Three
repetitions exist to detect that bug. "Void" is where you start looking, not where you
stop — and `P_cont`/plate [+0.026°, +0.000°] was filed as void in F22 without that hunt,
which is E1 below.

---

## Part 1 — the steering paper's outline, and what each section becomes here

### 1. Introduction

Steering opens on a test matrix with gaps, before any literature, for validation and AI
engineers who have never met formal verification.

**AEB:** the same opening with a harder fact in it. Steering's gaps are in a matrix we
chose; **FMVSS No. 127's three lighting conditions are a matrix a regulator chose, with a
compliance date**. Open there. Do not re-explain what bound propagation does at steering's
length — cite it and spend the space on the standard.

### 2. Related Work

Steering's clusters: E2E steering, NN verification, ODD specification.

**AEB:** swap the E2E-steering cluster for AEB perception and the regulatory cluster
(FMVSS 127, UN R152, Euro NCAP AEB). **Add the cluster steering left uncited and knows it:
simulation-based falsification** — S-TaLiRo, Breach, VerifAI, Corso's survey. Steering can
defer it; AEB cannot, because AEB has a measured falsification baseline (F15) and the
comparison is a contribution rather than an omission.

### 3. Methodology

#### 3.1 Simulator, Vehicle, and ODD

Steering: two towns, two routes, a lap as the unit, and 26 lines on determinism its own
status file says to cut to six.

**AEB:** one town, one surveyed site, and **three scenarios rather than routes** — lead
stop, crossing pedestrian, trench plate. The unit of repetition is not a lap: it is one
traversal of every scored sub-interval, which is what `--rep-index` brackets. Carry *less*
determinism boilerplate than steering and *more* of what is new: A13's harness, and F23,
which belongs here because it is a property of the ODD's own definition.

#### 3.2 AI Model Development

Steering: teacher → student distillation, two policies differing only in training
conditions.

**AEB:** same recipe, **three arms**, and the third changes what the paper claims.
`P_pts3` is trained on all three lighting conditions the standard actually tests, so the
result stops being "you undersampled" and becomes "the matrix is discrete". `P_pts3` is
not a control — it is the adversarial case, and it certifies slightly more of property S
while crashing four times as often.

#### 3.3 Disturbance Modeling

Steering: a chord in image space between two frames at an identical pose, one intensity
per pose. Its interpolation-fidelity measurement is **withdrawn** and sits in Limitations.

**AEB is ahead here and should say so.** The same construction, but the in-between check
**fails over the full interval**, so the axis is a set of sixteen measured sub-intervals
plus a declared uncovered sliver at the horizon (A5, A6). That is a built, enforced gate
with a repair procedure, where steering has a withdrawn figure. This is the AEB paper's
strongest methodological claim and it should not be buried.

#### 3.4 The Safety Criterion

Steering: one criterion, a CTE budget from lane width, vehicle width, wheelbase, speed and
a reaction horizon, with no fitted parameter.

**AEB: two properties, and they trade off.** `r_req` from `a_max`, `t_lat` and speed
(52.0 ft at 25 mph), inducing must-brake (S) as a lower bound and must-not-brake (A) as an
upper bound. Steering has no analogue and the trade is a result: `P_pts3` is falsified on A
over 89.2° of a 90° axis while certifying S more widely. **The peak-versus-sustained
argument lives here**, and it must be argued from AEB's own composition — once braking
latches the network leaves the loop, so the certificate composes into standoff in closed
form and nothing integrates network output over time. It cannot lean on steering, whose
comparable figure is withdrawn.

#### 3.5 Formal Verification

Steering: CROWN, family as a prepended linear layer, and it corrected itself from
α-CROWN to CROWN late.

**AEB:** α-CROWN **with input-space branch and bound**, stated explicitly, because F8
measured what its absence costs — without it the negative control read 14/16 and 13/16 and
the study would have reported that continuum training also fails at dusk. Add F20, the
verifier's own reproducibility floor at 0.0038 × threshold, which is what licenses
reporting margins at all. Steering has no equivalent.

### 4. Results

#### 4.1 Closed-Loop Driving

Steering: a precondition — drive every policy until its trained behaviour is established.

**AEB: this is the setup for the entire paper and it is short and devastating.** All three
arms pass all three regulatory lighting conditions, on both hazard scenarios, every
repetition. **By the standard's own procedure the three arms are indistinguishable.**

#### 4.2 Verification

Steering: bounds over the family per test case, scored against the criterion, no further
simulation.

**AEB:** the same, twice over — property S and property A, three arms, two hazards, plus
the false-activation scenario — and with **zero undecided sub-intervals**, which steering
cannot say. Report the margin with every verdict and F17's band, roughly 1.00× to 1.05×,
in which a bare pass carries no information.

#### 4.3 Between the Test Cases

Steering: goes inside the family to ask which intensity produces the worst output, with
three markers per row — the rendered condition, the worst single intensity, and the worst
per-pose combination. Its witnesses are **found by sampling**, and it says so.

**This is the section that has to change most, and it is the paper's opportunity.**
Steering never drives its interior systematically: it drives witnesses. AEB already drives
each sub-interval's midpoint *and* its exhibited witness, which is more, and it should go
further — **the interior outcomes get verified in closed loop**, densely, both to hunt bugs
and to measure the method. Two things AEB can report that steering cannot:

- **Does the driven failure boundary sit where the certificate says it does?** The study
  reports falsified band widths (50.3°, 48.3°, 43.0°) and has never driven the band edges.
  Bisecting on rendered illumination to find where the policy actually starts failing, and
  comparing that to the certified band edge, is a sharper test than any agreement count.
- **What the drivable slice is.** The certified set is one intensity per pose; a drive
  applies one rendered illumination to the whole approach. So closed loop can only ever
  probe a one-dimensional curve through a many-dimensional set. Saying that plainly is what
  makes the certificate's value legible, and measuring agreement densely along that curve
  is the strongest empirical claim available.

#### 4.4 The Difference Is the ODD

Steering: an ablation explaining why Town04 and Town06 differ — not network size, not input
projection, therefore the ODD.

**AEB has no two-ODD comparison and should not invent one.** The structural analogue is
**which property you certify decides which policy looks safe**: `P_cont` certifies S 16/16
and is the loudest arm on the plate; `P_pts3` certifies A on the lead and is falsified on A
over 89° on the pedestrian. Same ablation discipline, different axis.

### 5. Conclusion

One sentence, as `docs/PAPER_OUTLINE.md` already fixes it.

---

## Part 2 — experiments to run, ordered by what can still damage the claim

> **Status, later the same day.** E1 and E2 are closed, and the map moved. E1 found
> F24 — the false-activation driver was running at 10 Hz where PROTOCOL section 3
> specifies 20 — which withdrew F19's `P_cont` half and took the study's only
> certified-then-failed sub-interval with it. E2 became amendment A15, `cloudiness = 0`,
> decided before the rebuild recaptured anything. A14 then moved the study to Town12,
> which makes E3, E4 and E5 measurements on the new map rather than the old one. The
> remaining items stand as written.

**E1. Chase the `P_cont`/plate split as a bug.** **CLOSED, F24.** [+0.026°, +0.000°], 2/10 under A13's
harness, scene signature stable to 3e-5, peak demand bimodal at 1.90–1.91 against
2.61–2.62 m/s² with nothing between. A clean gap with no intermediate values is a
discrete difference between runs, not amplification. Named candidates: the trench plate is
built from tiles and **the per-run record does not carry the tile count**, so a partially
placed plate is invisible in the artifact; `plate_run` has no `brake_step` or
`speed_at_brake` diagnostic, which is exactly what made F21's mechanism visible; and the
approach is 200 m at 50 mph, so a one-frame offset at the start is 1.1 m of range. Add the
instrumentation, re-drive, and do not report the cell until the cause is written down.
**Cheap, and it is load-bearing:** this is the study's only certified-then-failed
sub-interval and F19 rests on it.

**E2. Decide F23, and measure what deciding it costs before paying.** **CLOSED, A15.** Do not rebuild on
the strength of the finding. Re-verify **one** cell and re-drive **one** at
`cloudiness = 0.0` and see whether any verdict moves. If none moves, the paper carries F23
as a stated limitation with a measured bound on its effect. If one moves, the captures are
unusable under D-11 and the study rebuilds — which is a decision, not a consequence.
Runs before anything expensive, because everything downstream is measured on the answer.

**E3. The dense closed-loop interior sweep, and the boundary bisection.** The new §4.3.
A coarse grid first — five rendered illuminations per sub-interval, sixteen sub-intervals,
three arms, both hazards, three repetitions each — as a bug detector at scale, since every
point is a reproducibility check and any repetition disagreement is a bug. Then a bisection
on rendered illumination at each falsified band edge, comparing the driven boundary to the
certified one. **This is what A13 bought:** at ten repetitions sharing a server it was
1,440 runs of a harness we now know was drifting; at three under per-repetition restart it
is a few hours and the repetitions mean something.

**E4. The same interior sweep for property A**, including the plate scenario, whose
interior has never been swept. `P_pts` commands 2% of the nuisance limit at every condition
the standard tests and 138% between them — that number currently rests on two driven points
and deserves the curve.

**E5. Re-drive the regulatory endpoints under A13.** §4.1 is the claim the whole paper
rests on and it is currently measured on the shared-server harness. Nine cells, three
repetitions, one server each. Cheap, and it removes the obvious question.

**E6. Seed sweep to n ≈ 20 per arm.** F16 holds the attribution at p = 0.002 on ten matched
pairs; the steering study's own measurement says n ≈ 20–60 to see a 20% effect. This is the
"you trained one seed" objection and it is now affordable.

**E7. Give the analytic-model rejection an artifact.** PROTOCOL §114 carries R² = 0.848 on
image fidelity against 23.8× worse driving, and it is prose in three files with no script
that computes it and no check that can verify it. It is a methodology claim in §3.3. The
steering paper has the identical hole in its own contribution 1 — do not inherit it.

**E8. Photometric check on the certificate captures.** Steering's open item 5, and F23
makes it mandatory here rather than advisable: a capture settles once and then walks its
poses, so the drift is inside a single capture as a gradient along the pose index.

**E9. Deepen the branch-and-bound witness search** past three concrete samples per domain.
The witnesses are what E3 drives, so this precedes the at-witness half of E3.

**E10. Resolve `a_max` read from stop time against stop distance**, a 3.9% difference in
the quantity the whole safety budget is derived from.

Ordering that matters: **E2 before everything expensive**; E1 before the plate results are
written up; E9 before E3's at-witness half; E3 and E4 are the paper's new section.

---

## Part 3 — what we are carrying that the planned scope does not need

**Dropped by A13, and still generating output:**

- **Wilson intervals.** `tools/stats.py:rate()` stamps `wilson_95` into every cell. The
  steering paper prints none, and under A13 an interval over repetitions is an interval on
  nothing — in either direction, because the ten-in-process fallback samples a drifting
  harness and an interval there describes the drift as though it were a failure rate.
  `merge_witness_reps.py` already writes null; the rest should stop emitting it.
  **Deliberately not done while the rebuild runs**: every stage is a fresh process that
  imports `stats.py`, so editing it mid-campaign would produce one rebuild out of two
  different scorers, which is the drift this repository has lost study logic to twice.
  It is the first change after the rebuild lands.
- **The ten-repetition drive pattern.** The twenty-four-drive M7 at ten repetitions per
  cell is superseded. It is not re-run to "confirm" F21 or F22 — more repetitions is the
  thing that was just measured to be the wrong instrument.

**Measured, answered, and not to be developed further** — each is one sentence or one
paragraph in the paper, not a subsection:

- **The latch-window disjunction** (item 11, F17). Built, measured, and worse: 8 of 9 crash
  cells caught instead of 9 of 9. A negative result, reported beside the frozen property.
- **The in-between gate as a predictor** (item 6, F10). r = −0.005. It predicts nothing.
  Report it and stop calibrating it.
- **Horizon glare ablation** (item 9, F13). Answered: illumination, not glare.
- **Conformal coverage on the uncovered sliver** (item 10, F14). Good work, and it is about
  a sliver excluded from every verdict by construction. Journal version — unless E1 turns
  the sliver load-bearing, in which case it moves up.
- **`P_pts3`'s 287 ft daylight brake.** Real, recorded, and property A rather than the
  headline.

**Explicitly journal, already on the deferred list, and worth restating because they are
the tempting ones:** the sun-angle second axis, the fused camera-plus-radar arm, the speed
sweep across FMVSS bands, fog and steam beyond the standard, and the general treatment of
matching the certified statistic to the temporal structure of the failure.

**Not ours to chase:** the steering paper's own open items. Its peak-versus-sustained
recompute, its interpolation-fidelity re-measurement, and its Town04 scope tidy-up all live
in that repository. AEB's peak-versus-sustained bet stands on its own composition argument
and must not wait on theirs.

**And the demo is not an experiment.** Novi is October 2026 and it is a deliverable. It
does not get to pull experiments forward or push them back.
