# Map survey (M1)

`python tools/survey_maps.py`, offline from each map's OpenDRIVE file.

**Town13 is the choice.** 401 pedestrian sites and 367 braking sites, with declared limits
spanning 30 to 55 mph, which covers both test speeds. Town12 has more long straights but
its roads are declared in km/h and top out near 34 mph outside one highway, so it cannot
host the 50 mph false-activation test on an appropriate road. Town11 has the single longest
straight, 12,048 ft, but only 133 pedestrian sites and just two declared speeds.

**None of the standard towns qualify.** Town10HD's longest straight is 190 ft, and Town02,
03, 05 and 07 all fall under 460 ft. A 25 mph pedestrian approach needs 500 ft and a 50 mph
braking site needs 650 ft, so a large map was not a preference here, it was forced.

**Town13 is a large map, so the ego must be tagged `role_name='hero'`** or the server dies
when a sensor is attached. See PROTOCOL.md section 12.

## Two things this cannot tell us

- **Lighting.** Street lamps are scenery, not road network, so lit and unlit stretches are
  invisible to this survey. Headlamp beam is a test variable, so candidate sites have to be
  checked in the simulator before one is fixed.
- **Marked crosswalks.** Zero pedestrian sites carry one, because crosswalks sit at
  junctions and the long straights sit between them. This is not a problem: FMVSS runs
  crossing-pedestrian tests on a proving ground and does not require a crosswalk. It is
  recorded because a marked crosswalk would have been nice for the demo imagery.

## Method note

CARLA splits one physical straight across many OpenDRIVE road records, so measuring runs
within a single record measures fragments and reports zero long straights everywhere. The
survey merges straight pieces that touch end-to-start on the same heading, in world
coordinates, which sidesteps road boundaries entirely.
