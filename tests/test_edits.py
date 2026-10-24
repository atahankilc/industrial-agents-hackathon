"""core/edits.py: JSON edit operations on building dicts (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §1)."""

import copy
import math
import json
from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from core.building_map import BuildingMap
from core.edits import EditError, apply_op, apply_steps, space_at
from core.solvers.walls import WALL_TOLERANCE_M, shared_wall_neighbours

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000" / "building.json"


@pytest.fixture
def base() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def by_id(building: dict, key: str, element_id: str) -> dict:
    return next(item for item in building[key] if item["id"] == element_id)


def neighbour_rooms(building: dict) -> tuple[str, str]:
    """Two rooms (type room) on one floor that share >= 2 m of wall."""
    bmap = BuildingMap(building)
    for space in building["spaces"]:
        if space["type"] != "room":
            continue
        for other in shared_wall_neighbours(bmap, space["id"], min_length=2.0):
            if other["type"] == "room":
                return space["id"], other["id"]
    raise AssertionError("fixture has no neighbouring rooms")


def far_rooms(building: dict) -> tuple[str, str]:
    rooms = [space for space in building["spaces"] if space["type"] == "room"]
    first = rooms[0]
    for other in rooms:
        if other["floor_id"] == first["floor_id"] and Polygon(first["polygon"]).distance(Polygon(other["polygon"])) > 5:
            return first["id"], other["id"]
    raise AssertionError("fixture has no far-apart rooms")


def shared_outline(building: dict, a: str, b: str):
    first, second = (Polygon(by_id(building, "spaces", space)["polygon"]) for space in (a, b))
    return first.exterior.intersection(second.buffer(WALL_TOLERANCE_M))


def test_apply_op_does_not_mutate_base(base):
    before = copy.deepcopy(base)
    room = next(space for space in base["spaces"] if space["type"] == "room")
    apply_op(base, {"op": "set_space", "space_id": room["id"], "name": "Renamed"})
    assert base == before


def test_add_space_gets_new_id(base):
    floor = base["floors"][0]["id"]
    square = [[100, 100], [104, 100], [104, 104], [100, 104]]
    once = apply_op(base, {"op": "add_space", "floor_id": floor, "polygon": square, "type": "room",
                           "room_type": "office", "name": "New office", "ref": "9.99"})
    added = once["spaces"][-1]
    assert added["id"] == f"{floor}-S-new1"
    assert added["synthetic"] is False and added["polygon"] == square
    twice = apply_op(once, {"op": "add_space", "floor_id": floor, "polygon": [[110, 100], [114, 100], [114, 104]],
                            "type": "room", "room_type": "office", "name": "Another", "ref": "9.98"})
    assert twice["spaces"][-1]["id"] == f"{floor}-S-new2"


def test_delete_space_removes_its_openings_and_assets(base):
    room = next(asset["space_id"] for asset in base["assets"])
    changed = apply_op(base, {"op": "delete_space", "space_id": room})
    assert all(space["id"] != room for space in changed["spaces"])
    assert all(room not in opening["space_ids"] for opening in changed["openings"])
    assert all(asset["space_id"] != room for asset in changed["assets"])
    assert any(room in opening["space_ids"] for opening in base["openings"])


def test_set_space_renames(base):
    room = base["spaces"][1]["id"]
    changed = apply_op(base, {"op": "set_space", "space_id": room, "name": "Quiet room", "room_type": "meeting_room"})
    assert by_id(changed, "spaces", room)["name"] == "Quiet room"
    assert by_id(changed, "spaces", room)["room_type"] == "meeting_room"


def test_add_opening_snaps_onto_shared_wall(base):
    a, b = neighbour_rooms(base)
    wall = shared_outline(base, a, b)
    near = wall.interpolate(0.5, normalized=True)
    off = [near.x + 2.0, near.y + 2.0]
    floor = by_id(base, "spaces", a)["floor_id"]
    changed = apply_op(base, {"op": "add_opening", "space_ids": [a, b], "position": off, "kind": "door",
                              "width_m": 0.9, "step_free": True})
    opening = changed["openings"][-1]
    assert opening["id"] == f"{floor}-O-new1"
    assert opening["floor_id"] == floor and opening["synthetic"] is False
    assert wall.distance(Point(opening["position"])) < 0.05


def test_add_opening_without_shared_wall_raises(base):
    a, b = far_rooms(base)
    with pytest.raises(EditError):
        apply_op(base, {"op": "add_opening", "space_ids": [a, b], "position": [0, 0], "kind": "door",
                        "width_m": 0.9, "step_free": True})


