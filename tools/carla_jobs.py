"""Everything queued for the simulator, in the order it has to run.

    python tools/carla_jobs.py --list
    python tools/carla_jobs.py --all              # stops at the first failure
    python tools/carla_jobs.py --job braking      # one job

Each job writes results/carla/<job>.json and prints a verdict. Jobs are ordered so the
cheapest thing that can kill the whole plan runs first.

Standing rules this file already obeys, from PROTOCOL.md and hard experience:

  * the ego is tagged role_name='hero'. Large maps stream terrain around the hero and
    actors outside the streamed area go dormant; attaching a sensor to a dormant one
    kills the server. Town01 is used now; the tag still matters if a large map is ever revisited.
  * a read issued next to a write does not see that write. Weather, transforms and
    sensor delivery all apply on the NEXT tick, and nothing errors when you get this
    wrong. Never read back state you just wrote.
  * contact is measured from geometry, never from sensor.other.collision, which has
    been observed reporting nothing while a vehicle sat 8 ft inside another body.
  * relaunch the server before every measurement run. It leaks memory over hours.
  * ONE client at a time. In synchronous mode the job owns the tick, and a second
    script calling get_world() blocks until it times out, which looks like a dead
    server rather than a busy one.
  * every closed-loop number is a rate over at least 10 repetitions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "results" / "carla"

MAP = "Town01"
FIXED_DT = 0.05  # 20 Hz, PROTOCOL section 1
MPH = 0.44704  # mph -> m/s
FT = 3.280839895  # m -> ft
HAZARD_MPH = 25.0
PLATE_MPH = 50.0
SETTLE_TICKS = 40
MAX_SETTLE_TICKS = 400  # the PI hold exits early once it is at speed
SETTLE_TOLERANCE_MPS = 0.15
# Scene lighting takes far longer to settle after a sun-altitude change than a "few
# ticks" intuition suggests. Measured on Town01, day (221) to night (42.5): still 74.4
# at 12 ticks, 60.1 at 20, 45.2 at 40, settled by 80, flat from 80 to 400. Capturing a
# darkness endpoint at 12 ticks makes it 75 percent too bright, and the disturbance
# family interpolates between endpoints, so that error would land in the verified set.
WEATHER_SETTLE_TICKS = 120
REPS = 10


def carla_module():
    try:
        import carla  # noqa
    except ImportError:
        sys.exit(
            "The carla module is not importable. Activate the environment that has the\n"
            "CARLA Python API on its path, then rerun."
        )
    return carla


def connect(load_map: str | None = MAP, rendering: bool = True):
    """Connect, load the map, and put the world in fixed-step synchronous mode.

    `rendering=False` turns off rendering entirely. Physics is unaffected, so it is
    correct for jobs that measure vehicle dynamics and use no camera, and on a large
    map it is the difference between a measurement run taking minutes and taking hours.
    It is NOT a quality reduction on any perception measurement, because those jobs
    need frames and therefore keep rendering on.
    """
    carla = carla_module()
    host = os.environ.get("CARLA_HOST", "127.0.0.1")
    port = int(os.environ.get("CARLA_PORT", "2000"))
    client = carla.Client(host, port)
    # Map loads dominate this timeout. Town13 takes minutes, and switching AWAY from it
    # is slower still, which times out a 120 s client while the server is working fine.
    client.set_timeout(float(os.environ.get("CARLA_TIMEOUT", "600")))
    world = client.get_world()
    if load_map and not world.get_map().name.endswith(load_map):
        print(f"  loading {load_map} (large maps take a while)", flush=True)
        world = client.load_world(load_map)
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = FIXED_DT
    settings.no_rendering_mode = not rendering
    world.apply_settings(settings)
    world.tick()  # the settings take effect on the next tick, not on the call
    left = clear_actors(world)
    if left:
        print(f"  cleared {left} actors left by an earlier run", flush=True)
    return client, world


def despawn(world, *actors):
    """Destroy actors and tick. A destroy issued next to a spawn at the same point
    fails, because the destroy has not been applied yet."""
    for a in actors:
        if a is not None:
            try:
                a.destroy()
            except RuntimeError:
                pass
    world.tick()


def grab_frame(world, images, timeout: float = 20.0):
    """Tick once and return THE frame that tick produced.

    Matched on the id `world.tick()` returns, and a missing frame raises rather than
    being skipped. This repository's own notes say so, and ignoring them cost a full
    set of lighting captures: a `except queue.Empty: pass` left the queue one frame
    ahead, so every image afterwards belonged to the previous condition. The captures
    then said headlamps make the road DARKER, monotonically, which is backwards and was
    entirely an artefact of reading stale frames.
    """
    import queue as _queue

    frame_id = world.tick()
    while True:
        try:
            img = images.get(timeout=timeout)
        except _queue.Empty:
            raise RuntimeError(f"no camera frame for tick {frame_id}")
        if img.frame == frame_id:
            return img
        if img.frame > frame_id:
            raise RuntimeError(
                f"camera is ahead of the world: got frame {img.frame}, wanted {frame_id}"
            )


def rgb_camera_bp(world, width: int = 640, height: int = 480, fov: float = 90.0):
    """A camera with FIXED exposure.

    CARLA's default `exposure_mode` is `histogram`, which is auto-exposure. That is
    exactly the defect this lab published about ACDC: auto-exposed, so absolute
    photometry is gone. It matters more here than there, because the disturbance family
    interpolates absolute pixel values between a daylight frame and a darkness frame. If
    the camera re-exposes between them, the two endpoints are not on a common scale and
    the interval between them means nothing.

    Measured with auto-exposure on: turning the headlamps ON made the mean image
    *darker*, 54.9 to 40.0 to 33.2 across off, low beam and high beam, because the
    bright patch pulled the exposure down. That ordering is backwards and it is the
    camera, not the scene.
    """
    bp = world.get_blueprint_library().find("sensor.camera.rgb")
    bp.set_attribute("image_size_x", str(width))
    bp.set_attribute("image_size_y", str(height))
    bp.set_attribute("fov", str(fov))
    bp.set_attribute("exposure_mode", "manual")
    bp.set_attribute("shutter_speed", "200.0")
    bp.set_attribute("iso", "100.0")
    bp.set_attribute("fstop", "1.4")
    bp.set_attribute("exposure_compensation", "0.0")
    return bp


def clear_actors(world) -> int:
    """Destroy every vehicle, walker and sensor left over from a previous run.

    A job killed mid-run leaves its actors in the world, and the next run then fails
    with "spawn blocked" at a point that is perfectly fine. Always start clean.
    """
    doomed = [
        a
        for a in world.get_actors()
        if a.type_id.startswith(("vehicle.", "walker.", "sensor."))
    ]
    for a in doomed:
        try:
            a.destroy()
        except RuntimeError:
            pass
    if doomed:
        world.tick()
    return len(doomed)


def usable_run_m(world, wp, limit: float = 400.0, step: float = 2.0) -> float:
    """How far you can actually drive from this waypoint before a junction.

    The offline survey knows the road geometry; it does not know where the drivable
    lane goes. Walking the lane in the simulator does, and it is what catches a site
    that runs out after 30 m.
    """
    travelled = 0.0
    cur = wp
    while travelled < limit:
        nxt = cur.next(step)
        if not nxt or nxt[0].is_junction:
            break
        cur = nxt[0]
        travelled += step
    return travelled


def site_transform(world, site: dict, along: float = 0.0, need_m: float = 0.0):
    """Turn a surveyed site into an on-road transform pointing DOWN the straight.

    Two things have to be right and neither is automatic:

    1. **Direction.** `get_waypoint` returns the nearest lane, which is as likely to be
       the opposing one. Launching along it drives off the end of the straight within
       seconds. Measured: a site running at 90 degrees projected to a lane facing 270,
       and the ego hit a junction 30 m later at 21 m/s, which the braking job then
       recorded as 4.94 g of braking authority.
    2. **Room.** The straight has to still be there ahead of the vehicle, which is a
       question about lanes and junctions, not about the road reference line.

    So both site endpoints are tried, and the one whose lane actually runs into the
    straight, with at least `need_m` of junction-free lane ahead, is used.
    """
    carla = carla_module()
    ends = [
        (site["x0"], site["y0"], site["x1"], site["y1"]),
        (site["x1"], site["y1"], site["x0"], site["y0"]),
    ]
    best = None
    for x_from, y_from, x_to, y_to in ends:
        found = world.get_map().get_waypoint(
            carla.Location(x=x_from, y=-y_from, z=0.0), project_to_road=True
        )
        if found is None:
            continue
        # The nearest lane is often the opposing one. Measured at the Town01 site:
        # the projected lane faced 270 with 84 m of run, and its LEFT lane faced 90
        # with 392 m. So consider the neighbours, not just the nearest.
        candidates = [found]
        for neighbour in (found.get_left_lane(), found.get_right_lane()):
            if neighbour is not None and neighbour.lane_type == carla.LaneType.Driving:
                candidates.append(neighbour)

        want = math.atan2(-(y_to - y_from), x_to - x_from)
        for wp in candidates:
            have = math.radians(wp.transform.rotation.yaw)
            if math.cos(want - have) <= 0.0:
                continue  # points back out of the straight
            run = usable_run_m(world, wp, limit=max(need_m, 50.0) + 100.0)
            if best is None or run > best[1]:
                best = (wp, run)

    if best is None:
        raise RuntimeError(
            f"no lane at site ({site['x0']:.0f}, {site['y0']:.0f}) runs along the straight"
        )
    wp, run = best
    if need_m and run < need_m:
        raise RuntimeError(
            f"site has only {run:.0f} m of junction-free lane, needs {need_m:.0f} m"
        )
    if along:
        nxt = wp.next(along)
        if nxt:
            wp = nxt[0]
    tf = wp.transform
    tf.location.z += 0.3
    return tf, wp


def spawn_hero(world, transform):
    """Spawn the ego. The hero tag is not cosmetic; see the module docstring."""
    carla = carla_module()
    bp = world.get_blueprint_library().filter("vehicle.tesla.model3")[0]
    bp.set_attribute("role_name", "hero")
    actor = world.try_spawn_actor(bp, transform)
    if actor is None:
        raise RuntimeError(f"spawn blocked at {transform.location}")
    for _ in range(SETTLE_TICKS):
        world.tick()
    return actor


def reset_vehicle(world, actor, transform, settle_ticks: int = SETTLE_TICKS):
    """Put an existing vehicle back at the start instead of respawning it.

    On a large map, destroying the hero un-anchors terrain streaming and the next spawn
    forces the whole neighbourhood to stream in again. Keeping one hero alive for the
    whole job avoids that churn entirely, and it is much faster.
    """
    carla = carla_module()
    actor.set_target_velocity(carla.Vector3D(0, 0, 0))
    actor.set_target_angular_velocity(carla.Vector3D(0, 0, 0))
    actor.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
    actor.set_transform(transform)
    for _ in range(settle_ticks):
        world.tick()
    actor.apply_control(carla.VehicleControl(throttle=0.0, brake=0.0))
    return actor


def speed_of(actor) -> float:
    v = actor.get_velocity()
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def _support(actor, axis_x: float, axis_y: float) -> float:
    """How far the actor's bounding box reaches along a world-frame unit axis."""
    ex = actor.bounding_box.extent.x
    ey = actor.bounding_box.extent.y
    yaw = math.radians(actor.get_transform().rotation.yaw)
    fx, fy = math.cos(yaw), math.sin(yaw)          # forward
    rx, ry = -math.sin(yaw), math.cos(yaw)         # right
    return abs(ex * (fx * axis_x + fy * axis_y)) + abs(ey * (rx * axis_x + ry * axis_y))


