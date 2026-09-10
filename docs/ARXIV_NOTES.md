# Notes for the paper repository

For `formal-verification--aeb--arxiv`. Everything the code repository knows that the paper
needs. The working notes are gone. `CLAUDE.md` holds the rest.

**The paper's numbers are stale in every row.** Its status file lists three blocking items,
and all three were written against numbers the rebuild has since changed. Run the figures
data tool against the current results before anybody reads its main table. That tool is the
only sanctioned way in. Regenerate nothing by hand.

---

## The outline

Conference length, posted as a preprint first. One claim with one control is a conference
paper. Speed matters more than completeness. The point of the first paper is to put the
result in front of manufacturers and regulators, and let their reaction choose the next
study.

### Methodology, five parts

1. **The task and the standard.** The braking function under test, and the scenarios,
   lighting conditions and thresholds the federal standard sets. Say what is out of scope.
   Say this is not a compliance demonstration.
2. **The safety budget and the criterion.** The required brake-onset range, built from
   values measured in the simulator. It induces two properties: must brake as a lower bound,
   must not brake as an upper bound. Both compose to a standoff distance in closed form.
3. **The disturbance family, and the check on it.** Two endpoints rendered at one camera
   pose, then blended. Say why an analytic light model was rejected on behaviour rather than
   on image likeness. **The check fails over the whole range**, so the range is a set of
   measured pieces. That is a result, not a detail.
4. **Two policies that differ only in how the range was sampled.** Training on the points the
   standard tests, against training on the whole range, through one distillation recipe. That
   is what makes any gap belong to the sampling and not to capacity.
5. **How the verification works.** The family as a layer in front of the network, bounded
   with branch and bound over the input. Verdicts written down before driving.

### Results, four parts

1. **Both policies pass the points the standard tests.** By the standard's own procedure the
   policies cannot be told apart. That is the setup for everything after it.
2. **Certificates over the range, and the counterexample.** Bounds per cell. The falsified
   cells, with the light level each exhibits and the width of the violating band. Then a
   drive at that light level, on a policy that passed both endpoints.
3. **The gap belongs to the sampling.** The policy trained on the whole range certifies over
   the same span. So the cause is the sampling and not the model.
4. **Cost and limits.** What certification costs against the equivalent test campaign. One
   range, one map, camera only, dry road, simulation.

### Conclusion, one sentence

A policy can satisfy every point in a discrete regulatory test matrix and still fail between
those points. A certificate over the range between two mandated conditions finds that
failure without simulating it, and names the single test that confirms it.

If nothing fails, the conclusion inverts to a coverage claim. No light level between two
mandated conditions defeats the policy. That is stronger than any test campaign can state.

### The figure the paper is built around

The certified bound against light level, with both regulatory points marked and the violation
between them. If a reader takes one thing from the paper, it is this plot.

---

## Where we differ from the finished steering paper

**Introduction.** Same opening with a harder fact. The steering gaps are in a matrix we
chose. The three lighting conditions here come from a matrix a regulator chose, with a
compliance date. Do not re-explain bound propagation at their length.

**Related work.** Swap their steering cluster for braking perception and the regulatory
cluster. **Add the cluster they left out and know it: falsification by simulation.** They can
defer it. We cannot, because we have a measured baseline, and the comparison is a
contribution rather than an omission.

**Simulator and domain.** One town, one surveyed site, three scenes rather than routes. The
unit of repetition is one traversal of every scored piece of the range, not a lap. Carry less
determinism boilerplate than they do and more of what is new.

**Model development.** Same recipe, three policies. The third changes the claim. One policy
trains on all three lighting conditions the standard tests, so the result stops being "you
undersampled" and becomes "the matrix is discrete". That policy is not a control. It is the
adversarial case, and it certifies slightly more while crashing four times as often.

**Disturbance modelling. We are ahead here and should say so.** Our check on the blend fails
over the whole range, so the range is a set of measured pieces with a repair procedure. They
have a withdrawn figure. This is our strongest methodological claim. Do not bury it.

