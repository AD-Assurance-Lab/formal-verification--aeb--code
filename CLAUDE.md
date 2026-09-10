# formal-verification--aeb--code

AEB under degraded visibility. Owner: Zach. Demo target: Novi, October 2026.

> **Stop: CARLA determinism defect.** Read `CARLA_DETERMINISM_PENDING.md` before
> you run or trust any closed-loop measurement here. Two defects found on
> 2026-08-28 affect every CARLA study in the lab. The rework waits behind Town06.
> Do not start it without talking to Zach.

## The protocol is locked

`PROTOCOL.md` is the study design and it is frozen. Run this before you read any
result, and before you propose a change of direction:

    python -m study.protocol_lock

It fails if anything above the Amendments section changed without a recorded
amendment.

When a result and `PROTOCOL.md` disagree about what the study is, `PROTOCOL.md`
is correct. Put findings in `FINDINGS.md`. Put current belief in
`docs/STATE_OF_PLAY.md`. Neither file may redefine the design.

To change the design, append an `### A<n>` entry under `## Amendments`. Say what
changed and why. Then run `python -m study.protocol_lock --accept`. The design may
change. It may not change silently while experiments run against it. This lab has
lost its study logic twice, both times by drift and not by decision.

## Repository hygiene

This is a public repository and a proof of concept. The bar is that an outsider
can follow it. It is not production quality. Try things. Do not leave the wreckage
behind.

- Delete nothing in anger. Move it to `stale/`, which git ignores. Zach inspects
  it and removes it. Git history keeps anything you ever committed.
- Run `python tools/tidy.py` before you push anything meant to be read. It reports
  an unclean tree, unpushed commits, large files, loose TODOs and unused modules.
  It never deletes.
- Push often. GitHub is the backup.
- Keep `README.md` honest about what runs without a simulator. Most readers do not
  have CARLA.
- Do not add CI, formatters or linters. This is not a production codebase.

## Write the specification before any code

The deliverable that unblocks the rest is a safety specification built from
primitives. The steering study did this: `delta_tol = 0.0120` came from lane
width, vehicle width, wheelbase, speed and a 1.85 s reaction horizon, with no
fitted parameter.

Do the same here from stopping distance, minimum time to collision and impact
speed. It is a document. It needs no simulator. Expo pressure will tempt you to
skip it.

## The statistic is a hypothesis

The working expectation is that the peak is the correct statistic for AEB,
because the hazard is one event. For lane keeping the peak was wrong, because
that threshold described a sustained error.

This is the scientific bet of the repository. Test it blind. If it fails, the
failure is the result.

## Inherited standing rules

These are measured results, not preferences. Each one exists because breaking it
cost the lab time.

- A result that contradicts a pre-registered expectation is a bug until you prove
  otherwise. Do not write it up as a finding until a written disposition lists
  the causes you ruled out.
- Commit verification verdicts to git before the matching closed-loop run. That is
  what makes a verdict a prediction. Four criteria in the parent study scored
  14/14, 7/8, 8/8 and 10/10 in sample, then 2/6, 3/7, 6/10 and 2/4 blind.
- Train on the parameterized family. Closed-loop test on points from that family's
  axis. Verify over that same interval. If training and verification disagree
  about the disturbance, the comparison means nothing.
- Make every closed-loop number a verdict over at least 3 repetitions. Give each
  repetition its own process and its own freshly restarted server. Report the
  margin. Never report a single run.
- Repetitions that disagree make the cell VOID. That is a bug until you prove
  otherwise. It is never a reason to run more repetitions. An amendment replaced
  the ten-repetition rule after measuring what ten bought: of 281 cells, 277 were
  unanimous, and all four splits had identifiable causes (A13, F22).
- Three repetitions depend on the restart harness, `scripts/drive_witness_reps.sh`.
  A `for _ in range(REPS)` loop inside one process is not that harness and keeps
  ten. That is why `carla_jobs.py` carries two constants.
- Keep a known-bad negative control in every experiment. A model that must fail
  the conditions it never saw is what catches specification bugs.
- Apply disturbances at full sensor resolution, before crop and downsampling.
  Never apply them to the network input.
- Certify against the closed-loop tolerance, not a per-frame corridor. In the
  steering study the per-frame corridor was about 3.4 times too permissive, and a
  vehicle left the road with every frame inside it.
- Keep the verifiable network ReLU-only. No BatchNorm and no Dropout. Width is the
  capacity lever. It must still drive closed-loop.
- Do not vendor `auto_LiRPA`. Depend on upstream `Verified-Intelligence/auto_LiRPA`
  through pip. Do not use SDP-CROWN. It needs an L2 ball and is vacuous on our
  sets.
- Never trade experimental quality for speed. No CPU fallback, no lowered
  simulator quality, no cut epochs. Warn Zach before a run longer than 1 hour.

## Two CARLA rules that keep biting

**A read or a placement next to a write does not see that write.** The simulator
applies `world.set_weather()`, spectator `set_transform()` and sensor delivery on
the next tick. Nothing raises an error when you get this wrong.

**A fixed weather is not a static scene.** Every driver here sets
`cloudiness = 10.0`, and the CARLA cloud layer moves. Scene brightness at the
horizon drifts 3.9% with elapsed simulated time and never settles. At
`cloudiness = 0.0` the same scene settles by tick 20 and holds to 0.08%.
`WEATHER_SETTLE_TICKS = 120` returns long before the drift ends. Illumination is
this study's independent variable, so the independent variable is what drifts. A
capture that settles once and then walks its poses sweeps the curve along its own
pose index. This is open, and it needs an amendment before you re-measure
anything on it (F23).

Never read back state you just wrote. Construct it. Match sensor frames on the id
that `world.tick()` returns. Never swallow a missing frame.

## CARLA is shared

- Book it. Zach, three students and the Isuzu project all want the same simulator.
- Relaunch the server before every measurement run. It leaks about 10.5 GiB over
  11 hours.
- Use the non-default port on the lab machine. Check before you assume 2000.
- Detach long runs with `setsid nohup ... &`. The harness kills foreground jobs.
- `pkill -f` matches your own command line. Use bracket patterns or PIDs.
- `grep` block-buffers into a file. Use `--line-buffered`, or a healthy run looks
  stalled.
- A wait loop on `pgrep -f` can match itself. `until ! pgrep -f "[v]erify.py"`
  looks safe, but if the waiting script's own command line holds the unbracketed
  text anywhere, pgrep finds the wrapper and the loop never exits. This cost an
  hour. Wait on a PID or a result file.
- `tail` buffers too. A job piped through `| tail -N` gives no output until it
  ends, so a healthy run looks hung. Do not pipe a job you want to watch.
- Look at the data, not only at the statistics. Two defects passed every numeric
  check and were obvious in one frame: an exposure six stops too fast, which the
  clipping check called healthy, and a pedestrian measured at 10.6 m who stood
  6 m to the side. Export a frame and open it.

## Read before you write code

`formal-verification--steering--code/CLAUDE.md`, then `docs/STATE_OF_PLAY.md`
sections 0, 0b and 0c, then `docs/TRAPS.md` and `docs/CONSTRAINTS.md`.