def separation_ft(a, b) -> float:
    """Gap between two bounding boxes along the line joining their centres, in feet.

    Negative means the boxes overlap. This is the contact measure for the whole study,
    and it replaces sensor.other.collision, which has been observed reporting nothing
    while a vehicle sat 8 ft inside another body.

    Each box is projected onto the connecting axis rather than using its diagonal. The
    diagonal over-estimates reach for a head-on approach, which would report contact
    before it happened and understate every standoff distance we measure.
    """
    la, lb = a.get_transform().location, b.get_transform().location
    dx, dy = lb.x - la.x, lb.y - la.y
    centre = math.hypot(dx, dy)
    if centre < 1e-6:
        return -_support(a, 1.0, 0.0) * FT
    ux, uy = dx / centre, dy / centre
    return (centre - _support(a, ux, uy) - _support(b, ux, uy)) * FT


def progress(msg: str) -> None:
    """Print and flush. A long job with buffered output looks like a dead one, and on a
    large map these take minutes."""
    print(f"    {msg}", flush=True)


def write(job: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{job}.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  wrote results/carla/{job}.json")


def flattest_site(max_grade_pct: float = 0.5) -> dict:
    """Longest straight that is actually flat.

    Measured: the longest straight in Town13 runs at 1.35 percent, which biases a
    braking measurement by a couple of percent. The flat-road number is the one the
    safety budget wants, so length alone is the wrong sort order here.
    """
    flat = [
        s
        for s in top_sites(200)
        if s.get("grade_pct") is not None and abs(s["grade_pct"]) <= max_grade_pct
    ]
    if not flat:
        raise RuntimeError(f"no straight flatter than {max_grade_pct}%")
    return flat[0]


def top_sites(n: int = 8) -> list[dict]:
    path = REPO / "results" / "survey" / "sites.json"
    sites = [s for s in json.loads(path.read_text()) if s["map"] == MAP]
    sites.sort(key=lambda s: s["run_ft"], reverse=True)
    return sites[:n]


# ----------------------------------------------------------------------------- jobs


def job_smoke() -> dict:
    """Can we even work on this map? The single cheapest way to kill the plan.

    Town13 is a large map, and attaching a sensor to a vehicle that is not tagged hero
    has crashed the server on every large map this lab has tried. Prove the tag fixes
    it before building anything on top.
    """
    carla = carla_module()
    client, world = connect()
    spawn = world.get_map().get_spawn_points()[0]
    ego = spawn_hero(world, spawn)
    try:
        bp = rgb_camera_bp(world)
        cam = world.spawn_actor(
            bp, carla.Transform(carla.Location(x=1.5, z=1.6)), attach_to=ego
        )
        frames = []
        cam.listen(lambda img: frames.append(img.frame))
        for _ in range(100):
            world.tick()
        time.sleep(0.5)
        cam.stop()
        cam.destroy()
        ok = len(frames) > 50
        return {
            "verdict": "PASS" if ok else "FAIL",
            "map": world.get_map().name,
            "frames_received": len(frames),
            "note": "server survived a sensor attach on a large map with the hero tag",
        }
    finally:
        despawn(world, ego)


def job_sites() -> dict:
    """The one thing the offline survey could not answer: is the site lit?

    Street lamps are scenery, not road network, so they are invisible to the OpenDRIVE.
    This visits the longest Town13 straights and photographs each under the three
    regulatory lighting conditions, plus a fourth with the headlamps off, which is what
    actually measures street lighting: with the lamps on you cannot tell an unlit road
    from a lit one.

    Mean image brightness makes it a number rather than an opinion. It also produces the
    first real imagery of the disturbance endpoints.
    """
    carla = carla_module()
    import queue

    client, world = connect()
    shots = OUT / "sites"
    shots.mkdir(parents=True, exist_ok=True)

    # day, then the two regulatory darkness conditions, then lamps-off as the control
    CONDITIONS = [
        ("day", 60.0, carla.VehicleLightState.NONE),
        ("night_nolights", -30.0, carla.VehicleLightState.NONE),
        ("night_lowbeam", -30.0, carla.VehicleLightState.LowBeam),
        ("night_highbeam", -30.0, carla.VehicleLightState.HighBeam),
    ]

    results = []
    for i, site in enumerate(top_sites(6)):
        progress(f"site {i}: {site['run_ft']:.0f} ft")
        try:
            tf, _ = site_transform(world, site, along=25.0, need_m=60.0)
            ego = spawn_hero(world, tf)
        except RuntimeError as exc:
            results.append({"site": i, "error": str(exc)})
            continue
        cam = None
        try:
            bp = world.get_blueprint_library().find("sensor.camera.rgb")
            bp.set_attribute("image_size_x", "640")
            bp.set_attribute("image_size_y", "480")
            bp.set_attribute("fov", "90")
            images: "queue.Queue" = queue.Queue()
            cam = world.spawn_actor(
                bp,
                carla.Transform(carla.Location(x=1.5, z=1.6)),
                attach_to=ego,
            )
            cam.listen(images.put)

            for label, altitude, lights in CONDITIONS:
                w = world.get_weather()
                w.sun_altitude_angle = altitude
                w.cloudiness = 10.0
                w.precipitation = 0.0
                world.set_weather(w)
                ego.set_light_state(carla.VehicleLightState(lights))
                # Weather, lights and sensor delivery all land on a later tick. Drain a
                # few frames rather than trusting the first one after the write.
                # Weather, lights and sensor delivery land on later ticks, and the
                # sky itself takes about 80 ticks to settle. See WEATHER_SETTLE_TICKS.
                for _ in range(WEATHER_SETTLE_TICKS):
                    grab_frame(world, images)
                img = grab_frame(world, images)
                name = f"site{i:02d}_{label}.png"
                img.save_to_disk(str(shots / name))
                buf = memoryview(img.raw_data)
                total = sum(buf[k] for k in range(0, len(buf), 64))  # sample every 16px
                mean = total / max(1, len(range(0, len(buf), 64)))
                results.append(
                    {
                        "site": i,
                        "run_ft": site["run_ft"],
                        "xy": [site["x0"], site["y0"]],
                        "lanes": site["driving_lanes"],
                        "condition": label,
                        "mean_brightness": round(mean, 2),
                        "image": name,
                    }
                )
        finally:
            if cam is not None:
                cam.stop()
            despawn(world, cam, ego)

    # A site is "lit" if it is meaningfully brighter than pitch dark with lamps off.
    lit = {}
    for r in results:
        if r.get("condition") == "night_nolights":
            lit[r["site"]] = r["mean_brightness"]
    return {
        "verdict": "PASS" if lit else "FAIL",
        "street_lighting_by_site": lit,
        "note": (
            "night_nolights is the measurement that matters: with headlamps on, an "
            "unlit road and a lit one look similar ahead of the vehicle. Higher mean "
            "brightness with the lamps off means street lighting is present."
        ),
        "captures": results,
    }


def _brake_from(world, ego, spawn, target_mps: float) -> dict:
    """One full-brake stop from target speed. Returns the measured run."""
    carla = carla_module()
    yaw = math.radians(spawn.rotation.yaw)
    ego.set_target_velocity(
        carla.Vector3D(x=target_mps * math.cos(yaw), y=target_mps * math.sin(yaw), z=0.0)
    )
    # Hold the speed through the settle, with an integral term.
    #
    # A proportional-only hold leaves steady-state error, because at the target the
    # throttle it commands is zero and the car coasts down until drag balances a small
    # throttle. Measured: it settled at 76 percent of the commanded speed at BOTH test
    # speeds, so runs labelled 25 and 50 mph were driven at 19 and 38.
    integral = 0.0
    for _ in range(MAX_SETTLE_TICKS):
        err = target_mps - speed_of(ego)
        integral = max(-20.0, min(20.0, integral + err * FIXED_DT))
        cmd = 0.5 * err + 0.5 * integral
        ego.apply_control(
            carla.VehicleControl(
                throttle=max(0.0, min(1.0, cmd)),
                brake=max(0.0, min(1.0, -cmd * 0.2)),
            )
        )
        world.tick()
        if abs(err) < SETTLE_TOLERANCE_MPS:
            break

    v0 = speed_of(ego)
    start = ego.get_transform().location
    ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))

    t_onset = None
    prev = v0
    ticks = 0
    while speed_of(ego) > 0.1 and ticks < 400:
        world.tick()
        ticks += 1
        v = speed_of(ego)
        if t_onset is None and (prev - v) / FIXED_DT > 0.5:
            t_onset = ticks * FIXED_DT
        prev = v

    end = ego.get_transform().location
    dist = math.hypot(end.x - start.x, end.y - start.y)
    stop_time = ticks * FIXED_DT
    return {
        "v0_mph": round(v0 / MPH, 2),
        "stop_ft": round(dist * FT, 2),
        "stop_s": round(stop_time, 3),
        "t_lat_s": round(t_onset, 3) if t_onset else None,
        # Average over the WHOLE stop, latency included. That makes it the conservative
        # number the safety budget wants, not the peak the tyres can manage.
        "a_avg_g": round(v0 / stop_time / 9.81, 4) if stop_time else None,
        "grade_pct": round(100.0 * (end.z - start.z) / dist, 2) if dist > 1 else None,
    }


