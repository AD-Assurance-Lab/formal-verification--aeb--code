# Next steps

Do these in order. A number in brackets points to the record in `FINDINGS.md`. You do not
need it to follow this file.

---

## 1. Make the training repeatable. DONE, 10 September 2026

The training now gives the same network every time. Four settings did it, and they cost 3
percent of the training time. Four separate runs of all three policies gave the same file,
byte for byte (F30). Before the change, two runs of one command differed in about three
quarters of the numbers.

The training tool now writes a hash of the weights into its report. The next person
compares two small files. Nobody runs the graphics card again. `--scratch DIR` trains into a
folder of its own, which is how this was tested without touching the study.

## 2. Put the map name in every results folder. DONE, 10 September 2026

Files from the old map used to sit beside files from the new one, under the same names. A
tool asked by name and got the old one, with no error. This happened four times in one
night, and once it nearly gave the wrong answer to step 1.

`tools/paths.py` is now the one place all three folders are named:

    results/captures/Town12/
    results/carla/Town12/     and  results/carla/Town01/
    results/models/Town12/

It imports nothing but the standard library. Two tools must run on a machine with no
simulator, and each had typed the path out again for that reason. Typing a path out again is
the fault, not the cure.

## 3. Measure the behavioural check again

Steps 1 and 2 are done, so this is ready.

The check asks one question. Does the blended picture make the policy behave like the real
picture at the same sun angle? On this map it fails at the dark end for all three policies.

Run `scripts/gate_repair_loop.sh`. It stops on its own if the number of failing pieces does
not fall. A round of twelve checks takes about 70 minutes, and a round that cuts the range
also needs fresh camera frames. Allow most of a night for three rounds.

The loop trains again after it cuts the range. It had stopped doing that while the networks
moved under it. Cutting the range adds knots. One policy is meant to see every knot. A range
with knots it never trained on is not the comparison the design asks for.
`tools/check_arms_unmoved.py` runs after each training. The two policies whose pictures did
not change must come out with the same weights, and the loop stops if they do not.

**If the check still fails, that is a result and not a fault.** It means a straight line
between two photographs does not stand for the real light in between, at night, on this
road.

## 4. Settle the two open questions

**The steel plate.** Every policy brakes for a steel plate at one or more of the three
lighting conditions the standard tests. On the old map all nine tests passed. Step 1
unblocks this and does not answer it, because those numbers came from networks that cannot
be made again. See `docs/OPEN_CONTRADICTION_2026-09-10_plate_endpoints.md`.

**The changing verdicts.** ANSWERED by step 1. See
`docs/DISPOSED_2026-09-10_training_nondeterminism.md`.

## 5. Finish the rebuild

Verify. Then write the verdicts to git by hand. Then drive.

Write them by hand. Do not put that step in a script. A verdict is a prediction only if
somebody wrote it down before the drive.

Then run `scripts/overnight_after_verdicts.sh`. It drives the test cases, then the dense
sweep between them, then writes the reports.

## 6. Drive between the test cases

This is the part the steering paper could not reach.

The certificate covers every light level between two photographs. A drive uses one light
level at a time, so a drive checks a line through the certificate. Nobody has checked that
line closely. Today the study drives two points in each piece of the range.

`drive_witness.py --interior 5` drives five points per piece. Two things come out.

- **Where the policy starts to fail.** The certificate names a band of light where it says
  the policy is unsafe. Nobody has driven the edges of that band. A grid brackets the edge,
  and the gap to the certificate's edge measures the method.
- **A wide net for faults.** Every point is three drives. If they disagree, that is a fault.
  Every disagreement in this study so far has been a real fault.

---

## Smaller jobs, in no order

- Take the confidence interval out of `tools/stats.py`. Three drives check that a result
  repeats. They do not estimate a rate.
- Report the distance in light beside every verdict, not the width in degrees. Eight of the
  29 pieces span nothing, and two of those are among the widest in degrees (F31).
- Record the map inside every result file, not only in its folder name. No file carries it,
  so the old ones had to be sorted by the time they were written.
- DONE. The amendment request now sits in the shared determinism package. Nothing there
  changed, and the launcher prints the old rule until Zach makes the change.

## Where the leftover files went

`stale/town01_superseded_2026-09-10/` holds 280 files from the old map. Look at them and
remove them. Nothing is lost. They are in git history, and that study is at the tag
`town01-final`.

`stale/nonreproducible_pre_F30_2026-09-10/` holds results measured against networks that
cannot be made again.

`tools/headlamp_probe.py` is kept although nothing calls it. It measured the headlamp beams,
and it is how anyone would check that measurement again.

## Settled, and not worth repeating

- The map is Town12, site road 1016. It has 308 metres of clear road past the plate, where
  the old map had 13.
- Cloud cover is zero. Clouds move, and they changed the brightness at the horizon by twice
  as much as anything else.
- Take the camera frames darkest first, and darken the world before the practice run.
- Three drives per test case, each with its own restart of the simulator.
- The speed, braking and pedestrian checks all pass on this map.
