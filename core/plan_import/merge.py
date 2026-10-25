"""New floors for an existing building: the Creator reads the new plans as a building of their own, `add_floors` lays
it onto the existing one (same IoU fit as the map placement, core/geoplace.fit_shape), adds its floors at the levels
the user gave (a level the building has is an error), joins the stairs / lifts across the seam and keeps each floor's plan for Edit mode."""

import copy
import math

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from core.geoplace import WALL_M, fit_shape

JOIN_M = 4.0  # a stair / lift above another within this distance is the same one


def outline(building: dict) -> Polygon:
    """All floors' spaces united, with the exterior walls (largest part)."""
    shape = unary_union([Polygon(space["polygon"]).buffer(0) for space in building["spaces"]]).buffer(WALL_M, join_style=2)
    return max(shape.geoms, key=lambda part: part.area) if isinstance(shape, MultiPolygon) else shape


def wall_angle(spaces: list[dict]) -> float:
    """The direction of the walls (degrees, 0–90): the length-weighted mean of the room edges' angles modulo 90."""
    x = y = 0.0
    for space in spaces:
        points = space["polygon"]
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
            length = math.hypot(x1 - x0, y1 - y0)
            quarter = 4 * math.atan2(y1 - y0, x1 - x0)  # a quarter turn apart counts as the same direction
            x, y = x + length * math.cos(quarter), y + length * math.sin(quarter)
    return math.degrees(math.atan2(y, x)) / 4 % 90


def lowest_spaces(building: dict) -> list[dict]:
    lowest = min(building["floors"], key=lambda floor: floor["level"])["id"]
    return [space for space in building["spaces"] if space["floor_id"] == lowest]


def turn_floor(building: dict, floor_id: str, degrees: float, centre: tuple[float, float]) -> None:
    """Turn one floor's rooms, doors, items and kept plan about `centre` (in place)."""
    turn = math.radians(degrees)
    move = np.array([[math.cos(turn), -math.sin(turn), 0.0], [math.sin(turn), math.cos(turn), 0.0]])
    move[:, 2] = np.array(centre) - move[:, :2] @ np.array(centre)
    shift(building, {floor_id}, move)


def shift(building: dict, floor_ids: set[str], move: np.ndarray) -> None:
    """Apply a 2×3 similarity `move` to the given floors (geometry and their kept plans), in place."""
    at = lambda point: [round(float(value), 3) for value in move @ [point[0], point[1], 1.0]]
    for space in building["spaces"]:
        if space["floor_id"] in floor_ids:
            space["polygon"] = [at(point) for point in space["polygon"]]
    for item in (*building["openings"], *building["assets"]):
        if item.get("floor_id") in floor_ids and item.get("position"):
            item["position"] = at(item["position"])[:2] + list(item["position"][2:])
    plans = ((building["building"].get("source_ref") or {}).get("import") or {}).get("floors") or {}
    for floor in building["floors"]:
        plan = plans.get(str(floor["level"]))
        if floor["id"] in floor_ids and plan and plan.get("reference"):
            plan["reference"]["transform"] = (move @ np.vstack([plan["reference"]["transform"], [0.0, 0.0, 1.0]])).tolist()


def add_floors(building: dict, new: dict) -> dict:
    """`building` with the floors of `new` (another import) added, aligned onto it. `building` keeps its id, name and
    location; `new`'s floors keep their ids (imports never share an id prefix)."""
    merged, new = copy.deepcopy(building), copy.deepcopy(new)
    # walls stay parallel to the building's: only quarter turns of the angle that lines the walls up
    base = wall_angle(lowest_spaces(merged)) - wall_angle(new["spaces"])
    bearing, scale, dx, dy, _ = fit_shape(outline(new), outline(merged), [base + 90 * turn for turn in range(4)])
    turn = math.radians(bearing)
    move = np.array([[scale * math.cos(turn), -scale * math.sin(turn), dx],
                     [scale * math.sin(turn), scale * math.cos(turn), dy]])
    at = lambda point: [round(float(value), 3) for value in move @ [point[0], point[1], 1.0]]
    for space in new["spaces"]:
        space["polygon"] = [at(point) for point in space["polygon"]]
    for item in (*new["openings"], *new["assets"]):
        if item.get("position"):
            item["position"] = at(item["position"])[:2] + list(item["position"][2:])

    plans = merged["building"]["source_ref"].setdefault("import", {"files": [], "floors": {}})
    plans.setdefault("floors", {})
    new_plans = (new["building"]["source_ref"].get("import") or {})
    plans["files"] = [*plans.get("files", []), *new_plans.get("files", [])]
    taken = {floor["level"] for floor in merged["floors"]}
    for floor in sorted(new["floors"], key=lambda item: item["level"]):
        plan = (new_plans.get("floors") or {}).get(str(floor["level"]))
        if floor["level"] in taken:  # the user names each new floor's level; one the building has is a mistake
            raise ValueError(f"the building already has floor {floor['level']}")
        taken.add(floor["level"])
        merged["floors"].append(floor)
        if plan is not None:
            if plan.get("reference"):
                transform = np.vstack([plan["reference"]["transform"], [0.0, 0.0, 1.0]])
                plan["reference"]["transform"] = (move @ transform).tolist()
            if plan.get("m_per_px"):
                plan["m_per_px"] *= scale
            plans["floors"][str(floor["level"])] = plan
    merged["floors"].sort(key=lambda item: item["level"])
    merged["spaces"] += new["spaces"]
    merged["openings"] += new["openings"]
    merged["assets"] += new["assets"]
    merged["vertical_connectors"] += new["vertical_connectors"]
    merged["vertical_connectors"] += joins(merged, {floor["id"] for floor in new["floors"]})
    return merged


def joins(building: dict, added: set[str]) -> list[dict]:
    """Stairs / lifts joining each pair of consecutive floors where one floor is new and the other is not: the same
    kind within JOIN_M; with none at all, the nearest stair (else lift) pair, marked synthetic so the floors connect."""
    centre = {space["id"]: Polygon(space["polygon"]).centroid for space in building["spaces"]}
    of = lambda floor_id, kind: [s for s in building["spaces"] if s["floor_id"] == floor_id and s["type"] == kind]
    result = []
    for lower, upper in zip(building["floors"], building["floors"][1:]):
        if (lower["id"] in added) == (upper["id"] in added):
            continue
        pairs = []
        for kind in ("stair", "lift"):
            used: set[str] = set()
            for down in of(lower["id"], kind):
                near = [(centre[up["id"]].distance(centre[down["id"]]), up) for up in of(upper["id"], kind)
                        if up["id"] not in used]
                if near and (best := min(near, key=lambda item: item[0]))[0] <= JOIN_M:
                    used.add(best[1]["id"])
                    pairs.append((kind, down, best[1], False))
        if not pairs:
            for kind in ("stair", "lift"):
                near = [(centre[up["id"]].distance(centre[down["id"]]), down, up)
                        for down in of(lower["id"], kind) for up in of(upper["id"], kind)]
                if near:
                    _, down, up = min(near, key=lambda item: item[0])
                    pairs.append((kind, down, up, True))
                    break
        for number, (kind, down, up, guessed) in enumerate(pairs, start=1):
            result.append({"id": f"{upper['id']}-V{number:02d}", "kind": "stairs" if kind == "stair" else "lift",
                           "name": down.get("name") or ("Stairs" if kind == "stair" else "Lift"),
                           "floor_ids": [lower["id"], upper["id"]], "space_ids": [down["id"], up["id"]],
                           "step_free": kind == "lift", "synthetic": guessed})
    return result
