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

## 2. The steering drivers disagreed, and the cause turned out to be a MISSING GUARD

**Updated 2026-09-06 after the cause was found.** This started as "two committed drivers
report different numbers for the same checkpoint, cause unknown":

```
  same checkpoint, same GPU, same night
    fog      evaluate.py 1.08 ft   ledger 1.34 ft
    low sun  evaluate.py 2.12 ft   ledger 1.30 ft   gate-failing vs comfortably passing
```

**The cause was six `world.tick()` calls.** `evaluate.py` ticked six times before driving to
grab a rendered frame for its condition check; the scored ledger did not. Six ticks of extra
settling moved where warmup ended by about a millimetre, and the closed loop amplified that
into a different discrete basin. Neither driver was scoring anything wrongly.

**The real finding was underneath it.** That rendered-frame check is R-SIM-4 — *"verify the
rendered condition from a FRAME, every run"* — and it existed **only in the sweep/gate
driver**. The driver that writes the published ledger never did it. A rule stated as "every
run" was enforced on the diagnostic path and not the authoritative one, for the whole study,
and the only visible symptom was two drivers quietly disagreeing.

**It cost something real:** one of my overnight conclusions was inverted by it. I reported
that the paper's "drives fog at 0.98 ft" did not replicate — measured 1.42 ft twelve times —
and recommended removing the number. On the corrected driver the same checkpoint drives
0.97/0.97/0.98, and the paper's number was right all along.

**The transferable lesson is not "check your drivers agree". It is: verify each guard on the
binary that produces the published numbers, not on the study as a whole.** "The study
enforces R-SIM-4" was true and useless.

## 2b. AEB's specific exposure, checked 2026-09-06

I looked, so this is about your code and not a generic warning.

**What is fine.** Both illumination call sites settle properly after writing the weather —
`world.set_weather(wx)` followed by `for _ in range(J.WEATHER_SETTLE_TICKS)` in
`tools/interval_sweep.py` and `tools/gate_behavioural.py`. The next-tick trap that bit the
steering study is handled here.

**What is missing.** There is **no frame-level verification anywhere in this repo** —
no signature check, no assertion that the rendered scene is the illumination that was asked
for. `grep` for `condition_signature|assert_condition` returns nothing.

**Why that matters more for AEB than it did for steering.** Illumination is not a nuisance
parameter here, it is *the independent variable*: the headline is a policy that passes both
FMVSS 127 lighting endpoints and fails between them. The steering failure this guard exists
to catch (T06-F35) was exactly this shape — sun altitude was swept while the declared
**exposure** belonged to a different condition, so daylight scenes were rendered through a
night camera. **Every run completed, every number was plausible, every step count was
normal.** Nothing downstream could reveal it.

**And there are six entry points that tick the world** (`scenarios.py`, `carla_jobs.py`,
`run_policy.py`, `drive_witness.py`, `capture_campaign.py`, `probe_memory.py`). The steering
study had two and they diverged. Six is more surface, not less.

**Cheap, proportionate fix:** record a photometric signature of one rendered frame per
illumination — mean, sigma, low percentile is enough — and assert it against a reference, or
at minimum record it in the artifact so a wrong illumination is recoverable after the fact
instead of invisible. The steering version (`scripts/condition_signature.py`) classified
24/24 held-out captures correctly and costs one frame.

## 3. Single-draw numbers are the recurring failure, but check your instrument first

Four claims in the steering study weakened once they were swept rather than drawn once:

* a resolution trend (`168x28 6.85 ft` vs `168x56 11.15 ft`) that turned out to span
  1.47–30.48 and 1.56–41.54 ft over six seeds;
* KD error figures quoted from the favourable end of a six-seed range;
* a learning-rate effect that was 6x on six seeds and landed at p = 0.055 on fifteen;
* a balancing result at n = 6 that needed n = 12 to reach p = 0.012.

**So: scan `docs/STUDY_REPORT.md` and the arXiv draft for any number quoted from a single
run**, especially one a Limitations or Conclusion sentence rests on. Quote the arm and its
interval.

**But the cautionary tale here is the opposite one, and it is the more useful half.** I
reported a fifth such failure overnight — the paper's "drives fog at 0.98 ft" measured
1.42 ft twelve times, so I recommended removing it. **That was my instrument, not the
number.** The scored driver was missing the guard described in §2, which put every one of
those twelve laps in a different basin. On the corrected driver it reads 0.97/0.97/0.98 and
the paper was right.

**Before concluding that a published number failed to replicate, confirm the thing measuring
it has not changed.** A disagreement between a new measurement and an old one is a claim
about *two* instruments, and the new one is not automatically the trustworthy one.

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
