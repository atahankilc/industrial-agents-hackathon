"""Plan import, stage 6: building.json assembly + auto-fixes (backend/core/plan_import/assemble.py)."""

from shapely.geometry import Polygon

from backend.core.plan_import.assemble import assemble, autofix, check
from tests.plan_fixtures import labelled_floor


def errors(building):
    return [issue for issue in check(building) if issue["severity"] == "error"]


def test_fixture_assembles_without_errors():
    building = autofix(assemble("imp-test", "Test", [labelled_floor()], ["fixture.png"]))
    assert errors(building) == []
    assert {space["type"] for space in building["spaces"]} == {"room", "corridor"}
    assert len(building["openings"]) == 3
    assert building["spaces"][0]["id"].startswith("imp-test-F0-S")
    assert building["assets"] == []
    notes = building["building"]["source_ref"]["import"]
    assert notes["files"] == ["fixture.png"]
    assert notes["floors"]["0"]["scale_method"] == "doors" and notes["floors"]["0"]["segmentation"] == "walls"
    assert building["floors"][0] == {"id": "imp-test-F0", "level": 0, "name": "Ground floor", "elevation_m": 0.0,
                                     "height_m": 3.0}


def test_rooms_have_metre_areas():
    building = assemble("imp-test", "Test", [labelled_floor()], [])
    from shapely.geometry import Polygon
    areas = sorted(round(Polygon(space["polygon"]).area) for space in building["spaces"])
    assert areas[0] in (18, 19, 20, 21) and areas[-1] in (37, 38, 39, 40, 41, 42)


def test_two_floors_with_stairs_are_connected():
    building = autofix(assemble("imp-test", "T", [labelled_floor(0, stair=True), labelled_floor(1, stair=True)], []))
    assert len(building["vertical_connectors"]) == 1
    connector = building["vertical_connectors"][0]
    assert connector["kind"] == "stairs" and connector["step_free"] is False
    assert connector["floor_ids"] == ["imp-test-F0", "imp-test-F1"]
    assert errors(building) == []


def test_two_floors_without_stairs_report_unreachable():  # Review Focus 5
    building = autofix(assemble("imp-test", "T", [labelled_floor(0), labelled_floor(1)], []))
    assert any(issue["code"] == "unreachable" for issue in errors(building))


def test_autofix_drops_slivers_and_their_doors():
    building = assemble("imp-test", "T", [labelled_floor()], [])
    sliver = dict(building["spaces"][0], id="imp-test-F0-S999", polygon=[[0, 0], [0.5, 0], [0.5, 0.5]])
    building["spaces"].append(sliver)
    building["openings"].append(dict(building["openings"][0], id="imp-test-F0-O9999",
                                     space_ids=[sliver["id"], building["spaces"][0]["id"]]))
    fixed = autofix(building)
    assert "imp-test-F0-S999" not in [space["id"] for space in fixed["spaces"]]
    assert "imp-test-F0-O9999" not in [opening["id"] for opening in fixed["openings"]]


def test_autofix_survives_self_intersecting_outlines():
    building = assemble("imp-test", "T", [labelled_floor()], [])
    bowtie = dict(building["spaces"][0], id="imp-test-F0-S998", polygon=[[1, 1], [9, 7], [9, 1], [1, 3]])
    building["spaces"].append(bowtie)
    fixed = autofix(building)  # must not raise
    assert all(Polygon(space["polygon"]).is_valid for space in fixed["spaces"])
