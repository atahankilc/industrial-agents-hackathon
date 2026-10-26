"""geometry solvers — see docs/architecture/solver-plan.md.

Pure polygon geometry on building.json (no route graph): summed / largest room area on a floor, 3D distance
between room centroids, and the room directly above / below another one."""

import math

from shapely.geometry import Polygon

from backend.core.building_map import BuildingMap, MapError
from backend.core.solvers import SolverResult, solver


def polygon(space: dict) -> Polygon:
    shape = Polygon(space["polygon"])
    return shape if shape.is_valid else shape.buffer(0)


def floor_spaces(building: BuildingMap, floor_id: str, room_type: str) -> list[dict]:
    if floor_id not in building.floors:
        raise MapError(f"Unknown floor '{floor_id}'")
    return [
        space
        for space in building.spaces.values()
        if space["floor_id"] == floor_id and space["room_type"] == room_type
    ]


def space(building: BuildingMap, space_id: str) -> dict:
    if space_id not in building.spaces:
        raise MapError(f"Unknown space '{space_id}'")
    return building.spaces[space_id]


def type_label(room_type: str) -> str:
    return room_type.replace("_", " ")


@solver("floor_area_total")
def floor_area_total(building: BuildingMap, floor_id: str, room_type: str, **_) -> SolverResult:
    """Sum of polygon areas of every space of `room_type` on `floor_id`."""
    rooms = floor_spaces(building, floor_id, room_type)
    areas = {room["id"]: round(polygon(room).area, 2) for room in rooms}
    total = round(sum(polygon(room).area for room in rooms), 2)
    return SolverResult(
        kind="floor_area_total",
        value=total,
        unit="m²",
        explanation=[
            f"Added up the floor-plan areas of all {len(rooms)} {type_label(room_type)} spaces on "
            f"{building.floor_name(floor_id)}."
        ],
        evidence={"floor_id": floor_id, "room_type": room_type, "space_ids": list(areas), "areas_m2": areas},
    )


@solver("largest_room")
def largest_room(building: BuildingMap, floor_id: str, room_type: str, **_) -> SolverResult:
    """The space of `room_type` on `floor_id` with the largest polygon area."""
    rooms = floor_spaces(building, floor_id, room_type)
    if not rooms:
        raise MapError(f"No {type_label(room_type)} spaces on {building.floor_name(floor_id)}")
    areas = {room["id"]: polygon(room).area for room in rooms}
    ranked = sorted(areas, key=areas.get, reverse=True)
    winner = ranked[0]
    return SolverResult(
        kind="largest_room",
        value=winner,
        area_m2=round(areas[winner], 2),
        explanation=[
            f"Compared the floor-plan areas of all {len(rooms)} {type_label(room_type)} spaces on "
            f"{building.floor_name(floor_id)}; the largest is {building.spaces[winner]['name']}."
        ],
        evidence={
            "floor_id": floor_id,
            "room_type": room_type,
            "space_id": winner,
            "ranking": [{"space_id": space_id, "area_m2": round(areas[space_id], 2)} for space_id in ranked],
        },
    )


def centre_3d(building: BuildingMap, space_id: str) -> tuple[float, float, float]:
    room = space(building, space_id)
    centroid = polygon(room).centroid
    return centroid.x, centroid.y, float(building.floors[room["floor_id"]]["elevation_m"])


@solver("straight_line_3d")
def straight_line_3d(building: BuildingMap, first: str, second: str, **_) -> SolverResult:
    """Euclidean distance between the two rooms' polygon centroids, each at its floor's elevation_m."""
    first_id, second_id = building.resolve_space(first), building.resolve_space(second)
    a, b = centre_3d(building, first_id), centre_3d(building, second_id)
    distance = math.dist(a, b)
    horizontal = math.dist(a[:2], b[:2])
    return SolverResult(
        kind="straight_line_3d",
        value=round(distance, 2),
        unit="m",
        explanation=[
            f"Straight line between the floor-plan centroids of {building.spaces[first_id]['name']} and "
            f"{building.spaces[second_id]['name']}, each at its floor's elevation."
        ],
        evidence={
            "first": first_id,
            "second": second_id,
            "first_centre": [round(value, 3) for value in a],
            "second_centre": [round(value, 3) for value in b],
            "horizontal_m": round(horizontal, 2),
            "vertical_m": round(abs(a[2] - b[2]), 2),
        },
    )


def adjacent_floor(building: BuildingMap, floor_id: str, direction: str) -> str | None:
    level = building.floors[floor_id]["level"]
    if direction == "above":
        candidates = [floor for floor in building.floors.values() if floor["level"] > level]
        return min(candidates, key=lambda floor: floor["level"])["id"] if candidates else None
    if direction == "below":
        candidates = [floor for floor in building.floors.values() if floor["level"] < level]
        return max(candidates, key=lambda floor: floor["level"])["id"] if candidates else None
    raise MapError(f"Direction must be 'above' or 'below', not '{direction}'")


@solver("room_stacked")
def room_stacked(building: BuildingMap, start: str, direction: str, **_) -> SolverResult:
    """The space on the next floor up/down whose outline covers most of this room's outline.

    Every space on that floor is a candidate (any `type`); the winner has the largest intersection area."""
    start_id = building.resolve_space(start)
    room = building.spaces[start_id]
    target_floor = adjacent_floor(building, room["floor_id"], direction)
    if target_floor is None:
        raise MapError(f"There is no floor {direction} {building.floor_name(room['floor_id'])}")
    shape = polygon(room)
    overlaps = {}
    for other in building.spaces.values():
        if other["floor_id"] == target_floor:
            area = shape.intersection(polygon(other)).area
            if area > 0:
                overlaps[other["id"]] = area
    if not overlaps:
        raise MapError(f"No space on {building.floor_name(target_floor)} overlaps {room['name']}")
    ranked = sorted(overlaps, key=overlaps.get, reverse=True)
    winner = ranked[0]
    return SolverResult(
        kind="room_stacked",
        value=winner,
        explanation=[
            f"Overlaid {room['name']} on the plan of {building.floor_name(target_floor)}; "
            f"{building.spaces[winner]['name']} covers the largest share of its outline."
        ],
        evidence={
            "start": start_id,
            "direction": direction,
            "floor_id": target_floor,
            "space_id": winner,
            "overlaps": [
                {"space_id": space_id, "overlap_ratio": round(overlaps[space_id] / shape.area, 3)}
                for space_id in ranked[:5]
            ],
        },
    )