**The criterion. Two properties, and they trade off.** Steering has no analogue, and the
trade is a result: one policy is falsified on the must-not-brake property over almost the
whole range while certifying the other more widely.

**Verification.** Say the branch and bound is over the input space, explicitly. Without it
the negative control read 14 of 16, and the study would have reported that continuum training
also fails at dusk.

**Results, the driving.** Short and hard. All three policies pass all three lighting
conditions the standard tests, on both hazard scenes, every repetition.

**Results, between the test cases. This is the opportunity.** The steering study drives
counterexamples and never drives its interior systematically. Go further.

- **Does the driven failure boundary sit where the certificate says it does?** We report
  falsified band widths and have never driven the band edges. Bracketing the edge by driving,
  then comparing to the certified edge, is sharper than any agreement count.
- **Say plainly what a drive can reach.** The certified set gives one light level per pose. A
  drive applies one rendered light level to the whole approach. So a drive probes a line
  through a many-dimensional set. Saying that makes the certificate's value legible.

**The ablation.** We have no two-map comparison and should not invent one. The analogue is
that which property you certify decides which policy looks safe.

---

## What the steering paper settles for us

- **Repetitions check that a result repeats.** Their paper says so in one sentence and prints
  no confidence intervals anywhere. Three repetitions are the rule here, measured here.
- **The message is one sentence.** Theirs is that these policies break between the conditions
  anyone tests. Ours is the same claim in a stronger form, because a federal standard chose
  the endpoints and we did not. Anything that does not serve that sentence is a journal item.
- **Limitations stay high level.** Detail that carries an argument stays where the argument is
  made. Moving clouds belong where the lighting range is defined.
- **A provenance check is a deliverable.** Their figures tool runs 388 checks of every figure
  number against the code. Our paper has no equivalent, and it should.
- **Two withdrawn numbers are warnings.** Their peak-versus-sustained figure is withdrawn,
  and so is their interpolation check. **Our scientific bet is that the peak is the right
  statistic for braking.** We cannot lean on them for it.

### Does not carry over

- **The lap as the unit.** A piece of our lighting range is its own condition and its own
  verdict, so the pieces are not repetitions of each other.
- **Their cell counts and width ratios.** They do not even carry between that paper's own two
  maps.
- **Their clean bill on the harness.** Moving clouds are a third mechanism neither study
  looked for, and both have it.

---

## Work the paper still needs

Hardest first.

1. **The dense interior sweep, and the boundary bracket.** Five rendered light levels per
   piece, three policies, both hazard scenes, three repetitions. Every point is a
   repeatability check, so it is a fault detector at scale. Then bracket each falsified band
   edge and compare to the certified edge.
2. **The same sweep for the must-not-brake property**, including the steel plate scene, whose
   interior has never been swept. One policy commands 2 percent of the nuisance limit at
   every condition the standard tests and 138 percent between them. That rests on two driven
   points and deserves the curve.
3. **Drive the regulatory endpoints again** under the three-repetition harness. This is the
   claim the whole paper rests on.
4. **Seed sweep to about 20 per policy.** This answers the "you trained one seed" objection.
5. **Give the rejected analytic light model an artifact.** It is prose with no script behind
   it. The steering paper has the identical hole. Do not inherit it.
6. **Check the light level from a frame in every capture.** A capture settles once and then
   walks its poses, so the drift sits inside one capture.

## What we carry that the paper does not need

Each is a sentence, not a section. The brake window stated the controller's way, which is
worse. The behavioural check as a predictor, which predicts nothing. Glare at the horizon,
which is the light level. Coverage without a certificate, on a sliver no verdict counts.

Held for the journal version: the sun angle as a second axis. A policy with radar. The speed
sweep. Fog and steam. The general treatment of matching the statistic to the shape of the
failure.

Not ours to chase: the steering paper's own open items live in that repository.

**The demo is not an experiment.** Novi is October 2026 and it is a deliverable. It does not
get to pull work forward or push it back.
