# State of play

What we believe today, and nothing else.

The study design is in `PROTOCOL.md`. It wins over this file. The measured record is in
`FINDINGS.md`, and nothing is ever removed from it. Rewrite this file. Do not add to it.

For live numbers, run `python -m study.status`.

---

## Where we are, 10 September 2026

The training now repeats. That was the block, and it is gone. The next job is the
behavioural check on the lighting range.

### What changed today

**Training gives the same network every time.** Four settings in the training tool did it.
They cost 3 percent of the training time. Four separate runs of all three policies gave the
same file, byte for byte. Before the change, two runs of one command differed in about three
quarters of the numbers in every policy. See the record of it (F30).

**Every results folder now carries the name of the map.** One file, `tools/paths.py`, names
all three folders. Files from the earlier map used to sit under the exact names the new
tools ask for. Nothing raised an error when a tool read one.

**Eight of the 29 pieces of the lighting range span nothing.** In those eight, the scene at
one end and the scene at the other are the same picture. Two of them are 7.4 degrees of sun
angle wide. Below about 14 degrees under the horizon only the headlamps light the road, so
the scene stops changing. The earlier measurement found one such piece, on camera frames we
now know were wrong at the dark end. See the record of it (F31).

### Do these in order

1. Run `scripts/gate_repair_loop.sh` to measure the behavioural check again. It runs twelve
   checks per round, and a round takes about 70 minutes. A round that cuts the range also
   needs a fresh set of camera frames.
2. Verify next. Write the verdicts to git by hand. Then drive. A verdict is a prediction
   only if somebody wrote it down first.
3. Settle the steel plate question last. It is in
   `docs/OPEN_CONTRADICTION_2026-09-10_plate_endpoints.md`. The training fix unblocks it. It
   does not answer it.

### What we have withdrawn

The overnight run of 10 September measured every endpoint verdict, check result and
certificate. It measured them against a network the next run would not give again. None of
it is evidence about the three policies. That includes the written prediction that all three policies pass
all three lighting conditions the standard tests.

The files are in `stale/nonreproducible_pre_F30_2026-09-10/`.

### What still stands

These measure the instrument and not a trained network, so the training fault does not
touch them.

- The map is Town12. The old map had no site long enough for the steel plate test. This one
  has 308 metres of spare road.
- Cloud cover is zero. Clouds move, and they moved the brightness at the horizon more than
  anything else did.
- Take the camera frames darkest first. Darken the world before the practice run. A dark
  frame comes out nine times too bright if a bright frame was taken first, and it never
  settles.
- The frame stamp guard works. One refine took four fresh frames and skipped twenty-one.
  That is six minutes instead of forty.
- The lighting range covers the whole span on this map. There is no gap at the horizon.
- The speed, braking, contact and pedestrian checks all pass.
- The lighting range itself: 30 knots and 29 pieces, every one with frames in all six
  scenes. Five knots were chosen from checks run against the old networks, so the choice is
  not evidence. The knots are real rendered points either way, which is what the design
  asks for. Keep them and measure again.

---

## One thing this file cannot fix

`python -m study.status` reports the six ledger cells as measured, with high confidence.
Those numbers come from the earlier map, tagged `town01-final`. The rebuild has no ledger
yet.

Clearing the ledger would destroy the only complete one the study has. Leaving it reports
numbers from the wrong map. That is Zach's call and it is not made.
