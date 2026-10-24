"""core.pointcloud: the viewer export (format, budget, connectors, openings) and route polylines in its frame."""

import math
from pathlib import Path

import pytest

from agent.tools import BuildingSession
from core.building_map import BuildingMap
from core.pointcloud import KINDS, export_points, route_vertices

BUILDING = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"


@pytest.fixture(scope="module")
def building_map() -> BuildingMap:
    return BuildingMap.load(BUILDING)


@pytest.fixture(scope="module")
def export(building_map) -> dict:
    return export_points(building_map)


def viewer_anchor(export: dict, space_id: str) -> tuple[float, float]:
    """A space's anchor (building x, y) in the viewer's horizontal plane (x, z)."""
    space = next(space for space in export["spaces"] if space["id"] == space_id)
    x, y = space["anchor"]
    return x - export["center"][0], -y - export["center"][1]


def test_export_shape_and_budget(building_map, export):
    assert 0 < export["count"] <= 180_000
    points = export["points"]
    assert len(points["position_cm"]) == 3 * export["count"]
    assert all(len(points[key]) == export["count"] for key in ("kind", "floor", "space", "reveal"))
    assert export["kinds"] == KINDS and set(points["kind"]) <= set(range(len(KINDS)))
    assert max(points["floor"]) < len(export["floors"]) and max(points["space"]) < len(export["spaces"])
    assert set(export["sampling"]) == {"wall_step", "wall_vstep", "floor_step"}
    assert export["closed"] == []


def test_budget_coarsens(building_map):
    small = export_points(building_map, max_points=40_000)
    assert small["count"] <= 40_000 and small["sampling"]["wall_step"] > 0.15


def test_connectors_and_openings(building_map, export):
    lift = next(connector for connector in export["connectors"] if connector["name"] == "Lift 1")
    assert lift["kind"] == "lift" and lift["spaces"]
    assert {export["spaces"][index]["id"] for index in lift["spaces"]} == set(
        building_map.connectors[lift["id"]]["space_ids"])
    assert {connector["kind"] for connector in export["connectors"]} <= {"stairs", "lift"}
    assert len(export["openings"]) == len(building_map.openings)
    for opening in export["openings"]:
        assert len(opening["position"]) == 3 and all(math.isfinite(value) for value in opening["position"])
        assert 0 <= opening["floor"] < len(export["floors"])
        assert opening["position"][1] == pytest.approx(export["floors"][opening["floor"]]["elevation_m"] + 1.0)


def test_export_reflects_session_changes(building_map):
    changed = BuildingMap(building_map.data)
    lift = next(connector["id"] for connector in changed.connectors.values() if connector["name"] == "Lift 1")
    changed.closed = {lift}
    assert export_points(changed, max_points=40_000)["closed"] == [lift]


def test_step_free_route_vertices(building_map, export):
    session = BuildingSession(building_map)
    session.tool_set_profile(step_free=True)
    route = session.tool_find_route("Main lobby", "Meeting room 3.07")
    assert route["reachable"]
    event = session.events[-1]
    vertices = route_vertices(export, session.building, event["space_path"], event["element_path"])
    assert len(vertices) >= 2
    start, end = viewer_anchor(export, event["space_path"][0]), viewer_anchor(export, event["space_path"][-1])
    assert math.dist((vertices[0][0], vertices[0][2]), start) < 0.05
    assert math.dist((vertices[-1][0], vertices[-1][2]), end) < 0.05
    floors = [vertex[3] for vertex in vertices]
    assert floors[0] == 0 and floors[-1] == 3 and floors == sorted(floors)
    assert vertices[0][1] == pytest.approx(export["floors"][0]["elevation_m"] + 1.0)
    assert vertices[-1][1] == pytest.approx(export["floors"][3]["elevation_m"] + 1.0)
    polyline = sum(math.dist(first[:3], second[:3]) for first, second in zip(vertices, vertices[1:]))
    assert polyline > 0 and event["length_m"] > 0
