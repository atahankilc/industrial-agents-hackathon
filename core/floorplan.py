"""Vector floor plan of a building for the app's plan view (docs/product/visualization.md).

`export_plan(building_map)` returns the map as it is *now* (doors added by an edit session included,
`building_map.closed` reported) as plain vectors per floor: space outlines, wall segments with the door gaps cut
out, solid wall polygons (`wall_solids`), doors with their wall direction (no swing: the data has none), vertical connectors and a
label point per space.

Wall solids: building.json has no walls, only room outlines. Sources traced from drawings (Swiss Dwellings, ResPlan)
leave the real wall thickness as a gap between neighbouring rooms (0.1-0.5 m); OSM and procedural rooms share edges
(gap 0). So the wall mass is the gaps between rooms (closed up to WALL_GAP_MAX_M), plus a synthetic partition where
rooms touch, plus an exterior shell outside the outline, minus the doorways; every room keeps its full outline.
Each piece is classed by thickness: "exterior", "structural" (at least STRUCTURAL_M thick, e.g. walls between
apartments or round stair/lift cores) or "partition". An open space (lobby, corridor) mapped inside a bigger one
(OSM: a lobby zone inside a lecture hall, a lobby inside a corridor) gets no wall where its outline runs through that
space, only where it meets the bigger space's own edge. So does an open stair: one with no door at all, only doorless
openings (OSM maps no door; the kit links it to the space around it by a synthetic opening). Lifts, stairwells with
a door and nested rooms keep their walls. `outlines` gives each floor's outline the exterior wall wraps
(the rooms with those gaps closed), as polygons with holes.

Overlaps: where two spaces' outlines overlap (OSM maps some zones inside others) the floor belongs to both, so
`overlaps` gives each such piece as diagonal stripes, alternately owned by one space and the other. Stairwells and
lifts are left out: they are shafts with their own walls, cut through the space mapped under them.

Frame: building metres (x right, y up), not centred. `center` = [cx, cz] is the centre of the space bounds in the
app's y-up scene frame (X = x - cx, Z = -y - cz), unless the caller passes one."""

import math

from shapely import affinity, set_precision
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import polylabel, unary_union
from shapely.strtree import STRtree

from core.building_map import OUTSIDE, BuildingMap
SKIPPED_TYPES = {"outdoor"}
DOOR_EDGE_DISTANCE_M = 0.35
GAP_MERGE = 1e-6
LABEL_TOLERANCE_M = 0.05
WALL_GAP_MAX_M = 0.6  # gaps between rooms up to this wide are wall (kit: walls within 0.35 m are shared)
EXTERIOR_M = 0.25
PARTITION_M = 0.1  # drawn where rooms touch (no thickness in the data)
TOUCH_M = 0.03  # rooms closer than this touch (OSM outlines drift ~2 cm); drawn walls are thicker (Swiss: 3 cm+)
CORE_M = 0.2  # ... and round stairwells and lifts
STRUCTURAL_M = 0.18
DOOR_CUT_DEPTH_M = 0.8
WALL_SIMPLIFY_M = 0.005
MITRE = {"join_style": "mitre", "mitre_limit": 3.0}
CORE_TYPES = {"stair", "lift"}
OPEN_TYPES = {"hall", "corridor"}  # zones of an open floor: no wall of their own inside a space that holds them
OVERLAP_MIN_M2 = 0.5
STRIPE_M = 0.5  # width of one stripe of an overlap
NESTED_SHARE = 0.9  # a space is inside another when at least this share of its area is


def r(value: float) -> float:
    return round(value, 3)


def sorted_floors(building_map: BuildingMap) -> list[dict]:
    return sorted(building_map.data["floors"], key=lambda floor: floor["level"])


def floor_indices(building_map: BuildingMap) -> dict[str, int]:
    """floor id → index into the export's `floors` (sorted by level)."""
    return {floor["id"]: index for index, floor in enumerate(sorted_floors(building_map))}


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


def is_open(space: dict, openings: list[dict]) -> bool:
    """A lobby or corridor, or a stair reached only through doorless openings (no door: an open stair)."""
    if space["type"] in OPEN_TYPES:
        return True
    kinds = {opening["kind"] for opening in openings if space["id"] in opening["space_ids"]}
    return space["type"] == "stair" and kinds == {"opening"}