def job_braking() -> dict:
    """Measure braking authority and actuation latency. Do not model them.

    a_max is the worst average deceleration over the stop, which already contains
    aerodynamic drag at that speed, so no drag model is needed anywhere in the study.
    """
    client, world = connect(rendering=False)  # no camera here; physics is unaffected
    # Measure on a surveyed straight that is actually flat, not an arbitrary spawn
    # point. Braking authority on a slope is not the flat-road number.
    site = flattest_site()
    # Settle at 50 mph is 2 s = 45 m, the stop is about 50 m, plus margin.
    spawn, _ = site_transform(world, site, along=10.0, need_m=160.0)
    progress(
        f"site {site['run_ft']:.0f} ft, grade {site.get('grade_pct')}%, {2 * REPS} runs"
    )

    runs = []
    ego = spawn_hero(world, spawn)  # spawned ONCE, then reset; see reset_vehicle
    try:
        for speed_mph in (HAZARD_MPH, PLATE_MPH):
            for rep in range(REPS):
                reset_vehicle(world, ego, spawn)
                run = _brake_from(world, ego, spawn, speed_mph * MPH)
                run.update(speed_mph=speed_mph, rep=rep)
                runs.append(run)
                progress(
                    f"{speed_mph:g} mph rep {rep + 1}/{REPS}: "
                    f"v0 {run['v0_mph']:.1f} mph, stop {run['stop_ft']:.0f} ft, "
                    f"{run['a_avg_g']} g"
                )
    finally:
        despawn(world, ego)

    accels = [r["a_avg_g"] for r in runs if r["a_avg_g"]]
    lats = [r["t_lat_s"] for r in runs if r["t_lat_s"]]
    # A passenger car on dry pavement cannot average much over 1 g, and a run that
    # reports more has hit something. This check exists because a run that drove into a
    # junction at 21 m/s was recorded as 4.94 g and reported PASS.
    implausible = [r for r in runs if r["a_avg_g"] and r["a_avg_g"] > 1.3]
    speed_short = [
        r for r in runs if r["v0_mph"] < 0.9 * r["speed_mph"]
    ]
    ok = len(accels) >= 2 * REPS and not implausible and not speed_short
    return {
        "verdict": "PASS" if ok else "FAIL",
        "implausible_runs": len(implausible),
        "runs_below_commanded_speed": len(speed_short),
        "site_run_ft": site["run_ft"],
        "site_grade_pct": site.get("grade_pct"),
        "site_xy": [site["x0"], site["y0"]],
        "a_max_g_worst": round(min(accels), 4) if accels else None,
        "a_max_g_median": round(statistics.median(accels), 4) if accels else None,
        "t_lat_s_worst": round(max(lats), 3) if lats else None,
        "note": "a_max is the WORST average over the stop, not the median. Use the worst.",
        "runs": runs,
    }


