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
import re
from collections.abc import Callable

from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from core.building_map import OUTSIDE
from core.solvers.walls import WALL_TOLERANCE_M


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
    except TypeError as error:  # wrong / missing arguments
        raise EditError(f"{name}: {error}") from None
    return changed


def apply_steps(base: dict, steps: list[list[dict]]) -> dict:
    building = base
    for step in steps:
        for operation in step:
            building = apply_op(building, operation)
    return copy.deepcopy(base) if building is base else building


# ---------- helpers ----------


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
    shared = polygon_of(first).exterior.intersection(polygon_of(second).buffer(WALL_TOLERANCE_M))
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
        "id": new_id(building, "spaces", f"{floor_id}-S-new"), "floor_id": floor_id, "type": type,
        "room_type": room_type, "name": name, "ref": ref, "polygon": outline, "synthetic": False,
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
            space[key] = value


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
        "id": new_id(building, "assets", f"{building['building']['id']}-A-new"), "name": name,
        "category": category, "type": type, "space_id": space_id, "floor_id": space["floor_id"],
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
            asset[key] = value
    if footprint is not None:
        asset["footprint"].update({key: float(value) for key, value in footprint.items()})


@op("delete_asset")
def delete_asset(building: dict, asset_id: str) -> None:
    find(building, "assets", asset_id)
    building["assets"] = [asset for asset in building["assets"] if asset["id"] != asset_id]
