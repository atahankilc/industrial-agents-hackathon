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


def test_compare_routes_pending_and_applied(session):
    session.call("set_profile", {"step_free": True})
    session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    events, last_route = list(session.events), session.last_route
    session.call("propose_change", {"action": "close", "targets": ["Lift 1"]})
    pending = session.call("compare_routes", {"change_id": "C1"})
    assert session.events == events and session.last_route == last_route  # predictions emit nothing
    assert pending["status"] == "pending" and pending["lost_access_count"] == 0
    assert pending["last_route"]["before_m"] == 61.24 and pending["last_route"]["after_m"] == 96.46
    assert pending["longer_routes_count"] > 0 and pending["max_extra_m"] == pending["longer_routes"][0]["extra_m"]
    assert "proc-campus-train-000-V02" not in session.building.closed  # comparing never applies
    session.call("apply_change", {"change_id": "C1"})
    applied = session.call("compare_routes", {"change_id": "C1"})
    assert applied["status"] == "applied" and applied["longer_routes"] == pending["longer_routes"]
    # With both lifts out, a wheelchair user loses every room above the ground floor.
    session.call("propose_change", {"action": "close", "targets": ["Lift 2"]})
    both = session.call("compare_routes", {"change_id": "C2", "start": "Main lobby"})
    assert both["lost_access_count"] == both["reachable_rooms_before"] - both["reachable_rooms_after"] > 0
    lost = both["lost_access_by_floor"]
    assert "Ground floor" not in lost and sum(floor["count"] for floor in lost.values()) == both["lost_access_count"]
    assert all(floor["count"] == len(floor["rooms"]) for floor in lost.values())
    assert session.events[-1]["style"] == "lost_access"
    assert "error" in session.call("compare_routes", {"change_id": "C9"})


def test_proposal_reports_who_loses_access(session):
    session.call("set_profile", {"step_free": True})
    session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    session.call("apply_change", {"change_id": session.call(
        "propose_change", {"action": "close", "targets": ["Lift 1"]})["change_id"]})
    events = list(session.events)
    effect = session.call("propose_change", {"action": "close", "targets": ["Lift 2"]})["effect"]
    assert effect["still_reachable"] is False and effect["lost_access_count"] > 0
    assert sum(floor["count"] for floor in effect["lost_access_by_floor"].values()) == effect["lost_access_count"]
    assert session.events == events  # a proposal highlights nothing
    assert "C2" in session.call("apply_change", {"change_id": "pending"})["error"]  # lists the real ids


def test_room_facts_skips_stacking_on_unaligned_buildings():
    swiss = next(Path(__file__).resolve().parent.parent.glob("data/train/swiss-1075"))
    session = BuildingSession.load(swiss)
    room = next(space for space in session.building.spaces.values() if space["type"] == "room")
    facts = session.call("room_facts", {"space": room["id"]})
    assert "error" not in facts and set(facts["stacked"]) == {"note"}
