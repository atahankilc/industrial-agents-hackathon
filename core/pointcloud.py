"""Deterministic point cloud of a building for the point-cloud viewer (docs/product/visualization.md).

`export_points(building_map)` samples walls, floor slabs, door lintels, stair/lift cores and assets of the map as
it is *now* (doors added by an edit session included, `building_map.closed` reported), and returns the JSON the
viewer loads. `route_vertices(export, building_map, space_path, element_path)` turns a route (navigation.find_route
path representation) into a polyline in the same frame.

Viewer frame: three.js is y-up, so building (x, y, elevation) -> viewer (x, elevation, -y), centred on the bounding
box of the sampled points (`center` = [cx, cz]). Every point carries kind, floor index, space index and a reveal
value (0-255) that the viewer uses to grow density progressively and to stagger the "emerge" animation.
Moved here from frontend/prototypes/pointcloud/export_points.py (now a thin CLI wrapper); output format unchanged
apart from the added `connectors`, `openings` and `closed` keys."""

import math
import random
from dataclasses import dataclass

from shapely.geometry import Point, Polygon

from core.building_map import OUTSIDE, BuildingMap

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


@dataclass
class Sampling:
    wall_step: float = 0.15  # horizontal spacing along walls (m)
    wall_vstep: float = 0.25  # vertical spacing on walls (m)
    floor_step: float = 0.6  # floor-slab grid spacing (m)
    asset_density: float = 40.0  # asset points per m³
    seed: int = 7


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
                 openings: list[dict], sampling: Sampling) -> None:
    polygon = space["polygon"]
    base = floor["elevation_m"]
    height = min(floor.get("height_m", MAX_WALL_HEIGHT_M), MAX_WALL_HEIGHT_M)
    kind = CORE if space["type"] in CORE_TYPES else WALL
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        gaps = door_gaps(openings, start, end)
        for t in steps(math.dist(start, end), sampling.wall_step):
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            in_gap = [gap for gap in gaps if gap[0] <= t <= gap[1]]
            for h in steps(height, sampling.wall_vstep):
                z = base + h * height
                if in_gap:
                    if z >= base + DOOR_HEIGHT_M:
                        cloud.add(x, y, z, DOOR if z <= base + DOOR_HEIGHT_M + sampling.wall_vstep else kind,
                                  floor_index, space_index)
                    continue
                cloud.add(x, y, z, kind, floor_index, space_index)
    shape = Polygon(polygon)
    min_x, min_y, max_x, max_y = shape.bounds
    jitter = sampling.floor_step * 0.35
    y = min_y + sampling.floor_step / 2
    while y < max_y:
        x = min_x + sampling.floor_step / 2
        while x < max_x:
            px = x + cloud.rng.uniform(-jitter, jitter)
            py = y + cloud.rng.uniform(-jitter, jitter)
            if shape.contains(Point(px, py)):
                cloud.add(px, py, base, CORE if kind == CORE else FLOOR, floor_index, space_index)
            x += sampling.floor_step
        y += sampling.floor_step


def sample_asset(cloud: Cloud, asset: dict, floor: dict, floor_index: int, space_index: int,
                 sampling: Sampling) -> None:
    footprint = asset.get("footprint") or {}
    width, depth = footprint.get("width_m", 0.5), footprint.get("depth_m", 0.5)
    angle = math.radians(footprint.get("rotation_deg", 0.0))
    height = ASSET_HEIGHT_M.get(asset["category"], 1.0)
    count = max(6, min(80, round(width * depth * height * sampling.asset_density)))
    cx, cy = asset["position"]
    for _ in range(count):
        u, v = cloud.rng.uniform(-width / 2, width / 2), cloud.rng.uniform(-depth / 2, depth / 2)
        x = cx + u * math.cos(angle) - v * math.sin(angle)
        y = cy + u * math.sin(angle) + v * math.cos(angle)
        cloud.add(x, y, floor["elevation_m"] + cloud.rng.uniform(0.05, height), ASSET, floor_index, space_index)


def sorted_floors(building_map: BuildingMap) -> list[dict]:
    return sorted(building_map.data["floors"], key=lambda floor: floor["level"])


def floor_indices(building_map: BuildingMap) -> dict[str, int]:
    """floor id → index into the export's `floors` (sorted by level)."""
    return {floor["id"]: index for index, floor in enumerate(sorted_floors(building_map))}


def to_viewer(x: float, y: float, elevation: float, center: list[float]) -> list[float]:
    """Building (x, y, elevation) → centred viewer frame [x, y-up, z], metres rounded to the cm."""
    return [round(x - center[0], 2), round(elevation, 2), round(-y - center[1], 2)]


