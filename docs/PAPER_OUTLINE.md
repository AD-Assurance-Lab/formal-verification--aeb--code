# Paper outline

**Conference length, posted to a preprint server first.** One claim with one control is a
conference paper. Speed matters more than completeness. The point of the first paper is to
put the result in front of manufacturers and regulators, and let their reaction choose the
next study.

## Methodology, five parts

1. **The task and the standard.** The braking function under test, and the scenarios,
   lighting conditions and thresholds the federal standard sets. Say what is out of scope,
   and that this is not a compliance demonstration.
2. **The safety budget and the criterion.** The required brake-onset range, built from
   values measured in the simulator. It induces two properties: must brake, as a lower
   bound, and must not brake, as an upper bound. Both compose to a standoff distance in
   closed form.
3. **The disturbance family, and the check on it.** Two endpoints rendered at one camera
   pose, then blended. Say why an analytic light model was rejected on behaviour rather than
   on image likeness. **The check fails over the whole range**, so the range is a set of
   measured pieces. That is a result, not a detail, and it belongs here because it is how
   the family is built.
4. **Two policies that differ only in how the range was sampled.** Training on the points
   the standard tests, against training on the whole range, through one distillation recipe.
   That is what makes any gap belong to the sampling and not to capacity.
5. **How the verification works.** The family as a layer in front of the network, bounded
   with branch and bound over the input. Verdicts written down before driving.

## Results, four parts

1. **Both policies pass the points the standard tests.** By the standard's own procedure the
   policies cannot be told apart. That is the setup for everything after it.
2. **Certificates over the range, and the counterexample.** Bounds per cell. The falsified
   cells, with the light level each one exhibits and the width of the violating band. Then a
   drive at that light level, on a policy that passed both endpoints.
3. **The gap belongs to the sampling.** The policy trained on the whole range certifies over
   the same span. So the cause is the sampling and not the model.
4. **Cost and limits.** What certification costs against the equivalent test campaign. One
   range, one map, camera only, dry road, simulation.

## Conclusion, one sentence

A policy can satisfy every point in a discrete regulatory test matrix and still fail between
those points. A certificate over the range between two mandated conditions finds that
failure without simulating it, and names the single test that confirms it.

If nothing fails, the conclusion inverts to a coverage claim: no light level between two
mandated conditions defeats the policy. That is stronger than any test campaign can state.

## The figure the paper is built around

The certified bound against light level, with both regulatory points marked and the
violation between them. If a reader takes one thing from the paper, it is this plot. The
pipeline must be designed to produce it.

## Held for the journal version

- The sun angle as a second disturbance axis.
- A policy with a radar channel, to say what radar buys.
- A speed sweep across the bands the standard sets.
- Conditions beyond the standard: fog, venting steam.
- A general treatment of matching the certified statistic to the shape of the failure in
  time.
- The capture requirements as a standalone caution. Settling, fixed exposure and frame
  matching each corrupt an endpoint silently, and each was found by one impossible result.