def job_contact() -> dict:
    """Prove the contact detector works, by causing a contact on purpose.

    A vehicle was once driven into a stationary car at 43 mph, ended 8.2 ft inside a
    body whose contact distance is 19.9 ft, and sensor.other.collision reported nothing.
    Every pass/fail in this study depends on detecting contact, so the detector is
    validated against a deliberate crash before it is trusted.
    """
    carla = carla_module()
    client, world = connect(rendering=False)  # no camera here; physics is unaffected
    site = top_sites(1)[0]
    spawn, _ = site_transform(world, site, along=20.0)
    ahead, _ = site_transform(world, site, along=60.0)
    bp = world.get_blueprint_library().filter("vehicle.audi.tt")[0]
    target = world.try_spawn_actor(bp, ahead)
    if target is None:
        return {"verdict": "FAIL", "note": "could not place the target vehicle"}
    ego = spawn_hero(world, spawn)
    sensor_events = []
    try:
        cbp = world.get_blueprint_library().find("sensor.other.collision")
        coll = world.spawn_actor(cbp, carla.Transform(), attach_to=ego)
        coll.listen(lambda e: sensor_events.append(e.frame))
        min_gap = 1e9
        ego.apply_control(carla.VehicleControl(throttle=1.0))
        for _ in range(300):
            world.tick()
            min_gap = min(min_gap, separation_ft(ego, target))
            if min_gap < -3.0:
                break
        coll.stop()
        coll.destroy()
        geometry_saw_it = min_gap <= 0.0
        return {
            "verdict": "PASS" if geometry_saw_it else "FAIL",
            "min_separation_ft": round(min_gap, 2),
            "collision_sensor_events": len(sensor_events),
            "note": (
                "PASS requires the geometry detector to register contact. The sensor "
                "event count is recorded only to document whether it agreed; the study "
                "does not depend on it either way."
            ),
        }
    finally:
        despawn(world, ego, target)


