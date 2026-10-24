"""Sample a deterministic point cloud from a building.json for the point-cloud viewer (index.html).

  uv run python frontend/prototypes/pointcloud/export_points.py data/train/proc-campus-train-001 out.json \
      [--route FROM TO] [--step-free] [--wall-step 0.15] [--wall-vstep 0.25] [--floor-step 0.6] [--seed 7]

Viewer frame: three.js is y-up, so building (x, y, elevation) -> viewer (x, elevation, -y), centred on the
building's bounding box. Every point carries kind, floor index, space index and a reveal value (0-255) that
the viewer uses to grow density progressively and to stagger the "emerge" animation."""

import argparse
import json
import math
import random
import sys
from pathlib import Path

import networkx as nx
from shapely.geometry import Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap  # noqa: E402

KINDS = ["wall", "floor", "door", "core", "asset"]
WALL, FLOOR, DOOR, CORE, ASSET = range(len(KINDS))
CORE_TYPES = {"stair", "lift"}
SKIPPED_TYPES = {"outdoor"}
MAX_WALL_HEIGHT_M = 3.0
DOOR_HEIGHT_M = 2.1
DOOR_EDGE_DISTANCE_M = 0.35
ROUTE_HEIGHT_M = 1.0
GRID_M = 0.05
ASSET_HEIGHT_M = {"furniture": 0.8, "fixture": 1.0, "machine": 1.8, "equipment": 1.2}


