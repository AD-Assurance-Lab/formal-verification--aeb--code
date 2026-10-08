# formal-verification--aeb--code

Automatic emergency braking under poor visibility. Owner: Zach. Demo: Novi, October 2026.

One file. It holds the study design, the amendments, current belief and every standing
rule. `docs/ARXIV_NOTES.md` is the only other notes file and it serves the paper
repository. `FINDINGS.md` is the measured record and nothing edits it after the fact.

Run `python -m study.protocol_lock` before you read any result. Run `python -m study.status`
for live numbers.

Older records name files that no longer exist. They were folded into this one on
2026-09-10 and they are all in git history. `git show 61b73d9^:<path>` recovers any of
them, and the design document is also at the tag `protocol-v1`. Do not look in `stale/`.
That directory is emptied on purpose.

A number in brackets points to a record in `FINDINGS.md`. You do not need it to follow this
file.

---

## Where the rest of the record is

The study design, its amendments and the status section are in `docs/DESIGN.md`.
The numbered findings are in `FINDINGS.md`. This file holds the operating rules only.

# Rules

Everything below is a measured result, not a preference. Each rule exists because breaking
it cost this lab time, and each says what it cost.

## Determinism. Do not break these

**This section is not optional and it is not advice.** The simulator and the graphics card
both produce results that look right and are not reproducible. Every rule here was measured
after a defect got past every other check.

### The training must repeat

Seeding the three random number generators is necessary. On the graphics card it is not
enough. Three things sit underneath the seeds:

- the convolution library picks an algorithm by timing it. The choice then depends on what
  else the card was doing;
- several operations have no repeatable version unless one is demanded;
- the matrix library sums in an order that follows the size of its workspace.

`tools/train_policies.py` closes all three. Set the workspace variable **before** the
machine learning library is imported. Setting it later fails quietly, and the failure
arrives much later as an error about a different kernel.

Without these, three quarters of every policy's numbers moved between two runs of one
command, and endpoint verdicts flipped with them (F29). With them, four separate runs gave
the same file, byte for byte, for 3 percent more time (F30).

The training report records a hash of the weights. Two runs that claim the same seed can be
compared by reading two small files. `--scratch DIR` trains into a folder of its own.

### Two simulator faults, and this study has not fixed them yet

Do not start the rework without talking to Zach. Another study is finishing the reference
version of the fix.

**The control command races the world step.** A fixed step lines up the step, not the queue
of commands feeding it. It only bites where the command changes, which in a closed loop is
every step. Three runs of one scripted sequence, feedback cut, finished 60 metres apart.

**The engine loads textures in the background.** Which version is in memory when a frame
renders depends on load timing, not on the state of the world. Turning texture streaming off
cut the renderer's noise by 168 times.

Neither shows up in a result. Both give trajectories that look right.

The fix is `pip install carla-determinism`. Bind the client, run the preflight, and route
every control command through it. Launch with texture streaming off and quality at Epic. Do
not turn off the post-process effects, because manual exposure lives in that chain.

Still owed here, and nothing fails if it is skipped. That is why it is written down.

1. Route every control command through one choke point.
2. Restart the server before every repetition.
3. Record the harness in every cell. Record unknown as null, never as false.

**Frames captured under the old harness cannot be reused.** Capture them again. Do not
reweight or filter them.

### Two simulator traps that keep biting

**A read or a placement next to a write does not see that write.** Weather, spectator
transforms and sensor delivery all apply on the next step. Nothing raises an error when you
get this wrong. Never read back state you just wrote. Construct it.

**A fixed weather is not a static scene.** The cloud layer moves, so scene brightness at the
horizon drifts with elapsed simulated time and never settles. Light is this study's
independent variable, so the independent variable is what drifts. Cloud cover is now zero
(A15, F23).

Match sensor frames on the identifier the world step returns. Never swallow a missing frame.

Take the camera frames darkest first, and darken the world before the practice run. A dark
frame comes out nine times too bright if a bright frame was taken first, and it never
settles (A16, A17, F28).

## Rules that protect the result

- **A result that contradicts a written expectation is a fault until you prove otherwise.**
  Do not write it up as a finding until a disposition lists the causes you ruled out. This
  is the rule that has caught the most real defects in this study.
- **Train, test and verify over the same disturbance.** If they disagree about it, the
  comparison means nothing.
- **Read contact from geometry, never from the collision sensor.** A car driven into a
  stationary car at 43 mph ended 8.2 ft inside a body whose contact distance is 19.9 ft.
  The sensor reported nothing.
- **Certify against the closed-loop tolerance, not a per-frame corridor.** In the steering
  study the per-frame corridor was about 3.4 times too permissive, and a vehicle left the
  road with every frame inside it.
- **Never trade experimental quality for speed.** No processor fallback, no lowered
  simulator quality, no cut training. Warn Zach before a run longer than 1 hour.

## The frames and the networks live on Hugging Face

`AD-Assurance-Lab/aeb-verification-captures`, a dataset repository. Git ignores them because
they are large: 66 frame sets at 1.4 GB, and 6 checkpoints.

The README says how to fetch them. What matters here is why they are kept at all, when the
tools that make them are committed. **Regenerable is not reproducible.** The simulator does
not render bit-identical frames twice, so recapturing gives different frames, different
networks and different certificates. Every certificate names its network by hash and the
dataset's `MANIFEST.json` carries those hashes.

