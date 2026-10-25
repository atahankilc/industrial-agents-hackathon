"""Edit operations on a building dict — the core of the Builder's Edit mode.

Design: docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §1. A draft is a base building plus an
ordered list of steps, each step a list of ops; `apply_steps` replays them, so undo = drop the last step and
replay. An op is a small JSON dict `{"op": <name>, ...arguments}`. Every op works on a deep copy and returns it;
the input is never mutated. Unknown ids, unknown ops and impossible geometry raise `EditError` (its message is
meant for the user and the Builder agent).

New ids: spaces `<floor_id>-S-new<n>`, openings `<floor_id>-O-new<n>`, assets `<building_id>-A-new<n>`, n = 1 +
the highest n already used with that prefix. Coordinates written by ops are rounded to 3 decimals. Openings are
always snapped onto the wall their two spaces share (the outer wall for entrances)."""

import copy
import math
import re
from collections.abc import Callable

from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points, unary_union

from core.building_map import OUTSIDE
from core.solvers.walls import WALL_TOLERANCE_M


VERTEX_MATCH_M = 0.01  # vertices this close to the dragged one move with it (shared corners)
MIN_OVERLAP_M2 = 0.01  # neighbour overlaps below this are rounding noise, not fitted
MIN_NEIGHBOUR_M2 = 0.5  # a fitted neighbour smaller than this would effectively be removed
MAX_WALL_GAP_M = 2.5  # thickest wall between the two spaces of a door (Swiss Dwellings: up to ~2 m)
ON_WALL_M = 0.05  # an opening farther than this from its wall after a change is re-projected


class EditError(ValueError):
    """An op that cannot be applied; nothing was changed."""


Op = Callable[..., None]
OPS: dict[str, Op] = {}


def op(name: str) -> Callable[[Op], Op]:
    def register(function: Op) -> Op:
        OPS[name] = function
        return function
    return register


def apply_op(building: dict, operation: dict) -> dict:
    """A new building dict with `operation` applied; `building` is untouched."""
    arguments = dict(operation)
    name = arguments.pop("op", None)
    if name not in OPS:
        raise EditError(f"unknown op {name!r}; known: {', '.join(sorted(OPS))}")
    changed = copy.deepcopy(building)
    try:
        OPS[name](changed, **arguments)
    except EditError:
        raise
    except (TypeError, ValueError, IndexError, KeyError) as error:  # wrong / missing / malformed arguments
        raise EditError(f"{name}: bad arguments ({type(error).__name__}: {error})") from None
    return changed


def apply_steps(base: dict, steps: list[list[dict]]) -> dict:
    building = base
    for step in steps:
        for operation in step:
            building = apply_op(building, operation)
    return copy.deepcopy(base) if building is base else building


# ---------- helpers ----------