def open_zones(spaces: list[dict], polygons: dict[str, Polygon], openings: list[dict]) -> dict[str, Polygon]:
    """Open spaces (`is_open`) lying inside a bigger space on their floor → that space's interior (where they have no
    wall)."""
    shapes = [polygons[space["id"]].buffer(0) for space in spaces]
    tree = STRtree(shapes)
    zones = {}
    for space, shape in zip(spaces, shapes):
        if shape.area == 0 or not is_open(space, openings):
            continue
        holders = [shapes[j] for j in tree.query(shape)
                   if spaces[j]["floor_id"] == space["floor_id"] and shapes[j].area > shape.area
                   and shapes[j].intersection(shape).area >= NESTED_SHARE * shape.area]
        if holders:
            zones[space["id"]] = unary_union(holders).buffer(-GAP_MERGE * 10000, **MITRE)
    return zones


def overlaps(spaces: list[dict], polygons: dict[str, Polygon]) -> list[dict]:
    """Overlaps of one floor's spaces as stripes: [{"space", "rings": [outer, *holes]}], at 45°, owners alternating."""
    drawn = [space for space in spaces if space["type"] not in CORE_TYPES]
    shapes = [polygons[space["id"]].buffer(0) for space in drawn]
    tree = STRtree(shapes)
    stripes = []
    for i, shape in enumerate(shapes):
        for j in sorted(int(j) for j in tree.query(shape)):
            if j <= i:
                continue
            common = _area(shape.intersection(shapes[j]))
            if common.area < OVERLAP_MIN_M2:
                continue
            # stripes across the overlap: bands in a frame turned 45°, then turned back
            turned = affinity.rotate(common, -45, origin=(0, 0))
            x0, y0, x1, y1 = turned.bounds
            start = math.floor(x0 / STRIPE_M)
            for band in range(start, math.ceil(x1 / STRIPE_M)):
                piece = turned.intersection(box(band * STRIPE_M, y0 - 1, (band + 1) * STRIPE_M, y1 + 1))
                owner = drawn[i if band % 2 == 0 else j]["id"]
                piece = set_precision(_area(affinity.rotate(piece, 45, origin=(0, 0))), 0.001)
                for polygon in _polygons(piece):
                    if polygon.area >= 0.001:
                        stripes.append({"space": owner, "rings": [[[r(x), r(y)] for x, y in ring.coords[:-1]]
                                                                  for ring in [polygon.exterior, *polygon.interiors]]})
    return stripes


def clip_segments(segments: list[list[float]], zone: Polygon | None) -> list[list[float]]:
    """The parts of the segments outside `zone`."""
    if zone is None or zone.is_empty:
        return segments
    clipped = []
    for x1, y1, x2, y2 in segments:
        rest = LineString([(x1, y1), (x2, y2)]).difference(zone)
        for part in getattr(rest, "geoms", [rest]):
            if isinstance(part, LineString) and part.length > GAP_MERGE:
                (ax, ay), (bx, by) = part.coords[0], part.coords[-1]
                clipped.append([r(ax), r(ay), r(bx), r(by)])
    return clipped


def dedupe(segments: list[list[float]]) -> list[list[float]]:
    """Shared walls come from both rooms: keep one copy of identical segments (either direction)."""
    seen, unique = set(), []
    for x1, y1, x2, y2 in segments:
        key = tuple(sorted([(round(x1, 2), round(y1, 2)), (round(x2, 2), round(y2, 2))]))
        if key not in seen:
            seen.add(key)
            unique.append([x1, y1, x2, y2])
    return unique


def outline(spaces: list[dict], polygons: dict[str, Polygon]) -> list[list[list[list[float]]]]:
    """One floor's outline (the rooms with the wall gaps closed, as in `wall_solids`): polygons as [outer, *holes]."""
    shapes = [shape for shape in (polygons[space["id"]].buffer(0) for space in spaces) if not shape.is_empty]
    if not shapes:
        return []
    half_gap = WALL_GAP_MAX_M / 2
    rooms = unary_union([shape.buffer(GAP_MERGE * 5000, **MITRE) for shape in shapes])
    closed = set_precision(_area(rooms.buffer(half_gap, **MITRE).buffer(-half_gap, **MITRE)).simplify(WALL_SIMPLIFY_M), 0.001)
    return [[[[r(x), r(y)] for x, y in ring.coords[:-1]] for ring in [polygon.exterior, *polygon.interiors]]
            for polygon in _polygons(closed) if polygon.area >= 0.01]