def sample(building_map: BuildingMap, sampling: Sampling) -> dict:
    """One sampling pass at fixed steps (no budget)."""
    data = building_map.data
    floors = sorted_floors(building_map)
    floor_index = floor_indices(building_map)
    spaces = [space for space in data["spaces"] if space["type"] not in SKIPPED_TYPES]
    space_index = {space["id"]: index for index, space in enumerate(spaces)}
    # The map's openings, not data["openings"]: an edit session may hold a door added to the map.
    openings_by_floor: dict[str, list[dict]] = {}
    for opening in building_map.openings.values():
        openings_by_floor.setdefault(opening["floor_id"], []).append(opening)

    cloud = Cloud(sampling.seed)
    for space in spaces:
        floor = building_map.floors[space["floor_id"]]
        sample_space(cloud, space, floor, floor_index[floor["id"]], space_index[space["id"]],
                     openings_by_floor.get(floor["id"], []), sampling)
    for asset in data["assets"]:
        floor = building_map.floors[asset["floor_id"]]
        sample_asset(cloud, asset, floor, floor_index[floor["id"]], space_index.get(asset["space_id"], -1), sampling)

    xs, zs = cloud.positions[0::3], cloud.positions[2::3]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    centred_cm = [
        round((value - (cx if axis == 0 else cz if axis == 2 else 0.0)) * 100)
        for index, value in enumerate(cloud.positions)
        for axis in [index % 3]
    ]
    center = [round(cx, 2), round(cz, 2)]

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
        "center": center,
        "count": len(cloud),
        "points": {
            "position_cm": centred_cm,
            "kind": cloud.kinds,
            "floor": cloud.floors,
            "space": cloud.spaces,
            "reveal": cloud.reveal,
        },
        "connectors": [
            {
                "id": connector["id"],
                "name": connector["name"],
                "kind": connector["kind"],
                "spaces": [space_index[space_id] for space_id in connector["space_ids"] if space_id in space_index],
            }
            for connector in building_map.connectors.values()
        ],
        "openings": [
            {
                "id": opening["id"],
                "kind": opening["kind"],
                "floor": floor_index[opening["floor_id"]],
                "position": to_viewer(*opening["position"],
                                      building_map.floors[opening["floor_id"]]["elevation_m"] + ROUTE_HEIGHT_M,
                                      center),
                "width_m": opening["width_m"],
                "step_free": opening["step_free"],
            }
            for opening in building_map.openings.values()
        ],
        "closed": sorted(building_map.closed),
    }


def export_points(
    building_map: BuildingMap,
    *,
    wall_step: float = 0.15,
    wall_vstep: float = 0.25,
    floor_step: float = 0.6,
    asset_density: float = 40.0,
    max_points: int = 180_000,
    seed: int = 7,
) -> dict:
    """The viewer export of the map's current state; sampling coarsens until the cloud fits `max_points`."""
    sampling = Sampling(wall_step, wall_vstep, floor_step, asset_density, seed)
    result = sample(building_map, sampling)
    while result["count"] > max_points:
        factor = math.sqrt(result["count"] / max_points) * 1.05
        sampling.wall_step *= factor
        sampling.wall_vstep *= factor
        sampling.floor_step *= factor
        result = sample(building_map, sampling)
    result["sampling"] = {"wall_step": round(sampling.wall_step, 3), "wall_vstep": round(sampling.wall_vstep, 3),
                          "floor_step": round(sampling.floor_step, 3)}
    return result


def route_nodes(building_map: BuildingMap, space_path: list[str], element_path: list[str]) -> list[tuple[str, str]]:
    """The walk as ("space"|"door", id) nodes: an opening appears twice in element_path (space→door, door→space),
    a connector once per floor hop (navigation.find_route path representation)."""
    nodes = [("space", space_path[0])]
    spaces = iter(space_path[1:])
    index = 0
    while index < len(element_path):
        element = element_path[index]
        if element in building_map.openings:
            nodes.append(("door", element))
            index += 2 if element_path[index + 1: index + 2] == [element] else 1
        else:
            index += 1
        nodes.append(("space", next(spaces)))
    return nodes


def route_vertices(export: dict, building_map: BuildingMap, space_path: list[str],
                   element_path: list[str]) -> list[list[float]]:
    """Route polyline [[x, y, z, floor_index], ...] in the export's viewer frame, ROUTE_HEIGHT_M above each floor:
    space anchor → door → next anchor; a floor change is drawn as "move across, then straight up/down"."""
    if not space_path:
        return []
    center = export["center"]
    floor_index = floor_indices(building_map)
    vertices: list[list[float]] = []
    previous_floor = None
    for node_kind, node in route_nodes(building_map, space_path, element_path):
        if node == OUTSIDE:
            continue
        if node_kind == "door":
            opening = building_map.openings[node]
            floor_id, (x, y) = opening["floor_id"], opening["position"]
        else:
            floor_id, (x, y) = building_map.spaces[node]["floor_id"], building_map.anchor(node)
        elevation = building_map.floors[floor_id]["elevation_m"] + ROUTE_HEIGHT_M
        if previous_floor is not None and previous_floor != floor_id and vertices:
            # move across at the previous height, then the riser
            vertices.append([*to_viewer(x, y, vertices[-1][1], center), vertices[-1][3]])
        vertices.append([*to_viewer(x, y, elevation, center), floor_index[floor_id]])
        previous_floor = floor_id
    return vertices
