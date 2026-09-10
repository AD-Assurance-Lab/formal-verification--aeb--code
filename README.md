# formal-verification--aeb--code

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](tools/)
[![CARLA 0.9.16](https://img.shields.io/badge/CARLA-0.9.16-orange.svg)](https://carla.org)

Proving that an emergency braking system is safe in lighting the safety test never checks.

---

## Start here

**The problem.** A federal standard tells makers to test emergency braking in three lighting
conditions: daylight, darkness with the low beam, and darkness with the high beam. Three
conditions. Real driving has every level in between, and dusk is not one of the three.

**The question.** Can a braking system pass all three tests and still fail at a light level
between them?

**The method.** Take two photographs of the same road, one in daylight and one at night,
from the same camera position. Blend them. The blend gives every light level in between. A
verification tool then proves, for the whole blended range at once, whether the network ever
fails to brake. It does that without driving a single mile. Where it says the network fails,
we drive that exact light level in the simulator and see whether it really does.

**The result so far.** Yes, a policy can pass all three tests and fail between them. Trained
on only the tested conditions, a policy is falsified over about 50 degrees of sun angle and
does hit the pedestrian. Trained on the whole range, it certifies clean.

**Why anyone cares.** A test campaign samples points. If the failure lives between the
points, testing cannot find it and a proof can.

## Where things stand

The study ran end to end once, on a small map. That result is complete, tagged
`town01-final`, and written up in `docs/STUDY_REPORT.md`. Read that for the science.

The study moved to a large map for a while. The small one has no stretch of road long
enough for the standard's false-activation test. It has moved back, because the large map
needs a bigger graphics card than this work now assumes.

So everything is being measured again on the small map, from the camera frames up. Those
frames predate a fix to the order they are captured in, and their dark end reads 11 times
too bright. Run `python -m study.status` to see where that stands.

## The large files are not in git

Two things this study needs are too big for git and are on the lab's Hugging Face instead:

> **`AD-Assurance-Lab/aeb-verification-captures`**

| | |
|---|---|
| the camera frames | 66 frame sets, 1.4 GB |
| the trained networks | 6 checkpoints |

**Get them before you run anything that needs them:**

```bash
pip install huggingface_hub
hf download AD-Assurance-Lab/aeb-verification-captures \
    --repo-type dataset --local-dir /tmp/aeb-data
cp -r /tmp/aeb-data/captures/Town01 results/captures/
cp -r /tmp/aeb-data/models/Town01   results/models/
```

**Why they are not in git, and why it matters.** They are large and regenerable, so git
ignores them. But regenerable is not the same as reproducible. The simulator does not render
bit-identical frames from one run to the next. So recapturing gives slightly different
frames, which give different networks, which give different certificates. Every certificate
names its network by a hash, and those hashes are in the dataset's `MANIFEST.json`.

So: **the study can always be re-run, and today's exact numbers can only be re-derived from
these files.** If a hash does not match, the certificate and the network are not a pair and
nothing may be concluded from them together.

Training itself reproduces exactly. Four separate runs from these frames gave byte-identical
checkpoints, so the networks can be rebuilt from the frames, and everything downstream from
the networks. The chain only breaks if the frames are lost.

## Set up

```bash
bash scripts/bootstrap_env.sh     # builds .venv, and proves a graphics kernel runs
```

It refuses to finish if the environment is wrong, which is deliberate. Three real defects hid
in this step before, and each one let the tools run while producing nothing usable.

## Run something today, with no simulator

Most of the repository works without CARLA, and this is the fastest way in.

```bash
python -m study.protocol_lock        # is the study design unchanged?
python -m study.status               # where does the study stand, in its own terms
python tools/family_fidelity.py      # how much light does each piece of the range span?
python tools/tidy.py                 # repository health
python tools/make_figure.py          # rebuild the paper's figure from the results
```

Start with `study.status`. It prints the milestones, the safety numbers and the six-cell
ledger. It reads the artifacts rather than any prose, so it cannot flatter the study.

## If your graphics card is smaller than the lab machine's

Everything here was measured on a 32 GiB card. On a smaller one, read the section in
`CLAUDE.md` before you plan any run. The short version. Training and every check that needs no simulator run anywhere.
Verification runs one job at a time, and its widest cases may not fit at all. The large map
probably will not run. The small map is the default now. `CARLA_MAP=Town12` reaches the
large map's artifacts.

## With the simulator

```bash
bash tools/carla_launch.sh                # the only launcher. The flags matter
python tools/carla_jobs.py --list         # what is queued, in dependency order
bash scripts/rebuild_all.sh               # the study, in order, up to verification
bash scripts/rebuild_all.sh witness       # the drives, after the verdicts are committed
```

`rebuild_all.sh` stops before the drives on purpose. The verdicts have to be written to git
first, because that is what makes a verdict a prediction rather than a description.

## Read in this order

1. **`CLAUDE.md`.** The study design, then the rules. The design is locked, and
   `python -m study.protocol_lock` fails if it changes without a recorded amendment.
2. **The determinism section of `CLAUDE.md`.** Read this before you run anything that
   measures. The simulator and the graphics card both produce results that look right and
   do not reproduce. Every rule there was written after a defect got past every other check.
3. **`docs/STUDY_REPORT.md`.** The complete method and the small-map results.
4. **`FINDINGS.md`.** Newest first. Every measured result and every correction. Nothing is
   ever removed from it.

`docs/ARXIV_NOTES.md` serves the paper repository and you can leave it alone until the
paper comes up.

## A good first project

**Measure how much the result depends on the training seed.**

The headline is an attribution: the gap between the two policies is caused by how the
lighting range was sampled. That claim needs the policies to differ because of the sampling,
and today it rests on one training run each. A reviewer will ask.

The training now repeats exactly, so a sweep over seeds measures seed spread and nothing
else. `tools/train_policies.py --seed N` and `tools/seed_sweep_report.py` already exist.
Train about twenty seeds per policy, verify each, and report the spread of certified count
and falsified width with a rank test.

It is self-contained, it needs no new design decision, and it walks you through the whole
pipeline: train, verify, score, report.

## Layout

| | |
|---|---|
| `CLAUDE.md` | the design, locked, then every rule. Read first |
| `FINDINGS.md` | the measured record, newest first. Append only |
| `docs/STUDY_REPORT.md` | the complete method and results |
| `docs/ARXIV_NOTES.md` | for the paper repository |
| `study/` | the lock, the status report, the recorded ledger |
| `tools/` | everything runnable |
| `scripts/` | multi-stage runs, detached |
| `results/` | outputs, scoped by map. Frames and networks are on Hugging Face, see above |
| `stale/` | on the way out, git-ignored. Never point at anything in here |

## House rules

Run `python tools/tidy.py` before you push anything meant to be read.

Delete nothing in anger. Move it to `stale/` and let Zach empty it. Anything ever committed
stays in git history, so parking a file loses nothing.

Book the simulator before you use it. Several people and another project share it.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