D_MARGIN_M = 1.0  # required standoff at rest. A declared design value, not a fit.


def r_req_m(v_mps: float, a_max_g: float, t_lat_s: float) -> float:
    """PROTOCOL section 3. Every term measured except the declared standoff."""
    a = a_max_g * 9.81
    return v_mps * (t_lat_s + FIXED_DT) + v_mps * v_mps / (2.0 * a) + D_MARGIN_M


def _approach(world, site, speed_mph, trigger_m, gap_m=140.0):
    """Drive at a stationary lead vehicle, brake when range reaches trigger_m.

    The oracle reads range from simulator ground truth, so it is a perfect perceiver.
    Braking latches once commanded, which is what the closed-form standoff bound in
    PROTOCOL section 7 assumes.
    """
    carla = carla_module()
    target_v = speed_mph * MPH
    ego = lead = None
    try:
        tf_ego, _ = site_transform(world, site, along=10.0, need_m=gap_m + 80.0)
        tf_lead, _ = site_transform(world, site, along=10.0 + gap_m)
        bp = world.get_blueprint_library().filter("vehicle.audi.tt")[0]
        lead = world.try_spawn_actor(bp, tf_lead)
        if lead is None:
            raise RuntimeError("lead vehicle spawn blocked")
        ego = spawn_hero(world, tf_ego)
        yaw = math.radians(tf_ego.rotation.yaw)
        ego.set_target_velocity(
            carla.Vector3D(x=target_v * math.cos(yaw), y=target_v * math.sin(yaw), z=0.0)
        )
        braking = False
        integral = 0.0
        min_gap_ft = 1e9
        v_at_brake = None
        for _ in range(1200):
            gap_ft = separation_ft(ego, lead)
            min_gap_ft = min(min_gap_ft, gap_ft)
            if not braking and gap_ft / FT <= trigger_m:
                braking = True
                v_at_brake = speed_of(ego)
            if braking:
                ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            else:
                err = target_v - speed_of(ego)
                integral = max(-20.0, min(20.0, integral + err * FIXED_DT))
                cmd = 0.5 * err + 0.5 * integral
                ego.apply_control(
                    carla.VehicleControl(
                        throttle=max(0.0, min(1.0, cmd)),
                        brake=max(0.0, min(1.0, -cmd * 0.2)),
                    )
                )
            world.tick()
            if braking and speed_of(ego) < 0.1:
                break
            if gap_ft < -3.0:
                break
        return {
            "min_gap_ft": round(min_gap_ft, 2),
            "v_at_brake_mph": round(v_at_brake / MPH, 1) if v_at_brake else None,
            "contact": min_gap_ft <= 0.0,
            "standoff_ok": min_gap_ft >= D_MARGIN_M * FT,
            "braked": braking,
        }
    finally:
        despawn(world, ego, lead)