def wall_solids(spaces: list[dict], openings: list[dict], polygons: dict[str, Polygon],
                zones: dict[str, Polygon] | None = None) -> list[dict]:
    """Solid walls of one floor as polygons with holes: [{"kind", "rings": [outer, *holes]}]. `zones`: see
    `open_zones` (computed here when not given)."""
    zones = open_zones(spaces, polygons, openings) if zones is None else zones
    shapes = [polygons[space["id"]].buffer(0) for space in spaces]
    shapes = [shape for shape in shapes if not shape.is_empty]
    if not shapes:
        return []
    # touching rooms merge (the tiny buffer closes float slivers along shared edges)
    rooms = unary_union([shape.buffer(GAP_MERGE * 5000, **MITRE) for shape in shapes])
    half_gap = WALL_GAP_MAX_M / 2
    closed = rooms.buffer(half_gap, **MITRE).buffer(-half_gap, **MITRE)
    gaps = _area(closed.difference(rooms))

    # outline pieces with a room on both sides lie inside `rooms`, away from its boundary
    edge = rooms.boundary.buffer(GAP_MERGE * 10000)
    # an open space's outline only counts where it leaves the space holding it
    lines = [shape.exterior.difference(zones[space["id"]]) if space["id"] in zones else shape.exterior
             for space, shape in zip(spaces, shapes)]
    outlines = unary_union(lines)
    shared = outlines.difference(edge)
    # rooms that almost touch (an OSM vertex drawn 2 cm off) leave a gap too thin for a wall: their edges get the
    # partition as well, else the wall drops from 10 cm to the gap's few mm where the gap first exceeds GAP_MERGE
    near = (TOUCH_M - GAP_MERGE * 10000) / 2  # the gap as measured between the grown rooms
    thin = gaps.difference(gaps.buffer(-near, **MITRE).buffer(near, **MITRE))
    shared = unary_union([shared, outlines.intersection(thin.buffer(GAP_MERGE * 10000))])
    cores = unary_union([shape.exterior for space, shape in zip(spaces, shapes) if space["type"] in CORE_TYPES])
    core_lines = shared.intersection(cores.buffer(GAP_MERGE * 10000)) if not cores.is_empty else LineString()
    partitions = unary_union([
        shared.buffer(PARTITION_M / 2, cap_style="flat", **MITRE),
        core_lines.buffer(CORE_M / 2, cap_style="flat", **MITRE),
    ])
    interior = _area(unary_union([gaps, _area(partitions)]).intersection(closed))
    exterior = _area(closed.buffer(EXTERIOR_M, **MITRE).difference(closed))

    cuts = []
    for opening in openings:
        edge = wall_edge(opening, polygons)
        if edge is None:
            continue
        x, y = opening["position"]
        half_width = opening.get("width_m", 0.9) / 2
        cut = box(x - half_width, y - DOOR_CUT_DEPTH_M / 2, x + half_width, y + DOOR_CUT_DEPTH_M / 2)
        cuts.append(affinity.rotate(cut, math.degrees(math.atan2(edge[1][1], edge[1][0])), origin=(x, y)))
    doorways = unary_union(cuts)

    thick = _area(interior.buffer(-STRUCTURAL_M / 2, **MITRE).buffer(STRUCTURAL_M / 2, **MITRE).intersection(interior))
    pieces = {
        "exterior": exterior,
        "structural": thick,
        "partition": _area(interior.difference(thick)),
    }
    solids = []
    for kind, shape in pieces.items():
        # snapping to the mm grid the export rounds to keeps every piece valid (plain rounding can self-intersect)
        shape = set_precision(_area(shape.difference(doorways)).simplify(WALL_SIMPLIFY_M), 0.001)
        for polygon in _polygons(shape):
            if polygon.area < 0.01:
                continue
            rings = [polygon.exterior, *polygon.interiors]
            solids.append({"kind": kind, "rings": [[[r(x), r(y)] for x, y in ring.coords[:-1]] for ring in rings]})
    return solids


