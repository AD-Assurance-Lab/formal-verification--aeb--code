"""Pick the map on evidence, not by eye. Runs offline, no simulator.

    python tools/survey_maps.py [--carla /home/za/carla] [--out results/survey]

Every CARLA map ships its road network as an OpenDRIVE (.xodr) file, so the geometry
questions the protocol asks can all be answered from disk:

  * is there a straight long enough to reach speed and stop from 50 mph
  * is there a real crosswalk with sidewalk on both sides
  * what speed is the road actually posted at

Reads the declared speed from the file, never `get_speed_limit()`, which returns the
nearest speed-limit sign prop or a default and disagrees with the declared limit on most
towns.

What this CANNOT answer: whether a stretch is lit. Street lamps are scenery, not road
network, so they are absent from the file. That criterion has to be checked in the
simulator and is reported as unknown here.

See PROTOCOL.md section 12.
"""

from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path

M_TO_FT = 3.280839895

# PROTOCOL section 12. A braking site must let the vehicle reach 50 mph and stop.
BRAKING_RUN_FT = 650.0
# Pedestrian scenarios run at 25 mph and need less room, but still a real approach.
PED_RUN_FT = 500.0


@dataclass
class Site:
    map: str
    road_id: str
    s_start_m: float
    run_m: float
    run_ft: float
    x0: float
    y0: float
    x1: float
    y1: float
    heading_rad: float
    speed_mph: float | None
    driving_lanes: int
    sidewalk_any_side: bool
    sidewalk_both_sides: bool
    crosswalk_on_run_roads: bool  # approximate: a contributing road carries one
    grade_pct: float | None  # approximate: first road start to last road end
    lit: None = None  # not knowable from the road network

    def is_braking_site(self) -> bool:
        return self.run_ft >= BRAKING_RUN_FT and self.driving_lanes > 0

    def is_pedestrian_site(self) -> bool:
        """A crossing-pedestrian test needs a straight approach and somewhere off the
        carriageway for the walker to start. It does NOT need a marked crosswalk:
        FMVSS runs these on a proving ground. Crosswalks are tracked separately as a
        realism bonus for the demo, not as a requirement."""
        return (
            self.run_ft >= PED_RUN_FT
            and self.driving_lanes > 0
            and self.sidewalk_any_side
        )


def road_speed_mph(road: ET.Element) -> float | None:
    """Declared limit, converted to mph. Roads may carry several; take the highest."""
    best = None
    for sp in road.findall("./type/speed"):
        try:
            v = float(sp.get("max", ""))
        except ValueError:
            continue  # "no limit" and similar
        unit = (sp.get("unit") or "m/s").lower()
        mph = v if unit == "mph" else v * 0.621371 if unit == "km/h" else v * 2.236936
        best = mph if best is None else max(best, mph)
    return best


def lane_summary(road: ET.Element) -> tuple[int, bool, bool]:
    """Most driving lanes in any section, and whether sidewalks appear on either side
    and on both sides."""
    most_driving = 0
    left_walk = right_walk = False
    for section in road.findall("./lanes/laneSection"):
        driving = 0
        for side in ("left", "right"):
            group = section.find(side)
            if group is None:
                continue
            for lane in group.findall("lane"):
                kind = lane.get("type")
                if kind == "driving":
                    driving += 1
                elif kind == "sidewalk":
                    if side == "left":
                        left_walk = True
                    else:
                        right_walk = True
        most_driving = max(most_driving, driving)
    return most_driving, (left_walk or right_walk), (left_walk and right_walk)


def line_segments(road: ET.Element) -> list[tuple[float, float, float, float]]:
    """Every straight piece of this road as (x, y, heading, length), world frame."""
    out = []
    for geo in road.findall("./planView/geometry"):
        if geo.find("line") is None:
            continue
        out.append(
            (
                float(geo.get("x", 0.0)),
                float(geo.get("y", 0.0)),
                float(geo.get("hdg", 0.0)),
                float(geo.get("length", 0.0)),
            )
        )
    return out


