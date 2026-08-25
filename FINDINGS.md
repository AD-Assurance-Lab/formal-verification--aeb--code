# Findings

Measured results and corrections, newest first. PROTOCOL.md section 8: a measured cell
that contradicts its expectation is a bug until proven otherwise, and findings live
here, never inside the protocol.

---

## F2 — 2026-08-25 re-measurements: the committed campaign survives its own audit

The four measurements the F1 audit demanded, all run on a fresh server:

- **P_pts capture gate: PASS at 0.260** of the decision threshold (P_cont was 0.191).
- **P_pts in-between gate: passes at 0.578 worst over the covered sub-intervals, and
  fails at 1.074 in exactly one place — the [0.143, 0.000] deg sliver A6 already
  declared uncovered.** That cell is FALSIFIED in the committed verdicts, drove 0/10
  at a RENDERED midpoint (independent of blend validity), and is excluded from the
  coverage claim. So the gate failure confirms the A5/A6 horizon discontinuity at the
  behavioural level rather than weakening any committed cell: every certified P_pts
  cell now has a passing behavioural gate, closing audit item F10.
- **Re-bisection under the corrected three-channel metric**
  (`results/carla/family_knots_rgb.json`): 15 sub-intervals against the campaign's
  11, and the uncoverable horizon band widens from [0.143, 0.000] (blue-only error
  0.0386) to **[0.36, 0.00] at error 0.0164**. The committed campaign's knots stand
  as its record — PROTOCOL section 4 makes the behavioural check the deciding one,
  and it passes for both policies everywhere the family claims coverage — but any
  FUTURE capture campaign must use the RGB knots and the wider exclusion.
- **Sites re-measured with the fixed-exposure camera** (audit F2's defect): street
  lighting site 1 = 0.23, site 3 = 9.86 (auto-exposed values were 4.55 / 25.71). The
  A4 conclusion — site 1 effectively unlit, site 3 lit — is unchanged; the old
  numeric values should not be quoted.

Amendment A11 (same day) records the certified property as the brake decision
threshold, which is what every committed verdict already meant.

---

## F1 — 2026-08-25 audit: results were filed under the wrong ledger cells, and five measurement defects found

A four-way audit (CARLA/capture handling, protocol-integrity tooling, paper–code
consistency, citation verification) found and fixed:

- **The lead-scenario results were recorded under the ped-cross cells (1/3).** Every
  artifact is `scenario: lead`; refiled to cells 2/4 with artifact bindings, and
  `python -m study.ledger --check-order` (new) now cross-checks each cell's artifact
  scenario/policy against the frozen row, verifies the verdict's *content* was
  committed before its witness drive (first-add checking would credit the A10
  retrain's overwrites with pre-retrain dates), and requires the violating width on
  falsified cells (cell 2: 10.802° of the 90° axis).
- **Every blend-error and brightness number was sampled from the BLUE channel only**
  (stride-40/64 over BGRA with a dead alpha guard). Fixed to all three channels in
  `build_family_knots`, `interval_sweep`, `carla_jobs` (in-between, capture-check,
  sites, expert samplers). **Consequence: the A5/A6 tables and the knots in
  `family_knots.json` were blue-only measurements; re-measure the knots before
  Iteration 2 trains against them.** The behavioural gate (full-RGB, policy-output
  space) partially backstops the committed result, but it was only run on P_cont.
- `job_sites` used an auto-exposure camera (the A4 defect); the lit/unlit numbers
  quoted in A4 were not absolute photometry. Fixed to the fixed-exposure camera;
  re-measure before anything relies on them again.
- `run_policy`/`drive_witness`/`gate_behavioural` silently drove the lead geometry
  for any `--scenario`; they now refuse anything but `lead` until the pedestrian
  harness exists. `job_pedestrian`'s oracle trigger used walker distance instead of
  conflict-point range (A7); fixed.
- Training now seeds every RNG, and verify/witness artifacts record git SHA,
  timestamp, and the model's sha256, so a committed verdict is tied to the network
  it describes. `drive_witness` refuses to run against uncommitted or modified
  verdicts. `protocol_lock` now hashes each amendment (append-only is enforced, and
  `--accept` is no longer pre-authorized by a stale counter). The A6 uncovered
  sliver is flagged `family_uncovered` in verify output.

Open questions for the study lead: the `a_max/2` verification threshold vs frozen
section 7's `a_max` (needs an amendment or a code change), and the knot re-measurement
above.
