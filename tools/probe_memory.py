"""Why did the server reach 58 GB and get OOM-killed?

    python tools/probe_memory.py --map Town13 --cycles 12 [--no-rendering]

Spawns and destroys the ego repeatedly, logging the SERVER's resident memory each
cycle, so growth per cycle is a measurement rather than a guess. Run it against a large
map and a standard one to find out whether the growth is map-size specific.
"""
from __future__ import annotations
import argparse, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carla_jobs as J


def server_rss_gb() -> float:
    # Matched on the process NAME, not the command line. The kernel truncates comm to
    # 15 characters, so the server is "CarlaUE4-Linux-". Matching the command line also
    # matches the shell that launched it, and that shell reports 0.00 GB, which is a
    # very convincing way to conclude there is no leak.
    out = subprocess.run(
        ["pgrep", "-x", "CarlaUE4-Linux-"], capture_output=True, text=True
    ).stdout.split()
    if not out:
        return float("nan")
    with open(f"/proc/{out[0]}/statm") as fh:
        return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e9


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="Town13")
    ap.add_argument("--cycles", type=int, default=12)
    ap.add_argument("--no-rendering", action="store_true")
    ap.add_argument("--ticks", type=int, default=100)
    ap.add_argument(
        "--reuse-hero",
        action="store_true",
        help="spawn once and reset it each cycle, instead of destroy and respawn",
    )
    ap.add_argument(
        "--no-spawn",
        action="store_true",
        help="tick only, never spawn. Separates per-tick growth from per-spawn growth",
    )
    a = ap.parse_args()

    J.MAP = a.map
    client, world = J.connect(load_map=a.map, rendering=not a.no_rendering)
    spawn = world.get_map().get_spawn_points()[0]
    base = server_rss_gb()
    mode = (
        "reuse one hero"
        if a.reuse_hero
        else "tick only"
        if a.no_spawn
        else "spawn + tick + destroy"
    )
    print(
        f"map {a.map}  rendering={'off' if a.no_rendering else 'on'}  "
        f"{mode}  {a.ticks} ticks/cycle  base {base:.2f} GB",
        flush=True,
    )
    prev = base
    held = J.spawn_hero(world, spawn) if a.reuse_hero else None
    for i in range(a.cycles):
        t0 = time.time()
        if a.reuse_hero:
            J.reset_vehicle(world, held, spawn)
            for _ in range(a.ticks):
                world.tick()
        elif a.no_spawn:
            for _ in range(a.ticks):
                world.tick()
        else:
            ego = J.spawn_hero(world, spawn)
            for _ in range(a.ticks):
                world.tick()
            J.despawn(world, ego)
        now = server_rss_gb()
        dt = max(time.time() - t0, 1e-6)
        print(
            f"  cycle {i+1:2d}: {now:6.2f} GB  ({now - prev:+.2f} this cycle, "
            f"{now - base:+.2f} total)   {dt:6.1f} s   {a.ticks / dt:5.1f} ticks/s",
            flush=True,
        )
        prev = now
    if held is not None:
        J.despawn(world, held)
    print(f"\ngrowth per cycle: {(prev - base) / a.cycles:+.3f} GB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
