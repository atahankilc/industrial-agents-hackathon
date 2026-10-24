"""Turn-by-turn legs (core/directions.py) for the camera walk mode and route cards."""

from pathlib import Path

import pytest

from agent.tools import BuildingSession
from core.directions import heading_change, route_legs, turn_word

BUILDING = Path("data/train/proc-campus-train-000")


@pytest.fixture(scope="module")
def session() -> BuildingSession:
    return BuildingSession.load(BUILDING)


def test_heading_change_sign_and_words():
    assert heading_change((0, 0), (1, 0), (1, 1)) == pytest.approx(90)  # east then north = left
    assert heading_change((0, 0), (1, 0), (1, -1)) == pytest.approx(-90)
    assert heading_change((0, 0), (0, 0), (1, 1)) is None
    assert [turn_word(d) for d in (None, 10, -10, 90, -90, 170)] == \
        ["straight", "straight", "straight", "left", "right", "back"]


def test_legs_follow_the_route_and_match_kit_steps(session):
    route = session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    legs = route_legs(session.building, route["space_path"], route["element_path"])
    assert legs[-1]["kind"] == "arrive" and legs[-1]["to_id"] == route["space_path"][-1]
    assert all(leg["to_id"] in route["space_path"] for leg in legs)
    # the kit's "Walk about N m … into X" lines carry the same rounded distances
    kit = [line for line in route["steps"] if line.startswith("Walk about")]
    ours = [f"{leg['distance_m']:.0f} m" for leg in legs if leg["kind"] == "door"]
    assert [line.split("Walk about ")[1].split(" m")[0] + " m" for line in kit] == ours
    # ground → floor 3 on one staircase is a single leg
    hops = [leg for leg in legs if leg["kind"] == "connector"]
    assert len(hops) == 1 and hops[0]["up"] and hops[0]["floors"] == 3


def test_route_event_carries_legs():
    from fastapi.testclient import TestClient

    from backend.app import app
    client = TestClient(app)
    session_id = client.post("/sessions", json={"building": "train/proc-campus-train-000"}).json()["session_id"]
    client.post("/chat", json={"session_id": session_id, "message": "from Main lobby to Meeting room 3.07"})
    route = [e for e in client.get("/events", params={"session_id": session_id}).json()["events"] if e["type"] == "route"]
    assert route and route[-1]["legs"][-1]["kind"] == "arrive"
