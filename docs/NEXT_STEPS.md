# Next steps

Written 2026-09-10. Read this before you start work. Do the steps in order. Each step
says why it comes before the next one.

Numbers in brackets point to the record in `FINDINGS.md` or `PROTOCOL.md`. You do not need
them to follow this file.

---

## 1. DONE 2026-09-10. Make the training repeatable.

The training now gives the same network every time. Four settings did it, and they cost
2.9 percent of the training time. Four separate runs of all three arms came out
byte-identical, checkpoint file included. (F30)

Without them, all three arms differed in about three quarters of their numbers, and one
arm's training error moved 40 percent between two runs of the same command.

`tools/train_policies.py` now writes the hash of the weights into its own report, so the
next person compares two small files instead of running the GPU again. `--scratch DIR`
trains to a directory of its own, which is how the test was run without overwriting the
study's networks.

---

## 2. DONE 2026-09-10. Put the map name in every results folder.

**The problem.** Old Town01 files sat in the same folders as new Town12 files, under the
same names. A tool asked for a file by name and got the old one. Nothing gave an error.

This happened four times in one night:

| what | how many old files | how it was caught |
|---|---|---|
| camera pictures | 3 knots, including both regulatory test conditions | one line in a log |
| `results/carla/` | 157 of 179 | I looked before running the next step |
| gate results | 10 of 12 | I looked before running the next step |
| trained networks | 54 | a return code of 2 |

The last one nearly gave the wrong answer to step 1. The training had failed. The file
compared was an old Town01 network, compared with itself. It said the training was
repeatable. It is not.

**What was done.** `tools/paths.py` is now the one place all three folders are named, and
all three carry the map:

    results/captures/Town12/
    results/carla/Town12/       results/carla/Town01/
    results/models/Town12/

That module imports nothing but the standard library. Two tools have to run on a machine
with no simulator, and each had re-typed the path for that reason. Re-typing a path is the
defect, not the cure for it.

---

## 3. Measure the gates again, on networks that repeat.

Steps 1 and 2 are done, so this one is ready to run.

The behavioural gate asks a question: does the blended picture make the policy behave like
the real picture at the same sun angle? On Town12 it fails at the dark end of the range,
for all three arms.

We cut the failing pieces in half once. The worst failure fell from 3.18 to 2.58. Three of
the eight new pieces passed. But we cut them again while the networks were changing, so the
second round means nothing.

Run `scripts/gate_repair_loop.sh`. It stops on its own if the number of failing pieces
does not fall. One round of twelve gates takes about 70 minutes, and a round that has to
split costs a recapture on top, so allow most of a night for three rounds.

The loop retrains after a split again. It had stopped doing that while the training moved
underneath it. A split adds knots, and `P_cont` is the arm that sees every knot, so an axis
carrying knots `P_cont` never trained on is not the comparison the protocol asks for.
`tools/check_arms_unmoved.py` runs after each retrain: the two arms whose pictures did not
change must come out with the same weights, and the loop stops if they do not.

**If the gates still fail after that, it is a result, not a fault.** It means a straight
line between two photographs does not represent the real lighting in between, at night, on
this road. That is worth reporting.

---

## 4. Decide the two open questions.

Both are written up in `docs/`. Neither could be answered before step 1.

**The trench plate.** Every arm brakes for a steel plate at one or more of the three
lighting conditions the standard tests. On Town01 all nine tests passed.
See `OPEN_CONTRADICTION_2026-09-10_plate_endpoints.md`.

**The changing verdicts.** ANSWERED by step 1. See
`DISPOSED_2026-09-10_training_nondeterminism.md` and F30. The endpoint numbers in that
file were measured on networks that cannot be reproduced, so they are withdrawn rather
than explained.

The plate question is unblocked by that, and it is not answered by it. It has to be
measured again on the networks that repeat.

---

## 5. Finish the rebuild.

In order: verification, then commit the verdicts to git, then drive the test cases.

Commit the verdicts by hand. Do not put that step in a script. A verdict is a prediction
only if somebody wrote it down before the drive.

Then run `scripts/overnight_after_verdicts.sh`. It drives the test cases, then drives the
dense sweep between the test cases, then writes the reports.

---

## 6. The new part of the paper: drive between the test cases.

This is the part the steering paper could not reach.

The certificate covers every lighting level between two photographs. A drive can only use
one lighting level at a time. So driving can check a line through the certificate, and it
has never been checked closely: the study drives two points in each piece of the range.

`drive_witness.py --interior 5` drives five points in each piece. Two things come out:

- **Where the policy starts to fail.** The certificate names a band of lighting where it
  says the policy is unsafe. Nobody has driven the edges of that band. A grid brackets the
  edge, and the distance from the bracket to the certificate's edge measures the method.
- **A wide net for faults.** Every point is three drives. If they disagree, that is a
  fault. Every disagreement in this study so far has been a real fault.

---

## Where the leftover files went

`stale/town01_superseded_2026-09-10/` holds 280 files from the Town01 study: results,
trained networks, and the probe files behind the three-drives rule. Look at them and remove
them. Nothing is lost -- they are all in git history, and the whole Town01 study is at the
tag `town01-final`.

`tools/headlamp_probe.py` is kept although nothing calls it. It is the tool that measured
the headlamp beams and it is how anyone would check that measurement again.

## Smaller jobs, in no order

- Take the confidence interval out of `tools/stats.py`. Three drives check repeatability.
  They do not estimate a rate, so an interval on them means nothing. (A13)
- Record the map inside every result file, not only in its folder name. No artifact in
  `results/carla/` said which map made it, so the Town01 files had to be sorted by the
  time they were written. A folder name is a good guard and a field in the file is a
  better one.
- Report how wide each piece of the lighting range is, next to every verdict. One piece
  can be 200 times wider than another, and a count of verdicts treats them as equal. (F27)
- Measure the family fidelity again. The last measurement used camera pictures that we now
  know were wrong at the dark end. (F27, F28)
- Send the amendment request in `docs/D7_AMENDMENT_REQUEST.md` to the shared determinism
  package. It still prints a rule this study no longer follows.

---

## What is already settled and does not need repeating

- The map is Town12. The test site is road 1016. It has 308 metres of clear road past
  where the plate sits, where Town01 had 13. (A14)
- Cloud cover is zero. Clouds move, and they changed the brightness at the horizon by twice
  as much as anything else. (A15, F23)
- Take the camera pictures darkest first, and make the world dark before the practice run.
  A dark picture comes out 9 times too bright if a bright picture was taken first, and it
  never settles down. (A16, A17, F28)
- Three drives per test case, each with its own restart of the simulator. (A13)
- The speed, braking and pedestrian checks all pass on Town12.
