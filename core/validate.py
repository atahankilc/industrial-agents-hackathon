"""Validator for edited buildings — issues the Edit mode shows in red (archive/hackathon/superpowers/specs/2026-10-24-builder-edit-mode-design.md §2).

`validate(building, base=None)` → issues `{"severity", "code", "message", "ids"}`, errors first. Codes:
`polygon_invalid`, `duplicate_id`, `dangling_ref`, `overlap`, `opening_off_wall`, `asset_outside`, `unreachable`
(from any entrance, stairs allowed) and the warning `no_entrance` (then reachability is not checked).

Calibration (scripts/validate_dataset.py, 280 buildings, 2026-10-24): every building has an entrance and every
space is reachable; no invalid polygons, dangling refs or assets outside their space. But the real-world sources
are not clean: overlapping spaces on one floor (osm_indoor 281 pairs, resplan 13, swiss_dwellings 38) and doors
off the wall their two spaces share, even allowing for the wall's thickness (osm_indoor 61, swiss_dwellings 46,
resplan 1). So an issue the base
building already has (same code, same ids) is a **warning** — "already in the original" — and only issues the
edits introduce are errors. Validating a dataset building against itself gives no errors (tests/test_validate.py).
"""

from collections import Counter, defaultdict

from shapely import STRtree
from shapely.geometry import Point, Polygon

from core.building_map import OUTSIDE, BuildingMap
from core.edits import wall_target
from core.solvers.reachability import reachable_spaces
from core.solvers.walls import WALL_TOLERANCE_M

OVERLAP_M2 = 0.05  # overlaps up to this are rounding noise
ASSET_OUTSIDE_M = 0.01


def issue(code: str, message: str, ids: list[str], severity: str = "error") -> dict:
    return {"severity": severity, "code": code, "message": message, "ids": ids}


def validate(building: dict, base: dict | None = None) -> list[dict]:
    issues = find_issues(building)
    if base is not None:
        known = {(item["code"], tuple(item["ids"])) for item in find_issues(base)}
        for item in issues:
            if item["severity"] == "error" and (item["code"], tuple(item["ids"])) in known:
                item["severity"] = "warning"
                item["message"] += " (already in the original building)"
    return sorted(issues, key=lambda item: (item["severity"] != "error", item["code"], item["ids"]))


def find_issues(building: dict) -> list[dict]:
    issues: list[dict] = []
    spaces = {space["id"]: space for space in building["spaces"]}
    floors = {floor["id"] for floor in building["floors"]}
    names = {space_id: space["name"] for space_id, space in spaces.items()}

    every_id = [item["id"] for key in ("floors", "spaces", "openings", "vertical_connectors", "assets")
                for item in building[key]]
    for element_id, count in Counter(every_id).items():
        if count > 1:
            issues.append(issue("duplicate_id", f"id {element_id} is used {count} times", [element_id]))

    shapes: dict[str, Polygon] = {}
    for space_id, space in spaces.items():
        shape = Polygon(space["polygon"]) if len(space["polygon"]) >= 3 else None
        if shape is None or not shape.is_valid or shape.area <= 0:
            issues.append(issue("polygon_invalid", f"{space['name']} has a broken outline", [space_id]))
        else:
            shapes[space_id] = shape
        if space["floor_id"] not in floors:
            issues.append(issue("dangling_ref", f"{space['name']} is on a missing floor", [space_id]))

    issues += overlaps(spaces, shapes, names)

    dangling = False
    for opening in building["openings"]:
        missing = [space_id for space_id in opening["space_ids"] if space_id != OUTSIDE and space_id not in spaces]
        if missing:
            dangling = True
            issues.append(issue("dangling_ref", f"door {opening['id']} joins a missing space", [opening["id"]]))
        elif all(space_id in shapes for space_id in opening["space_ids"] if space_id != OUTSIDE):
            if off_wall(building, opening, shapes):
                between = " and ".join(names.get(space_id, "outside") for space_id in opening["space_ids"])
                issues.append(issue("opening_off_wall", f"the door between {between} is not on a wall they share",
                                    [opening["id"]]))
    for connector in building["vertical_connectors"]:
        if any(space_id not in spaces for space_id in connector["space_ids"]) or \
                any(floor_id not in floors for floor_id in connector["floor_ids"]):
            dangling = True
            issues.append(issue("dangling_ref", f"{connector['name']} stops at a missing space", [connector["id"]]))
    for asset in building["assets"]:
        if asset["space_id"] not in spaces:
            dangling = True
            issues.append(issue("dangling_ref", f"{asset['name']} is in a missing space", [asset["id"]]))
        elif asset["space_id"] in shapes and \
                shapes[asset["space_id"]].distance(Point(asset["position"])) > ASSET_OUTSIDE_M:
            issues.append(issue("asset_outside", f"{asset['name']} is outside {names[asset['space_id']]}",
                                [asset["id"]]))

    if not any(OUTSIDE in opening["space_ids"] for opening in building["openings"]):
        issues.append(issue("no_entrance", "the building has no entrance, so reachability is not checked", [],
                            "warning"))
    elif not dangling:
        reached = reachable_spaces(BuildingMap(building), OUTSIDE, step_free=False)
        for space_id in spaces:
            if space_id not in reached:
                issues.append(issue("unreachable", f"{names[space_id]} can't be reached from an entrance",
                                    [space_id]))
    return issues


def overlaps(spaces: dict[str, dict], shapes: dict[str, Polygon], names: dict[str, str]) -> list[dict]:
    found = []
    by_floor: dict[str, list[str]] = defaultdict(list)
    for space_id in shapes:
        by_floor[spaces[space_id]["floor_id"]].append(space_id)
    for ids in by_floor.values():
        polygons = [shapes[space_id] for space_id in ids]
        tree = STRtree(polygons)
        for index, polygon in enumerate(polygons):
            for other in tree.query(polygon):
                if other <= index:
                    continue
                area = polygon.intersection(polygons[other]).area
                if area > OVERLAP_M2:
                    pair = sorted([ids[index], ids[other]])
                    found.append(issue("overlap", f"{names[pair[0]]} and {names[pair[1]]} overlap by "
                                                  f"{area:.1f} m²", pair))
    return found


def off_wall(building: dict, opening: dict, shapes: dict[str, Polygon]) -> bool:
    inside = [space_id for space_id in opening["space_ids"] if space_id != OUTSIDE]
    try:
        target = wall_target(building, opening["space_ids"])
    except ValueError:  # EditError: malformed opening (e.g. spaces on two floors)
        return True
    if target is None:
        return True
    gap = shapes[inside[0]].distance(shapes[inside[1]]) if len(inside) == 2 else 0.0
    return target.distance(Point(opening["position"])) > WALL_TOLERANCE_M + gap