def test_move_opening_snaps(base):
    opening = next(item for item in base["openings"] if "outside" not in item["space_ids"])
    a, b = opening["space_ids"]
    x, y = opening["position"]
    changed = apply_op(base, {"op": "move_opening", "opening_id": opening["id"], "position": [x + 0.5, y + 3.0]})
    moved = by_id(changed, "openings", opening["id"])
    assert shared_outline(base, a, b).distance(Point(moved["position"])) < 0.05
    assert moved["position"] != opening["position"]


def test_set_opening_width(base):
    opening = base["openings"][0]
    changed = apply_op(base, {"op": "set_opening", "opening_id": opening["id"], "width_m": 1.6, "step_free": False})
    assert by_id(changed, "openings", opening["id"])["width_m"] == 1.6
    assert by_id(changed, "openings", opening["id"])["step_free"] is False


def test_add_asset_and_move_recomputes_space(base):
    a, b = neighbour_rooms(base)
    first, second = (Polygon(by_id(base, "spaces", space)["polygon"]).representative_point() for space in (a, b))
    added = apply_op(base, {"op": "add_asset", "space_id": a, "name": "3D printer", "category": "machine",
                            "type": "3d_printer", "position": [first.x, first.y],
                            "footprint": {"width_m": 1.0, "depth_m": 0.8, "rotation_deg": 0.0}})
    asset = added["assets"][-1]
    assert asset["id"] == f"{base['building']['id']}-A-new1"
    assert asset["source"] == "edited" and asset["floor_id"] == by_id(base, "spaces", a)["floor_id"]
    moved = apply_op(added, {"op": "move_asset", "asset_id": asset["id"], "position": [second.x, second.y]})
    assert by_id(moved, "assets", asset["id"])["space_id"] == b


def test_move_asset_rotation(base):
    asset = base["assets"][0]
    changed = apply_op(base, {"op": "move_asset", "asset_id": asset["id"], "position": asset["position"],
                              "rotation_deg": 45.0})
    assert by_id(changed, "assets", asset["id"])["footprint"]["rotation_deg"] == 45.0


def test_set_and_delete_asset(base):
    asset = base["assets"][0]
    renamed = apply_op(base, {"op": "set_asset", "asset_id": asset["id"], "name": "Standing desk"})
    assert by_id(renamed, "assets", asset["id"])["name"] == "Standing desk"
    deleted = apply_op(renamed, {"op": "delete_asset", "asset_id": asset["id"]})
    assert all(item["id"] != asset["id"] for item in deleted["assets"])


def test_delete_opening(base):
    opening = base["openings"][0]
    changed = apply_op(base, {"op": "delete_opening", "opening_id": opening["id"]})
    assert all(item["id"] != opening["id"] for item in changed["openings"])


def test_unknown_id_raises(base):
    with pytest.raises(EditError, match="no-such-space"):
        apply_op(base, {"op": "set_space", "space_id": "no-such-space", "name": "x"})
    with pytest.raises(EditError, match="unknown op"):
        apply_op(base, {"op": "teleport"})


def test_space_at(base):
    a, _ = neighbour_rooms(base)
    space = by_id(base, "spaces", a)
    point = Polygon(space["polygon"]).representative_point()
    assert space_at(base, space["floor_id"], [point.x, point.y]) == a
    assert space_at(base, space["floor_id"], [10_000, 10_000]) is None


def test_apply_steps_is_deterministic(base):
    a, b = neighbour_rooms(base)
    steps = [
        [{"op": "set_space", "space_id": a, "name": "Lab A"}],
        [{"op": "add_opening", "space_ids": [a, b], "position": [0, 0], "kind": "door", "width_m": 1.0,
          "step_free": True},
         {"op": "delete_asset", "asset_id": base["assets"][0]["id"]}],
    ]
    assert apply_steps(base, steps) == apply_steps(base, steps)
    assert by_id(apply_steps(base, steps), "spaces", a)["name"] == "Lab A"


def test_apply_steps_returns_a_copy_even_without_ops(base):
    assert apply_steps(base, [[]]) is not base
    assert apply_steps(base, []) is not base


# ---------- Task 2: wall moves keep shared walls ----------


