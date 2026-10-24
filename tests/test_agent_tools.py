"""The Guide agent's tool layer, driven like a conversation: find, route, profile, propose/apply changes."""

import json
from pathlib import Path

import pytest

from agent.tools import TOOL_DEFINITIONS, BuildingSession
from core.building_map import BuildingMap

BUILDING = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"


@pytest.fixture
def session() -> BuildingSession:
    return BuildingSession.load(BUILDING)


def test_every_definition_has_a_handler(session):
    for definition in TOOL_DEFINITIONS:
        assert hasattr(session, f"tool_{definition['name']}"), definition["name"]
        assert definition["input_schema"]["type"] == "object"


def test_results_are_json_and_errors_are_returned(session):
    for name, arguments in [
        ("building_overview", {}),
        ("search", {"query": "meeting room"}),
        ("locate", {"query": "defibrillator"}),
        ("count_assets", {"asset_type": "desks"}),
        ("room_facts", {"space": "Main lobby"}),
        ("find_route", {"start": "Canteen 0.20", "destination": "Meeting room 3.07"}),
        ("solve", {"kind": "largest_room", "params": {"floor_id": "proc-campus-train-000-F3",
                                                       "room_type": "meeting_room"}}),
    ]:
        result = session.call(name, arguments)
        assert "error" not in result, (name, result)
        json.dumps(result)
    assert "error" in session.call("find_route", {"start": "Room 9.99", "destination": "Main lobby"})
    assert "error" in session.call("no_such_tool", {})


def test_profile_and_closure_change_routes(session):
    trip = {"start": "Canteen 0.20", "destination": "Meeting room 3.07"}
    free = session.call("find_route", trip)
    session.call("set_profile", {"step_free": True})
    step_free = session.call("find_route", trip)
    assert step_free["length_m"] >= free["length_m"]
    assert step_free["profile"] == "step-free"

    lift = next(c for c in session.building.connectors.values() if c["kind"] == "lift")
    proposal = session.call("propose_change", {"action": "close", "targets": [lift["name"]]})
    assert proposal["needs_confirmation"] and proposal["effect"]["before_m"] == step_free["length_m"]
    assert session.building.closed == set()  # nothing applied before confirmation
    session.call("apply_change", {"change_id": proposal["change_id"]})
    assert lift["id"] in session.building.closed
    after = session.call("find_route", trip)
    assert after["reachable"] is (proposal["effect"]["still_reachable"])


def test_add_door_is_isolated_to_the_session(session):
    original = BuildingMap.load(BUILDING)
    wall = next(item for item in session.call("room_facts", {"space": "Main lobby"})["shared_walls"])
    proposal = session.call("propose_change", {"action": "add_door", "targets": ["Main lobby", wall["id"]]})
    session.call("apply_change", {"change_id": proposal["change_id"]})
    assert len(session.building.openings) == len(original.openings) + 1
    assert len(BuildingMap.load(BUILDING).openings) == len(original.openings)