def merge_collinear(pieces: list[tuple[tuple, str]]) -> list[tuple[float, list[str]]]:
    """Join straight pieces that touch end-to-start on the same heading.

    CARLA splits one physical straight across many <road> records, so measuring runs
    within a single record measures fragments. Merging in world coordinates sidesteps
    road boundaries and link-following entirely.

    Returns (total length, contributing road ids, start point, end point, heading).
    """
    POS_TOL = 0.5      # metres
    HDG_TOL = 0.0087   # radians, half a degree

    def end_of(seg):
        x, y, h, L = seg
        return (x + L * math.cos(h), y + L * math.sin(h), h)

    # Bucket starts by rounded position so the join is near linear rather than O(n^2).
    starts: dict[tuple, list[int]] = {}
    for i, (seg, _) in enumerate(pieces):
        key = (round(seg[0] / POS_TOL), round(seg[1] / POS_TOL))
        starts.setdefault(key, []).append(i)

    def successor(i: int) -> int | None:
        ex, ey, eh = end_of(pieces[i][0])
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in starts.get((round(ex / POS_TOL) + dx, round(ey / POS_TOL) + dy), ()):
                    if j == i:
                        continue
                    sx, sy, sh, _ = pieces[j][0]
                    if math.hypot(sx - ex, sy - ey) > POS_TOL:
                        continue
                    d = (sh - eh + math.pi) % (2 * math.pi) - math.pi
                    if abs(d) <= HDG_TOL:
                        return j
        return None

    nxt = {i: successor(i) for i in range(len(pieces))}
    has_pred = set(j for j in nxt.values() if j is not None)

    runs = []
    visited = set()
    for i in range(len(pieces)):
        if i in has_pred or i in visited:
            continue  # start only from the head of a chain
        total, roads, cur = 0.0, [], i
        head = pieces[i][0]
        tail = head
        while cur is not None and cur not in visited:
            visited.add(cur)
            total += pieces[cur][0][3]
            roads.append(pieces[cur][1])
            tail = pieces[cur][0]
            cur = nxt[cur]
        ex, ey, _ = end_of(tail)
        runs.append((total, roads, (head[0], head[1]), (ex, ey), head[2]))

    for i in range(len(pieces)):  # any cycle left over
        if i not in visited:
            visited.add(i)
            seg = pieces[i][0]
            ex, ey, _ = end_of(seg)
            runs.append((seg[3], [pieces[i][1]], (seg[0], seg[1]), (ex, ey), seg[2]))
    return runs


def elevation_at(road: ET.Element, s: float) -> float | None:
    """Road surface height at station s, from the OpenDRIVE cubic elevation profile."""
    best = None
    best_s = -1.0
    for e in road.findall("./elevationProfile/elevation"):
        s0 = float(e.get("s", 0.0))
        if s0 <= s and s0 > best_s:
            best, best_s = e, s0
    if best is None:
        return None
    ds = s - best_s
    a, b, c, d = (float(best.get(k, 0.0)) for k in "abcd")
    return a + b * ds + c * ds**2 + d * ds**3


def crosswalk_positions(road: ET.Element) -> list[float]:
    return [
        float(o.get("s", 0.0))
        for o in road.findall("./objects/object")
        if (o.get("type") or "").lower() == "crosswalk"
    ]


def survey(path: Path) -> list[Site]:
    name = path.stem
    root = ET.parse(path).getroot()

    info: dict[str, dict] = {}
    pieces: list[tuple[tuple, str]] = []
    for road in root.findall("road"):
        if road.get("junction", "-1") != "-1":
            continue  # inside an intersection
        rid = road.get("id", "?")
        driving, walk_any, walk_both = lane_summary(road)
        if driving == 0:
            continue
        info[rid] = {
            "elem": road,
            "length": float(road.get("length", 0.0)),
            "driving": driving,
            "walk_any": walk_any,
            "walk_both": walk_both,
            "speed": road_speed_mph(road),
            "crosswalks": len(crosswalk_positions(road)),
        }
        for seg in line_segments(road):
            pieces.append((seg, rid))

    sites: list[Site] = []
    longest_ft = 0.0
    for run_m, road_ids, p0, p1, hdg in merge_collinear(pieces):
        run_ft = run_m * M_TO_FT
        longest_ft = max(longest_ft, run_ft)
        if run_ft < PED_RUN_FT:
            continue
        contributing = [info[r] for r in dict.fromkeys(road_ids) if r in info]
        if not contributing:
            continue
        speeds = [c["speed"] for c in contributing if c["speed"] is not None]
        # Approximate: height at the first contributing road's start against the last
        # one's end, over the run length. Good enough to rank sites by flatness, which
        # is all it is used for. Braking authority on a slope is not the flat number.
        z0 = elevation_at(contributing[0]["elem"], 0.0)
        z1 = elevation_at(contributing[-1]["elem"], contributing[-1]["length"])
        grade = (
            round(100.0 * (z1 - z0) / run_m, 2)
            if (z0 is not None and z1 is not None and run_m > 1.0)
            else None
        )
        sites.append(
            Site(
                map=name,
                road_id=",".join(dict.fromkeys(road_ids))[:60],
                s_start_m=0.0,
                run_m=round(run_m, 1),
                run_ft=round(run_ft, 1),
                x0=round(p0[0], 2),
                y0=round(p0[1], 2),
                x1=round(p1[0], 2),
                y1=round(p1[1], 2),
                heading_rad=round(hdg, 5),
                speed_mph=round(max(speeds), 1) if speeds else None,
                driving_lanes=max(c["driving"] for c in contributing),
                sidewalk_any_side=any(c["walk_any"] for c in contributing),
                sidewalk_both_sides=any(c["walk_both"] for c in contributing),
                crosswalk_on_run_roads=any(c["crosswalks"] > 0 for c in contributing),
                grade_pct=grade,
            )
        )
    return sites, longest_ft