Training reproduces exactly from a given frame set, so the chain from frames to certificates
can always be rebuilt. It breaks only if the frames are lost.

If a certificate's `model_sha256` does not match the checkpoint you hold, they are not a
pair. Do not conclude anything from them together, and do not "fix" it by rerunning one half.

## Every path is named once, and carries the map

`tools/paths.py` names the frames folder, the results folder and the models folder. It
imports nothing but the standard library, so the tools that must run without a simulator can
share it. Do not type a path out again. That is the fault, not the cure.

Files from an old map used to sit under the exact names the new tools ask for, and nothing
raised an error. That happened four times in one night.

## A count of pieces is not a measure of coverage

The lighting range is cut until the middle of a piece is close enough to the straight line
across it. The rule uses a fixed distance, so it can make a piece across which the scene
does not change at all.

On clean frames, 8 of the 29 pieces span nothing. Two of those are 7.4 degrees of sun angle
wide, because below about 14 degrees under the horizon only the headlamps light the road.
Width in degrees and distance in light disagree, and they disagree most at the dark end
(F27, F31).

Report the distance in light beside every verdict. `tools/family_fidelity.py` measures it
and needs no simulator.

## The statistic is a hypothesis

The working expectation is that the peak is the correct statistic for braking, because the
hazard is one event. For lane keeping the peak was wrong, because that threshold described a
sustained error.

This is the scientific bet of the repository. Test it blind. If it fails, the failure is the
result.

## Working in this repository

This is a public repository and a proof of concept. The bar is that an outsider can follow
it. It is not production quality. Try things. Do not leave the wreckage behind.

- Delete nothing in anger. Move it to `stale/`, which git ignores. Zach inspects it and
  empties it, often the same day, so never write a pointer INTO `stale/`. Point at git
  history instead. Anything ever committed is recoverable from there.
- Run `python tools/tidy.py` before you push anything meant to be read. It never deletes.
- Push often. GitHub is the backup.
- Keep `README.md` honest about what runs without a simulator. Most readers have none.
- Do not add continuous integration, formatters or linters.
- `tools/headlamp_probe.py` and `tools/choose_input_size.py` are kept although nothing calls
  them, and the hygiene report flags them. They are how anyone would check the headlamp
  beams and the network input size again.

## If your graphics card is smaller than the lab machine's

Everything measured here ran on a 32 GiB card. Two numbers decide what fits, and both are
measured rather than guessed.

| what | needs |
|---|---|
| the simulator | 13 to 15 GiB on a 32 GiB card, every map, and it leaks over a long session |
| one bound computation | 3.3 to 8.3 GiB, depending on the policy and how much the sub-interval branches |

They never need to fit at the same time. Verification runs with the simulator stopped, and
the pipeline stops it for you.

**That simulator figure does not predict a smaller card.** Measured here against a clean
baseline of 498 MiB: 13.7 GiB for the small map, 13.5 for the mid-size one, 14.8 for the
large one, all on a 32 GiB card. The
engine sizes its pools to the card it finds, and a 12 GiB card ran a large map at 9.5 GiB.
So memory is not what decides. **Speed is**, and there the measurements are clear: on a
12 GiB card the small map ran at 720 steps per second and a large map at under 0.6.

Measure your own card before planning a campaign on it. Do not carry these numbers over.

**On an 8 GiB card**, one bound computation at its worst case does not fit. The pipeline now
reads the card and runs them one at a time, and says so. The widest sub-intervals may still
run out of memory. That is a fact about the card, not a fault in the run. Two honest
responses: verify the narrow sub-intervals and say which ones you could not reach, or borrow
the big machine for the verification stage only.

**The map is the harder problem.** The study moved off large maps once already. A 12 GiB
card ran a large map at under 0.6 steps per second, against 720 for a small one (A3). It
moved back only when a 32 GiB card held 26.5 steps per second (A14). An 8 GiB card is below
the card that failed the first time.

The small map is the default and it is the one a smaller card should use. Everything except
the false-activation test fits there. That scenario needs 320 m of junction-free lane and
the map's longest straight is 307 m (A20).

**What does not care about the card.** Training takes about 75 seconds for all three
policies. Every check that needs no simulator runs anywhere, including the lighting range
measurement and the whole of `study/`.

**Do not lower the simulator quality to make something fit.** Below Epic the rendering
measured far worse. Manual exposure lives inside the post-process chain, so turning that off
measured about 2000 times worse. A run that does not fit is a run that does not fit.

## The simulator is shared

- Book it. Zach, three students and another project want the same machine.
- Relaunch the server before every measurement run. It leaks about 10.5 GiB over 11 hours.
- Use the non-default port on the lab machine. Check before you assume 2000.
- Detach long runs with `setsid nohup`. The harness kills foreground jobs.
- One client at a time. A second script asking for the world just times out, and that looks
  exactly like a dead server.
- A pattern kill matches your own command line. Use bracket patterns or process numbers.
- `grep` and `tail` both buffer. Use `--line-buffered`, and never pipe a job you want to
  watch, or a healthy run looks stalled.
- Look at the data, not only at the statistics. Two faults passed every numeric check and
  were obvious in one frame. One was an exposure six stops too fast, which the clipping
  check called healthy. One was a pedestrian measured at 10.6 m who stood 6 m to the side.
  Export a frame and open it.
