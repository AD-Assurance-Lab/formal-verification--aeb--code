# OPEN: every policy brakes for the steel plate at a condition the standard tests

Measured 10 September 2026. **Not a finding.** A result that contradicts a written
prediction is a fault until somebody proves otherwise. It is not written up until a
disposition lists the causes ruled out. This file is the contradiction.

## Read this first

**The numbers below are withdrawn.** They were measured against networks that cannot be made
again, because the training did not repeat (F29). The fix landed the same day (F30). The old
files are in `stale/nonreproducible_pre_F30_2026-09-10/`.

So this file states a question. Measure it again on networks that repeat.

## Predicted, then measured

The prediction, written before any of this: all three policies pass all three regulatory
endpoints, ten times out of ten.

The hazard endpoints held it exactly. Eighteen cells, every one ten of ten.

The false-activation endpoints did not. The limit is 2.4525 m/s².

| policy | daylight | dark, lower beam | dark, upper beam |
|---|---|---|---|
| points-trained | 10/10, peak 1.42 | 9/10, peak 2.50 | **0/10, peak 3.03** |
| continuum-trained | 10/10, peak 2.24 | 10/10, peak 1.79 | **0/10, peak 3.28** |
| three-condition | 10/10, peak 1.41 | **0/10, peak 3.19** | 10/10, peak 0.56 |

On the old map all nine passed.

## Why it would matter, if it survives

The study's setup sentence is that the standard's own procedure cannot tell the policies
apart. That still holds for the hazard scenes. It would be false here: the standard's own
test would separate them, and fail all three.

It would also invert a published claim. Earlier work treated false activation as the thing
one policy might do and the others would not. Here it is every policy, at the endpoints,
before any interior is considered.

## Causes to rule out, none ruled out

1. **The training did not repeat.** Now fixed. Exclude it first. It can explain the whole
   table on its own.
2. **The night frames changed by nine times.** The capture order fix made the dark captures
   much darker. The plate is steel and lit by the headlamps, so at night it may be one of
   the few bright things in frame.
3. **The road.** The new site is four lanes with pavements. The old one was two. The plate
   covers a different fraction of a differently lit scene.
4. **The beam split.** One policy fails on lower beam and passes on upper. The other two do
   the reverse. That is not one physical story. Opposite failures in different policies look
   more like a threshold meeting training than a property of the plate.
5. **The plate.** Nine tiles covering exactly 8.0 by 12.0 feet, so the placement is right.
   Nobody has looked at how its material renders under these headlamps.
6. **A real result.** A camera-only braking system firing on steel at night is plausible and
   worth reporting. It is last on purpose: it is the most interesting explanation, so accept
   it only after the others are dead.

## What must not happen

Do not quietly drop the plate endpoints from the criterion so the study can proceed. The
pipeline did not stop here, because the milestone criterion names only the hazard scenes. So
this could pass unnoticed into the paper as an unexamined regression. That is why this file
exists.