def job_oracle() -> dict:
    """Sanity-check the harness with a policy whose answer is already known.

    A ground-truth braking law that brakes at r_req must pass 10/10. The same law
    delayed must fail 10/10. If either comes back mixed, the harness is measuring noise
    and no policy result from it means anything.
    """
    braking_file = OUT / "braking.json"
    if not braking_file.exists():
        return {"verdict": "TODO", "note": "run the braking job first; needs a_max and t_lat"}
    b = json.loads(braking_file.read_text())
    a_max_g = b["a_max_g_worst"]
    t_lat = b["t_lat_s_worst"] or 0.2

    client, world = connect(rendering=False)  # no camera here; physics is unaffected
    site = flattest_site()
    out = {"a_max_g": a_max_g, "t_lat_s": t_lat, "d_margin_m": D_MARGIN_M, "cases": {}}

    for speed in (HAZARD_MPH,):
        v = speed * MPH
        rr = r_req_m(v, a_max_g, t_lat)
        out[f"r_req_m_at_{speed:g}mph"] = round(rr, 2)
        out[f"r_req_ft_at_{speed:g}mph"] = round(rr * FT, 1)
        for label, trigger in (("perfect", rr), ("late", rr * 0.6)):
            runs = []
            for rep in range(REPS):
                runs.append(_approach(world, site, speed, trigger))
                progress(
                    f"{label} {speed:g} mph rep {rep + 1}/{REPS}: "
                    f"min gap {runs[-1]['min_gap_ft']:.1f} ft"
                )
            passes = sum(1 for r in runs if not r["contact"] and r["standoff_ok"])
            out["cases"][f"{label}_{speed:g}mph"] = {
                "trigger_m": round(trigger, 2),
                "passes": passes,
                "of": REPS,
                "min_gap_ft": [r["min_gap_ft"] for r in runs],
            }

    perfect = out["cases"].get(f"perfect_{HAZARD_MPH:g}mph", {})
    late = out["cases"].get(f"late_{HAZARD_MPH:g}mph", {})
    ok = perfect.get("passes") == REPS and late.get("passes") == 0
    out["verdict"] = "PASS" if ok else "FAIL"
    out["note"] = (
        "PASS requires the perfect oracle 10/10 and the late oracle 0/10. Anything in "
        "between means the harness is measuring noise, and no policy result from it "
        "would mean anything."
    )
    return out


def job_inbetween() -> dict:
    """Early look at the in-between check, before any policy exists.

    The family blends a daylight frame with a darkness frame and calls the middle
    "dusk". Nothing has ever confirmed that a blend resembles rendered dusk. CARLA can
    render intermediate sun altitudes, so this compares the two at matched poses.

    IMPORTANT: this is an IMAGE-space comparison, and PROTOCOL section 4 says the check
    that counts is BEHAVIOURAL, because image fidelity is not the property that
    matters. An analytic fog model once scored R-squared 0.848 on images while driving a
    policy 23.8 times harder than the real condition. So a good score here proves
    nothing. A BAD score is still worth having now: it would tell us to shorten the
    interval before spending weeks training policies against it.
    """
    carla = carla_module()
    import queue

    client, world = connect()
    shots = OUT / "inbetween"
    shots.mkdir(parents=True, exist_ok=True)

    DAY_ALT, NIGHT_ALT = 60.0, -30.0
    STEPS = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]

    site = flattest_site()
    tf, _ = site_transform(world, site, along=25.0, need_m=60.0)
    ego = spawn_hero(world, tf)
    cam = None
    frames: dict[float, list[int]] = {}
    try:
        bp = rgb_camera_bp(world)
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            bp, carla.Transform(carla.Location(x=1.5, z=1.6)), attach_to=ego
        )
        cam.listen(images.put)
        # Headlamps stay on throughout. At dusk they are on, and the darkness endpoint
        # is defined with lower beam, so switching them mid-axis would confound the
        # illumination sweep with a lamp transition.
        ego.set_light_state(carla.VehicleLightState(carla.VehicleLightState.LowBeam))

        for s in STEPS:
            progress(f"rendering s={s:.2f}")
            w = world.get_weather()
            w.sun_altitude_angle = DAY_ALT + s * (NIGHT_ALT - DAY_ALT)
            w.cloudiness = 10.0
            w.precipitation = 0.0
            world.set_weather(w)
            for _ in range(WEATHER_SETTLE_TICKS):
                grab_frame(world, images)
            img = grab_frame(world, images)
            img.save_to_disk(str(shots / f"rendered_s{s:.2f}.png"))
            frames[s] = list(memoryview(img.raw_data))
    finally:
        if cam is not None:
            cam.stop()
        despawn(world, cam, ego)

    day, night = frames[0.0], frames[1.0]
    n = len(day)
    rows = []
    for s in STEPS[1:-1]:
        rendered = frames[s]
        # BGRA buffer; skip the alpha channel
        diffs = []
        for k in range(0, n, 40):
            if (k % 4) == 3:
                continue
            blended = day[k] + s * (night[k] - day[k])
            diffs.append(abs(blended - rendered[k]))
        mae = sum(diffs) / len(diffs)
        rows.append(
            {
                "s": s,
                "mean_abs_error_0_255": round(mae, 2),
                "mean_abs_error_normalised": round(mae / 255.0, 4),
            }
        )

    worst = max(r["mean_abs_error_normalised"] for r in rows)
    return {
        "verdict": "MEASURED",
        "interval": {"day_sun_alt": DAY_ALT, "night_sun_alt": NIGHT_ALT},
        "blend_vs_rendered": rows,
        "worst_normalised_error": worst,
        "note": (
            "IMAGE space only. The check that decides the study is behavioural and "
            "waits for a policy (PROTOCOL section 4). A low number here is not "
            "evidence the family is valid; a high number is evidence it is not."
        ),
    }