def text(value: object, field: str) -> str:
    """A name / ref / type field as a string: numbers become strings (models send refs like 0.21 as numbers),
    anything else is refused — a dict or None in a name breaks search and the plan labels."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise EditError(f"{field} must be text, not {type(value).__name__}")


def rounded(xy: list[float]) -> list[float]:
    return [round(float(xy[0]), 3), round(float(xy[1]), 3)]


def find(building: dict, key: str, element_id: str) -> dict:
    for item in building[key]:
        if item["id"] == element_id:
            return item
    raise EditError(f"no {key[:-1].replace('_', ' ')} with id {element_id!r}")


def floor_of(building: dict, floor_id: str) -> dict:
    return find(building, "floors", floor_id)


def new_id(building: dict, key: str, prefix: str) -> str:
    pattern = re.compile(re.escape(prefix) + r"(\d+)$")
    used = [int(match.group(1)) for item in building[key] if (match := pattern.match(item["id"]))]
    return f"{prefix}{max(used, default=0) + 1}"


def polygon_of(space: dict) -> Polygon:
    return Polygon(space["polygon"])


def space_at(building: dict, floor_id: str, xy: list[float]) -> str | None:
    """The first space on the floor whose polygon contains the point."""
    point = Point(xy)
    for space in building["spaces"]:
        if space["floor_id"] == floor_id and polygon_of(space).contains(point):
            return space["id"]
    return None


def wall_target(building: dict, space_ids: list[str]):
    """The line an opening between `space_ids` must sit on (None if the spaces share no wall)."""
    inside = [space_id for space_id in space_ids if space_id != OUTSIDE]
    spaces = [find(building, "spaces", space_id) for space_id in inside]
    if len(space_ids) != 2 or not spaces:
        raise EditError("an opening joins exactly two spaces (or one space and 'outside')")
    if len(spaces) == 1:
        return polygon_of(spaces[0]).exterior
    first, second = spaces
    if first["floor_id"] != second["floor_id"]:
        raise EditError("an opening can only join two spaces on the same floor")
    near, far = polygon_of(first), polygon_of(second)
    gap = near.distance(far)  # wall thickness: 0 for procedural/OSM, up to ~2 m in Swiss Dwellings
    if gap > MAX_WALL_GAP_M:
        return None
    shared = near.exterior.intersection(far.buffer(WALL_TOLERANCE_M + gap))
    return None if shared.is_empty or shared.length == 0 else shared


def snapped(building: dict, space_ids: list[str], xy: list[float]) -> list[float]:
    target = wall_target(building, space_ids)
    if target is None:
        names = " and ".join(find(building, "spaces", space_id)["name"] for space_id in space_ids)
        raise EditError(f"{names} share no wall, so no opening can join them")
    point = nearest_points(target, Point(xy))[0]
    return rounded([point.x, point.y])


# ---------- spaces ----------


@op("add_space")
def add_space(building: dict, floor_id: str, polygon: list[list[float]], type: str, room_type: str, name: str,
              ref: str | None = None) -> None:
    floor_of(building, floor_id)
    outline = [rounded(point) for point in polygon]
    if len(outline) < 3 or not Polygon(outline).is_valid or Polygon(outline).area <= 0:
        raise EditError("a space needs a valid outline with at least three corners")
    building["spaces"].append({
        "id": new_id(building, "spaces", f"{floor_id}-S-new"), "floor_id": floor_id, "type": text(type, "type"),
        "room_type": text(room_type, "room_type"), "name": text(name, "name"),
        "ref": None if ref is None else text(ref, "ref"), "polygon": outline, "synthetic": False,
    })


@op("delete_space")
def delete_space(building: dict, space_id: str) -> None:
    find(building, "spaces", space_id)
    for connector in building["vertical_connectors"]:
        if space_id in connector["space_ids"]:
            raise EditError(f"{space_id} is a stop of {connector['name']}; stairs and lifts can't be edited yet")
    building["spaces"] = [space for space in building["spaces"] if space["id"] != space_id]
    building["openings"] = [item for item in building["openings"] if space_id not in item["space_ids"]]
    building["assets"] = [asset for asset in building["assets"] if asset["space_id"] != space_id]


@op("set_space")
def set_space(building: dict, space_id: str, name: str | None = None, ref: str | None = None,
              type: str | None = None, room_type: str | None = None) -> None:
    space = find(building, "spaces", space_id)
    for key, value in (("name", name), ("ref", ref), ("type", type), ("room_type", room_type)):
        if value is not None:
            space[key] = text(value, key)


# ---------- openings ----------


@op("add_opening")
def add_opening(building: dict, space_ids: list[str], position: list[float], kind: str = "door",
                width_m: float = 0.9, step_free: bool = True) -> None:
    if kind not in ("door", "opening", "entrance"):
        raise EditError("kind must be door, opening or entrance")
    inside = [space_id for space_id in space_ids if space_id != OUTSIDE]
    xy = snapped(building, space_ids, position)
    floor_id = find(building, "spaces", inside[0])["floor_id"]
    building["openings"].append({
        "id": new_id(building, "openings", f"{floor_id}-O-new"), "floor_id": floor_id, "space_ids": list(space_ids),
        "kind": "entrance" if OUTSIDE in space_ids else kind, "position": xy, "width_m": float(width_m),
        "step_free": bool(step_free), "synthetic": False,
    })


@op("move_opening")
def move_opening(building: dict, opening_id: str, position: list[float]) -> None:
    opening = find(building, "openings", opening_id)
    opening["position"] = snapped(building, opening["space_ids"], position)


@op("set_opening")
def set_opening(building: dict, opening_id: str, width_m: float | None = None, step_free: bool | None = None,
                kind: str | None = None) -> None:
    opening = find(building, "openings", opening_id)
    if width_m is not None:
        if width_m <= 0:
            raise EditError("width_m must be positive")
        opening["width_m"] = float(width_m)
    if step_free is not None:
        opening["step_free"] = bool(step_free)
    if kind is not None:
        if kind not in ("door", "opening", "entrance"):
            raise EditError("kind must be door, opening or entrance")
        opening["kind"] = kind


@op("delete_opening")
def delete_opening(building: dict, opening_id: str) -> None:
    find(building, "openings", opening_id)
    building["openings"] = [item for item in building["openings"] if item["id"] != opening_id]


# ---------- assets ----------


@op("add_asset")
def add_asset(building: dict, space_id: str, name: str, category: str, type: str, position: list[float],
              footprint: dict | None = None) -> None:
    space = find(building, "spaces", space_id)
    footprint = footprint or {"width_m": 1.0, "depth_m": 1.0, "rotation_deg": 0.0}
    building["assets"].append({
        "id": new_id(building, "assets", f"{building['building']['id']}-A-new"), "name": text(name, "name"),
        "category": text(category, "category"), "type": text(type, "type"), "space_id": space_id,
        "floor_id": space["floor_id"],
        "position": rounded(position),
        "footprint": {"width_m": float(footprint["width_m"]), "depth_m": float(footprint["depth_m"]),
                      "rotation_deg": float(footprint.get("rotation_deg", 0.0))},
        "source": "edited",
    })


@op("move_asset")
def move_asset(building: dict, asset_id: str, position: list[float], rotation_deg: float | None = None,
               space_id: str | None = None) -> None:
    asset = find(building, "assets", asset_id)
    asset["position"] = rounded(position)
    if space_id is not None:
        asset["space_id"] = find(building, "spaces", space_id)["id"]
    else:
        asset["space_id"] = space_at(building, asset["floor_id"], asset["position"]) or asset["space_id"]
    if rotation_deg is not None:
        asset["footprint"]["rotation_deg"] = float(rotation_deg) % 360


@op("set_asset")
def set_asset(building: dict, asset_id: str, name: str | None = None, type: str | None = None,
              category: str | None = None, footprint: dict | None = None) -> None:
    asset = find(building, "assets", asset_id)
    for key, value in (("name", name), ("type", type), ("category", category)):
        if value is not None:
            asset[key] = text(value, key)
    if footprint is not None:
        asset["footprint"].update({key: float(value) for key, value in footprint.items()})


@op("delete_asset")
def delete_asset(building: dict, asset_id: str) -> None:
    find(building, "assets", asset_id)
    building["assets"] = [asset for asset in building["assets"] if asset["id"] != asset_id]


# ---------- geometry: outlines and shared walls ----------


def outline(geometry: Polygon) -> list[list[float]]:
    return [rounded(point) for point in list(geometry.exterior.coords)[:-1]]


def checked_outline(points: list[list[float]], what: str) -> list[list[float]]:
    result = [rounded(point) for point in points]
    shape = Polygon(result)
    if len(result) < 3 or not shape.is_valid or shape.area <= 0:
        raise EditError(f"{what}: the outline must be a simple polygon with at least three corners")
    return result


def on_wall(building: dict, opening: dict) -> bool:
    target = wall_target(building, opening["space_ids"])
    return target is not None and target.distance(Point(opening["position"])) <= ON_WALL_M


def settle(before: dict, building: dict, floor_id: str, changed: set[str]) -> None:
    """After outlines in `changed` moved: neighbours take the area the changed rooms gave up and lose the area they
    took, so shared walls stay shared whichever way a wall moves; then displaced openings go back on a wall."""
    fitted: set[str] = set()  # neighbours grown / trimmed here; still fitted against every other changed outline
    old = unary_union([polygon_of(find(before, "spaces", space_id)) for space_id in changed])
    new = unary_union([polygon_of(find(building, "spaces", space_id)) for space_id in changed])
    vacated = old.difference(new)
    for part in getattr(vacated, "geoms", [vacated]):
        if part.is_empty or part.area <= MIN_OVERLAP_M2:
            continue
        # the area a changed room gave up goes to the neighbour it borders most (a corridor, the next room);
        # bordering nobody (the outer wall moved in) it stays outside the building
        border = {other["id"]: part.boundary.intersection(polygon_of(other).buffer(VERTEX_MATCH_M)).length
                  for other in building["spaces"] if other["floor_id"] == floor_id and other["id"] not in changed}
        taker = max(border, key=border.get, default=None)
        if taker is None or border[taker] <= VERTEX_MATCH_M:
            continue
        other = find(building, "spaces", taker)
        grown = polygon_of(other).union(part)
        if grown.geom_type == "Polygon":
            other["polygon"] = outline(grown.simplify(0.001))
            fitted.add(taker)
    for space_id in sorted(changed):
        shape = polygon_of(find(building, "spaces", space_id))
        for other in building["spaces"]:
            if other["floor_id"] != floor_id or other["id"] in changed:
                continue
            neighbour = polygon_of(other)
            if neighbour.intersection(shape).area <= MIN_OVERLAP_M2:
                continue
            rest = neighbour.difference(shape)
            if rest.is_empty or rest.geom_type != "Polygon" or rest.area < MIN_NEIGHBOUR_M2:
                verb = "split" if rest.geom_type == "MultiPolygon" else "remove"
                raise EditError(f"this change would {verb} {other['name']}; move it less far or delete that room first")
            other["polygon"] = outline(rest.simplify(0.001))
            fitted.add(other["id"])
    changed = changed | fitted
    was_on_wall = {opening["id"] for opening in before["openings"] if on_wall(before, opening)}
    for opening in building["openings"]:
        if opening["id"] in was_on_wall and changed & set(opening["space_ids"]) and not on_wall(building, opening):
            target = wall_target(building, opening["space_ids"])
            if target is not None:
                point = nearest_points(target, Point(opening["position"]))[0]
                opening["position"] = rounded([point.x, point.y])


@op("set_polygon")
def set_polygon(building: dict, space_id: str, polygon: list[list[float]]) -> None:
    before = copy.deepcopy(building)
    space = find(building, "spaces", space_id)
    space["polygon"] = checked_outline(polygon, space["name"])
    settle(before, building, space["floor_id"], {space_id})


@op("move_vertex")
def move_vertex(building: dict, floor_id: str, from_xy: list[float], to_xy: list[float]) -> None:
    floor_of(building, floor_id)
    before = copy.deepcopy(building)
    origin, target = Point(from_xy), rounded(to_xy)
    changed = set()
    for space in building["spaces"]:
        if space["floor_id"] != floor_id:
            continue
        moved = [target if Point(point).distance(origin) <= VERTEX_MATCH_M else point for point in space["polygon"]]
        if moved != space["polygon"]:
            space["polygon"] = checked_outline(moved, space["name"])
            changed.add(space["id"])
    if not changed:
        raise EditError(f"no corner at {rounded(from_xy)} on this floor")
    settle(before, building, floor_id, changed)


# ---------- walls: sides and moving a whole wall ----------

SIDE_TOLERANCE_DEG = 10.0


def outward_normals(polygon: list[list[float]]) -> list[tuple[float, float]]:
    """Unit outward normal of each edge i → i+1 (x east, y north), from the ring's orientation."""
    twice_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
    sign = 1.0 if twice_area > 0 else -1.0  # counter-clockwise: outward is to the right of each edge
    normals = []
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        normals.append((sign * dy / length, -sign * dx / length))
    return normals


