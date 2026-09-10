# Pending: two simulator faults this study has not fixed

Written 28 August 2026. Updated 10 September 2026. Do not start the rework without talking
to Zach. Another study is finishing the reference version of the fix first.

## What was found

Measured in the steering study. Both faults affect every simulator study in this lab.

**1. The control command races the world step.** Synchronous mode with a fixed step lines
up the step. It does not line up the queue of commands feeding it. A late command that
repeats the same value changes nothing, so the fault only bites on a step where the command
changes. In a closed loop that is every step. Three runs of one scripted command sequence,
with the feedback cut, finished 60 metres apart.

**2. The engine loads textures in the background.** Which version of a texture is in memory
when a frame renders depends on load timing, not on the state of the world. Launching with
texture streaming off cut the noise the renderer adds by 168 times. It also removed the odd
first run after a restart.

Neither fault shows up in a result. Both give trajectories that look right. Every setting
these studies had pinned was pinned correctly. They were aimed at the wrong layer.

## What it means here

Closed-loop numbers carry the first fault. They are still rates over repetitions, which is
the right form. The spread between runs is wider than it needed to be, and nobody knew why.

Frames captured under the old harness cannot be reused. They hold texture variation that a
run with streaming off will never show. Capture them again. Do not reweight or filter them.

This is not only bad news. With the physics made exact, a tiny steering nudge still grew to
7.6 feet of cross-track error over 349 steps. That growth belongs to the policy, not to the
simulator. So the spread between runs reads as a measurement of how close to the edge a
policy sits.

## The fix, when this study's turn comes

    pip install carla-determinism

Bind the client, run the preflight, and route every control command through the package.
Launch the server with texture streaming off and quality at Epic.

Read the package's rules first. Two are easy to get backwards. Do not turn off the
post-process effects, because manual exposure lives inside that chain and turning it off
measured about 2000 times worse. Do not drop below Epic quality, because High measured far
worse.

Order of work, set by Zach on 28 August 2026: the steering study's two maps first, then this
study, then the rest.

---

## Settled here on 9 September 2026

**Three repetitions, not ten.** Each gets its own process and its own freshly restarted
server. Report the margin. Repetitions that disagree make the cell void.

This was measured here rather than taken from another study. Of 281 committed
ten-repetition cells, 277 were unanimous. All four splits had causes we found, and none of
the causes was sampling. Two were a scoring fault, one was a policy sitting on its own brake
threshold, and one was the simulator drifting.

The shared package still says ten. Its measurement is not in dispute: frames are never
identical. What this study disputes is the step from "frames are never identical" to
"therefore ten repetitions with a confidence interval". What the floor protects is a stable
verdict, not identical frames.

The request to change that rule is now in the package, at
`docs/amendment-requests/2026-09-10-D7-repetition-floor-from-aeb.md`. Nothing in the package
changed. The change is Zach's to make.

**And the repetition count was the smaller half.** Clouds move under a fixed weather
setting, so scene brightness at the horizon drifts with elapsed simulated time. Cloud cover
is now zero here. Whether the package should carry that rule is not a study's call.

## Still owed, and nothing fails if it is skipped

That last clause is why it is written down.

1. Bind the client and route every control command through one choke point. A raw control
   call anywhere else is the fault.
2. Launch with texture streaming off and quality at Epic.
3. Restart before every repetition. One process, one vehicle, one camera each.
4. Record the harness in every cell: the package version, the rules digest, the lock check
   and the server's real command line. Record unknown as null, never as false. Without this,
   the rule against reusing old data cannot be enforced after the fact.
5. Make the blind-order check run on every commit. The tool is here. In the steering study a
   prune deleted it. Nobody noticed for a whole study. A rule that names a missing tool
   fails the way a passing check looks.