def _approach_pedestrian(world, site, speed_mph, trigger_m, gap_m=120.0,
                         ped_speed=1.5, lateral_m=6.0):
    """Ego approaches a pedestrian who crosses into its path.

    The pedestrian is RELEASED on the ego's time-to-conflict, not on a wall clock, so
    the conflict happens at the same geometry every run regardless of how the approach
    went. Its ramp is compensated: a walker released at the geometrically correct moment
    arrives late, because it accelerates at about 2.22 m/s^2 rather than starting at
    speed (see tools/scenarios.py).
    """
    import scenarios as S

    carla = carla_module()
    target_v = speed_mph * MPH
    ego = ped = None
    try:
        tf_ego, _ = site_transform(world, site, along=10.0, need_m=gap_m + 80.0)
        tf_conflict, wp_conflict = site_transform(world, site, along=10.0 + gap_m)
        ped, direction = S.spawn_crossing_pedestrian(
            world, wp_conflict, lateral_m=lateral_m
        )
        ego = spawn_hero(world, tf_ego)

        yaw = math.radians(tf_ego.rotation.yaw)
        ego.set_target_velocity(
            carla.Vector3D(x=target_v * math.cos(yaw), y=target_v * math.sin(yaw), z=0.0)
        )
        # Time for the walker to reach the ego's path, ramp included.
        cross_m = max(0.0, lateral_m - ego.bounding_box.extent.y)
        ramp_s = ped_speed / S.WALKER_ACCEL_MPS2
        ramp_m = S.walker_lead_distance(ped_speed)
        walk_s = ramp_s + max(0.0, cross_m - ramp_m) / ped_speed

        ctrl = carla.WalkerControl()
        ctrl.direction = carla.Vector3D(x=direction[0], y=direction[1], z=0.0)

        braking = False
        released = False
        integral = 0.0
        min_gap_ft = 1e9
        for _ in range(1500):
            gap_ft = separation_ft(ego, ped)
            min_gap_ft = min(min_gap_ft, gap_ft)

            if not released:
                loc = ego.get_transform().location
                to_conflict = math.hypot(
                    tf_conflict.location.x - loc.x, tf_conflict.location.y - loc.y
                )
                v = max(speed_of(ego), 0.1)
                if to_conflict / v <= walk_s:
                    ctrl.speed = ped_speed
                    ped.apply_control(ctrl)
                    released = True

            if not braking and gap_ft / FT <= trigger_m:
                braking = True
            if braking:
                ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
            else:
                err = target_v - speed_of(ego)
                integral = max(-20.0, min(20.0, integral + err * FIXED_DT))
                cmd = 0.5 * err + 0.5 * integral
                ego.apply_control(
                    carla.VehicleControl(
                        throttle=max(0.0, min(1.0, cmd)),
                        brake=max(0.0, min(1.0, -cmd * 0.2)),
                    )
                )
            world.tick()
            if braking and speed_of(ego) < 0.1:
                break
            if gap_ft < -2.0:
                break
        return {
            "min_gap_ft": round(min_gap_ft, 2),
            "contact": min_gap_ft <= 0.0,
            "standoff_ok": min_gap_ft >= D_MARGIN_M * FT,
            "braked": braking,
            "released": released,
        }
    finally:
        despawn(world, ego, ped)


def job_pedestrian() -> dict:
    """Same oracle check, on the crossing-pedestrian scenario.

    The lead-vehicle oracle proved the harness can separate a correct braking law from a
    late one against a STATIONARY target on the ego's own line. A crossing pedestrian
    adds a moving conflict and a release that has to be timed, so it is a different
    thing to get wrong and gets its own validation before any policy is trained on it.
    """
    braking_file = OUT / "braking.json"
    if not braking_file.exists():
        return {"verdict": "TODO", "note": "run the braking job first"}
    b = json.loads(braking_file.read_text())
    a_max_g, t_lat = b["a_max_g_worst"], (b["t_lat_s_worst"] or 0.2)

    client, world = connect(rendering=False)
    site = flattest_site()
    v = HAZARD_MPH * MPH
    rr = r_req_m(v, a_max_g, t_lat)
    out = {
        "r_req_m": round(rr, 2),
        "r_req_ft": round(rr * FT, 1),
        "cases": {},
    }
    for label, trigger in (("perfect", rr), ("late", rr * 0.5)):
        runs = []
        for rep in range(REPS):
            runs.append(_approach_pedestrian(world, site, HAZARD_MPH, trigger))
            progress(
                f"{label} rep {rep + 1}/{REPS}: min gap {runs[-1]['min_gap_ft']:.1f} ft"
                f"{'' if runs[-1]['released'] else '  PEDESTRIAN NEVER RELEASED'}"
            )
        passes = sum(1 for r in runs if not r["contact"] and r["standoff_ok"])
        out["cases"][label] = {
            "trigger_m": round(trigger, 2),
            "passes": passes,
            "of": REPS,
            "all_released": all(r["released"] for r in runs),
            "min_gap_ft": [r["min_gap_ft"] for r in runs],
        }

    ok = (
        out["cases"]["perfect"]["passes"] == REPS
        and out["cases"]["late"]["passes"] == 0
        and out["cases"]["perfect"]["all_released"]
        and out["cases"]["late"]["all_released"]
    )
    out["verdict"] = "PASS" if ok else "FAIL"
    out["note"] = (
        "PASS needs the perfect oracle 10/10, the late oracle 0/10, and the pedestrian "
        "released on every run. A run where the pedestrian never crossed is not a "
        "pedestrian test, however good its standoff looks."
    )
    return out


