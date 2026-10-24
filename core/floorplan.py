"""Vector floor plan of a building for the app's plan view (docs/product/visualization.md).

`export_plan(building_map, center)` returns the map as it is *now* (doors added by an edit session included,
`building_map.closed` reported) as plain vectors per floor: space outlines, wall segments with the door gaps cut
out, doors with their wall direction and swing side, vertical connectors and a label point per space.

Frame: building metres (x right, y up), not centred. `center` is the point-cloud export's centre
(core/pointcloud.py) so the app can map route vertices (viewer frame) back: x = vx + cx, y = -(vz + cz)."""

import math

from shapely.geometry import Point, Polygon
from shapely.ops import polylabel

from core.building_map import OUTSIDE, BuildingMap
from core.pointcloud import SKIPPED_TYPES, door_gaps, floor_indices, sorted_floors

GAP_MERGE = 1e-6
LABEL_TOLERANCE_M = 0.05


def r(value: float) -> float:
    return round(value, 3)


def wall_segments(polygon: list, openings: list[dict]) -> list[list[float]]:
    """Polygon edges as [x1, y1, x2, y2] segments, with every door/opening gap on the edge removed."""
    segments = []
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        if math.dist(start, end) == 0:
            continue
        gaps = sorted((max(0.0, a), min(1.0, b)) for a, b, _ in door_gaps(openings, start, end) if b > 0 and a < 1)
        t = 0.0
        for a, b in gaps + [(1.0, 1.0)]:
            if a > t + GAP_MERGE:
                segments.append([r(start[0] + (end[0] - start[0]) * t), r(start[1] + (end[1] - start[1]) * t),
                                 r(start[0] + (end[0] - start[0]) * a), r(start[1] + (end[1] - start[1]) * a)])
            t = max(t, b)
    return segments


def dedupe(segments: list[list[float]]) -> list[list[float]]:
    """Shared walls come from both rooms: keep one copy of identical segments (either direction)."""
    seen, unique = set(), []
    for x1, y1, x2, y2 in segments:
        key = tuple(sorted([(round(x1, 2), round(y1, 2)), (round(x2, 2), round(y2, 2))]))
        if key not in seen:
            seen.add(key)
            unique.append([x1, y1, x2, y2])
    return unique


def door_geometry(opening: dict, polygons: dict[str, Polygon]) -> dict:
    """Wall direction at the opening (angle in degrees of the nearest edge of its first indoor space) and which
    side of that edge the first indoor space lies on (+1 left of the edge direction, -1 right)."""
    position = Point(opening["position"])
    for space_id in opening["space_ids"]:
        shape = polygons.get(space_id)
        if shape is None:
            continue
        coords = list(shape.exterior.coords)
        best = min(zip(coords, coords[1:]), key=lambda edge: _edge_distance(position, edge))
        (x1, y1), (x2, y2) = best
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        nx, ny = -(y2 - y1), x2 - x1
        probe = Point(position.x + nx * 0.01 / math.hypot(nx, ny), position.y + ny * 0.01 / math.hypot(nx, ny))
        side = 1 if shape.contains(probe) else -1
        return {"angle": round(angle, 1), "space": space_id, "side": side}
    return {"angle": 0.0, "space": None, "side": 1}


def _edge_distance(point: Point, edge: tuple) -> float:
    (x1, y1), (x2, y2) = edge
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((point.x - x1) * dx + (point.y - y1) * dy) / length))
    return math.hypot(point.x - (x1 + t * dx), point.y - (y1 + t * dy))


def label_point(shape: Polygon) -> tuple[list[float], float]:
    """Pole of inaccessibility (best spot for a label) and its distance to the outline (room for the label)."""
    try:
        point = polylabel(shape, tolerance=LABEL_TOLERANCE_M)
    except Exception:  # degenerate polygon
        point = shape.representative_point()
    room = shape.exterior.distance(point)
    centroid = shape.centroid
    # Long corridors: polylabel lands near an end; the centroid reads better when it is almost as roomy.
    if shape.contains(centroid) and shape.exterior.distance(centroid) >= 0.8 * room:
        point, room = centroid, shape.exterior.distance(centroid)
    return [r(point.x), r(point.y)], r(room)


def export_plan(building_map: BuildingMap, center: list[float]) -> dict:
    data = building_map.data
    floors = sorted_floors(building_map)
    floor_index = floor_indices(building_map)
    spaces = [space for space in data["spaces"] if space["type"] not in SKIPPED_TYPES]
    polygons = {space["id"]: Polygon(space["polygon"]) for space in spaces}
    openings_by_floor: dict[str, list[dict]] = {}
    for opening in building_map.openings.values():
        openings_by_floor.setdefault(opening["floor_id"], []).append(opening)

    walls: dict[int, list[list[float]]] = {index: [] for index in range(len(floors))}
    space_items = []
    for space in spaces:
        index = floor_index[space["floor_id"]]
        shape = polygons[space["id"]]
        walls[index] += wall_segments(space["polygon"], openings_by_floor.get(space["floor_id"], []))
        label, room = label_point(shape)
        space_items.append({
            "id": space["id"],
            "floor": index,
            "type": space["type"],
            "room_type": space.get("room_type") or "",
            "name": space["name"],
            "ref": space.get("ref") or "",
            "polygon": [[r(x), r(y)] for x, y in space["polygon"]],
            "area_m2": round(shape.area, 1),
            "label": label,
            "label_room_m": room,
        })

    xs = [x for space in spaces for x, _ in space["polygon"]]
    ys = [y for space in spaces for _, y in space["polygon"]]
    return {
        "building": {"id": data["building"]["id"], "name": data["building"]["name"],
                     "source": data["building"]["source"], "attribution": data["building"].get("attribution", "")},
        "floors": [{"id": f["id"], "level": f["level"], "name": f["name"], "elevation_m": f["elevation_m"],
                    "height_m": f.get("height_m", 3.0)} for f in floors],
        "bounds": [r(min(xs)), r(min(ys)), r(max(xs)), r(max(ys))] if xs else [0, 0, 0, 0],
        "center": center,
        "spaces": space_items,
        "walls": [dedupe(walls[index]) for index in range(len(floors))],
        "openings": [
            {
                "id": opening["id"],
                "floor": floor_index[opening["floor_id"]],
                "kind": opening["kind"],
                "position": [r(opening["position"][0]), r(opening["position"][1])],
                "width_m": opening["width_m"],
                "step_free": opening["step_free"],
                "spaces": opening["space_ids"],
                "entrance": OUTSIDE in opening["space_ids"],
                **door_geometry(opening, polygons),
            }
            for opening in building_map.openings.values()
        ],
        "connectors": [
            {"id": connector["id"], "name": connector["name"], "kind": connector["kind"],
             "spaces": connector["space_ids"], "step_free": connector["step_free"]}
            for connector in building_map.connectors.values()
        ],
        "assets": [
            {
                "id": asset["id"],
                "floor": floor_index[asset["floor_id"]],
                "space": asset["space_id"],
                "category": asset["category"],
                "type": asset["type"],
                "name": asset["name"],
                "position": [r(asset["position"][0]), r(asset["position"][1])],
                "size": [r((asset.get("footprint") or {}).get("width_m", 0.5)),
                         r((asset.get("footprint") or {}).get("depth_m", 0.5))],
                "rotation_deg": (asset.get("footprint") or {}).get("rotation_deg", 0.0),
            }
            for asset in data["assets"]
            if asset["space_id"] in polygons  # not on balconies / outdoor spaces, which the plan does not draw
        ],
        "closed": sorted(building_map.closed),
    }
