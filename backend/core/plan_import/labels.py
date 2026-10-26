"""Stage 4 — apply what the model read off the plan to a floor's cells: keep / outside / merge, type, room type,
name, ref; which neighbours have a door; which cells have an entrance. Code checks every answer (closed type lists,
adjacency) and returns problems for the model to fix. Calls add up: later labels override earlier ones."""

import cv2
import numpy as np
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import unary_union

from backend.core.plan_import.ingest import png
from backend.core.plan_import.model import CellLabel, DoorCandidate, FloorPlan

TYPES = {"room", "corridor", "stair", "lift", "hall", "outdoor"}
# docs/kit/data-format.md#room-types
ROOM_TYPES = {
    "bedroom", "living_room", "kitchen", "bathroom", "toilet", "storage", "corridor", "balcony", "stairwell", "lift",
    "office", "meeting_room", "seminar_room", "lecture_hall", "lab", "makerspace", "library", "server_room",
    "technical_room", "lobby", "canteen", "shop", "print_room", "locker_room", "production_zone", "additive_zone",
    "assembly_zone", "warehouse_zone", "logistics_zone", "quality_lab", "generic_room",
}


def kept(floor: FloorPlan) -> list[int]:
    return sorted(cell_id for cell_id, cell in floor.seg.cells.items() if not cell.outside)


def rekey(pair: tuple, mapping: dict[int, int | str]) -> tuple | None:
    """A door's cell pair after merges / cells marked outside; None if it now joins a cell to itself or two outsides."""
    ends = [mapping.get(end, end) if end != "outside" else "outside" for end in pair]
    if ends[0] == ends[1]:
        return None
    if "outside" in ends:
        inner = [end for end in ends if end != "outside"]
        return (inner[0], "outside")
    return tuple(sorted(ends))


def merge(floor: FloorPlan, cell_id: int, into: int) -> str | None:
    cells = floor.seg.cells
    if cell_id not in cells or into not in cells or cell_id == into:
        return f"cannot merge cell {cell_id} into {into}"
    if cells[cell_id].outside or cells[into].outside:
        return f"cannot merge cell {cell_id} into {into}: one of them is outside"
    if (min(cell_id, into), max(cell_id, into)) not in floor.seg.adjacency:
        return f"cannot merge cell {cell_id} into {into}: they do not touch (merge only neighbours)"
    union = unary_union([Polygon(cells[into].polygon).buffer(0.5), Polygon(cells[cell_id].polygon).buffer(0.5)])
    union = union.buffer(-0.5)
    if union.geom_type != "Polygon":
        union = max(union.geoms, key=lambda part: part.area)
    target = cells[into]
    target.polygon = [(float(x), float(y)) for x, y in list(union.exterior.coords)[:-1]]
    target.area_px += cells[cell_id].area_px
    del cells[cell_id]
    floor.labels.pop(cell_id, None)
    remap({cell_id: into}, floor)
    return None


def remap(mapping: dict[int, int | str], floor: FloorPlan) -> None:
    adjacency = {}
    for pair, points in floor.seg.adjacency.items():
        new = rekey(pair, mapping)
        if new is not None and "outside" not in new:
            adjacency.setdefault(new, []).extend(points)
    floor.seg.adjacency = adjacency
    for door in floor.seg.doors + floor.doors:
        new = rekey(door.cells, mapping)
        door.cells = new if new is not None else ("dropped", "dropped")
    floor.seg.doors = [door for door in floor.seg.doors if door.cells[0] != "dropped"]
    floor.doors = [door for door in floor.doors if door.cells[0] != "dropped"]


def boundary_door(floor: FloorPlan, a: int, b: int) -> DoorCandidate | None:
    points = floor.seg.adjacency.get((min(a, b), max(a, b)))
    if not points:
        return None
    centre = np.mean(points, axis=0)
    nearest = min(points, key=lambda point: (point[0] - centre[0]) ** 2 + (point[1] - centre[1]) ** 2)
    return DoorCandidate((min(a, b), max(a, b)), (float(nearest[0]), float(nearest[1])), 0.0)


def entrance_door(floor: FloorPlan, cell_id: int) -> DoorCandidate | None:
    """Midpoint of the longest stretch of the cell's outline that no other kept cell touches."""
    shape = Polygon(floor.seg.cells[cell_id].polygon)
    others = [Polygon(floor.seg.cells[other].polygon) for other in kept(floor) if other != cell_id]
    free = shape.exterior
    if others:
        free = free.difference(unary_union(others).buffer(4))
    parts = list(free.geoms) if isinstance(free, MultiLineString) else [free] if isinstance(free, LineString) else []
    parts = [part for part in parts if part.length > 0]
    if not parts:
        return None
    longest = max(parts, key=lambda part: part.length)
    middle = longest.interpolate(0.5, normalized=True)
    return DoorCandidate((cell_id, "outside"), (float(middle.x), float(middle.y)), 0.0)


