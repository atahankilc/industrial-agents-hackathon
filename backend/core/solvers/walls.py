"""walls solvers — see docs/architecture/solver-plan.md#shared_walls_count.

Shared wall rule (Q-003, verified 143/143 on train+dev gold inputs): a neighbour on the same floor shares a wall
with room A when at least 1 m of A's outline lies within 0.35 m of the neighbour's polygon. Spaces with
`type` in {corridor, stair, lift, outdoor} are not counted (outdoor = balconies); halls do count.
Direction (A's outline vs B's), `>=` vs `>` and the exact tolerance (0.2–0.5 m) make no difference on the
labelled data — no labelled pair has a shared length near 1 m."""

from functools import cache

from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge, nearest_points

from backend.core.building_map import BuildingMap
from backend.core.solvers import SolverResult, solver

WALL_TOLERANCE_M = 0.35
MIN_SHARED_WALL_M = 1.0
# Space `type`s that never count as a wall neighbour ("corridors, stairwells and lifts don't count"; balconies,
# which are `type == "outdoor"`, are not rooms either — including them drops the score to 90/143).
NOT_COUNTED_TYPES = frozenset({"corridor", "stair", "lift", "outdoor"})


@cache
def _polygon(points: tuple[tuple[float, float], ...]) -> Polygon:
    return Polygon(points)


def space_polygon(building: BuildingMap, space_id: str) -> Polygon:
    return _polygon(tuple(tuple(point) for point in building.spaces[space_id]["polygon"]))


def _shared_outline(a: Polygon, b: Polygon, tolerance: float) -> list[LineString]:
    """Pieces of a's outline within `tolerance` of b, merged across the ring's start point."""
    shared = a.exterior.intersection(b.buffer(tolerance))
    lines: list[LineString] = []
    for part in getattr(shared, "geoms", [shared]):
        if isinstance(part, LineString) and part.length > 0:
            lines.append(part)
        elif isinstance(part, MultiLineString):
            lines += [line for line in part.geoms if line.length > 0]
    if len(lines) > 1:
        merged = linemerge(lines)
        lines = list(getattr(merged, "geoms", [merged]))
    return lines


def shared_wall_length(building: BuildingMap, a: str, b: str, tolerance: float = WALL_TOLERANCE_M) -> float:
    """Metres of a's outline within `tolerance` of b's polygon (0 if far apart or on different floors)."""
    if building.spaces[a]["floor_id"] != building.spaces[b]["floor_id"]:
        return 0.0
    first, second = space_polygon(building, a), space_polygon(building, b)
    if first.distance(second) > tolerance:
        return 0.0
    return sum(line.length for line in _shared_outline(first, second, tolerance))


def shared_wall_neighbours(
    building: BuildingMap, space_id: str, min_length: float = MIN_SHARED_WALL_M, tolerance: float = WALL_TOLERANCE_M
) -> list[dict]:
    """Every other space on the same floor sharing >= `min_length` m of wall with `space_id`, longest first.

    No type filter here (corridors, lifts, balconies included) — callers filter on `counted` / `type`."""
    floor_id = building.spaces[space_id]["floor_id"]
    neighbours = []
    for other in building.spaces.values():
        if other["id"] == space_id or other["floor_id"] != floor_id:
            continue
        length = shared_wall_length(building, space_id, other["id"], tolerance)
        if length >= min_length:
            neighbours.append(
                {
                    "id": other["id"],
                    "name": other["name"],
                    "type": other["type"],
                    "room_type": other["room_type"],
                    "shared_m": round(length, 2),
                    "counted": other["type"] not in NOT_COUNTED_TYPES,
                }
            )
    return sorted(neighbours, key=lambda item: (-item["shared_m"], item["id"]))


def shared_wall_segment(building: BuildingMap, a: str, b: str, tolerance: float = WALL_TOLERANCE_M) -> dict | None:
    """Geometry of the wall a and b share, or None if they share none.

    `midpoint` is the middle of the longest contiguous shared stretch of a's outline, moved half way across the
    wall gap towards b's outline — the place for a "door in the middle of the wall they share" (what_if_door).
    `segments` are all stretches of a's outline near b, as coordinate lists."""
    if building.spaces[a]["floor_id"] != building.spaces[b]["floor_id"]:
        return None
    first, second = space_polygon(building, a), space_polygon(building, b)
    if first.distance(second) > tolerance:
        return None
    lines = _shared_outline(first, second, tolerance)
    if not lines:
        return None
    longest = max(lines, key=lambda line: line.length)
    on_a = longest.interpolate(0.5, normalized=True)
    _, on_b = nearest_points(on_a, second.exterior)
    middle = Point((on_a.x + on_b.x) / 2, (on_a.y + on_b.y) / 2)
    return {
        "length_m": sum(line.length for line in lines),
        "longest_m": longest.length,
        "midpoint": [middle.x, middle.y],
        "midpoint_on_a": [on_a.x, on_a.y],
        "segments": [[list(point) for point in line.coords] for line in lines],
    }


@solver("shared_walls_count")
def shared_walls_count(building: BuildingMap, start: str, **_) -> SolverResult:
    space = building.spaces[start]
    neighbours = [item for item in shared_wall_neighbours(building, start) if item["counted"]]
    count = len(neighbours)
    listed = ", ".join(f"{item['name']} ({item['shared_m']:.1f} m)" for item in neighbours[:8])
    more = f", +{count - 8} more" if count > 8 else ""
    explanation = [
        f"{space['name']} ({building.floor_name(space['floor_id'])}) shares at least {MIN_SHARED_WALL_M:.0f} m of "
        f"wall with {count} other room{'s' if count != 1 else ''}; corridors, stairwells, lifts and balconies "
        "are not counted.",
    ]
    if listed:
        explanation.append(f"Neighbours: {listed}{more}.")
    return SolverResult(
        kind="shared_walls_count",
        value=count,
        unit="rooms",
        explanation=explanation,
        evidence={
            "space_id": start,
            "neighbours": [{"id": item["id"], "shared_m": item["shared_m"]} for item in neighbours],
        },
    )
