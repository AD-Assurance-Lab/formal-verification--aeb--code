# The queue

Ten items, ordered so that nothing is measured twice because a definition changed
underneath it, and so that the things which could still **damage** the claim run first.
Agreed 2026-09-07 with no deadline pressure; `docs/STATE_OF_PLAY.md` is current belief,
this is what happens next.

Two states per item, because a tool that exists is not a measurement that ran:
**built** (the instrument is committed and validated) and **measured** (it has produced a
result on the current harness).

| # | item | built | measured | result |
|---|---|---|---|---|
| 1 | third regulatory lighting condition | yes | **yes** | gap survives: 43.0° vs 50.3° falsified, F12 |
| 2 | per-run recording, Wilson, write-up | yes | **yes** | report rewritten, banner gone |
| 3 | open-loop determinism probe (D-8) | yes | **yes** | physics bit-exact, policy contractive, F11 |
| 4 | seed sweep, 10 matched pairs | yes | **yes** | attribution holds p = 0.002, F16 |
| 5 | falsification baseline | yes | **yes** | search wins on cost, 2/6 reliable, F15 |
| 6 | in-between gate calibration | yes | **yes** | gate predicts nothing, r = −0.005, F10 |
| 7 | trench plate, cells 5 and 6 | **yes** | **yes** | ledger 6/6. No arm brakes for the plate except `P_cont`, once. F18, F19 |
| 8 | harness hardening | partly | partly | per-repetition restart built and adopted (A13, F22). Two pieces left; and F23 opens a new one |
| 9 | horizon glare ablation | yes | **yes** | illumination not glare, F13 |
| 10 | conformal coverage | yes | **yes** | separates the arms on the sliver, F14 |
| 11 | latch-window property, PROTOCOL section 8 dispositions | yes | **yes** | all four contradictions disposed, F17 |

**Item 11 in one line.** Property S is a conjunction over 25 poses and the controller only
needs a disjunction over the two or three in the latch window; both ledger contradictions
live in that gap. Stating the property the controller's way was then built and measured
and **it is worse** — 8 of 9 crash cells caught instead of 9 of 9 — so PROTOCOL section 7
stays as written and the disjunction is reported beside it. F17.

**Item 8, what is done and what is not.** Done: `claim_output` so a crashed stage leaves no
artifact; `stop_server` waiting on the process and the VRAM rather than the socket;
`VERIFY_CONC` set from the worst-case per-job memory rather than the average;
`expandable_segments`; `enable_postprocess_effects` set explicitly (D-4); the verifyA
stage takes an explicit scope argument instead of a silent default; **the per-repetition
server restart (D-6)**, built as `tools/drive_witness.py --rep-index` +
`tools/merge_witness_reps.py` + `scripts/drive_witness_reps.sh`, adopted as amendment A13
and validated end to end against a committed ten-repetition cell. Not done: the
branch-and-bound witness search still samples three concrete points per domain; and
`a_max` is still read from stop TIME while `r_req = v²/2a` composes with distance, a 3.9%
difference.

**Items 13-16, from the A14 rebuild's own findings.** None is started; each names what it
would change and why it is not being done unilaterally.

| # | item | why it is not done yet |
|---|---|---|
| 13 | Make the bisection tolerance relative to endpoint distance, or refuse a sub-interval below a span floor (F27) | Either changes what the axis IS, so it needs an amendment. Both maps produced a sub-interval spanning nothing that certifies at 1.9x in every arm |
| 14 | Report the span beside every verdict, everywhere a count appears (F27) | Small and safe, and it touches `record_cells.py`, which the running rebuild invokes. Queued behind the rebuild rather than edited underneath it |
| 15 | Render `blend_error` and endpoint distance at the SAME poses (F27) | Needs the simulator. The ratio is the number the family's fidelity claim wants and a first pass at it was wrong; it is queued rather than guessed |
| 16 | Drop the Wilson interval from `stats.py:rate()` (A13) | Same reason as 14: every rebuild stage is a fresh process importing it, and one rebuild out of two scorers is the drift this repo has lost study logic to twice |

**Also open, and not a study's to decide:** the D-7 amendment request in
`docs/D7_AMENDMENT_REQUEST.md`. The `carla-determinism` package is hash-locked and lab-wide
and currently prints "closed-loop numbers are still RATES over >=10 repetitions" on every
launch of a study that A13 governs.

**Item 12, new and ahead of the rest of 8.** F23: `cloudiness = 10.0` leaves a moving
cloud layer, so scene brightness at the horizon drifts 3.9% with elapsed simulated time
and never settles. It is the study's independent variable drifting, it is inside every
capture as a gradient along the pose index, and it is not covered by any rule in the
`carla-determinism` package. Fixing it means `cloudiness = 0` or a much longer settle plus
a photometric check on every capture and drive, and both change what the conditions ARE —
so it needs its own amendment before anything is re-measured. Ranked ahead of the
remaining item 8 work: it can move a number, and they cannot.

Items 7 and 8 change `capture_campaign.py`, `run_policy.py` and `carla_jobs.py`, which the
running pipeline invokes on every stage. They wait for it to finish rather than being
edited underneath it.

---

## [~] 1. The third regulatory lighting condition

**Why.** FMVSS 127 as PROTOCOL section 2 records it tests three lighting conditions:
daylight, darkness with lower beam, darkness with upper beam. `P_pts` — the policy that
exists to be *what a manufacturer optimising against the test matrix builds* — has only
ever seen two of them. If the dusk gap closes when the third is added, this study is about
*which* points were sampled rather than about the discreteness of the matrix, which is a
different and much weaker paper. Cheapest thing that could most damage the claim, so it
runs first.

