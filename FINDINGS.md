# Findings

Measured results and corrections, newest first. PROTOCOL.md section 8: a measured cell
that contradicts its expectation is a bug until proven otherwise, and findings live
here, never inside the protocol.

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
