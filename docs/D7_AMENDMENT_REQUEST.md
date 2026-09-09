# Amendment request to `carla-determinism` D-7, from the AEB study

**For Zach. Not an amendment — a request, in the form section 4 asks for.** The package is
hash-locked and lab-wide; a study does not change it. This states the measurement that
contradicts the rule, names where it is recorded, and proposes the wording. Nothing in the
package has been touched.

## The rule, and the half of it that is not in dispute

> **D-7. Bit-exact closed-loop replay is NOT achievable, and no configuration reaches it.**
> On a scene where nothing moves at all […] frames at the same index across repetitions are
> never bit-identical. The floor is ~30 pixels of 307,200 differing by at most 13 levels
> […] **Therefore every closed-loop number remains a RATE over at least 10 repetitions with
> a confidence interval.** D-1..D-6 shrink the noise; they do not remove it, and no future
> version of this file may claim they do without a measurement showing a frozen scene
> rendering bit-identically across reps.

**The measurement is not disputed and is not proposed for change.** Frames are not
bit-identical, this study has not shown otherwise, and the sentence forbidding such a claim
without evidence should stay exactly as written.

**What is disputed is the "therefore".** Frame identity is not what the repetition floor
protects; verdict stability is. The inference from one to the other is what the measurement
below contradicts.

## The measurement

Recorded in `formal-verification--aeb--code/FINDINGS.md` as **F21, F22, F23 and F24**, and
adopted there as `PROTOCOL.md` amendment A13.

Across **281 committed ten-repetition cells** in that study, **277 were unanimous**. Only a
split cell can be sensitive to the repetition count at all, because a cell passes iff every
repetition passes. All four splits were re-driven under D-6's own harness — a stopped
server, a fresh launch through the determinism preflight, a new process, a new client and a
new vehicle before **every repetition** — with two unanimous controls beside them:

| cell | ten in one process | ten on ten fresh servers | cause |
|---|---|---|---|
| `P_pts`/lead | 9/10 | 10/10 | scoring defect, F21 |
| `P_pts`/lead at-witness | 8/10 | 10/10 | scoring defect, F21 |
| `P_pts3`/ped | 2/10 | 10/10 | simulator drift, F23 |
| `P_cont`/plate | 6/10 | 2/10 | driver at half the control rate, F24 |
| CONTROL `P_cont`/lead | 10/10 | 3/3 | — |
| CONTROL `P_pts3`/lead | 0/10 | 0/3 | — |

**Not one was sampling.** Under a per-repetition restart the repetitions are not merely
close, they are identical to the recorded precision. The sibling steering study reports the
same thing independently: rep-to-rep verdict disagreement 0 of 48 section-pairs.

Two further results bear directly on the rule:

- **F23.** CARLA's cloud layer moves under fixed weather parameters, so scene brightness at
  horizon illuminations drifts with elapsed simulated time. Ten repetitions inside one
  server sample further along that curve than three do. **The larger sample was the worse
  measurement**, which is the opposite of what a repetition floor is for.
- **F24.** The one cell still split under the correct harness was a driver running at 10 Hz
  where its protocol specifies 20. A confidence interval over those ten repetitions would
  have reported a 60% pass rate for a policy whose true rate at the specified control rate
  is 100%.

This is also what **D-10 already says** — *"a policy whose verdict flips between repetitions
is reporting its own marginality. Do not 'fix' that spread by adding repetitions until the
verdict settles"* — and D-7's second sentence points the other way.

## Proposed wording

Replace the "therefore" sentence only:

> **Therefore closed-loop numbers are VERDICTS over repetitions, never single runs.** Under
> D-6's harness — a fresh server, a new process and a new vehicle for every repetition —
> three repetitions are a reproducibility check and are sufficient; repetitions that
> disagree make the cell VOID and are a defect to be found, not a rate to be estimated
> (D-10). Where that harness is not enforced, repetitions share a simulator whose state
> drifts, the floor of ten stands, and the answer is to enforce the harness rather than to
> raise the count.

Everything before it, including the prohibition on claiming bit-identity without evidence,
is unchanged.

## What section 4 requires, and where each piece is

| requirement | where |
|---|---|
| state the measurement that contradicts the rule | above, and F21–F24 |
| record it in the study's findings file | `FINDINGS.md` F21, F22, F23, F24 |
| change the rule | **not done** — this is a request |
| regenerate the lock in the same commit | for whoever makes the change |
| name the amendment in section 4 | proposed: *A-1, the repetition floor, on measurement from the AEB study* |

## Two notes for whoever picks this up

**It is lab-wide, and the other studies have not measured it.** The AEB study has, and the
steering study has for a lane-keeper on a lap. Multi-condition and the rest have not, and
the proposed wording is careful to keep ten as the floor wherever the harness is not
enforced, so nothing changes for a repo that has not done the work.

**The package currently contradicts a study's own protocol on that study's console.** Every
launch through `tools/carla_launch.sh` prints *"D-7 floor remains: closed-loop numbers are
still RATES over >=10 repetitions"*, immediately before a run that A13 governs. That is
cosmetic and it is also exactly how a rule quietly wins an argument it has not had.