def job_capture_check() -> dict:
    """Does a frame captured at a pose match the frame seen driving through it?

    Verification runs on frames captured off-policy, by placing the ego at a pose. If
    those frames do not reproduce what the vehicle actually sees there, sound bounds on
    them prove nothing about the vehicle. The parent steering study found exactly this:
    holding the vehicle at its spawn ride height while relocating it put the camera
    metres below the road on climbs, and one direction's captures were unusable.

    This is the IMAGE version of that gate. The one that finally matters compares the
    POLICY OUTPUT at the same poses and waits for a policy; PROTOCOL section 8 calls
    that the capture check. A large mismatch here is disqualifying now, and a small one
    is not yet a pass.
    """
    carla = carla_module()
    import queue

    client, world = connect(rendering=True)
    site = flattest_site()
    start_tf, _ = site_transform(world, site, along=10.0, need_m=160.0)
    ego = spawn_hero(world, start_tf)
    cam = None
    try:
        images: "queue.Queue" = queue.Queue()
        cam = world.spawn_actor(
            rgb_camera_bp(world),
            carla.Transform(carla.Location(x=1.5, z=1.6)),
            attach_to=ego,
        )
        cam.listen(images.put)
        w = world.get_weather()
        w.sun_altitude_angle = 60.0
        w.cloudiness = 10.0
        world.set_weather(w)
        for _ in range(WEATHER_SETTLE_TICKS):
            grab_frame(world, images)

        # 1. Drive, recording a frame and the pose it belongs to.
        target = HAZARD_MPH * MPH
        yaw = math.radians(start_tf.rotation.yaw)
        ego.set_target_velocity(
            carla.Vector3D(x=target * math.cos(yaw), y=target * math.sin(yaw), z=0.0)
        )
        integral = 0.0
        driven = []
        for i in range(160):
            err = target - speed_of(ego)
            integral = max(-20.0, min(20.0, integral + err * FIXED_DT))
            cmd = 0.5 * err + 0.5 * integral
            ego.apply_control(
                carla.VehicleControl(throttle=max(0.0, min(1.0, cmd)))
            )
            img = grab_frame(world, images)
            if i >= 60 and i % 20 == 0:  # after the launch settles
                driven.append((ego.get_transform(), list(memoryview(img.raw_data))))
        progress(f"drove past {len(driven)} sample poses")

        # 2. Place the ego at each recorded pose and capture again.
        ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
        for _ in range(40):
            grab_frame(world, images)

        rows = []
        for k, (pose, driven_px) in enumerate(driven):
            ego.set_target_velocity(carla.Vector3D(0, 0, 0))
            ego.set_target_angular_velocity(carla.Vector3D(0, 0, 0))
            ego.set_transform(pose)
            # Let the suspension settle onto the surface. Freezing at spawn ride height
            # is what put the parent study's camera under the road.
            for _ in range(SETTLE_TICKS):
                grab_frame(world, images)
            img = grab_frame(world, images)
            captured = memoryview(img.raw_data)
            diffs = [
                abs(driven_px[j] - captured[j])
                for j in range(0, len(driven_px), 40)
                if j % 4 != 3
            ]
            mae = sum(diffs) / len(diffs)
            here = ego.get_transform().location
            rows.append(
                {
                    "pose": k,
                    "mae_0_255": round(mae, 2),
                    "mae_normalised": round(mae / 255.0, 4),
                    "position_error_m": round(
                        math.dist(
                            (here.x, here.y, here.z),
                            (pose.location.x, pose.location.y, pose.location.z),
                        ),
                        3,
                    ),
                }
            )
            progress(
                f"pose {k}: image {mae / 255.0:.4f}, "
                f"placement {rows[-1]['position_error_m']:.3f} m"
            )
    finally:
        if cam is not None:
            cam.stop()
        despawn(world, cam, ego)

    worst = max(r["mae_normalised"] for r in rows)
    worst_pos = max(r["position_error_m"] for r in rows)
    return {
        "verdict": "MEASURED",
        "worst_image_error_normalised": worst,
        "worst_placement_error_m": worst_pos,
        "poses": rows,
        "note": (
            "Image space. The gate that decides compares POLICY OUTPUT at the same "
            "poses and waits for a policy (PROTOCOL section 8). A large error here is "
            "disqualifying now; a small one is not yet a pass."
        ),
    }


JOBS = {
    "smoke": (job_smoke, "load the map, tag hero, attach a sensor, survive"),
    "sites": (job_sites, "photograph candidate straights day and night, settle lighting"),
    "braking": (job_braking, "measure a_max and t_lat over 10 reps at each speed"),
    "contact": (job_contact, "validate the contact detector against a deliberate crash"),
    "oracle": (job_oracle, "perfect oracle 10/10, late oracle 0/10"),
    "inbetween": (job_inbetween, "does a day/night blend resemble rendered dusk (image space)"),
    "pedestrian": (job_pedestrian, "oracle check on the crossing-pedestrian scenario"),
    "capture_check": (job_capture_check, "does a placed frame match a driven frame"),
}

ORDER = [
    "smoke", "sites", "braking", "contact", "oracle", "pedestrian",
    "capture_check", "inbetween",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--job", choices=ORDER)
    args = ap.parse_args()

    if args.list or not (args.all or args.job):
        print("\nQueued for the simulator, in order:\n")
        for i, name in enumerate(ORDER, 1):
            done = (OUT / f"{name}.json").exists()
            print(f"  {i}. [{'x' if done else ' '}] {name:<9} {JOBS[name][1]}")
        print(
            "\n  Relaunch the server before a measurement run. Set CARLA_PORT if it is\n"
            "  not on 2000. [x] means a result file exists in results/carla/.\n"
        )
        return 0

    todo = ORDER if args.all else [args.job]
    for name in todo:
        print(f"\n=== {name}: {JOBS[name][1]}")
        try:
            result = JOBS[name][0]()
        except Exception as exc:  # a failed job must not look like a passed one
            print(f"  ERROR: {exc}")
            write(name, {"verdict": "ERROR", "error": str(exc)})
            return 1
        print(f"  verdict: {result.get('verdict')}")
        write(name, result)
        if result.get("verdict") in {"FAIL", "ERROR"}:
            print("  stopping: fix this before running the rest")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