def _area(shape) -> MultiPolygon:
    """Only the polygon parts of an overlay result (which may mix in lines and points)."""
    return MultiPolygon([polygon for polygon in _polygons(shape) if not polygon.is_empty])


def _polygons(shape) -> list[Polygon]:
    if isinstance(shape, Polygon):
        return [shape]
    if isinstance(shape, MultiPolygon):
        return list(shape.geoms)
    return [part for geom in getattr(shape, "geoms", []) for part in _polygons(geom)]


def door_geometry(opening: dict, polygons: dict[str, Polygon]) -> dict:
    """Wall direction at the opening (angle in degrees of the nearest edge of its first drawn space, `space`). The
    data has no swing or hinge, so the plan marks a doorway without a leaf."""
    edge = wall_edge(opening, polygons)
    if edge is None:
        return {"angle": 0.0, "space": None}
    space_id, (ux, uy) = edge
    return {"angle": round(math.degrees(math.atan2(uy, ux)), 1), "space": space_id}


def wall_edge(opening: dict, polygons: dict[str, Polygon]) -> tuple[str, tuple[float, float]] | None:
    """First drawn space of an opening and the unit direction of its outline edge nearest the opening."""
    position = Point(opening["position"])
    for space_id in opening["space_ids"]:
        shape = polygons.get(space_id)
        if shape is None:
            continue
        coords = list(shape.exterior.coords)
        (x1, y1), (x2, y2) = min(zip(coords, coords[1:]), key=lambda edge: _edge_distance(position, edge))
        length = math.hypot(x2 - x1, y2 - y1) or 1.0
        return space_id, ((x2 - x1) / length, (y2 - y1) / length)
    return None


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


def export_plan(building_map: BuildingMap, center: list[float] | None = None) -> dict:
    data = building_map.data
    floors = sorted_floors(building_map)
    floor_index = floor_indices(building_map)
    spaces = [space for space in data["spaces"] if space["type"] not in SKIPPED_TYPES]
    polygons = {space["id"]: Polygon(space["polygon"]) for space in spaces}
    openings_by_floor: dict[str, list[dict]] = {}
    for opening in building_map.openings.values():
        openings_by_floor.setdefault(opening["floor_id"], []).append(opening)

    zones = open_zones(spaces, polygons, list(building_map.openings.values()))
    walls: dict[int, list[list[float]]] = {index: [] for index in range(len(floors))}
    space_items = []
    for space in spaces:
        index = floor_index[space["floor_id"]]
        shape = polygons[space["id"]]
        walls[index] += clip_segments(wall_segments(space["polygon"], openings_by_floor.get(space["floor_id"], [])),
                                      zones.get(space["id"]))
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
    if center is None:
        center = [round((min(xs) + max(xs)) / 2, 2), round(-(min(ys) + max(ys)) / 2, 2)] if xs else [0.0, 0.0]
    return {
        "building": {"id": data["building"]["id"], "name": data["building"]["name"],
                     "source": data["building"]["source"], "attribution": data["building"].get("attribution", "")},
        "floors": [{"id": f["id"], "level": f["level"], "name": f["name"], "elevation_m": f["elevation_m"],
                    "height_m": f.get("height_m", 3.0)} for f in floors],
        "bounds": [r(min(xs)), r(min(ys)), r(max(xs)), r(max(ys))] if xs else [0, 0, 0, 0],
        "center": center,
        "spaces": space_items,
        "walls": [dedupe(walls[index]) for index in range(len(floors))],
        "wall_solids": [
            wall_solids([space for space in spaces if floor_index[space["floor_id"]] == index],
                        openings_by_floor.get(floor["id"], []), polygons, zones)
            for index, floor in enumerate(floors)
        ],
        "overlaps": [
            overlaps([space for space in spaces if floor_index[space["floor_id"]] == index], polygons)
            for index in range(len(floors))
        ],
        "outlines": [
            outline([space for space in spaces if floor_index[space["floor_id"]] == index], polygons)
            for index in range(len(floors))
        ],
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
