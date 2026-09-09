# Captures, scoped by map

One directory per CARLA map, and that is not cosmetic. Until 2026-09-09 this was a flat
directory with frame sets named `<scenario>_sun<altitude>.npz`, and `capture_campaign.py`
skipped any knot whose file already existed. Nothing in the name or the test said which
map, which weather, or which harness had produced it.

The A14 rebuild moved the study from Town01 to Town12 and re-bisected the illumination
axis. The two axes share exactly three knots -- **+60.000, 0.000 and -30.000** -- and two
of those are the regulatory endpoints, the daylight and darkness frames the entire
disturbance family is built between. The capture stage started, printed
`lead_sun+60.000.npz exists, skipping`, and would have built a Town12 family out of Town01
endpoints with every downstream number looking finished. See FINDINGS F26.

`Town01/` holds the complete capture set behind the tag `town01-final`. It is not stale and
it is not wrong; it is a Town01 measurement, and it is here so that nothing can reach it by
accident from a Town12 campaign.

Two guards now, because one of them is a directory layout and layouts get flattened:

1. **The path carries the map**, from `carla_jobs.CAPTURES`, defined once. Eleven modules
   had this path re-typed as a literal before F26.
2. **Every frame set carries a `harness` stamp inside the npz** -- map, cloudiness, weather
   settle, rules digest, texture-streaming and quality flags -- and the resume-skip
   compares it against the harness running now. A mismatch recaptures. An unstamped file is
   a mismatch by definition, because it predates the stamp and there is no way to tell what
   made it.

`.npz` files are gitignored. The manifests and `states_*.json` are not.
