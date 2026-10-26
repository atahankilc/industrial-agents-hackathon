"""Solid walls of the plan export (backend/core/floorplan.py `wall_solids`)."""

import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon

from backend.core.building_map import BuildingMap
from backend.core.floorplan import CORE_TYPES, export_plan

DATA = Path(__file__).resolve().parent.parent / "data"


def solids(building: str, floor: int) -> list[tuple[str, Polygon]]:
    plan = export_plan(BuildingMap.load(DATA / building), [0, 0])
    return [(wall["kind"], Polygon(wall["rings"][0], wall["rings"][1:])) for wall in plan["wall_solids"][floor]], plan


def test_drawn_source_wall_fills_the_gap_without_covering_rooms():
    walls, plan = solids("train/swiss-1075", 0)
    assert {kind for kind, _ in walls} >= {"exterior", "partition"}
    rooms = [Polygon(space["polygon"]) for space in plan["spaces"] if space["floor"] == 0]
    for _, wall in walls:
        for room in rooms:
            assert wall.intersection(room).area < 0.02 * room.area  # walls sit between rooms, not in them


def test_touching_rooms_get_a_partition_and_doorways_stay_open():
    walls, plan = solids("dev/proc-campus-dev-001", 0)
    shapes = [wall for _, wall in walls]
    # a corridor/room edge with no gap in the data still gets a wall ...
    corridor = next(s for s in plan["spaces"] if s["floor"] == 0 and s["type"] == "corridor")
    door_positions = [Point(o["position"]) for o in plan["openings"] if o["floor"] == 0]
    edge_y = min(y for _, y in corridor["polygon"])
    probe = next(Point(x, edge_y) for x in range(1, 50) if all(Point(x, edge_y).distance(d) > 1.0 for d in door_positions))
    assert any(wall.distance(probe) < 1e-6 for wall in shapes)
    # ... but no wall covers a door
    for door in door_positions:
        assert all(wall.distance(door) > 0.1 for wall in shapes)


def test_stair_and_lift_cores_are_structural():
    walls, plan = solids("dev/proc-campus-dev-001", 0)
    structural = [wall for kind, wall in walls if kind == "structural"]
    cores = [Polygon(s["polygon"]) for s in plan["spaces"] if s["floor"] == 0 and s["type"] in CORE_TYPES]
    assert cores and all(any(wall.distance(core) < 0.01 for wall in structural) for core in cores)


def test_outline_covers_every_room_and_the_exterior_wall_wraps_it():
    plan = export_plan(BuildingMap.load(DATA / "dev/proc-campus-dev-001"), [0, 0])
    assert len(plan["outlines"]) == len(plan["floors"])
    for index in range(len(plan["floors"])):
        outline = [Polygon(rings[0], rings[1:]) for rings in plan["outlines"][index]]
        assert outline
        for space in (s for s in plan["spaces"] if s["floor"] == index):
            room = Polygon(space["polygon"])
            assert sum(part.intersection(room).area for part in outline) > 0.99 * room.area
        shell = [Polygon(w["rings"][0], w["rings"][1:]) for w in plan["wall_solids"][index] if w["kind"] == "exterior"]
        for part in outline:
            assert all(part.intersection(wall).area < 0.01 for wall in shell)


def test_open_space_inside_a_bigger_one_gets_no_wall_through_it():
    # OSM maps Lobby 0.22 as a zone inside the Friedrich L. Bauer Hörsaal: its curved outline is no wall
    walls, plan = solids("dev/osm-way27917482", 1)
    lobby = next(s for s in plan["spaces"] if s["floor"] == 1 and s["name"] == "Lobby 0.22")
    hall = next(s for s in plan["spaces"] if s["floor"] == 1 and s["ref"] == "00.02.001")
    # the lobby's outline away from the hall's own edge (and from the walls along it)
    inside = Polygon(lobby["polygon"]).exterior.intersection(Polygon(hall["polygon"]).buffer(-0.5))
    assert inside.length > 10
    assert sum(wall.intersection(inside.buffer(0.02)).area for _, wall in walls) < 0.01
    assert all(LineString([s[:2], s[2:]]).difference(inside.buffer(0.02)).length > 0 for s in plan["walls"][1])


def test_nested_lifts_and_stairwells_with_a_door_keep_their_walls_open_stairs_lose_them():
    walls, plan = solids("train/osm-way13507441", 1)
    space = {s["name"]: s for s in plan["spaces"] if s["floor"] == 1}

    def wall_along(name: str, holder: str) -> float:
        # wall area along the part of the space's outline that runs through the space holding it
        inside = Polygon(space[name]["polygon"]).exterior.intersection(Polygon(space[holder]["polygon"]).buffer(-0.5))
        assert inside.length > 1
        return sum(wall.intersection(inside.buffer(0.05)).area for _, wall in walls) / inside.length

    assert wall_along("Lift 1.17", "Foyer") > 0.05  # a lift shaft is walled
    assert wall_along("Stairwell 1.02", "Festsaal") > 0.05  # has a door: a walled stairwell
    assert wall_along("Stairwell 1.15", "Foyer") < 0.005  # only a doorless opening: an open stair


def test_overlap_of_two_spaces_is_striped_in_both():
    plan = export_plan(BuildingMap.load(DATA / "dev/osm-way27917482"), [0, 0])
    lobby = next(s for s in plan["spaces"] if s["floor"] == 1 and s["name"] == "Lobby 0.22")
    hall = next(s for s in plan["spaces"] if s["floor"] == 1 and s["ref"] == "00.02.001")
    stripes = [(o["space"], Polygon(o["rings"][0], o["rings"][1:])) for o in plan["overlaps"][1]]
    mine = [shape for owner, shape in stripes if owner in (lobby["id"], hall["id"])]
    assert {owner for owner, _ in stripes} >= {lobby["id"], hall["id"]}
    overlap = Polygon(lobby["polygon"]).intersection(Polygon(hall["polygon"]))
    assert abs(sum(shape.area for shape in mine) - overlap.area) < 0.01 * overlap.area  # covered once, no gaps
    # stairwells and lifts inside a corridor are shafts, not overlaps
    plan = export_plan(BuildingMap.load(DATA / "dev/osm-way22744230"), [0, 0])
    cores = {s["id"] for s in plan["spaces"] if s["type"] in CORE_TYPES}
    assert not any(o["space"] in cores for floor in plan["overlaps"] for o in floor)


def test_rooms_that_almost_touch_keep_a_full_partition():
    # OSM draws the FMI Bistro's edge to the Magistrale up to 1.9 cm off the hall's: the wall stays >= 10 cm all along
    walls, plan = solids("dev/osm-way27917482", 1)
    bistro = next(s for s in plan["spaces"] if s["floor"] == 1 and s["name"] == "FMI Bistro")
    ring = bistro["polygon"] + bistro["polygon"][:1]
    a, b = (0.039, -9.893), (12.097, -13.22)  # the hall side, across the 2 cm-off vertex between
    assert a in map(tuple, ring) and b in map(tuple, ring)
    length = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    for step in range(1, 25):
        x, y = a[0] + ux * length * step / 25, a[1] + uy * length * step / 25
        across = LineString([(x - uy * 0.5, y + ux * 0.5), (x + uy * 0.5, y - ux * 0.5)])
        thickness = sum(wall.intersection(across).length for _, wall in walls)
        assert thickness > 0.099, (step, thickness)