def compass(normal: tuple[float, float]) -> str:
    angle = math.degrees(math.atan2(normal[1], normal[0])) % 360
    for centre, name in ((0.0, "east"), (90.0, "north"), (180.0, "west"), (270.0, "south"), (360.0, "east")):
        if abs(angle - centre) <= SIDE_TOLERANCE_DEG:
            return name
    return "other"


def edge_sides(polygon: list[list[float]]) -> list[dict]:
    """Each edge with the compass side it faces: `{"side", "from", "to", "length_m"}` (the Builder's walls)."""
    return [{"side": compass(normal), "from": list(a), "to": list(b), "length_m": round(math.dist(a, b), 2)}
            for (a, b), normal in zip(zip(polygon, polygon[1:] + polygon[:1]), outward_normals(polygon))]


@op("move_edge")
def move_edge(building: dict, space_id: str, edge: list[list[float]], offset_m: float) -> None:
    """Move one wall of a space along its outward normal (negative = inward), corners moving in every space that
    has them; neighbours are fitted once afterwards (`settle`)."""
    space = find(building, "spaces", space_id)
    polygon = space["polygon"]
    first, second = edge

    def same(a: list[float], b: list[float]) -> bool:
        return math.dist(a, b) <= VERTEX_MATCH_M

    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        if (same(start, first) and same(end, second)) or (same(start, second) and same(end, first)):
            break
    else:
        raise EditError(f"{edge} is not an edge of {space['name']}; take one from space_info's edges")
    nx, ny = outward_normals(polygon)[index]
    moves = [(Point(corner), rounded([corner[0] + nx * offset_m, corner[1] + ny * offset_m]))
             for corner in (start, end)]
    before = copy.deepcopy(building)
    changed = set()
    for other in building["spaces"]:
        if other["floor_id"] != space["floor_id"]:
            continue
        moved = [next((target for origin, target in moves if Point(point).distance(origin) <= VERTEX_MATCH_M), point)
                 for point in other["polygon"]]
        if moved != other["polygon"]:
            other["polygon"] = checked_outline(moved, other["name"])
            changed.add(other["id"])
    settle(before, building, space["floor_id"], changed)


