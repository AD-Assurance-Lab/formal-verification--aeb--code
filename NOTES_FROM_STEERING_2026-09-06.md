# What the steering study learned, for this one

Written 6 September 2026. These are the results that carry over. The full detail is in the
steering study's own findings files.

## 1. Check the instrument before you say a number failed to repeat

A new measurement that disagrees with an old one is a claim about two instruments. The new
one is not automatically the right one.

The steering study reported that a published number, 0.98 feet, did not repeat. It measured
1.42 feet twelve times and recommended dropping the number. The instrument was wrong. The
scored driver was missing a guard the diagnostic driver had. On the corrected driver the
same checkpoint drives 0.97, 0.97 and 0.98. The paper was right all along.

## 2. Check each guard on the tool that makes the published numbers

The missing guard above is a rule that says "verify the rendered condition from a frame,
every run". It lived only in the sweep tool. The tool that writes the published ledger never
did it, for the whole study. The only symptom was two tools quietly disagreeing.

"The study enforces the rule" was true and useless.

## 3. This study's own exposure, checked 6 September 2026

**What is fine.** Both places that set the light settle properly after writing the weather.
The next-tick trap is handled here.

**What is missing.** Nothing in this study checks the light level from a frame. There is no
signature check anywhere.

**Why it matters more here.** Light is not a nuisance parameter in this study. It is the
independent variable. The steering fault this guard catches was exactly this shape: the sun
angle was swept while the declared exposure belonged to a different condition, so daylight
scenes rendered through a night camera. Every run finished. Every number looked right.

**The cheap fix.** Record the mean, the spread and a low percentile of one rendered frame
per light level. Assert it against a reference, or at least store it, so a wrong light level
is recoverable afterwards instead of invisible.

## 4. Watch the summarising code as hard as the experiment

Two errors in the steering programme were in the summarising scripts, not in the data, and
both would have inverted a conclusion. One tally credited whichever condition was listed
first. One scorer counted a void cell as a failure.

Both were found by working a number out by hand and not matching. Do that once per findings
document.

## 5. Report the margin, and keep void meaning void

A pass at 1 percent of budget and a pass at 60 percent are different results.

A cell whose repetitions disagree is void, not uncertain. More repetitions turn a fault you
could have found into a plausible failure rate, and lose it. The steering void cell resolved
because the hardware changed, not because 24 extra laps averaged it away.

## 6. Two results about distillation this study will meet

**Distillation error is not a proxy for driving.** The arm with the best distillation error
of three had the worst driving record. Use the cheap measure to screen. Never to decide.

**The spread between training runs is intrinsic.** Not the starting weights, not the data
order, not the pool size, and not beaten by combining models. Plan for 20 to 60 runs to see
a 20 percent effect on a driving result. Comparing training settings at 3 to 6 runs measures
noise.

## 7. Two traps for anything this study certifies

**Bound width does not track driving quality.** On identical frames and identical size, the
better-driving student had a bound 3.3 times wider. Do not choose models on bound width.

**Check what the criterion varies over.** The steering certificate takes the worst
disturbance per pose and then averages. Its search for a counterexample used one global
value. Two cells looked undecided for the whole study because of that gap. Searching the set
the criterion actually uses found a counterexample for both.

Write down what is free to vary. Make the search cover the same set.
