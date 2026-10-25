"""Stage 6 — labelled, scaled, stacked floors → a `building.json` in the dataset's schema (docs/kit/data-format.md),
then mechanical fixes (slivers dropped, small overlaps trimmed, doors snapped onto the wall the two spaces share) and
the Edit mode's validator. Floor names follow the dataset ("Ground floor", "Floor 1", "Basement 1"); the name read on
the plan is kept in `source_ref.import.floors`."""

import copy

from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points

from core.edits import EditError, wall_target
from core.plan_import.labels import kept
from core.plan_import.model import FloorPlan
from core.plan_import.stack import align, connectors, to_frame
from core.plan_import.scale import ensure_scales
from core.validate import validate

STOREY_M = 3.0
DOOR_M = 0.9
DOOR_WIDTH_M = (0.6, 3.0)  # measured gaps outside this are not doors' widths
SLIVER_M2 = 0.5
TRIM_M2 = 0.5


def floor_name(level: int) -> str:
    if level == 0:
        return "Ground floor"
    return f"Floor {level}" if level > 0 else f"Basement {-level}"


def clean_polygon(points: list) -> list[list[float]]:
    shape = Polygon(points)
    if not shape.is_valid:
        shape = shape.buffer(0)
        if shape.geom_type != "Polygon":
            shape = max(shape.geoms, key=lambda part: part.area)
    shape = orient(shape)
    return [[round(x, 2), round(y, 2)] for x, y in list(shape.exterior.coords)[:-1]]


def assemble(building_id: str, name: str, floors: list[FloorPlan], origins: list[str]) -> dict:
    if any(floor.m_per_px is None for floor in floors):
        ensure_scales(floors)
    if any(floor.transform is None for floor in floors):
        align(floors)
    ordered = sorted(floors, key=lambda floor: floor.level)
    building = {
        "building": {"id": building_id, "name": name, "source": "imported",
                     "source_ref": {"import": {"files": list(origins), "floors": {}}},
                     "license": "user-provided", "attribution": "", "split": "user", "units": "m"},
        "floors": [], "spaces": [], "openings": [], "vertical_connectors": [], "assets": [],
    }
    space_ids: dict[tuple[int, int], str] = {}
    for floor in ordered:
        floor_id = f"{building_id}-F{floor.level}"
        building["floors"].append({"id": floor_id, "level": floor.level, "name": floor_name(floor.level),
                                   "elevation_m": STOREY_M * floor.level, "height_m": STOREY_M})
        building["building"]["source_ref"]["import"]["floors"][str(floor.level)] = {
            "name_on_plan": floor.name, "source": floor.source_id, "scale_method": floor.scale_method,
            "m_per_px": round(floor.m_per_px, 5), "segmentation": floor.seg.method,
            "low_confidence": floor.low_confidence, "carved_rooms": len(floor.carved),
            "alignment": floor.alignment,
        }
        number = 0
        for cell_id in kept(floor):
            label = floor.labels.get(cell_id)
            if label is None:
                continue
            number += 1
            space_id = f"{floor_id}-S{number:03d}"
            space_ids[(floor.level, cell_id)] = space_id
            polygon = [to_frame(floor, point).tolist() for point in floor.seg.cells[cell_id].polygon]
            building["spaces"].append({"id": space_id, "floor_id": floor_id, "type": label.type,
                                       "room_type": label.room_type, "name": label.name, "ref": label.ref,
                                       "polygon": clean_polygon(polygon), "synthetic": False})
        number = 0
        for door in floor.doors:
            ends = [space_ids.get((floor.level, end)) if end != "outside" else "outside" for end in door.cells]
            if None in ends:
                continue
            number += 1
            width = door.width_px * floor.m_per_px if door.width_px > 0 else DOOR_M
            if not DOOR_WIDTH_M[0] <= width <= DOOR_WIDTH_M[1]:
                width = DOOR_M
            position = to_frame(floor, door.position)
            building["openings"].append({"id": f"{floor_id}-O{number:04d}", "floor_id": floor_id, "space_ids": ends,
                                         "kind": "entrance" if "outside" in ends else "door",
                                         "position": [round(float(position[0]), 2), round(float(position[1]), 2)],
                                         "width_m": round(width, 2), "step_free": True, "synthetic": False})
    for number, (kind, stops, guessed) in enumerate(connectors(ordered), start=1):
        first = next(floor for floor in ordered if floor.level == stops[0][0])
        building["vertical_connectors"].append({
            "id": f"{building_id}-V{number:02d}", "kind": kind,
            "name": first.labels[stops[0][1]].name or ("Stairs" if kind == "stairs" else "Lift"),
            "floor_ids": [f"{building_id}-F{level}" for level, _ in stops],
            "space_ids": [space_ids[(level, cell_id)] for level, cell_id in stops],
            "step_free": kind == "lift", "synthetic": guessed})  # guessed = joined only so floors connect
    return building


def autofix(building: dict) -> dict:
    building = copy.deepcopy(building)
    for space in building["spaces"]:  # self-intersections (from rounding or merges) break every later geometry step
        if not Polygon(space["polygon"]).is_valid:
            space["polygon"] = clean_polygon(space["polygon"])
    slivers = {space["id"] for space in building["spaces"] if Polygon(space["polygon"]).area < SLIVER_M2}
    building["spaces"] = [space for space in building["spaces"] if space["id"] not in slivers]
    building["openings"] = [opening for opening in building["openings"] if not slivers & set(opening["space_ids"])]
    connectors_kept = []
    for connector in building["vertical_connectors"]:
        stops = [(f, s) for f, s in zip(connector["floor_ids"], connector["space_ids"]) if s not in slivers]
        if len(stops) >= 2:
            connector["floor_ids"], connector["space_ids"] = [f for f, _ in stops], [s for _, s in stops]
            connectors_kept.append(connector)
    building["vertical_connectors"] = connectors_kept

    by_floor: dict[str, list[dict]] = {}
    for space in building["spaces"]:
        by_floor.setdefault(space["floor_id"], []).append(space)
    for spaces in by_floor.values():
        for index, first in enumerate(spaces):
            for second in spaces[index + 1:]:
                a, b = Polygon(first["polygon"]), Polygon(second["polygon"])
                if not a.intersects(b):
                    continue
                overlap = a.intersection(b).area
                if 0 < overlap <= TRIM_M2:
                    small, large = (first, b) if a.area <= b.area else (second, a)
                    trimmed = Polygon(small["polygon"]).difference(large)
                    if not trimmed.is_empty:
                        if trimmed.geom_type != "Polygon":
                            trimmed = max(trimmed.geoms, key=lambda part: part.area)
                        small["polygon"] = clean_polygon(list(trimmed.exterior.coords)[:-1])

    for opening in building["openings"]:
        try:
            target = wall_target(building, opening["space_ids"])
        except EditError:
            continue
        if target is not None:
            point = nearest_points(target, Point(opening["position"]))[0]
            opening["position"] = [round(point.x, 2), round(point.y, 2)]
    return building


def check(building: dict) -> list[dict]:
    return validate(building)