def find_maps(carla: Path) -> list[Path]:
    seen: dict[str, Path] = {}
    for p in sorted(carla.rglob("*.xodr")):
        name = p.stem
        if name.endswith("_Opt"):
            continue  # same network as the base map, layered assets only
        seen.setdefault(name, p)
    return list(seen.values())


def main() -> int:
    global BRAKING_RUN_FT, PED_RUN_FT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--carla", default="/home/za/carla", type=Path)
    ap.add_argument("--out", default="results/survey", type=Path)
    ap.add_argument(
        "--braking-ft",
        type=float,
        default=BRAKING_RUN_FT,
        help="straight needed for the 50 mph false-activation approach",
    )
    ap.add_argument(
        "--ped-ft",
        type=float,
        default=PED_RUN_FT,
        help="straight needed for the 25 mph pedestrian approach",
    )
    args = ap.parse_args()

    BRAKING_RUN_FT = args.braking_ft
    PED_RUN_FT = args.ped_ft

    maps = find_maps(args.carla)
    if not maps:
        print(f"No .xodr files under {args.carla}")
        return 1

    all_sites: list[Site] = []
    rows = []
    for path in maps:
        sites, longest_ft = survey(path)
        all_sites += sites
        braking = [s for s in sites if s.is_braking_site()]
        ped = [s for s in sites if s.is_pedestrian_site()]
        speeds = sorted({s.speed_mph for s in sites if s.speed_mph is not None})
        rows.append(
            {
                "map": path.stem,
                "braking_sites": len(braking),
                "pedestrian_sites": len(ped),
                "longest_ft": round(longest_ft, 1),
                "pedestrian_sites_with_crosswalk": sum(
                    1 for s in ped if s.crosswalk_on_run_roads
                ),
                "declared_speeds_mph": speeds,
                "roads_with_declared_speed": sum(
                    1 for s in sites if s.speed_mph is not None
                ),
                "total_candidate_runs": len(sites),
            }
        )

    rows.sort(key=lambda r: (r["pedestrian_sites"], r["braking_sites"]), reverse=True)

    print(
        f"\nA braking site is a straight of {BRAKING_RUN_FT:.0f} ft, enough to reach 50 mph"
        f" and stop.\nA pedestrian site is {PED_RUN_FT:.0f} ft with a sidewalk alongside for"
        " the walker to start from.\nMarked crosswalks are counted separately: the standard"
        " does not require one.\n"
    )
    head = (
        f"  {'map':<12}{'ped sites':>10}{'w/ xwalk':>10}{'brake sites':>13}"
        f"{'longest ft':>12}   declared mph"
    )
    print(head)
    print("  " + "-" * (len(head) - 2))
    for r in rows:
        speeds = ", ".join(f"{v:g}" for v in r["declared_speeds_mph"]) or "none declared"
        print(
            f"  {r['map']:<12}{r['pedestrian_sites']:>10}"
            f"{r['pedestrian_sites_with_crosswalk']:>10}{r['braking_sites']:>13}"
            f"{r['longest_ft']:>12.0f}   {speeds}"
        )

    print("\n  Lit versus unlit is not in the road network and must be checked in the")
    print("  simulator. Every site above is reported with lighting unknown.\n")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "map_summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    (args.out / "sites.json").write_text(
        json.dumps([asdict(s) for s in all_sites], indent=2) + "\n"
    )
    print(f"  Wrote {args.out}/map_summary.json and sites.json\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
