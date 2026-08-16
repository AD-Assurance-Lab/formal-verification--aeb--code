"""Everything queued for the simulator, in the order it has to run.

    python tools/carla_jobs.py --list
    python tools/carla_jobs.py --all              # stops at the first failure
    python tools/carla_jobs.py --job braking      # one job

Each job writes results/carla/<job>.json and prints a verdict. Jobs are ordered so the
cheapest thing that can kill the whole plan runs first. Nothing here has been run: the
simulator was busy when it was written, so treat the first pass as debugging.

Standing rules this file already obeys, from PROTOCOL.md and hard experience:

  * the ego is tagged role_name='hero'. Large maps stream terrain around the hero and
    actors outside the streamed area go dormant; attaching a sensor to a dormant one
    kills the server. Town13 is a large map.
  * a read issued next to a write does not see that write. Weather, transforms and
    sensor delivery all apply on the NEXT tick, and nothing errors when you get this
    wrong. Never read back state you just wrote.
  * contact is measured from geometry, never from sensor.other.collision, which has
    been observed reporting nothing while a vehicle sat 8 ft inside another body.
  * relaunch the server before every measurement run. It leaks memory over hours.
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

MAP = "Town13"
FIXED_DT = 0.05  # 20 Hz, PROTOCOL section 1
MPH = 0.44704  # mph -> m/s
FT = 3.280839895  # m -> ft
HAZARD_MPH = 25.0
PLATE_MPH = 50.0
SETTLE_TICKS = 40
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


def connect(load_map: str | None = MAP):
    """Connect, load the map, and put the world in fixed-step synchronous mode."""
    carla = carla_module()
    host = os.environ.get("CARLA_HOST", "127.0.0.1")
    port = int(os.environ.get("CARLA_PORT", "2000"))
    client = carla.Client(host, port)
    client.set_timeout(120.0)
    world = client.get_world()
    if load_map and not world.get_map().name.endswith(load_map):
        print(f"  loading {load_map} (large maps take a while)")
        world = client.load_world(load_map)
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = FIXED_DT
    world.apply_settings(settings)
    world.tick()  # the settings take effect on the next tick, not on the call
    return client, world


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


def speed_of(actor) -> float:
    v = actor.get_velocity()
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def separation_ft(a, b) -> float:
    """Gap between two actors' bounding boxes along the line joining them.

    This is the contact measure. Negative means interpenetrating. It replaces
    sensor.other.collision, which cannot be trusted.
    """
    la, lb = a.get_transform().location, b.get_transform().location
    centre = math.sqrt((la.x - lb.x) ** 2 + (la.y - lb.y) ** 2)
    ea = a.bounding_box.extent
    eb = b.bounding_box.extent
    reach_a = math.hypot(ea.x, ea.y)
    reach_b = math.hypot(eb.x, eb.y)
    return (centre - reach_a - reach_b) * FT


def write(job: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{job}.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  wrote results/carla/{job}.json")


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
        bp = world.get_blueprint_library().find("sensor.camera.rgb")
        bp.set_attribute("image_size_x", "640")
        bp.set_attribute("image_size_y", "480")
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
        ego.destroy()


def job_sites() -> dict:
    """The one thing the offline survey could not answer: is the site lit?

    Street lamps are scenery, not road network. Visit the longest Town13 straights at
    night and photograph them so a site can be fixed on evidence.
    """
    carla = carla_module()
    client, world = connect()
    shots = OUT / "sites"
    shots.mkdir(parents=True, exist_ok=True)
    results = []
    for i, site in enumerate(top_sites()):
        for label, altitude in (("day", 60.0), ("night", -30.0)):
            w = world.get_weather()
            w.sun_altitude_angle = altitude
            world.set_weather(w)
            world.tick()  # weather applies on the next tick
            results.append(
                {
                    "site_index": i,
                    "road_ids": site["road_id"],
                    "run_ft": site["run_ft"],
                    "lighting": label,
                    "shot": f"site{i:02d}_{label}.png",
                }
            )
    return {
        "verdict": "MANUAL",
        "note": (
            "Sites need a camera placed on each straight and a screenshot saved. "
            "Placement needs the site's world coordinates, which the survey does not "
            "yet export. Add that export before running this job."
        ),
        "candidates": results,
    }


def job_braking() -> dict:
    """Measure braking authority and actuation latency. Do not model them.

    a_max is the worst average deceleration over the stop, which already contains
    aerodynamic drag at that speed, so no drag model is needed anywhere in the study.
    """
    carla = carla_module()
    client, world = connect()
    spawn = world.get_map().get_spawn_points()[0]
    runs = []
    for speed_mph in (HAZARD_MPH, PLATE_MPH):
        target = speed_mph * MPH
        for rep in range(REPS):
            ego = spawn_hero(world, spawn)
            try:
                ego.set_target_velocity(
                    carla.Vector3D(
                        x=target * math.cos(math.radians(spawn.rotation.yaw)),
                        y=target * math.sin(math.radians(spawn.rotation.yaw)),
                        z=0.0,
                    )
                )
                for _ in range(SETTLE_TICKS):
                    world.tick()
                v0 = speed_of(ego)
                start = ego.get_transform().location
                ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0))
                t_command = 0.0
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
                dist = math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2)
                stop_time = ticks * FIXED_DT
                runs.append(
                    {
                        "speed_mph": speed_mph,
                        "rep": rep,
                        "v0_mph": round(v0 / MPH, 2),
                        "stop_ft": round(dist * FT, 2),
                        "stop_s": round(stop_time, 3),
                        "t_lat_s": round(t_onset, 3) if t_onset else None,
                        "a_avg_g": round(v0 / stop_time / 9.81, 4) if stop_time else None,
                    }
                )
            finally:
                ego.destroy()
    accels = [r["a_avg_g"] for r in runs if r["a_avg_g"]]
    lats = [r["t_lat_s"] for r in runs if r["t_lat_s"]]
    return {
        "verdict": "PASS" if len(accels) >= 2 * REPS else "FAIL",
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
    client, world = connect()
    spawn_points = world.get_map().get_spawn_points()
    spawn = spawn_points[0]
    ahead = carla.Transform(
        carla.Location(
            x=spawn.location.x + 40.0 * math.cos(math.radians(spawn.rotation.yaw)),
            y=spawn.location.y + 40.0 * math.sin(math.radians(spawn.rotation.yaw)),
            z=spawn.location.z,
        ),
        spawn.rotation,
    )
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
        ego.destroy()
        target.destroy()


def job_oracle() -> dict:
    """Sanity-check the harness with a policy whose answer is already known.

    A ground-truth braking law that brakes at r_req must pass 10/10. The same law
    delayed past r_req must fail 10/10. If either comes back mixed, the harness is
    measuring noise and no policy result from it means anything.
    """
    return {
        "verdict": "TODO",
        "note": (
            "Needs r_req, which needs a_max and t_lat from the braking job. Run braking "
            "first, write the primitives into study/results.json, then implement this "
            "against them."
        ),
    }


JOBS = {
    "smoke": (job_smoke, "load Town13, tag hero, attach a sensor, survive"),
    "sites": (job_sites, "photograph candidate straights day and night, settle lighting"),
    "braking": (job_braking, "measure a_max and t_lat over 10 reps at each speed"),
    "contact": (job_contact, "validate the contact detector against a deliberate crash"),
    "oracle": (job_oracle, "perfect oracle 10/10, late oracle 0/10"),
}

ORDER = ["smoke", "sites", "braking", "contact", "oracle"]


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
            "  not on 2000. Nothing here has been run yet.\n"
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
