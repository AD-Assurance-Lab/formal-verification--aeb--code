# OPEN: every arm fails the FMVSS 127 false-activation test at a regulatory condition

**Measured 2026-09-10 02:43 on Town12, under A14/A15/A16/A17. Not a finding.** The standing
rule is that a result contradicting a pre-registered expectation is a bug until proven
otherwise, and is not written up as a finding until a written disposition lists the
candidate causes that were ruled out. This file is the contradiction; the disposition is
not written and the work is not done.

## What was expected

`docs/PREREGISTRATION_2026-09-09.md`, prediction 2, committed before any of this was
measured: *"All three arms pass all three regulatory endpoints, 10/10."*

## What was measured

The **hazard** endpoints held it exactly. Eighteen cells, three arms × three lighting
conditions × two scenarios, every one 10/10:

| arm | lead: day / low / high | ped: day / low / high |
|---|---|---|
| `P_pts` | 10/10 · 10/10 · 10/10 | 10/10 · 10/10 · 10/10 |
| `P_cont` | 10/10 · 10/10 · 10/10 | 10/10 · 10/10 · 10/10 |
| `P_pts3` | 10/10 · 10/10 · 10/10 | 10/10 · 10/10 · 10/10 |

The **false-activation** endpoints did not. Limit 2.4525 m/s²:

| arm | daylight | darkness, lower beam | darkness, upper beam |
|---|---|---|---|
| `P_pts` | 10/10, peak 1.42 | 9/10, peak 2.50 | **0/10, peak 3.03** |
| `P_cont` | 10/10, peak 2.24 | 10/10, peak 1.79 | **0/10, peak 3.28** |
| `P_pts3` | 10/10, peak 1.41 | **0/10, peak 3.19** | 10/10, peak 0.56 |

On Town01 all nine passed 10/10. Every arm now brakes for a steel plate at at least one
condition the standard tests.

## Why this matters more than a moved number

The study's setup sentence is that the arms are indistinguishable by the standard's own
procedure. That still holds on the hazard side and it is now false on the
false-activation side: FMVSS 127's own test **does** separate them, and it fails all three.

It also inverts a published claim. F19 and section 9 treated false activation as the
sleeper — the thing `P_cont` might do and the others would not. Here it is every arm, at
the endpoints, before any interior is considered.

## Candidate causes, none ruled out

1. **The night frames changed by 9x.** A16/A17 made the darkness captures 0.0036 where they
   were 0.0342 (F28). The policies are trained on these, so every arm's night behaviour is
   trained on a much darker image set than any previous arm in this study. The plate is
   steel and headlamp-lit, so at night it may be one of the few bright things in frame.
   **This is the first thing to check, and it is checkable**: the Town01 policies never saw
   frames this dark.
2. **The road.** Town12's site is four lanes with sidewalks; Town01's was two. The plate
   subtends a different fraction of a differently-lit scene.
3. **The upper/lower beam split.** `P_pts3` fails lower beam and passes upper; the other two
   do the reverse. That is not one physical story, and a mechanism that produces opposite
   failures in different arms is more likely to be a threshold interacting with training
   than a property of the plate.
4. **The plate itself.** Nine tiles covering 8.0 × 12.0 ft against a specified 8.0 × 12.0,
   so placement is exact. Its material and reflectance under Town12's headlamp rendering
   have not been examined.
5. **A real result.** Camera-only AEB false-activating on steel at night is a plausible
   failure and would be worth reporting. It is listed last deliberately: it is the most
   interesting explanation and therefore the one to accept only after the others are dead.

## What must not happen

The plate endpoints must not be quietly dropped from the endpoint criterion so the study
proceeds. PROTOCOL section 10's M4 criterion names the hazard scenarios, so the pipeline
did not stop — which means this could pass unnoticed into the paper as an unexamined
regression. That is the reason this file exists.