# ---------- position on the map (core/geoplace.py) ----------


@op("scale_building")
def scale_building(building: dict, factor: float) -> None:
    """Scale the whole building about its (0, 0) — a map fit correcting the import's scale estimate. Door widths
    stay (they are real door widths)."""
    factor = float(factor)
    if not 0.5 <= factor <= 2.0:
        raise EditError(f"scale_building: factor {factor} is out of range (0.5–2)")
    for space in building["spaces"]:
        space["polygon"] = [[round(x * factor, 3), round(y * factor, 3)] for x, y in space["polygon"]]
    for item in (*building["openings"], *building["assets"]):
        if item.get("position"):
            item["position"] = [round(value * factor, 3) for value in item["position"][:2]] + list(item["position"][2:])
    # the import's plans (Edit mode's reference / trace) map pixels to these metres: they scale with them
    for floor in ((building["building"].get("source_ref") or {}).get("import") or {}).get("floors", {}).values():
        if floor.get("reference"):
            floor["reference"]["transform"] = [[value * factor for value in row] for row in floor["reference"]["transform"]]
        if floor.get("m_per_px"):
            floor["m_per_px"] *= factor


@op("set_reference")
def set_reference(building: dict, floor_id: str, transform: list) -> None:
    """Where a floor's kept plan lies under the editor (its 2×3 px → metres transform) — Edit mode's trace, moved /
    turned / scaled by hand onto the rooms. The rooms do not move."""
    floor = find(building, "floors", floor_id)
    plan = (((building["building"].get("source_ref") or {}).get("import") or {}).get("floors") or {}).get(str(floor["level"]))
    if not plan or not plan.get("reference"):
        raise EditError(f"set_reference: floor {floor_id} has no plan image")
    try:
        rows = [[float(value) for value in row] for row in transform]
    except (TypeError, ValueError):
        rows = []
    if len(rows) != 2 or any(len(row) != 3 for row in rows) or abs(rows[0][0] * rows[1][1] - rows[0][1] * rows[1][0]) < 1e-12:
        raise EditError("set_reference: transform must be 2×3 numbers [[a, b, c], [d, e, f]] that do not flatten the image")
    plan["reference"]["transform"] = rows


