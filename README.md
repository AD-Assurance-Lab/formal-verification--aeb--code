# formal-verification--aeb--code

Formal verification of automatic emergency braking under degraded visibility.

**Owner:** Zach. **Status:** new, empty. **First milestone:** demo at the automotive
technology expo, Novi, October 2026.

## What this is for

Certify that an AEB function meets its stopping requirement across a declared range of
illumination and contrast degradation, without running the test fleet.

The commercial artifact is one sentence:

> Here is the certified illumination and contrast envelope in which your pedestrian AEB
> meets its stopping requirement, computed without running the test fleet.

## Why AEB, and why first

1. **Regulatory anchor with a date.** US rulemaking mandates AEB including pedestrian
   detection in darkness for light vehicles, and Euro NCAP already scores night pedestrian
   AEB. **Verify the rule number, scope and compliance date against the source before this
   appears in any deck or proposal.** It has not been checked here. Also settle the vehicle
   class question: the light-vehicle rule may not cover truck platforms, and heavy-vehicle
   AEB is separate rulemaking.
2. **We already have the hard half.** The steering study established that night and shadows
   break a perception model that is fine in clear weather. That is exactly the condition the
   regulation targets.
3. **The hazard is localized by construction.** In lane keeping the safety threshold is a
   *sustained* error, and the peak statistic is dimensionally wrong for it. In AEB the hazard
   is a single event, so the peak should be the right quantity here.

## The scientific bet

If the peak statistic works for AEB and fails for lane keeping, the two results together
state a general principle: **match the certified statistic to the temporal structure of the
failure**, demonstrated with both failure modes of getting it wrong. That is stronger than
either result alone, and it is the reason to run this as a study rather than only as a demo.

## Scope

- A braking policy, a closed-loop AEB harness, and longitudinal dynamics, which the steering
  study deliberately held fixed.
- A safety specification **derived from primitives**, the way `delta_tol = 0.0120` was
  derived from lane width, vehicle width, wheelbase, speed and a 1.85 s reaction horizon.
  Candidate primitives here: stopping distance, minimum TTC, impact speed.
- The specification is a document and should be written before any code.

## Prior art in this lab

The steering study is the parent. Read, in this order:

- `formal-verification--automated-driving--code/CLAUDE.md`
- `formal-verification--automated-driving--code/docs/STATE_OF_PLAY.md`, sections 0, 0b, 0c
- `formal-verification--automated-driving--code/docs/TRAPS.md` and `docs/CONSTRAINTS.md`
- `lab--future-plans--docs/RESEARCH_DIRECTIONS.md`, entry A1

## Risk

The build is larger than it looks and the expo date is fixed. If it slips, the expo demo
falls back to the twelve canonical steering cells plus the occlusion result. Decide that
fallback early rather than late.

---

## Running this

The repository is public and is a **proof of concept**, not production code. It is meant to
be readable by someone outside the lab.

**Without a simulator**, which is most of what exists today:

```bash
python tools/survey_maps.py           # choose the test map from map geometry alone
python -m study.protocol_lock         # confirm the frozen design has not moved
python -m study.status                # where the study stands, in the protocol's terms
python tools/tidy.py                  # repo hygiene report
```

`tools/survey_maps.py` needs a CARLA **installation** for its map files, but not a running
server. Point it anywhere with `--carla`.

**With a simulator:**

```bash
python tools/carla_jobs.py --list     # what is queued, in dependency order
python tools/carla_jobs.py --all      # runs them, stops at the first failure
```

## Layout

| | |
|---|---|
| `PROTOCOL.md` | the study design, frozen. Start here |
| `study/` | the lock, the status report, and recorded results |
| `tools/` | everything runnable |
| `docs/` | the paper outline and working notes |
| `results/` | outputs. Large artefacts are git-ignored |
| `stale/` | files on their way out, git-ignored. Inspect and delete |

## Housekeeping

Before pushing anything you want read by someone else, run `python tools/tidy.py`. Delete
nothing by hand in anger: move it to `stale/` instead, look at it later, then remove it.
Anything that was ever committed stays in git history, so parking a file loses nothing.
