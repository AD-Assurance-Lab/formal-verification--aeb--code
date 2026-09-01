# PENDING: CARLA determinism defect — this repo's closed-loop numbers are affected

**Written 2026-08-28. Nothing here has been changed yet. Do not start the rework without
talking to Zach — Town06 in `formal-verification--steering--code` is being finished first,
and it is the reference implementation for the fix.**

## What was found

Measured in `formal-verification--steering--code` on the Town06 branch (`docs/TOWN06_FINDINGS.md`,
T06-F22). Two defects affect **every CARLA study in the lab**, including this one:

1. **`vehicle.apply_control()` races `world.tick()`.** Synchronous mode with a fixed
   timestep synchronises the *tick*, not the *command queue feeding it*. The race is
   invisible while a command is unchanged, because a late arrival re-applies the same
   value — so it only bites on a step where the command *changes*, which in a closed-loop
   run is every step. Measured open loop with the feedback cut and an identical scripted
   command sequence, three repetitions finished **60 m apart**.

2. **UE4 streams texture mips asynchronously**, so which mip is resident when a frame
   renders depends on load timing rather than on world state. Launching with
   `-notexturestreaming` cut the steering noise the renderer injects by **168x** and
   removed the cold-server outlier that makes the first run after a restart disagree with
   every later run.

Neither is visible in a result. Both produce physically plausible trajectories. Every
determinism setting these studies had pinned was pinned correctly — they were just aimed
at the wrong layer.

## What it means for this repo

- **Closed-loop numbers carry defect 1.** They remain rates over repetitions, which is
  still the right reporting form (see D-7/D-10 below), but the run-to-run spread is
  larger than it needed to be and its source was uncharacterised.
- **Data captured under the old harness is not reusable** (rule D-11). Training images
  captured with texture streaming on contain mip variation a `-notexturestreaming`
  evaluation will never show — a train/test distribution shift. Recollect; do not
  reweight, filter, or reuse.
- **This is not only bad news.** With physics made bit-exact, a 2.6e-6 steering
  perturbation still grew to 7.6 ft of cross-track error over 349 steps. That
  amplification is a property of the *policy*, not the simulator, so run-to-run spread is
  readable as a **closed-loop stability-margin measurement**. A model whose verdict flips
  between repetitions is reporting its own marginality.

## The fix, when this repo's turn comes

    pip install carla-determinism            # repo: carla-determinism--simulation--package

    import carla_determinism as cd
    client = carla.Client(host, port); cd.bind_client(client)
    cd.require_deterministic(port, world, fixed_dt=..., deterministic_control=True)
    cd.apply_control(vehicle, control)       # everywhere; never vehicle.apply_control()

and launch the server with `-notexturestreaming -quality-level=Epic`.

Read `RULES.md` in that package first — D-1..D-11, each one a measurement with the cost of
violating it recorded. Two that are easy to get backwards: **do not disable
`enable_postprocess_effects`** (manual exposure lives inside the postprocess chain, and
turning it off measured ~2000x worse), and **do not drop below `-quality-level=Epic`**
(High measured catastrophically worse). `require_deterministic` reads the server's real
command line from `/proc`, because those are launch flags and invisible over RPC.

## Order of work

Town06 first, then Town04 steering, then AEB, then the rest. Set by Zach on 2026-08-28.

---

## Also pending: the LAP protocol (added 2026-09-01)

Adopting deterministic control is not the whole of what this repo owes. The steering
study's `PROTOCOL.md` amendment A-4 changed what a repetition IS, and this repo has not
adopted it. Zach has said it will.

**A lap is the repetition.** One traversal of all the unique scored road, and it fails if
any scored span departs. Sections are not repetitions: six sections driven twice is six
different roads sampled twice, not twelve trials of one experiment. Pooling them produced
a cell reporting 2/12 = 17% when the SAME section had failed in BOTH passes — a 100%
failure of every attempt, diluted by five sections that were never in question.

