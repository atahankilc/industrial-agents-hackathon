"""core/routeline.py: the route polyline the plan view draws."""

from pathlib import Path

import pytest
from shapely.geometry import LineString

from core.building_map import BuildingMap
from core.floorplan import floor_indices
from core.navigation import find_route
from core.routeline import route_line
from core.solvers.geometry import polygon

DATA = Path(__file__).resolve().parent.parent / "data"
BUILDING = DATA / "train" / "proc-campus-train-000"


@pytest.fixture(scope="module")
def building() -> BuildingMap:
    return BuildingMap.load(BUILDING)


def rooms(building: BuildingMap) -> list[str]:
    return sorted(space_id for space_id, space in building.spaces.items() if space["type"] == "room")


def test_route_from_outside_starts_at_an_entrance_and_ends_at_the_destination(building: BuildingMap) -> None:
    destination = rooms(building)[-1]
    route = find_route(building, "outside", destination).to_dict()
    line = route_line(building, route["space_path"], route["element_path"])
    entrances = {tuple(o["position"]) for o in building.openings.values() if o["kind"] == "entrance"}
    assert tuple(line[0][:2]) in entrances
    end = building.anchor(destination)
    assert line[-1] == [round(end[0], 3), round(end[1], 3), floor_indices(building)[building.spaces[destination]["floor_id"]]]


def test_every_door_on_the_route_is_on_the_line_and_floors_follow_the_path(building: BuildingMap) -> None:
    ids = rooms(building)
    for start, destination in zip(ids[::7], ids[3::7]):
        route = find_route(building, start, destination).to_dict()
        if not route.get("reachable"):
            continue
        line = route_line(building, route["space_path"], route["element_path"])
        points = {(x, y) for x, y, _ in line}
        for element in route["element_path"]:
            if element in building.openings:
                x, y = building.openings[element]["position"]
                assert (round(x, 3), round(y, 3)) in points
        floors = [floor for _, _, floor in line]
        visited = [floor_indices(building)[building.spaces[s]["floor_id"]] for s in route["space_path"]]
        assert [f for i, f in enumerate(floors) if i == 0 or floors[i - 1] != f] == \
            [f for i, f in enumerate(visited) if i == 0 or visited[i - 1] != f]


def test_skipped_anchors_leave_a_straight_line_inside_the_space(building: BuildingMap) -> None:
    ids = rooms(building)
    route = find_route(building, ids[0], ids[-1]).to_dict()
    line = route_line(building, route["space_path"], route["element_path"])
    anchors = {(round(x, 3), round(y, 3)) for x, y in (building.anchor(s) for s in route["space_path"] if s != "outside")}
    drawn = {(x, y) for x, y, _ in line}
    skipped = [s for s in route["space_path"][1:-1]
               if (round(building.anchor(s)[0], 3), round(building.anchor(s)[1], 3)) not in drawn]
    assert skipped, "a through-corridor should be drawn door to door"
    # each consecutive same-floor segment that crosses a skipped space stays inside it (plus tolerance)
    for (ax, ay, af), (bx, by, bf) in zip(line, line[1:]):
        if af != bf:
            continue
        segment = LineString([(ax, ay), (bx, by)])
        for space in skipped:
            shape = polygon(building.spaces[space])
            if shape.intersects(segment.interpolate(0.5, normalized=True)):
                assert shape.buffer(0.05).contains(segment)
    assert len(anchors) > len(skipped)