@op("straighten_floor")
def straighten_floor(building: dict, floor_id: str) -> None:
    """Turn a floor in place (about its middle) so its walls run parallel to the lowest floor's — a floor added from
    a plan drawn or photographed a few degrees off. Its kept plan turns with it."""
    from core.plan_import.merge import lowest_spaces, outline, turn_floor, wall_angle

    floor = find(building, "floors", floor_id)
    spaces = [space for space in building["spaces"] if space["floor_id"] == floor["id"]]
    if not spaces:
        raise EditError(f"straighten_floor: floor {floor_id} has no rooms")
    off = (wall_angle(lowest_spaces(building)) - wall_angle(spaces) + 45) % 90 - 45  # the smallest turn, ±45°
    middle = outline({"spaces": spaces}).centroid
    turn_floor(building, floor["id"], off, (middle.x, middle.y))


@op("add_floors")
def add_floors(building: dict, building_with_floors: dict) -> None:
    """The floors of another import (a building of their own) laid onto this one and stacked on it
    (core/plan_import/merge.py) — "Add a floor" in Edit mode."""
    from core.plan_import.merge import add_floors as merged  # merge → geoplace → edits: imported when used

    if not isinstance(building_with_floors, dict) or not building_with_floors.get("floors"):
        raise EditError("add_floors: building_with_floors needs floors")
    try:
        result = merged(building, building_with_floors)
    except ValueError as error:
        raise EditError(f"add_floors: {error}") from None
    building.clear()
    building.update(result)


@op("set_location")
def set_location(building: dict, location: dict | None) -> None:
    """The building's real position (`building.location`, core/geoplace.location_for); None removes it."""
    if location is None:
        building["building"].pop("location", None)
    elif not isinstance(location, dict) or not {"origin", "bearing"} <= set(location):
        raise EditError("set_location: location needs origin and bearing")
    else:
        building["building"]["location"] = location