**What it is not.** Upper beam is not a third point on the sun-altitude axis. It is the
same darkness, -30 deg, with a different headlamp state — `job_sites` has always treated
it that way. An interval has two endpoints and the certified axis is correctly two. What
is missing is a *training* condition and an *endpoint test*, not a knot.

**Method.** Capture darkness/upper-beam for all four scenarios as a lights variant. Train
a third policy `P_pts3` on all three regulatory conditions, leaving `P_pts` and `P_cont`
exactly as the frozen section 5 comparison defines them, so the existing result is
undisturbed and the new one answers its own question. Add darkness/upper-beam as a third
M4 endpoint for every policy — the standard tests it, so "passes the regulatory test
points" should mean all three. Verify property S for `P_pts3`, drive its witnesses,
and report whether the falsified width shrinks.

## [ ] 2. Re-run M7 with per-run recording, Wilson intervals everywhere, and write up the rebuild

Witness artifacts carry summary counts only, so re-scoring against PROTOCOL section 7's
criterion means inferring failure modes from `min_gap` instead of reading a recorded flag
(FINDINGS F9). Wilson intervals are required by section 1, `CLAUDE.md` and rule D-7 and
exist nowhere in the repository. `docs/STUDY_REPORT.md` still carries a SUPERSEDED banner
and none of the rebuilt results. Runs after item 1 so the drives happen once, on final
policies.

## [ ] 3. Open-loop determinism probe (D-8)

The one determinism rule this repo has never satisfied: it adopted the *fixes* without ever
running the *measurement* that validates them here. Cut the feedback, drive a command
sequence that is a pure function of step index, record pose, a hash of the raw sensor
buffer, and the policy output computed-but-not-applied. Per D-9, copy each repetition's
artifact before the next runs. Yields the render floor for this map and camera, whether the
AEB policy is contractive or amplifying (D-10), and the repetition count that makes item 2's
intervals mean something.

## [ ] 4. Seed sweep, n ≈ 20 per arm, matched pairwise

The central claim is an attribution and it rests on one seed per arm whose initialisations
are not even independent draws — `train_policies.py` seeds once and trains the two policies
sequentially in one process. The steering study measured that training dispersion is
intrinsic, not beaten by ensembling, and needs n ≈ 20-60 to see a 20% effect. Report the
distribution of certified count and falsified width per arm with a rank test, not two point
estimates, and pre-register the expected effect size before looking.

## [ ] 5. Falsification baseline

Random and adversarial search over the same illumination axis, reporting simulator runs to
first failure against certificate cost. Without it the paper invites "twenty random samples
would have found that too". With it the argument inverts, because a sampler cannot certify
the sub-intervals where nothing fails.

## [ ] 6. Calibrate the in-between gate as a predictor of certificate transfer

Drive both the blend-implied and the rendered illumination at matched `s` for every
falsified sub-interval and regress disagreement on the gate value, turning a pass/fail into
a quantitative statement about when a blend-based certificate transfers. Cost the sounder
variant at the same time: verify over the convex hull of ADJACENT RENDERED frames, so the
family contains only images the renderer actually produces.

## [ ] 7. Cells 5 and 6, the trench-plate false-activation scenario

Two of six frozen ledger cells have no harness. Property A is currently verified on the
no-target control, which is a legitimate must-not-brake property and is **not** the
standard's scenario. Needs a `plate` and `none_plate` capture at 50 mph, a must-not-brake
closed-loop criterion (`one_run` has no notion of passing by not stopping), and witness
drives. Section 9 calls cell 6 the sleeper, and property A says the sleeper is awake.

## [ ] 8. Harness hardening, batched

- Set `enable_postprocess_effects` explicitly. D-4's lesson is precisely not to rely on a
  default that silently un-pins manual exposure, and the preflight cannot check it because
  it is a camera attribute rather than a world setting.
- ~~Restart the server per repetition rather than per stage (D-6). 170 runs currently share
  one server inside a witness stage.~~ **Done**, and it was not cosmetic: three of the
  four split cells in the study turned out to be defects the shared server was hiding
  (F21, F22, F23).
- Deepen the branch-and-bound witness search past three concrete samples per domain.
- Resolve `a_max` read from stop TIME (section 3's wording) against stop DISTANCE, which is
  what `r_req = v^2/2a` actually composes with. They differ by 4%.

## [ ] 9. Horizon nuisance braking: mechanism, not just measurement

Both policies brake at 200-300 ft near sun altitude 0 and property A certifies it as real.
Sweep the horizon band finely with the no-target control, then repeat with the sun's
AZIMUTH rotated away from the direction of travel. If the effect follows the sun rather
than the altitude it is glare geometry, not illumination, and F6's brightness spike at
exactly 0.000 deg is the suspect.

## [ ] 10. Conformal coverage for the uncovered sliver, and the STL framing

The horizon sliver is where the family provably cannot represent reality, so a certificate
is unavailable there by construction — but a distribution-free coverage statement is not.
Certificate where the family holds, conformal guarantee where it does not. Separately,
restate the peak-versus-sustained bet as the difference between the eventually and always
operators in STL, which makes it a principled claim with existing machinery behind it
rather than an observation from two studies.

---

## Ordering constraints

- **1 before everything**: it changes what the policies are.
- **3 before 4**: you cannot say two seeds differ before you know the noise floor.
- **4 before 5**: a falsification baseline against a single-seed policy measures that seed.
- Items 1-4 can still change the paper's claim. 5-7 are what a reviewer or a Tier 1 will
  ask for. 8-10 are strengthening.
