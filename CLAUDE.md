# formal-verification--aeb--code

Automatic emergency braking under poor visibility. Owner: Zach. Demo: Novi, October 2026.

This file holds every working note the repository used to keep in `docs/`. One notes file
is left: `docs/ARXIV_NOTES.md`, for the paper repository. The rest are in
`stale/notes_folded_into_claude_2026-09-10/` and in git history.

`FINDINGS.md`, the amendments and the pre-registration still name the old filenames. Those
records were true when they were written and nothing edits them after the fact. Look in
`stale/` for anything they name and you cannot find.

A number in brackets points to a record in `FINDINGS.md` or `PROTOCOL.md`. You do not need
it to follow this file.

## Read before you write code

1. Run `python -m study.protocol_lock`.
2. Run `python -m study.status` for live numbers.
3. Read `PROTOCOL.md` for the design and `FINDINGS.md` for the measured record.

## The protocol is locked

`PROTOCOL.md` is the study design and it is frozen. Run the lock check before you read any
result, and before you propose a change of direction. It fails if anything above the
amendments changed without a recorded amendment.

When a result and the design disagree about what the study is, the design is correct. Put
findings in `FINDINGS.md`. Neither may redefine the design.

To change the design, append an amendment entry, say what changed and why, then run
`python -m study.protocol_lock --accept`. The design may change. It may not change silently
while experiments run against it. This lab has lost its study logic twice, both times by
drift and not by decision.

## Where the study is, 10 September 2026

The training now repeats, which was the block. Next: measure the behavioural check on the
lighting range with `scripts/gate_repair_loop.sh`. Then verify, write the verdicts to git by
hand, then drive.

**Withdrawn.** Every endpoint verdict, check result and certificate from the overnight run of
10 September is withdrawn. They were measured against networks that cannot be made again.
That includes the written prediction that all three policies pass all three lighting
conditions the standard tests. The files are in `stale/nonreproducible_pre_F30_2026-09-10/`.

**Open.** Every policy brakes for a steel plate at one or more of the three lighting
conditions the standard tests. On the old map all nine tests passed. Measure it again on
networks that repeat before you reason about it (F29 causes it, F30 fixes it).

## Repository hygiene

This is a public repository and a proof of concept. The bar is that an outsider can follow
it. It is not production quality. Try things. Do not leave the wreckage behind.

- Delete nothing in anger. Move it to `stale/`, which git ignores. Zach inspects it and
  removes it. Git history keeps anything you ever committed.
- Run `python tools/tidy.py` before you push anything meant to be read. It reports an
  unclean tree, unpushed commits, large files, loose notes and unused modules. It never
  deletes.
- Push often. GitHub is the backup.
- Keep `README.md` honest about what runs without a simulator. Most readers have none.
- Do not add continuous integration, formatters or linters.

## Write the specification before any code

The deliverable that unblocks the rest is a safety specification built from primitives. The
steering study did this. Its tolerance came from lane width, vehicle width, wheelbase, speed
and a reaction horizon, with no fitted parameter.

Do the same here from stopping distance, minimum time to collision and impact speed. It is a
document. It needs no simulator. Expo pressure will tempt you to skip it.

## The statistic is a hypothesis

The working expectation is that the peak is the correct statistic for braking, because the
hazard is one event. For lane keeping the peak was wrong, because that threshold described a
sustained error.

This is the scientific bet of the repository. Test it blind. If it fails, the failure is the
result. Do not lean on the steering study for it. Over there the comparable figure is
withdrawn and the paper says the question is open.

## Standing rules

Each one is a measured result, not a preference. Each exists because breaking it cost time.

- A result that contradicts a written expectation is a fault until you prove otherwise. Do
  not write it up until a disposition lists the causes you ruled out.
- Write verification verdicts to git before the matching drive. That is what makes a verdict
  a prediction. Four criteria in the parent study scored 14/14, 7/8, 8/8 and 10/10 in
  sample, then 2/6, 3/7, 6/10 and 2/4 blind.
- Train on the parameterised family. Test closed loop on points from that family's axis.
  Verify over the same interval. If training and verification disagree about the
  disturbance, the comparison means nothing.
- Make every closed-loop number a verdict over at least 3 repetitions. Give each repetition
  its own process and its own freshly restarted server. Report the margin. Never report a
  single run.
- Repetitions that disagree make the cell void. That is a fault until you prove otherwise.
  It is never a reason to run more repetitions. Of 281 committed ten-repetition cells, 277
  were unanimous, and all four splits had causes we found (A13, F22).
- Three repetitions depend on the restart harness, `scripts/drive_witness_reps.sh`. A loop
  inside one process is not that harness and keeps ten. That is why `carla_jobs.py` carries
  two constants.
- Keep a known-bad control in every experiment. A model that must fail the conditions it
  never saw is what catches specification faults.
- Apply disturbances at full sensor resolution, before crop and downsampling. Never apply
  them to the network input.
- Certify against the closed-loop tolerance, not a per-frame corridor. In the steering study
  the per-frame corridor was about 3.4 times too permissive, and a vehicle left the road
  with every frame inside it.
- Keep the verifiable network free of batch normalisation and dropout. Width is the capacity
  lever. It must still drive closed loop.
- Depend on the bound library from upstream through pip. Do not vendor it. Do not use the
  method that needs a round ball, because it is vacuous on our sets.
- Never trade experimental quality for speed. No processor fallback, no lowered simulator
  quality, no cut training. Warn Zach before a run longer than 1 hour.

## Training must repeat, and four settings make it

Seeding the three random number generators is necessary. On the graphics card it is not
enough. The convolution library picks an algorithm by timing it. Some operations have no
repeatable version unless one is demanded. The matrix library sums in an order that follows
its workspace.

