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
    a = ap.parse_args()

    J.MAP = a.map
    client, world = J.connect(load_map=a.map, rendering=not a.no_rendering)
    spawn = world.get_map().get_spawn_points()[0]
    base = server_rss_gb()
    print(f"map {a.map}  rendering={'off' if a.no_rendering else 'on'}  base {base:.2f} GB", flush=True)
    prev = base
    for i in range(a.cycles):
        ego = J.spawn_hero(world, spawn)
        for _ in range(a.ticks):
            world.tick()
        J.despawn(world, ego)
        now = server_rss_gb()
        print(f"  cycle {i+1:2d}: {now:6.2f} GB  (+{now - prev:+.2f} this cycle, "
              f"{now - base:+.2f} total)", flush=True)
        prev = now
    print(f"\ngrowth per cycle: {(prev - base) / a.cycles:+.3f} GB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
