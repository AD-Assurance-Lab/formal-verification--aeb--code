# Paper outline

**Target: conference length, posted to arXiv first.** One claim with one control is a
conference paper, not a journal paper. Speed matters more than completeness here, because the
point of the first paper is to put the result in front of Tier 1s and regulators and let
their reaction choose the next study. The journal version is the second study, with the
sun-angle interval, the fusion comparison and the width analysis folded in.

Condensed from a fifteen-subsection draft to nine. What was cut is listed at the bottom so it
is not re-litigated.

## Methodology, 5 subsections

1. **Task, ODD and regulatory grounding.** The AEB function under test and the FMVSS 127
   scenarios, lighting conditions and thresholds that define it, including what is out of
   scope and why this is not a compliance demonstration.
2. **Derived safety budget and the safety criterion.** The required brake-onset range from
   primitives measured in the simulator, and the two properties it induces, must-brake as a
   lower bound and must-not-brake as an upper bound, each a conjunction over a window the
   hazard geometry defines and composing to standoff distance in closed form.
3. **The disturbance family and its validation.** Endpoints rendered at an identical camera
   pose and interpolated between two regulatory test conditions, why an analytic photometric
   model was rejected on behavioral rather than image-fidelity grounds, and the check that the
   interpolated interior matches rendered intermediate illumination. **The check fails over
   the full interval**, so the axis is composed of measured sub-intervals split at the
   horizon, where the curvature of illumination against sun angle peaks; this is a result,
   not a detail, and it belongs in the methodology because it is how the family is built.
4. **Two policies differing only in axis sampling.** Regulatory-points training against
   continuum training, through one teacher-to-student distillation recipe, so that any gap is
   attributable to the sampling and not to capacity.
5. **Verification architecture and protocol.** The family as a prepended linear layer bounded
   with alpha-CROWN and input-space branch and bound, with surrogate validation before
   bounding, verdicts committed before driving, and failure rates over repetitions.

## Results, 4 subsections

1. **Both policies pass the regulatory test points.** By the standard's own procedure the two
   policies are indistinguishable, which is the setup for everything after it.
2. **Certificates over the interval, and the witness.** Bounds across the interval per cell,
   the falsified cells with their witness intensities and the width of the violating region,
   and closed-loop confirmation at the witness on a policy that passed both endpoints.
3. **The gap is attributable to how the training axis was sampled.** The continuum-trained
   control certifies across the same interval, so the mechanism is the sampling rather than
   the model, and the false-activation cells show whether robustness on one property was
   bought at the cost of the other.
4. **Cost and limitations.** What certification costs against the equivalent test campaign,
   and the boundaries of the claim: one interval, one map, camera only, dry road, simulation.

## Conclusion, one sentence

A policy can satisfy every point in a discrete regulatory test matrix and still fail between
those points, and a per-frame certificate over the interval between two mandated test
conditions finds that failure without simulating it and names the single test that confirms
it.

If nothing fails, results 2 becomes a certified absence and the conclusion inverts to a
coverage claim: no illumination between two mandated test conditions defeats the policy, which
is a stronger statement than any test campaign can make.

## The figure the paper is built around

Certified bound against `s`, with both regulatory test points marked and the violation between
them. If a reader takes one thing from the paper it is this plot, and the pipeline must be
designed to produce it.

## Deferred to the journal version

- The sun-angle interval as a second disturbance axis.
- `P_fused`, quantifying formally what a radar channel buys.
- Speed sweep across the FMVSS bands.
- Extension beyond the standard: fog, steam venting.
- A general treatment of statistic selection, matching the certified statistic to the temporal
  structure of the failure, across sustained, localized and event-shaped hazards.
- The capture requirements as a standalone caution: scene lighting settling, fixed exposure,
  and frame matching. Each of them silently corrupts a disturbance endpoint, each was found
  by one physically impossible result, and the auto-exposure one is the objection this lab
  has already published against real datasets, reproduced in a simulator.
