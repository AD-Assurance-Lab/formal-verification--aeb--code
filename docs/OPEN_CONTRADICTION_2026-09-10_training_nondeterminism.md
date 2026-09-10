# OPEN: the same seed on the same frames produces a different policy, and endpoint verdicts flip

**Measured 2026-09-10 between 02:43 and 05:29 on Town12. Not a finding — no disposition.**

## What happened

The gate repair split four dark sub-intervals and added four knots: +1.025, +0.012,
−14.770, −29.770. `rebuild_all` then retrained all three arms and re-ran the endpoints.

**Only `P_cont`'s training set changed.** `train_policies.POLICY_ARMS` puts `P_pts` and
`P_pts3` on `REGULATORY_KNOTS = [60.0, −30.0]`, and `training.json` confirms both trained on
exactly `[-30.0, 60.0]` before and after. Those two knots were **skipped by the capture
stamp guard**, so their frames are byte-identical between the two trainings. Same frames,
same `SEED=0`, same recipe.

The endpoint verdicts moved anyway:

| cell | before the refine | after |
|---|---|---|
| `P_pts` plate / darkness, upper beam | **0/10**, peak 3.032 | **10/10**, peak 1.079 |
| `P_pts` plate / darkness, lower beam | 9/10, peak 2.500 | 10/10, peak 1.186 |
| `P_pts3` plate / darkness, upper beam | **10/10**, peak 0.556 | **0/10**, peak 3.072 |
| `P_pts3` lead / darkness, lower beam | 10/10 | **0/10**, on standoff |

Peak commanded deceleration changing by a factor of three, on identical training data, is
not a marginal cell drifting. And a **hazard** endpoint now fails, which the earlier run
did not have: `P_pts3` brakes at darkness/lower beam and comes to rest inside `d_margin`,
ten times out of ten, with no contact and no premature brake.

## Why it matters more than the plate contradiction it supersedes

`docs/OPEN_CONTRADICTION_2026-09-10_plate_endpoints.md` recorded the false-activation
failures and listed five candidate causes. This is a sixth and it subsumes several of them:
if retraining on identical data flips a verdict from 0/10 to 10/10, then the earlier
pattern — `P_pts` and `P_cont` failing upper beam while `P_pts3` passed — was not
necessarily telling us anything about the arms at all.

**The study's central claim is an attribution**: the gap between `P_pts` and `P_cont` is
caused by how the training axis was sampled. That claim requires the arms to differ *because
of the sampling* and not because of where a nondeterministic optimiser happened to land. One
seed per arm cannot separate those, and this measurement shows the same seed does not even
reproduce itself.

## What has NOT been established

- **That the weights actually differ.** The inference is from behaviour, and it is strong —
  identical inputs, flipped outputs — but the direct test is to train twice and compare
  `model_sha256`. That test was **not run tonight** because it would overwrite
  `results/models/*.pt` while the gate repair loop is reading them.
- **The mechanism.** GPU non-determinism in cuDNN kernel selection and reduction order is
  the obvious candidate; `torch.use_deterministic_algorithms` and a fixed cuBLAS workspace
  are the obvious response. Neither is measured.
- **The magnitude.** Two retrains is two samples. Whether verdicts flip on most retrains or
  this was an unlucky pair is unmeasured.

## The decisive test, to run first

1. Train `P_pts` twice with the same seed on the same frames, to a scratch directory, and
   compare the model hashes and the endpoint peaks.
2. If they differ: turn on deterministic algorithms and repeat, to see what it costs and
   whether it closes.
3. Only then decide what the seed sweep (queue item 6) has to measure — with reproducible
   training it measures seed dispersion, and without it, it measures both at once and can
   separate neither.

Until then **no endpoint verdict in this rebuild should be quoted**, including the
false-activation failures in the companion file.
