# DISPOSED: the same seed on the same frames gave a different policy

Opened and closed on 10 September 2026.

## The contradiction

The training gave a different network on every run. The seed was the same. The pictures were
the same. Endpoint verdicts moved with it: one policy went from failing every run to passing
every run, and another went the other way, on training data that did not change (F29).

That went at the study's central claim. The claim is an attribution: the gap between the
policies is caused by how the lighting range was sampled. That needs the policies to differ
because of the sampling. If retraining one policy on identical data flips a verdict, a
difference between two policies trained once each cannot be attributed to anything.

## The cause

Seeding the three random number generators is necessary. On the graphics card it is not
enough. Three mechanisms sit underneath the seeds.

- The convolution library picks an algorithm by timing candidates on the first call. A
  different algorithm sums in a different order.
- Several operations have no repeatable version unless one is demanded.
- The matrix library's summing order follows the size of its workspace.

## The fix, and what it cost

Four settings close all three. The workspace setting has to be applied before the machine
learning library is imported, because the library reads it when it first creates a handle.
Setting it later fails quietly.

| | without | with |
|---|---|---|
| policies that differ between two runs | 3 of 3 | **0 of 3** |
| numbers that differ | 74.7 to 79.9 percent | **none** |
| checkpoint file | different | **the same, byte for byte** |
| time | 72.6 s | 74.7 s, 3 percent slower |

Four separate runs agree, including two written into the study's own folder. The full record
is in the findings file (F30).

## What this does not settle

Repeating is not being right. The networks are now the same on every run, which makes every
measurement after training meaningful again. It says nothing about which network the recipe
should give, and one seed is still one draw. A seed sweep can now measure seed spread alone,
which was always its point.

The steel plate question was blocked on this. It is now unblocked, and it is not answered.
See `docs/OPEN_CONTRADICTION_2026-09-10_plate_endpoints.md`. Its numbers came from networks
that cannot be made again, so measure it once more rather than reason about it.
