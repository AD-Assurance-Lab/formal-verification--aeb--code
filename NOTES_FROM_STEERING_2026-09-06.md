# Notes from the steering study, for AEB — read before the next session

Written 2026-09-06 after a follow-on programme on `formal-verification--steering--code`
(Q1–Q8, V1–V3, A1). These are the findings that **transfer**, ordered by how much they
would cost to rediscover here. Full detail in that repo's `docs/*_FINDINGS.md`.

---

## 1. Your closed-loop results predate the GPU. Re-drive before the paper goes out.

`study/results.json` is dated **2026-08-25**. This repo adopted the new environment on
**2026-09-04** (`71197ff`), and the RTX 5090 migration in the steering repo landed
**2026-09-03 22:56**. So every AEB closed-loop number was collected on the old card and
**has never been re-driven on the current one.**

The steering study had exactly this gap and I measured what it costs. Re-driving all eight
Town06 cells on the new GPU:

* **7 of 8 verdicts reproduced.** Three cells agreed to **two decimal places** — a 25 ft
  lane departure landed at 25.52 ft then 25.51 ft on a different GPU.
* **The eighth flipped**, and it was the one marginal cell — the one whose laps disagreed
  and which had been marked VOID. On the new hardware it passes, 27 laps, none over budget.

So the risk is not general drift. It is concentrated exactly where a cell sits near a
threshold, which is where AEB's interesting cells live by construction — your headline is a
policy that passes both FMVSS 127 lighting endpoints and fails *between* them. **Any cell
near the boundary is the kind that can move.**

**Cost to check:** the steering re-drive was 8 cells × 3 laps ≈ 25 minutes. Do it before the
draft is shared, not after a reviewer asks whether the results reproduce on current
hardware. It converts an unexamined assumption into a reproducibility result you can quote.

## 2. Check whether you have more than one driver, and whether they agree

The steering repo has two committed drivers — `closed_loop_ledger.py` (writes the scored
ledger) and `evaluate.py` (used by the sweeps and the selection gate). **They disagree, per
cell, in both directions, by enough to flip a verdict:**

```
  same checkpoint, same GPU, same night
    fog      evaluate.py 1.08 ft   ledger 1.34 ft   (+0.26)
    low sun  evaluate.py 2.12 ft   ledger 1.30 ft   (-0.82)   gate-failing vs comfortably passing
```

Ruled out by measurement: scoring scope (both exclude bridged spans), route, spawn, warmup.
**Cause still unidentified.** Nothing in that study is invalidated because every comparison
was kept driver-consistent within itself — but the two families of numbers are not
interchangeable, and it went unnoticed for the whole study.

**If AEB has a screening driver and a scored driver, run the same checkpoint through both
and diff.** It is an hour, and finding out later that a gate number and a ledger number were
never comparable is much worse.

## 3. A number that survived two measurements still died on the third

`sec_results.tex` in the steering paper quotes a student that "drives fog at 0.98 ft". It
measured 0.98 twice. On the third measurement, through the scored driver, it drove
**1.42 ft in twelve of twelve laps** and cleared the margin gate **zero** times.

That was the fifth single-draw claim in that study to weaken under a sweep. **AEB's
`docs/STUDY_REPORT.md` and the arXiv draft should be scanned for any number quoted from a
single run**, especially any that a Limitations or Conclusion sentence rests on. The fix is
cheap: quote the arm and its interval, not the seed.

## 4. Watch your own analysis code as hard as the experiment

Two of the errors in the steering programme were in **my summarising scripts**, not in the
data, and both would have inverted a conclusion:

* A "which condition stopped this candidate" tally recorded *the first failing condition in
  list order*, which systematically credited whichever condition was listed first. It
  reported that fog was no longer the stopper when fog was failing **every** candidate.
* A prediction scorer required N *measured* cells when VOID cells are excluded by design,
  so a VOID counted as a falsification — penalising an arm for a harness outcome.

Both were found by re-deriving a number by hand and not matching. **Do that once per
findings document.**

## 5. Report the margin, and keep VOID meaning what it means

A pass at 1% of budget and a pass at 60% are different results. In the steering study the
best tuned student passed every scored cell at 61% of budget while failing a 50%-margin
gate, and both statements are true and needed together.

On VOID: standing rule 3 says a cell whose repetitions disagree is void, not uncertain, and
**more laps convert an identified defect into a plausible failure rate and lose it.** When
the steering VOID cell resolved, it resolved because the *hardware* changed — not because
24 extra laps averaged it away. The 24 laps explained it; they did not rehabilitate it.

## 6. Two results about distillation that AEB is likely to hit

* **Distillation error is not a proxy for driving.** An arm with the *best* KD error of
  three had the *worst* driving record and three times the unmeasurable cells. Use the cheap
  metric to screen, never to decide.
* **The training dispersion is intrinsic.** Not initialisation, not data order (Levene
  p = 0.99 between them), not training-pool size, and not beaten by ensembling — an 8-model
  ensemble was still 31% worse than simply drawing the best seed. Plan for **n ≈ 20–60** to
  see a 20% effect on a driving endpoint. If AEB is comparing training configurations at
  n = 3–6, it is measuring noise.
* **Label balancing was the one cheap win** (`--balance`): fog holds 10/12 vs 5/14 raw,
  Fisher p = 0.012, and it *improved* the control condition. Worth trying early.

## 7. If AEB certifies anything, two traps

* **Bound width does not track driving quality.** On identical captures and identical ReLU
  count, the better-driving student had a **3.3× wider** bound. Do not select models on
  bound width.
* **Check what your criterion quantifies over.** The steering certificate takes the worst
  disturbance intensity **per pose** and then averages, while its witness search used a
  single global intensity. Two cells looked "undecided" for the whole study because of that
  gap — searching the family the criterion actually uses exhibited a witness for both.
  Whatever AEB's statistic is (a time-mean? a worst-instant?), write down explicitly what is
  free to vary and make the falsification search cover the same set.
