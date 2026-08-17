# CLAUDE.md - read this before doing anything

AEB under degraded visibility. Owner: Zach. Demo target: Novi, October 2026.

## The protocol is locked. Read it first, and do not edit it.

**`PROTOCOL.md` is the study design and it is frozen.** Run this before interpreting any
result, and before proposing any change of direction:

    python -m study.protocol_lock

It fails if anything above the Amendments section changed without a recorded amendment.

**When a result and `PROTOCOL.md` disagree about what the study is, `PROTOCOL.md` is right.**
Findings go in `FINDINGS.md`, current belief goes in `docs/STATE_OF_PLAY.md`, and neither may
quietly redefine the design.

To change the design: append an `### A<n>` entry under `## Amendments` saying what changed and
why, then `python -m study.protocol_lock --accept`. The design is allowed to change. It is not
allowed to change silently while experiments run against it. Study logic in this lab has been
lost twice, both times by drift rather than by decision.

See `README.md` for what this repository is, and `docs/PAPER_OUTLINE.md` for the write-up.

## Repo hygiene

Public repository, proof of concept. The bar is **an outsider can follow it**, not
production quality. Iterating and trying things is expected; leaving the wreckage behind
is not.

- **Nothing is deleted in anger. It goes in `stale/`**, which is git-ignored, and Zach
  inspects and removes it. Parking a tracked file there loses nothing, because anything
  ever committed stays in git history.
- **`python tools/tidy.py` before pushing** anything meant to be read. It reports an
  unclean tree, unpushed commits, oversized files, loose TODOs and unreferenced modules.
  It never deletes.
- **Push often.** GitHub is the backup. An experiment worth keeping is worth committing.
- **Keep `README.md` honest about what runs without a simulator.** Most people reading
  this will not have CARLA, and a repo that cannot be tried is a repo nobody reads.
- Do not add CI, formatters or linters. That is production tooling and this is not a
  production codebase.

## Write the specification before any code

The deliverable that unblocks everything else is a **safety specification derived from
primitives**, in the manner of the steering study: `delta_tol = 0.0120` came from lane width,
vehicle width, wheelbase, speed and a 1.85 s reaction horizon, with no fitted parameter.

Do the same here from stopping distance, minimum TTC and impact speed. It is a document, it
needs no simulator, and it is the thing most likely to be skipped under expo pressure.

## The statistic is a hypothesis, not an assumption

The working expectation is that the **peak** is the right statistic for AEB, because the
hazard is a single event, where it was dimensionally wrong for lane keeping because that
threshold described a *sustained* error.

That is the scientific bet of this repository. It is not a licence to assume it. It gets
tested blind like everything else, and if it fails, the failure is the result.

## Inherited standing rules

These are measured results from the steering study, not preferences. Violating one silently
reproduces a bug that has already cost this lab real time.

- **A result that contradicts a pre-registered expectation is a bug until proven otherwise.**
  It may not be written up as a finding until a written disposition lists the candidate
  causes that were ruled out.
- **Verification verdicts are committed to git before the corresponding closed-loop run.**
  That is what makes a verdict a prediction. Four criteria in the parent study scored 14/14,
  7/8, 8/8 and 10/10 in-sample and then 2/6, 3/7, 6/10 and 2/4 blind. In-sample agreement
  means nothing here.
- **Train on the parameterized family, closed-loop test on points from that family's axis,
  and verify over that same interval.** If training and verification disagree about what the
  disturbance is, the comparison is meaningless.
- **Every closed-loop number is a failure RATE over at least 10 repetitions**, never a single
  run. Report Wilson intervals.
- **Keep a known-bad negative control in every experiment.** A model that must fail the
  conditions it never saw is what catches specification bugs.
- **Disturbances apply at full sensor resolution, before crop and downsampling**, never to
  the network input.
- **Certify against the closed-loop tolerance**, not a per-frame corridor. In the steering
  study the per-frame corridor was about 3.4x too permissive and a vehicle departed the road
  with every frame inside it.
- **The verifiable network stays ReLU-only**, no BatchNorm or Dropout. Width is the capacity
  lever. Do not collapse to a trivial controller either; it must still drive closed-loop.
- **Do not vendor `auto_LiRPA`.** Depend on upstream `Verified-Intelligence/auto_LiRPA` via
  pip. **Do not use SDP-CROWN**; it requires an L2 ball and is vacuous on our sets.
- **Never trade experimental quality for speed.** No CPU fallback, no lowered simulator
  quality, no cut epochs. Warn before runs over 1 h.

## The CARLA rule that has bitten five times

> **A read or a placement issued next to a write does not see that write.**
> `world.set_weather()`, spectator `set_transform()` and sensor delivery are all applied by
> the simulator on the NEXT TICK. Nothing errors when you get this wrong.

Never read back state you just wrote; construct it. Match sensor frames on the id
`world.tick()` returns, and never swallow a missing frame.

## CARLA is shared. Operating notes.

- Book it. Zach, three students and the Isuzu project all want the same simulator.
- **Relaunch the server before every measurement run.** It leaks about 10.5 GiB over 11 h.
- **Non-default port** on the lab machine. Check before assuming 2000.
- **Long runs must be detached** (`setsid nohup ... &`). Foreground and harness-waited jobs
  get killed.
- **`pkill -f` matches your own command line.** Use bracket patterns or PIDs.
- **`grep` block-buffers into a file.** Use `--line-buffered`, or a healthy run looks stalled.
- **`tail` buffers too.** Piping a long job through `| tail -N` gives NO output until it
  ends, so progress is invisible and a healthy run looks hung. Do not pipe a job you want
  to watch. Written down after doing it twice in one session.
- **Look at the data, not only at statistics.** Two defects this session survived every
  numeric check and were obvious in one frame: an exposure six stops too fast, which the
  clipping check called healthy, and a pedestrian measured at "10.6 m" who was 6 m off to
  the side. Export a frame and open it.

## Parent repository

Read before writing code:
`formal-verification--automated-driving--code/CLAUDE.md`, then `docs/STATE_OF_PLAY.md`
sections 0, 0b and 0c, then `docs/TRAPS.md` and `docs/CONSTRAINTS.md`.