def axis_shift(building: dict, a: str, b: str, metres: float) -> list[list[float]]:
    """A's outline with the vertices on its shared wall with B moved `metres` towards B (axis-aligned rooms)."""
    first, second = (Polygon(by_id(building, "spaces", space)["polygon"]) for space in (a, b))
    dx, dy = second.centroid.x - first.centroid.x, second.centroid.y - first.centroid.y
    step = [metres * (1 if dx > 0 else -1), 0.0] if abs(dx) > abs(dy) else [0.0, metres * (1 if dy > 0 else -1)]
    return [[x + step[0], y + step[1]] if second.distance(Point(x, y)) < 0.01 else [x, y]
            for x, y in by_id(building, "spaces", a)["polygon"]]


def test_move_vertex_moves_shared_corner_in_both_rooms(base):
    a, b = neighbour_rooms(base)
    corners_b = {tuple(point) for point in by_id(base, "spaces", b)["polygon"]}
    corner = next(point for point in by_id(base, "spaces", a)["polygon"] if tuple(point) in corners_b)
    target = [round(corner[0] + 0.2, 3), round(corner[1] + 0.2, 3)]
    floor = by_id(base, "spaces", a)["floor_id"]
    changed = apply_op(base, {"op": "move_vertex", "floor_id": floor, "from_xy": corner, "to_xy": target})
    assert target in by_id(changed, "spaces", a)["polygon"]
    assert target in by_id(changed, "spaces", b)["polygon"]


def test_widen_room_shrinks_neighbour(base):
    a, b = neighbour_rooms(base)
    first, second = (Polygon(by_id(base, "spaces", space)["polygon"]) for space in (a, b))
    wall = first.exterior.intersection(second.buffer(0.001)).length - 0.002  # exact shared length, not the 0.35 m band
    old_b = Polygon(by_id(base, "spaces", b)["polygon"]).area
    changed = apply_op(base, {"op": "set_polygon", "space_id": a, "polygon": axis_shift(base, a, b, 1.0)})
    new_a, new_b = (Polygon(by_id(changed, "spaces", space)["polygon"]) for space in (a, b))
    assert abs(new_b.area - (old_b - wall)) < 0.05
    assert new_a.intersection(new_b).area < 0.01


def test_set_polygon_that_would_erase_neighbour_raises(base):
    a, b = neighbour_rooms(base)
    before = copy.deepcopy(base)
    huge = list(Polygon(by_id(base, "spaces", a)["polygon"]).union(
        Polygon(by_id(base, "spaces", b)["polygon"]).buffer(0.5, join_style="mitre")).envelope.exterior.coords)[:-1]
    with pytest.raises(EditError, match="remove"):
        apply_op(base, {"op": "set_polygon", "space_id": a, "polygon": [list(point) for point in huge]})
    assert base == before


def test_doors_follow_moved_wall(base):
    a, b = neighbour_rooms(base)
    with_door = apply_op(base, {"op": "add_opening", "space_ids": [a, b], "position": [0, 0], "kind": "door",
                                "width_m": 0.9, "step_free": True})
    door = with_door["openings"][-1]["id"]
    changed = apply_op(with_door, {"op": "set_polygon", "space_id": a, "polygon": axis_shift(with_door, a, b, 1.0)})
    assert shared_outline(changed, a, b).distance(Point(by_id(changed, "openings", door)["position"])) < 0.05


def test_self_intersecting_polygon_raises(base):
    a, _ = neighbour_rooms(base)
    with pytest.raises(EditError):
        apply_op(base, {"op": "set_polygon", "space_id": a, "polygon": [[0, 0], [4, 4], [4, 0], [0, 4]]})


def test_move_opening_across_a_thick_wall():
    """Swiss Dwellings walls leave gaps up to ~2 m between the two spaces of a door; snapping must still work."""
    for file in sorted((FIXTURE.parent.parent).glob("*/building.json")):
        building = json.loads(file.read_text(encoding="utf-8"))
        if building["building"]["source"] != "swiss_dwellings":
            continue
        spaces = {space["id"]: Polygon(space["polygon"]) for space in building["spaces"]}
        for opening in building["openings"]:
            ids = opening["space_ids"]
            if "outside" not in ids and 0.5 < spaces[ids[0]].distance(spaces[ids[1]]) < 1.0:
                x, y = opening["position"]
                changed = apply_op(building, {"op": "move_opening", "opening_id": opening["id"],
                                              "position": [x + 0.1, y + 0.1]})
                assert math.dist(by_id(changed, "openings", opening["id"])["position"], [x, y]) < 1.0
                return
    pytest.skip("no swiss building with a 0.5-1.0 m wall in train")