**Three laps, not ten.** On the corrected harness, rep-to-rep verdict disagreement was
**0 of 48 section-pairs**. Three laps is a REPRODUCIBILITY CHECK, not a sample for
estimating a rate. The old floor was measured on the broken harness, where single runs
were wrong about one time in eight — that premise no longer holds.

**Conditional on the harness, and the condition is not optional:** a clean server restart
before EVERY lap (not before every group of laps — the steering repo's own teacher gate
was doing 3 restarts for 12 laps until 2026-09-01), a fresh vehicle and camera per lap,
one process per lap, the determinism preflight green on each fresh server, one client per
port. Where that is not enforced, enforce it — do not compensate with more laps. A larger
sample drawn through a harness known to be wrong measures the harness, and it still has
the shape of a result.

**Report the margin with every verdict**, and **if the laps disagree that is a BUG**, not a
reason to run more laps. A cell whose laps disagree is void, not uncertain.

**Cells must record the harness they ran under.** D-11 makes data from a violating harness
unusable, which is enforceable only if the artifact says which harness produced it:
deterministic control on/off, the package version and RULES digest, `check_lock()`, and the
server's actual command line read from the running process. See
`scripts/closed_loop_ledger.py:_determinism_provenance` in the steering repo.

### Unresolved, and it affects the text above this section

This file (and D-7 in the `carla-determinism` package, which is hash-locked) says
closed-loop numbers remain **rates over at least 10 repetitions**. A-4 supersedes that with
three laps. The two do not collide on the facts — D-7 measured that rendering never reaches
bit-identity, which A-4 does not dispute; A-4 disputes the INFERENCE from that to a
repetition floor, on the grounds that verdict stability rather than frame identity is what
the floor protected.

Resolving it needs the package's section 4 amendment procedure, and it is lab-wide: this
repo's already-collected numbers were taken under the ten-repetition reading. Do not change
either document unilaterally. Flagged for Zach 2026-09-01.

### Adoption checklist — what to port, and from where

Measured in this repo on 2026-09-01: the determinism package is referenced in almost
nothing here, there is no lap bridging, and `study/ledger.py` (blind order) is present.
Source for every item is `formal-verification--steering--code`, which is the reference
implementation.

1. **Bind the client and route every command.** `cd.bind_client`, `cd.require_deterministic`
   inside the sync-mode helper so no driver can skip it, and `cd.apply_control` at ONE
   choke point every driving loop calls — see `pipeline/carla_env.py:apply_control`. A raw
   `vehicle.apply_control()` anywhere else is the defect.
2. **Launch flags.** `-notexturestreaming -quality-level=Epic`, windowed on `DISPLAY=:0`
   (Zach watches runs). `scripts/carla_launch.sh`.
3. **Restart before EVERY lap**, one process per lap, fresh vehicle and camera. Not before
   every group of laps — the steering repo's own teacher gate was doing 3 restarts for 12
   laps until this was caught.
4. **Bridging, if the route crosses road the ODD excludes.** Steer by pure pursuit there
   and exclude those steps from scoring, in EVERY driving loop. Open routes must not use
   index arithmetic modulo the route length — see `pipeline/route.py:route_is_closed`.
5. **Cells record the harness.** `closed_loop_ledger.py:_determinism_provenance` —
   deterministic control, package version, RULES digest, `check_lock()`, and the server's
   real command line read from the running process. Unknown is recorded as null, never as
   false. Without this, D-11 is unenforceable after the fact.
6. **The blind-order check must RUN.** `study/ledger.py` exists here, but in the steering
   repo the prune deleted it and nobody noticed for an entire study, because a rule naming
   a missing command fails the way a passing check looks. Wire it into whatever this repo
   runs on every commit, and confirm it actually executes.
7. **Report in LAPS**, with the margin, and treat disagreeing laps as a bug.

None of this is automated across repos. It is a manual port and it is owed; nothing here
fails if it is skipped, which is exactly why it is written down.
