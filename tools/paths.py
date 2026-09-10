"""Where this study's artifacts live. ONE definition, scoped by map.

    import paths
    paths.OUT / "braking.json"

Every directory here is named after the map that produced its contents, and that is not
tidiness. It is the fix for the defect this repository has now written down four times.

**The defect.** An artifact from the old study sits in the flat directory under exactly
the name the new study's tool asks for. The tool reads it, gets a Town01 answer to a
Town12 question, and reports success. Nothing raises. On the night of 2026-09-10 it
happened four times in one night: the captures at both regulatory endpoints (F26),
`results/carla/` with 157 of 179 files still Town01's and `--refine` about to read ten
Town01 gate artifacts as current, ten of twelve gate artifacts, and 54 checkpoints in
`results/models/` -- one of which was hashed against itself and nearly closed F29 with
the answer "training is reproducible". Three of the four were caught by luck or by a
return code. `results/captures/` was scoped after F26 and stopped producing them.

**Why this module and not a constant in `carla_jobs`.** `condition_signature` and
`record_primitives` must run on a machine with no simulator and no `carla` package, so
they cannot import `carla_jobs`, and each had re-typed the path instead. That is how a
"single definition" becomes three. This module imports nothing but the standard library,
so every one of them can share it.

`CARLA_MAP` overrides the map for one reason: the Town01 artifacts are where the plate
defects (F22, F24) can still be settled, and reaching them must not need an edit.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# A19: back to Town01. The large map needs a graphics card this study no longer assumes.
# Measurement code reads this constant; nothing hard-codes a map. Override with CARLA_MAP,
# which is how the Town12 artifacts stay reachable.
MAP = os.environ.get("CARLA_MAP", "Town01")

CAPTURES = REPO / "results" / "captures" / MAP   # rendered frames, .npz + manifests
OUT = REPO / "results" / "carla" / MAP           # every measured artifact, as JSON
MODELS = REPO / "results" / "models" / MAP       # trained checkpoints, .pt
