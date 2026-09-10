# The queue

What happens after the steps in `docs/NEXT_STEPS.md`. Ordered so that nothing gets measured
twice because a definition moved under it.

A tool that exists is not a measurement that ran. **Built** means the tool is committed and
checked. **Measured** means it has given a result on the harness we use now.

---

## Done, and not to be developed further

Each of these is one sentence or one paragraph in the paper. None is a section.

| item | result |
|---|---|
| the third lighting condition the standard tests | the gap survives: 43.0 degrees falsified against 50.3 |
| per-run recording, and the write-up | report rewritten, superseded banner gone |
| open-loop repeatability probe | physics is exact, the policy shrinks small errors |
| seed sweep, 10 matched pairs | the attribution holds, p = 0.002 |
| falsification baseline | search wins on cost, and 2 of 6 runs are reliable |
| the behavioural check as a predictor | it predicts nothing, r = -0.005 |
| steel plate, ledger cells 5 and 6 | ledger complete at 6 of 6 |
| glare at the horizon | it is the light level, not glare |
| coverage without a certificate, on the gap at the horizon | it separates the policies |
| the brake window, stated the way the controller uses it | worse: 8 of 9 crash cells caught, not 9 of 9 |
| training that repeats | four settings, 3 percent slower, four runs identical (F30) |
| results folders named after the map | `tools/paths.py` is the one definition |

## Open

**1. Report the distance in light beside every verdict.** Eight of the 29 pieces of the
lighting range span nothing, and two of those are among the widest in sun angle (F31). A
count of pieces treats them all as equal, and they are not. The tool exists and needs no
simulator.

**2. Stop the range from making pieces that span nothing.** Make the stopping rule relative
to how much the light changes, or refuse a piece below a floor. Both change what the
lighting range IS, so both need an amendment.

**3. Render the blend error and the endpoint distance at the same poses.** The ratio is the
number the family's fidelity claim wants. A first attempt at it was wrong. This needs the
simulator.

**4. Drop the confidence interval from `tools/stats.py`.** Three drives check that a result
repeats. They do not estimate a rate. Wait until nothing is running. Every stage is a fresh
process that imports it. Two scorers in one campaign is the drift this lab has lost study
logic to twice.

**5. Record the map inside every result file.** The folder name is a good guard. A field in
the file is a better one. No file carries it today.

**6. Seed sweep to about 20 per policy.** Ten matched pairs hold the attribution. The
steering study measured that 20 to 60 are needed to see a 20 percent effect. This answers
the "you trained one seed" objection. The training now repeats, so a sweep measures seed
spread alone.

**7. Deepen the search for a counterexample.** It still samples three concrete points per
region. The witnesses are what the interior drives visit, so this comes first.

**8. Settle the peak braking limit, read two ways.** It is read from the stopping time. The
required range formula composes with the distance covered. They differ by 4 percent, in the
quantity the whole safety budget comes from.

**9. Give the rejected analytic light model an artifact.** The design records a fit of 0.848
on image likeness against driving 23.8 times harder. It is prose in three files. No script
computes it, and no check can verify it.

**10. Check the light level from a frame, in every capture.** A capture settles once and
then walks its poses, so the drift sits inside one capture as a gradient along the pose
index.

---

## Not this study's to decide

The amendment request against the repetition floor now sits in the shared determinism
package, at `docs/amendment-requests/2026-09-10-D7-repetition-floor-from-aeb.md`. Nothing in
that package changed. It still prints the old rule on every launch.
