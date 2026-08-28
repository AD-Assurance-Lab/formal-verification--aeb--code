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