def apply_labels(floor: FloorPlan, cells: list[dict], doors: list | None, entrances: list[int] | None) -> list[str]:
    problems: list[str] = []

    for item in cells:
        cell_id, action = item.get("cell"), item.get("action", "room")
        if action == "merge":
            problem = merge(floor, cell_id, item.get("into"))
            if problem:
                problems.append(problem)
    for item in cells:
        cell_id, action = item.get("cell"), item.get("action", "room")
        if action == "merge":
            continue
        if cell_id not in floor.seg.cells:
            problems.append(f"cell {cell_id} does not exist (merged away or never there)")
            continue
        if action == "outside":
            floor.seg.cells[cell_id].outside = True
            floor.labels.pop(cell_id, None)
            remap({cell_id: "outside"}, floor)
            continue
        kind, room_type, name = item.get("type"), item.get("room_type"), str(item.get("name") or "").strip()
        if kind not in TYPES:
            problems.append(f"cell {cell_id}: unknown type {kind!r} (use one of {', '.join(sorted(TYPES))})")
            continue
        if room_type not in ROOM_TYPES:
            problems.append(f"cell {cell_id}: unknown room_type {room_type!r} (use one of the dataset's room types, "
                            "generic_room if none fits)")
            continue
        if not name:
            problems.append(f"cell {cell_id}: a name is needed")
            continue
        floor.labels[cell_id] = CellLabel(kind, room_type, name, str(item.get("ref") or ""))

    # doors between cells
    if doors is not None:
        chosen: list[DoorCandidate] = []
        for entry in doors:
            if isinstance(entry, str) and entry.startswith("d") and entry[1:].isdigit():
                found = [door for door in floor.seg.doors if door.number == int(entry[1:])]
                if not found:
                    problems.append(f"door {entry} does not exist (any more: it joined two cells you merged)")
                elif "outside" not in found[0].cells:
                    chosen.append(found[0])
                continue
            try:
                a, b = int(entry[0]), int(entry[1])
            except (TypeError, ValueError, IndexError):
                problems.append(f"door {entry!r}: give a door as \"d<n>\" or [cell, cell]")
                continue
            pair = (min(a, b), max(a, b))
            matching = [door for door in floor.seg.doors if door.cells == pair]
            if matching:
                chosen.extend(matching)
            elif (door := boundary_door(floor, a, b)) is not None:
                chosen.append(door)
            else:
                problems.append(f"cells {a} and {b} are not adjacent")
        inner = chosen
    elif floor.doors:
        inner = [door for door in floor.doors if "outside" not in door.cells]
    else:
        inner = [door for door in floor.seg.doors if "outside" not in door.cells]

    # entrances
    if entrances is None:
        outer = [door for door in (floor.doors or floor.seg.doors) if "outside" in door.cells]
    else:
        outer = []
        for cell_id in entrances:
            if cell_id not in floor.seg.cells or floor.seg.cells[cell_id].outside:
                problems.append(f"entrance cell {cell_id} does not exist")
                continue
            matching = [door for door in floor.seg.doors if door.cells == (cell_id, "outside")]
            if matching:
                outer.extend(matching)
            elif (door := entrance_door(floor, cell_id)) is not None:
                outer.append(door)
            else:
                problems.append(f"cell {cell_id} has no outside wall for an entrance")

    live = set(kept(floor))
    floor.doors = [door for door in inner + outer
                   if all(end == "outside" or end in live for end in door.cells)]
    for cell_id in kept(floor):
        if cell_id not in floor.labels:
            problems.append(f"cell {cell_id} has no label (label it, merge it or mark it outside)")
    if floor.level == 0 and not any("outside" in door.cells for door in floor.doors):
        problems.append("no entrance on this floor")
    return problems


TYPE_COLOURS = {"room": (180, 220, 250), "corridor": (200, 200, 200), "stair": (120, 170, 255), "lift": (255, 170, 120),
                "hall": (210, 190, 250), "outdoor": (170, 230, 170)}


def render_labels(floor: FloorPlan) -> bytes:
    """Rooms tinted by type with "<cell> <name>", doors as green dots, entrances as blue dots, unlabelled cells red."""
    view = floor.image.copy()
    overlay = view.copy()
    for cell_id in kept(floor):
        cell = floor.seg.cells[cell_id]
        label = floor.labels.get(cell_id)
        colour = TYPE_COLOURS.get(label.type, (200, 200, 200)) if label else (60, 60, 230)
        cv2.fillPoly(overlay, [np.int32(cell.polygon)], colour)
    view = cv2.addWeighted(overlay, 0.5, view, 0.5, 0)
    scale = max(0.35, max(view.shape[:2]) / 2000)
    for cell_id in kept(floor):
        cell = floor.seg.cells[cell_id]
        cv2.polylines(view, [np.int32(cell.polygon)], True, (50, 50, 50), 1)
        label = floor.labels.get(cell_id)
        text = f"{cell_id} {label.name}"[:28] if label else f"{cell_id} ?"
        point = Polygon(cell.polygon).representative_point()
        at = (int(point.x) - 10, int(point.y) + 4)
        cv2.putText(view, text, at, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 3)
        cv2.putText(view, text, at, cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20), 1)
    for door in floor.doors:
        colour = (230, 120, 0) if "outside" in door.cells else (0, 170, 0)
        cv2.circle(view, (int(door.position[0]), int(door.position[1])), max(3, int(4 * scale)), colour, -1)
    return png(view)