class Cloud:
    """Point buffers with grid de-duplication (shared walls are sampled from both rooms)."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.seen: set[tuple[int, int, int, int]] = set()
        self.positions: list[float] = []
        self.kinds: list[int] = []
        self.floors: list[int] = []
        self.spaces: list[int] = []
        self.reveal: list[int] = []

    def add(self, x: float, y: float, z: float, kind: int, floor: int, space: int) -> None:
        key = (round(x / GRID_M), round(y / GRID_M), round(z / GRID_M), kind)
        if key in self.seen:
            return
        self.seen.add(key)
        self.positions += [x, z, -y]
        self.kinds.append(kind)
        self.floors.append(floor)
        self.spaces.append(space)
        self.reveal.append(self.rng.randrange(256))

    def __len__(self) -> int:
        return len(self.kinds)


def steps(length: float, step: float) -> list[float]:
    count = max(1, math.ceil(length / step))
    return [index / count for index in range(count + 1)]


def door_gaps(openings: list[dict], start: tuple, end: tuple) -> list[tuple[float, float, dict]]:
    """Openings lying on this edge, as (from_t, to_t) intervals along it."""
    edge_length = math.dist(start, end)
    if edge_length == 0:
        return []
    ux, uy = (end[0] - start[0]) / edge_length, (end[1] - start[1]) / edge_length
    gaps = []
    for opening in openings:
        px, py = opening["position"][0] - start[0], opening["position"][1] - start[1]
        along = px * ux + py * uy
        across = abs(px * uy - py * ux)
        if across <= DOOR_EDGE_DISTANCE_M and -0.5 <= along <= edge_length + 0.5:
            half = opening.get("width_m", 0.9) / 2
            gaps.append(((along - half) / edge_length, (along + half) / edge_length, opening))
    return gaps


def sample_space(cloud: Cloud, space: dict, floor: dict, floor_index: int, space_index: int,
                 openings: list[dict], args: argparse.Namespace) -> None:
    polygon = space["polygon"]
    base = floor["elevation_m"]
    height = min(floor.get("height_m", MAX_WALL_HEIGHT_M), MAX_WALL_HEIGHT_M)
    kind = CORE if space["type"] in CORE_TYPES else WALL
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        gaps = door_gaps(openings, start, end)
        for t in steps(math.dist(start, end), args.wall_step):
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            in_gap = [gap for gap in gaps if gap[0] <= t <= gap[1]]
            for h in steps(height, args.wall_vstep):
                z = base + h * height
                if in_gap:
                    if z >= base + DOOR_HEIGHT_M:
                        cloud.add(x, y, z, DOOR if z <= base + DOOR_HEIGHT_M + args.wall_vstep else kind,
                                  floor_index, space_index)
                    continue
                cloud.add(x, y, z, kind, floor_index, space_index)
    shape = Polygon(polygon)
    min_x, min_y, max_x, max_y = shape.bounds
    jitter = args.floor_step * 0.35
    y = min_y + args.floor_step / 2
    while y < max_y:
        x = min_x + args.floor_step / 2
        while x < max_x:
            px = x + cloud.rng.uniform(-jitter, jitter)
            py = y + cloud.rng.uniform(-jitter, jitter)
            if shape.contains(Point(px, py)):
                cloud.add(px, py, base, CORE if kind == CORE else FLOOR, floor_index, space_index)
            x += args.floor_step
        y += args.floor_step


def sample_asset(cloud: Cloud, asset: dict, floor: dict, floor_index: int, space_index: int,
                 args: argparse.Namespace) -> None:
    footprint = asset.get("footprint") or {}
    width, depth = footprint.get("width_m", 0.5), footprint.get("depth_m", 0.5)
    angle = math.radians(footprint.get("rotation_deg", 0.0))
    height = ASSET_HEIGHT_M.get(asset["category"], 1.0)
    count = max(6, min(80, round(width * depth * height * args.asset_density)))
    cx, cy = asset["position"]
    for _ in range(count):
        u, v = cloud.rng.uniform(-width / 2, width / 2), cloud.rng.uniform(-depth / 2, depth / 2)
        x = cx + u * math.cos(angle) - v * math.sin(angle)
        y = cy + u * math.sin(angle) + v * math.cos(angle)
        cloud.add(x, y, floor["elevation_m"] + cloud.rng.uniform(0.05, height), ASSET, floor_index, space_index)


def route_polyline(building_map: BuildingMap, start: str, destination: str, step_free: bool,
                   floor_index: dict[str, int]) -> dict:
    """Full node path (rooms and doors) of the exact route model, as viewer-frame vertices."""
    first, last = building_map.resolve_space(start), building_map.resolve_space(destination)
    result = building_map.route(first, last, step_free=step_free)
    graph = building_map.graph(step_free)
    _, nodes = nx.single_source_dijkstra(graph, first, last, weight="weight")
    vertices = []
    previous_floor = None
    for node in nodes:
        if node == OUTSIDE:
            continue
        if node.startswith(DOOR_PREFIX):
            opening = building_map.openings[node[len(DOOR_PREFIX):]]
            floor_id, (x, y) = opening["floor_id"], opening["position"]
        else:
            floor_id, (x, y) = building_map.spaces[node]["floor_id"], building_map.anchor(node)
        elevation = building_map.floors[floor_id]["elevation_m"] + ROUTE_HEIGHT_M
        if previous_floor is not None and previous_floor != floor_id and vertices:
            prev = vertices[-1]
            vertices.append([x, y, prev[2], prev[3]])  # move across, then straight up/down the core
        vertices.append([x, y, elevation, floor_index[floor_id]])
        previous_floor = floor_id
    return {
        "from": building_map.describe_space(first),
        "to": building_map.describe_space(last),
        "length_m": result.length_m,
        "step_free": step_free,
        "steps": result.steps,
        "vertices": vertices,
    }


def export(building_dir: Path, args: argparse.Namespace) -> dict:
    building_map = BuildingMap.load(building_dir)
    data = building_map.data
    floors = sorted(data["floors"], key=lambda floor: floor["level"])
    floor_index = {floor["id"]: index for index, floor in enumerate(floors)}
    spaces = [space for space in data["spaces"] if space["type"] not in SKIPPED_TYPES]
    space_index = {space["id"]: index for index, space in enumerate(spaces)}
    openings_by_floor: dict[str, list[dict]] = {}
    for opening in data["openings"]:
        openings_by_floor.setdefault(opening["floor_id"], []).append(opening)

    cloud = Cloud(args.seed)
    for space in spaces:
        floor = building_map.floors[space["floor_id"]]
        sample_space(cloud, space, floor, floor_index[floor["id"]], space_index[space["id"]],
                     openings_by_floor.get(floor["id"], []), args)
    for asset in data["assets"]:
        floor = building_map.floors[asset["floor_id"]]
        sample_asset(cloud, asset, floor, floor_index[floor["id"]], space_index.get(asset["space_id"], -1), args)

    route = None
    if args.route:
        route = route_polyline(building_map, args.route[0], args.route[1], args.step_free, floor_index)

    xs, zs = cloud.positions[0::3], cloud.positions[2::3]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    centred_cm = [
        round((value - (cx if axis == 0 else cz if axis == 2 else 0.0)) * 100)
        for index, value in enumerate(cloud.positions)
        for axis in [index % 3]
    ]
    if route:
        route["vertices"] = [[round(x - cx, 2), round(z, 2), round(-y - cz, 2), f] for x, y, z, f in route["vertices"]]

    return {
        "building": {"id": data["building"]["id"], "name": data["building"]["name"],
                     "source": data["building"]["source"], "attribution": data["building"].get("attribution", "")},
        "kinds": KINDS,
        "floors": [{"level": f["level"], "name": f["name"], "elevation_m": f["elevation_m"]} for f in floors],
        "spaces": [
            {
                "id": space["id"],
                "name": space["name"],
                "ref": space.get("ref") or "",
                "floor": floor_index[space["floor_id"]],
                "anchor": [round(a, 2) for a in building_map.anchor(space["id"])],
            }
            for space in spaces
        ],
        "center": [round(cx, 2), round(cz, 2)],
        "count": len(cloud),
        "points": {
            "position_cm": centred_cm,
            "kind": cloud.kinds,
            "floor": cloud.floors,
            "space": cloud.spaces,
            "reveal": cloud.reveal,
        },
        "route": route,
    }


def export_within_budget(building_dir: Path, args: argparse.Namespace) -> dict:
    """Coarsen the sampling steps until the cloud fits --max-points (large OSM buildings)."""
    result = export(building_dir, args)
    while result["count"] > args.max_points:
        factor = math.sqrt(result["count"] / args.max_points) * 1.05
        args.wall_step, args.wall_vstep, args.floor_step = (
            args.wall_step * factor, args.wall_vstep * factor, args.floor_step * factor
        )
        result = export(building_dir, args)
    result["sampling"] = {"wall_step": round(args.wall_step, 3), "wall_vstep": round(args.wall_vstep, 3),
                          "floor_step": round(args.floor_step, 3)}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("building", type=Path, help="building directory (with building.json)")
    parser.add_argument("output", type=Path)
    parser.add_argument("--route", nargs=2, metavar=("FROM", "TO"), help="space id / exact room name or ref")
    parser.add_argument("--step-free", action="store_true")
    parser.add_argument("--wall-step", type=float, default=0.15, help="horizontal spacing along walls (m)")
    parser.add_argument("--wall-vstep", type=float, default=0.25, help="vertical spacing on walls (m)")
    parser.add_argument("--floor-step", type=float, default=0.6, help="floor-slab grid spacing (m)")
    parser.add_argument("--asset-density", type=float, default=40.0, help="asset points per m³")
    parser.add_argument("--max-points", type=int, default=180_000, help="coarsen sampling above this")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    result = export_within_budget(args.building, args)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    route = f", route {result['route']['length_m']} m" if result["route"] else ""
    print(f"{result['count']} points, {args.output.stat().st_size / 1e6:.2f} MB{route} -> {args.output}")


if __name__ == "__main__":
    main()
