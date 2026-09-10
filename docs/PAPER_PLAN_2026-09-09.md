# The paper, against the finished steering paper

Written 9 September 2026. `docs/PAPER_OUTLINE.md` is the locked outline and this does not
replace it. This maps the steering paper's structure onto ours, and turns the difference
into work.

**The correction this is built on.** Under a fully enforced harness, repetitions that
disagree have been a fault every time in this lab. Three repetitions exist to find that
fault. Void is where you start looking, not where you stop.

---

## Where we differ from the steering paper, section by section

**Introduction.** Same opening, with a harder fact in it. The steering gaps are in a matrix
we chose. The three lighting conditions here come from a matrix a regulator chose, with a
compliance date. Do not re-explain bound propagation at their length. Cite it and spend the
space on the standard.

**Related work.** Swap their steering cluster for braking perception and the regulatory
cluster. **Add the cluster they left out and know it: falsification by simulation.** They
can defer it. We cannot, because we have a measured falsification baseline, and the
comparison is a contribution rather than an omission.

**Simulator and domain.** One town, one surveyed site, and three scenes rather than routes.
The unit of repetition is one traversal of every scored piece of the range, not a lap. Carry
less determinism boilerplate than they do and more of what is new.

**Model development.** Same recipe, three policies, and the third changes the claim. One
policy trains on all three lighting conditions the standard tests. So the result stops being
"you undersampled" and becomes "the matrix is discrete". That policy is not a control. It is
the adversarial case, and it certifies slightly more while crashing four times as often.

**Disturbance modelling. We are ahead here and should say so.** Same construction. But our check on the blend
**fails over the whole range**, so the range is a set of measured pieces with a repair
procedure. They have a withdrawn figure. This is our strongest methodological
claim and it should not be buried.

**The criterion. Two properties, and they trade off.** Must brake as a lower bound, must not
brake as an upper bound. Steering has no analogue, and the trade is a result: one policy is
falsified on the must-not-brake property over almost the whole range while certifying the
other property more widely.

**The peak-versus-sustained argument lives here**, and it has to stand on our own
composition. Once braking latches, the network leaves the loop, so the certificate composes
to a standoff in closed form and nothing integrates network output over time. We cannot lean
on the steering study. Their comparable figure is withdrawn.

**Verification.** Say the branch and bound is over the input space, explicitly, because we
measured what its absence costs. Without it the negative control read 14 of 16, and the
study would have reported that continuum training also fails at dusk.

**Results, the driving.** Short and hard. All three policies pass all three lighting
conditions the standard tests, on both hazard scenes, every repetition. By the standard's
own procedure the three cannot be told apart.

**Results, between the test cases. This is the opportunity.** The steering study drives
counterexamples. It never drives its interior systematically. We already drive each piece at
its middle and at the light level the certificate exhibits. Go further:

- **Does the driven failure boundary sit where the certificate says it does?** We report
  falsified band widths and have never driven the band edges. Bracketing the edge by driving
  and comparing it to the certified edge is sharper than any agreement count.
- **Say plainly what a drive can reach.** The certified set gives one light level per pose.
  A drive applies one rendered light level to the whole approach. So a drive can only probe
  a line through a many-dimensional set. Saying that is what makes the certificate's value
  legible.

**The ablation.** We have no two-map comparison and should not invent one. The analogue is
that **which property you certify decides which policy looks safe**.

---

## Work still to do, hardest first

1. **The dense interior sweep, and the boundary bracket.** Five rendered light levels per
   piece, three policies, both hazard scenes, three repetitions. It is a fault detector at
   scale, because every point is a repeatability check. Then bracket each falsified band
   edge and compare to the certified edge.
2. **The same sweep for the must-not-brake property**, including the steel plate scene,
   whose interior has never been swept. One policy commands 2 percent of the nuisance limit
   at every condition the standard tests and 138 percent between them. That number rests on
   two driven points and deserves the curve.
3. **Drive the regulatory endpoints again** under the three-repetition harness. This is the
   claim the whole paper rests on.
4. **Seed sweep to about 20 per policy.** This answers the "you trained one seed" objection,
   and it is now affordable.
5. **Give the rejected analytic light model an artifact.** It is prose in three files with
   no script behind it. The steering paper has the identical hole. Do not inherit it.
6. **Check the light level from a frame in every capture.** A capture settles once and then
   walks its poses, so the drift sits inside one capture.
7. **Deepen the counterexample search** past three concrete points per region. The
   counterexamples are what the interior sweep drives, so this comes first.
8. **Settle the peak braking limit read from time against distance.** They differ by 4
   percent, in the quantity the whole budget comes from.

---

## What we are carrying that the paper does not need

**Dropped, and still producing output.** The confidence interval on every cell. The steering
paper prints none, and over three repetitions an interval is an interval on nothing. Change
it when nothing is running, because every stage is a fresh process that imports it.

**Measured, answered, and not to be developed further.** The brake window stated the
controller's way, which is worse. The behavioural check as a predictor, which predicts
nothing. Glare at the horizon, which is the light level. Coverage without a certificate on a
sliver that no verdict counts. Each is a sentence, not a section.

**Journal, and worth restating because they are the tempting ones.** The sun angle as a
second axis. A policy with radar. The speed sweep. Fog and steam. The general treatment of
matching the statistic to the shape of the failure.

**Not ours to chase.** The steering paper's own open items live in that repository. Our
peak-versus-sustained bet stands on its own argument and must not wait on theirs.

**The demo is not an experiment.** Novi is October 2026 and it is a deliverable. It does not
get to pull work forward or push it back.