Set the workspace variable before the machine learning library is imported. Setting it later
fails quietly. Then demand repeatable operations and turn off algorithm timing.

Without them, three quarters of every policy's numbers moved between two runs of one
command, and endpoint verdicts flipped with them (F29). With them, four separate runs gave
the same file, byte for byte, at a cost of 3 percent (F30).

## Every path is named once, and carries the map

`tools/paths.py` names the frames folder, the results folder and the models folder. It
imports nothing but the standard library, so the tools that must run without a simulator can
share it. Do not type a path out again. That is the fault, not the cure.

Old files used to sit under the exact names the new tools ask for. Nothing raised an error.
This happened four times in one night, and once it nearly gave a wrong answer about whether
the training repeats.

## A count of pieces is not a measure of coverage

The lighting range is cut until the middle of a piece is close enough to the straight line
across it. The rule uses a fixed distance, so it can make a piece across which the scene does
not change at all.

On clean frames, 8 of the 29 pieces span nothing. Two of those are 7.4 degrees of sun angle
wide, because below about 14 degrees under the horizon only the headlamps light the road. So
width in degrees and distance in light disagree, and they disagree most at the dark end
(F27, F31).

Report the distance in light beside every verdict. `tools/family_fidelity.py` measures it and
needs no simulator.

## Two simulator faults, still not fixed here

Measured in the steering study. Both affect every simulator study in this lab. Do not start
the rework without talking to Zach.

**The control command races the world step.** Synchronous mode with a fixed step lines up the
step, not the queue of commands feeding it. A late command that repeats a value changes
nothing, so it only bites where the command changes. In a closed loop that is every step.
Three runs of one scripted sequence, with the feedback cut, finished 60 metres apart.

**The engine loads textures in the background.** Which version is in memory when a frame
renders depends on load timing, not on world state. Turning texture streaming off cut the
noise the renderer adds by 168 times.

Neither shows up in a result. Both give trajectories that look right.

Frames captured under the old harness cannot be reused. Capture them again. Do not reweight
or filter them.

The fix is `pip install carla-determinism`. Bind the client, run the preflight, and route
every control command through the package. Launch with texture streaming off and quality at
Epic. Do not turn off the post-process effects, because manual exposure lives in that chain.
Do not drop below Epic quality.

Still owed, and nothing fails if it is skipped. That is why it is written down.

1. Route every control command through one choke point.
2. Restart the server before every repetition.
3. Record the harness in every cell. Record unknown as null, never as false.
4. Make the blind-order check run on every commit.

## Two simulator rules that keep biting

**A read or a placement next to a write does not see that write.** Weather, spectator
transforms and sensor delivery all apply on the next step. Nothing raises an error when you
get this wrong.

**A fixed weather is not a static scene.** The cloud layer moves, so scene brightness at the
horizon drifts with elapsed simulated time and never settles. Light is this study's
independent variable, so the independent variable is what drifts. Cloud cover is now zero
here, which settles it (A15, F23).

Never read back state you just wrote. Construct it. Match sensor frames on the identifier the
world step returns. Never swallow a missing frame.

Take the camera frames darkest first, and darken the world before the practice run. A dark
frame comes out nine times too bright if a bright frame was taken first, and it never settles
(A16, A17, F28).

## The simulator is shared

- Book it. Zach, three students and another project want the same machine.
- Relaunch the server before every measurement run. It leaks about 10.5 GiB over 11 hours.
- Use the non-default port on the lab machine. Check before you assume 2000.
- Detach long runs with `setsid nohup`. The harness kills foreground jobs.
- A pattern kill matches your own command line. Use bracket patterns or process numbers.
- `grep` block-buffers into a file. Use `--line-buffered`, or a healthy run looks stalled.
- A wait loop on a command-line match can match itself. Wait on a process number or a result
  file. This cost an hour.
- `tail` buffers too. Do not pipe a job you want to watch.
- One client at a time in synchronous mode. A second script asking for the world just times
  out, and that looks exactly like a dead server.
- Look at the data, not only at the statistics. Two faults passed every numeric check and
  were obvious in one frame. One was an exposure six stops too fast, which the clipping
  check called healthy. One was a pedestrian measured at 10.6 m who stood 6 m to the side.
  Export a frame and open it.

## What the steering study learned, for this one

- **Check the instrument before you say a number failed to repeat.** A disagreement between
  a new measurement and an old one is a claim about two instruments. The new one is not
  automatically right. The steering study nearly withdrew a correct published number that
  way. Its scored driver was missing a guard its diagnostic driver had.
- **Check each guard on the tool that makes the published numbers.** That missing guard lived
  only in the sweep tool, for a whole study. "The study enforces the rule" was true and
  useless.
- **Watch the summarising code as hard as the experiment.** Two errors were in the
  summarising scripts, and both would have inverted a conclusion. Both were found by working
  a number out by hand.
- **Report the margin.** A pass at 1 percent of budget and a pass at 60 percent are different
  results.
- **Distillation error is not a proxy for driving.** The arm with the best distillation error
  of three had the worst driving record. Screen with the cheap measure. Never decide with it.
- **The spread between training runs is intrinsic.** Not the starting weights, not the data
  order, and not beaten by combining models. Plan for 20 to 60 runs to see a 20 percent
  effect. Comparing settings at 3 to 6 runs measures noise.
- **Bound width does not track driving quality.** The better-driving student had a bound 3.3
  times wider. Do not choose models on bound width.
- **Check what the criterion varies over.** Two steering cells looked undecided for a whole
  study because the search used one global value where the criterion varies per pose. Write
  down what is free to vary. Make the search cover the same set.
