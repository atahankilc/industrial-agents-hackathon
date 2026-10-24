"""Route polyline for the plan view: where to draw a route the navigation core found.

`route_line(building_map, space_path, element_path)` walks the route as space anchor → door → next anchor (the
same walk core/directions.py describes in words) and returns points in building metres with the index of the
floor they lie on, in the floor order of core/floorplan.py's export (sorted by level). A floor change is two
consecutive points on different floors (the connector's space on each floor); the app draws those as a riser or
a badge, never as a line across the plan.

Drawing only: where a space is just passed through (in by one door, out by another on the same floor), its anchor
is skipped and the line runs door to door along the shortest path inside the space (15 cm off the walls, round
its corners, doors entered at their 30 cm landing: the walk core/building_map.py measures), instead of running on
to the space's centre and turning back. The first and last space are drawn the
same way between their anchor and the door. Route lengths are not affected (they come from core/route_models.py,
not from this line)."""

import math
from functools import lru_cache

import networkx as nx
import numpy as np

from core.building_map import (
    COVER_TOLERANCE_M,
    OUTSIDE,
    WALL_CLEARANCE_M,
    BuildingMap,
    door_landing,
    outline,
    visibility_matrix,
)
from core.floorplan import floor_indices

Point2 = tuple[float, float]


@lru_cache(maxsize=256)
def _walkable(polygon: tuple[Point2, ...]):
    """(outline, area a walk may cover, its corners, corner-to-corner visibility graph), as walking_lengths builds
    them in core/building_map.py; cached per outline (a big OSM corridor has ~1,000 corners)."""
    shape = outline(list(polygon))
    walkable = shape.buffer(-WALL_CLEARANCE_M)
    if walkable.is_empty or walkable.geom_type != "Polygon":
        walkable = shape
    allowed = walkable.buffer(COVER_TOLERANCE_M)
    corners = [corner for ring in [walkable.exterior, *walkable.interiors] for corner in list(ring.coords)[:-1]]
    graph = nx.Graph()
    if corners:
        matrix = visibility_matrix(allowed, corners)
        for first, second in zip(*np.nonzero(np.isfinite(np.triu(matrix, k=1)))):
            graph.add_edge(int(first), int(second), weight=float(matrix[first, second]))
    return shape, allowed, corners, graph


def walk_corners(polygon: list[list[float]], first: Point2, last: Point2) -> list[Point2]:
    """Corners of the shortest walk from first to last inside the space (ends excluded). A door position is
    entered at its landing; with no clear walk the line goes straight."""
    shape, allowed, corners, corner_graph = _walkable(tuple(map(tuple, polygon)))
    ends = [first, last]
    landings = [door_landing(shape, point) for point in ends]
    matrix = visibility_matrix(allowed, landings + corners)
    graph = corner_graph.copy()
    graph = nx.relabel_nodes(graph, {node: node + 2 for node in graph}, copy=False)
    graph.add_nodes_from([0, 1])
    for end in (0, 1):
        for other in np.nonzero(np.isfinite(matrix[end]))[0]:
            if other != end:
                graph.add_edge(end, int(other), weight=float(matrix[end, other]))
    try:
        nodes = nx.shortest_path(graph, 0, 1, weight="weight")
    except nx.NetworkXNoPath:
        return []
    points = [landings[0], *(corners[node - 2] for node in nodes[1:-1]), landings[1]]
    return [point for point, end in zip(points, [first, *[None] * (len(points) - 2), last])
            if end is None or math.dist(point, end) > 1e-9]


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


def route_line(building_map: BuildingMap, space_path: list[str], element_path: list[str]) -> list[list[float]]:
    """[[x, y, floor_index], …] in building metres; points outside the building are skipped."""
    if not space_path:
        return []
    floor_index = floor_indices(building_map)
    nodes = route_nodes(building_map, space_path, element_path)

    def point(kind: str, node: str) -> tuple[str, tuple[float, float]]:
        if kind == "door":
            opening = building_map.openings[node]
            return opening["floor_id"], tuple(opening["position"])
        return building_map.spaces[node]["floor_id"], building_map.anchor(node)

    def is_door(index: int) -> bool:
        return 0 <= index < len(nodes) and nodes[index][0] == "door"

    def inside(space_id: str, first: tuple[float, float], last: tuple[float, float]) -> list[tuple[float, float]]:
        """Corners of the shortest walk from first to last inside the space (ends excluded)."""
        return walk_corners(building_map.spaces[space_id]["polygon"], first, last)

    walk: list[tuple[str, tuple[float, float]]] = []
    for index, (kind, node) in enumerate(nodes):
        if node == OUTSIDE:
            continue
        floor_id, here = point(kind, node)
        if kind == "door":
            walk.append((floor_id, here))
            continue
        before, after = is_door(index - 1), is_door(index + 1)
        if before and after:  # passed through: door to door, the anchor is skipped
            walk += [(floor_id, corner) for corner in inside(node, point(*nodes[index - 1])[1], point(*nodes[index + 1])[1])]
            continue
        if before:  # end of a walk inside this space: door → anchor
            walk += [(floor_id, corner) for corner in inside(node, point(*nodes[index - 1])[1], here)]
        walk.append((floor_id, here))
        if after:  # start of a walk inside this space: anchor → door
            walk += [(floor_id, corner) for corner in inside(node, here, point(*nodes[index + 1])[1])]

    points: list[list[float]] = []
    for floor_id, (x, y) in walk:
        item = [round(x, 3), round(y, 3), floor_index[floor_id]]
        if not points or points[-1] != item:
            points.append(item)
    return points
