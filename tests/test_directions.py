"""Turn-by-turn legs (backend/core/directions.py) for the camera walk mode and route cards."""

from pathlib import Path

import pytest

from backend.agents.tools import BuildingSession
from backend.core.directions import about_m, guidance, guidance_steps, heading_change, landmark, maneuvers, route_legs, turn_word

BUILDING = Path("data/buildings/proc-campus-train-000")


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
    # the kit's "Walk about N m … into X" lines (backend.core.navigation; the Guide's tool now gives guidance steps)
    from backend.core import navigation
    kit_route = navigation.find_route(session.building, route["space_path"][0], route["space_path"][-1]).to_dict()
    assert kit_route["length_m"] == route["length_m"]
    kit = [line for line in kit_route["steps"] if line.startswith("Walk about")]
    ours = [leg["distance_m"] for leg in legs if leg["kind"] == "door"]
    assert len(kit) == len(ours)  # one step per door, the same metres as the kit's step text
    assert all(abs(int(line.split("Walk about ")[1].split(" m")[0]) - metres) <= 0.55 for line, metres in zip(kit, ours))
    # door legs + stair/lift costs = the route's length (kit 1.1.0 walks, not straight lines)
    graph = session.building.graph(False)
    rides = sum(min(e["weight"] for e in graph.get_edge_data(a, b).values() if e.get("via") == v)
                for a, b, v in zip(route["space_path"], route["space_path"][1:], route["element_path"])
                if v in session.building.connectors)
    assert sum(ours) + rides == pytest.approx(route["length_m"], abs=0.05 * len(ours) + 0.01)
    # ground → floor 3 on one staircase is a single leg
    hops = [leg for leg in legs if leg["kind"] == "connector"]
    assert len(hops) == 1 and hops[0]["up"] and hops[0]["floors"] == 3


def test_route_event_carries_legs():
    from fastapi.testclient import TestClient

    from backend.api.app import app
    client = TestClient(app)
    session_id = client.post("/sessions", json={"building": "proc-campus-train-000"}).json()["session_id"]
    client.post("/chat", json={"session_id": session_id, "message": "from Main lobby to Meeting room 3.07"})
    route = [e for e in client.get("/events", params={"session_id": session_id}).json()["events"] if e["type"] == "route"]
    assert route and route[-1]["legs"][-1]["kind"] == "arrive"


def test_about_m_rounds_like_a_person():
    assert [about_m(m) for m in (0.4, 5.2, 9.6, 26, 27.6, 85.15, 97.03, 148.38)] == [1, 5, 10, 25, 30, 85, 95, 150]


def test_guidance_steps_have_turns_landmarks_rounded_metres_and_no_ids(session):
    route = session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    steps = route["steps"]
    assert steps == guidance_steps(session.building, route["space_path"], route["element_path"])
    assert steps[0] == "Start in Main lobby (Ground floor)." and steps[-1].startswith("You have arrived at Meeting room")
    assert "Walk about 3 m through the door (by the reception desk) into Corridor 0.01." in steps
    assert any(step.startswith(("Turn left", "Turn right")) for step in steps)
    assert sum(step.startswith("Take Staircase") for step in steps) == 1  # one line for ground → floor 3
    assert not any("proc-campus" in step or "[" in step for step in steps)
    assert route["about_m"] == about_m(route["length_m"])


def test_guidance_is_the_same_steps_as_data(session):
    route = session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    data = guidance(session.building, route["space_path"], route["element_path"])
    assert [step["text"] for step in data] == route["steps"][1:]  # everything after the "Start in …" line
    assert [step["kind"] for step in data] == [leg["kind"] for leg in route_legs(session.building, route["space_path"], route["element_path"])]
    walked = [step for step in data if step["kind"] in ("door", "exit") and step["metres"]]
    assert all(step["text"].startswith({"straight": "Walk", "left": "Turn left", "right": "Turn right", "back": "Turn around"}[step["turn"]])
               for step in walked)
    assert any(step["landmark"] == "reception desk" for step in data)
    assert sum(step["kind"] == "connector" for step in data) == 1 and data[-1]["kind"] == "arrive"


def test_landmark_is_a_recognisable_item_next_to_the_door(session):
    building = session.building
    marked = {landmark(building, opening) for opening in building.openings}
    assert "reception desk" in marked and None in marked
    assert not marked & {"chair", "desk", "office chair"}


def test_tour_legs_get_guidance_steps(session):
    tour = session.call("tour", {"stops": ["Main lobby", "Meeting room 3.07", "Main lobby"]})
    assert tour["reachable"] and tour["about_m"] == about_m(tour["length_m"])
    assert all(leg["steps"][0].startswith("Start in") and "[" not in " ".join(leg["steps"]) for leg in tour["legs"])


def test_maneuvers_join_straight_doors_and_cover_every_leg(session):
    route = session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    steps = guidance(session.building, route["space_path"], route["element_path"])
    moves = maneuvers(steps)
    assert [move["text"] for move in moves] == route["steps"][1:]  # the Guide says the card's steps
    assert sum(move["legs"] for move in moves) == len(steps)  # the app places each step on the route line by legs
    assert moves[-1]["kind"] == "arrive"
    for before, move in zip(moves, moves[1:]):  # a straight door on the same floor never starts a step
        assert not (move["kind"] == "door" and move["turn"] == "straight" and before["kind"] == "door"
                    and before["floor"] == move["floor"])


def test_maneuvers_text_for_joined_doors():
    door = {"kind": "door", "floor": "Ground floor", "door": "door"}
    steps = [{**door, "turn": "left", "metres": 4, "distance_m": 4.2, "to": "A", "to_id": "a", "landmark": None},
             {**door, "turn": "straight", "metres": 2, "distance_m": 2.4, "to": "B", "to_id": "b", "landmark": "lift sign"},
             {"kind": "arrive", "turn": "straight", "metres": 0, "to": "B", "to_id": "b", "floor": "Ground floor", "text": "You have arrived."}]
    moves = maneuvers(steps)
    assert [move["legs"] for move in moves] == [2, 1]
    assert moves[0]["text"] == "Turn left and walk about 7 m through 2 doors into B (the last one by the lift sign)."
    assert moves[0]["metres"] == 7 and moves[0]["to_id"] == "b"
