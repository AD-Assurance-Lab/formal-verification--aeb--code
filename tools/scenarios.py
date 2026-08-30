"""The three FMVSS scenario objects, built to the standard's own dimensions.

Imported by the jobs; not run directly. Every constant here traces to PROTOCOL section 2
or to a measurement recorded in the session notes.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

FT = 0.3048  # ft -> m

# FMVSS No. 127 false-activation target: ASTM A36 steel trench plate, 8 x 12 ft x 1 in.
PLATE_W_FT, PLATE_L_FT = 8.0, 12.0
# Measured: static.prop.ironplank is 3.9 x 4.8 ft x 0.81 in, about a quarter of the
# plate's area, so it is tiled. Thickness is close enough that a vehicle drives over it
# the same way; the width and length are what a perception system sees.
PLANK_W_FT, PLANK_L_FT = 3.9, 4.8

# Measured walker dynamics. A walker does NOT start at its commanded speed: it ramps
# linearly at about 2.22 m/s^2, reaching 1.5 m/s after roughly 13 ticks (0.65 s). Once
# there it tracks the command exactly, 1.500 against 1.500 and 2.000 against 2.000.
# An earlier "8 percent shortfall" was this ramp being averaged into the measurement.
WALKER_ACCEL_MPS2 = 2.22
WALKER_SETTLE_TICKS = 20  # let the spawn drop resolve before commanding motion


def lane_axes(wp):
    """Forward and right unit vectors in the world frame, from a waypoint."""
    yaw = math.radians(wp.transform.rotation.yaw)
    return (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))


def place_trench_plate(world, wp):
    """Tile ironplanks to cover at least 8 x 12 ft, centred on the lane.

    Returns the spawned actors and the actual covered size, because a scenario that
    silently covers half the area the standard specifies is not that scenario.
    """
    carla = J.carla_module()
    bp = world.get_blueprint_library().find("static.prop.ironplank")
    (fx, fy), (rx, ry) = lane_axes(wp)
    # Tiles are OVERLAPPED so the outer edges land exactly on the specified size.
    # Butting them edge to edge and rounding the count up covered 11.7 x 14.4 ft
    # against a specified 8 x 12, which is a different target from the one in the
    # standard.
    n_across = max(1, math.ceil(PLATE_W_FT / PLANK_W_FT))
    n_along = max(1, math.ceil(PLATE_L_FT / PLANK_L_FT))
    span_r = (PLATE_W_FT - PLANK_W_FT) * FT
    span_f = (PLATE_L_FT - PLANK_L_FT) * FT
    step_r = span_r / (n_across - 1) if n_across > 1 else 0.0
    step_f = span_f / (n_along - 1) if n_along > 1 else 0.0
    base = wp.transform.location

    actors = []
    for i in range(n_across):
        for j in range(n_along):
            off_r = (i - (n_across - 1) / 2.0) * step_r
            off_f = (j - (n_along - 1) / 2.0) * step_f
            loc = carla.Location(
                x=base.x + rx * off_r + fx * off_f,
                y=base.y + ry * off_r + fy * off_f,
                z=base.z + 0.02,
            )
            a = world.try_spawn_actor(
                bp, carla.Transform(loc, wp.transform.rotation)
            )
            if a is not None:
                actors.append(a)
    world.tick()
    return actors, {
        "tiles": len(actors),
        "covered_w_ft": round(span_r / FT + PLANK_W_FT, 1),
        "covered_l_ft": round(span_f / FT + PLANK_L_FT, 1),
        "target_w_ft": PLATE_W_FT,
        "target_l_ft": PLATE_L_FT,
    }


def calibrate_walker_speed(
    world, walker, direction, commanded: float, warmup: int = 30, ticks: int = 60
):
    """Walkers do not achieve the speed you command them. Measure the steady state.

    Measured over the whole window including the start, 1.5 commanded gives 1.34, and
    correcting by that ratio then overshoots, because the window average is dragged down
    by the walker accelerating from rest. Discarding a warm-up makes the relationship
    stable and correctable.

    For a crossing-pedestrian test the arrival time IS the scenario, so this is not a
    detail: an eight percent speed error moves the conflict point by metres.
    """
    carla = J.carla_module()
    ctrl = carla.WalkerControl()
    ctrl.direction = carla.Vector3D(x=direction[0], y=direction[1], z=0.0)
    ctrl.speed = commanded
    carla_jobs.apply_control(walker, ctrl)
    for _ in range(warmup):
        world.tick()
    p0 = walker.get_transform().location
    for _ in range(ticks):
        world.tick()
    p1 = walker.get_transform().location
    achieved = math.hypot(p1.x - p0.x, p1.y - p0.y) / (ticks * J.FIXED_DT)
    ctrl.speed = 0.0
    carla_jobs.apply_control(walker, ctrl)
    world.tick()
    return achieved, (commanded / achieved if achieved > 0.01 else 1.0)


def spawn_crossing_pedestrian(world, wp, lateral_m: float = 6.0, height: float = 1.0):
    """A pedestrian standing off the right of the lane, facing across it.

    Driven by direct WalkerControl rather than `controller.ai.walker`. The AI controller
    picks its own path and speed, which makes two runs of the same cell different runs,
    and PROTOCOL requires determinism.
    """
    carla = J.carla_module()
    bp = world.get_blueprint_library().filter("walker.pedestrian.*")[0]
    if bp.has_attribute("is_invincible"):
        bp.set_attribute("is_invincible", "false")
    (_, _), (rx, ry) = lane_axes(wp)
    base = wp.transform.location
    tf = carla.Transform(
        carla.Location(x=base.x + rx * lateral_m, y=base.y + ry * lateral_m,
                       z=base.z + height),
        carla.Rotation(yaw=wp.transform.rotation.yaw - 90.0),
    )
    walker = world.try_spawn_actor(bp, tf)
    if walker is None:
        raise RuntimeError("pedestrian spawn blocked")
    # Spawned above the ground so it does not intersect it, then allowed to settle.
    # Without this the first commanded tick shows 0.49 m of displacement and an
    # apparent 9.8 m/s, which is the drop and the navmesh snap, not walking.
    for _ in range(WALKER_SETTLE_TICKS):
        world.tick()
    return walker, (-rx, -ry)  # direction that crosses INTO the lane


def walker_lead_distance(speed_mps: float) -> float:
    """How far a walker travels while getting up to speed.

    A crossing scenario that releases the pedestrian at the geometrically correct moment
    arrives LATE by this much, because the ramp is not instantaneous. Either start the
    walker this far back, or start it early by speed / WALKER_ACCEL_MPS2 seconds.
    """
    t_ramp = speed_mps / WALKER_ACCEL_MPS2
    return 0.5 * WALKER_ACCEL_MPS2 * t_ramp * t_ramp
