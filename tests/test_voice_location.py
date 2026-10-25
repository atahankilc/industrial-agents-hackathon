"""Talking to the map: "I'm in …" places the user (set_my_location → `location` event, "here" for routes), and a
room selected on the plan reaches the Guide with the question (`selected` → a selection note)."""

from pathlib import Path

import pytest

from agent.guide import Guide
from agent.tools import BuildingSession
from tests.test_backend import BUILDING, client, new_session  # noqa: F401  (client is a fixture)
from tests.test_guide import ScriptedClient, say

DATA = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"


@pytest.fixture
def session() -> BuildingSession:
    return BuildingSession.load(DATA)


def space_named(session: BuildingSession, name: str) -> str:
    return next(space_id for space_id, space in session.building.spaces.items() if space["name"] == name)


def test_set_my_location_makes_here_and_emits_the_figure(session):
    result = session.call("set_my_location", {"place": "Main lobby"})
    lobby = space_named(session, "Main lobby")
    assert result["location"]["space_id"] == lobby
    assert session.events[-1] == {"type": "location", "space_id": lobby}
    route = session.call("find_route", {"start": "here", "destination": "Meeting room 3.07"})
    assert route["reachable"]
    assert session.call("set_my_location", {"place": "no such room at all"}).get("error")


def test_selection_note_tells_the_guide_what_this_means(session):
    guide = Guide(session, client=ScriptedClient([say("Meeting room 3.07 is on Floor 3."), say("Still Floor 3.")]))
    room = space_named(session, "Meeting room 3.07")
    guide.reply("How do I get there?", selected=room)
    sent = guide.messages[0]["content"]
    assert "[selection note" in sent and "Meeting room 3.07" in sent and sent.endswith("How do I get there?")
    guide.reply("And now?", selected="not-an-id")  # unknown ids are ignored
    assert "[selection note" not in guide.messages[-2]["content"]


def test_offline_guide_places_the_user_then_routes_from_here(client):  # noqa: F811
    session_id = new_session(client)
    placed = client.post("/chat", json={"session_id": session_id, "message": "I'm in the Main lobby"}).json()
    assert [event["type"] for event in placed["events"]] == ["location"]
    assert "Main lobby" in placed["reply"]
    routed = client.post("/chat", json={"session_id": session_id, "message": "Take me to Meeting room 3.07"}).json()
    assert any(event["type"] == "route" for event in routed["events"])
    both = client.post("/chat", json={"session_id": session_id,
                                      "message": "I am at Meeting room 3.07 and want to go to Main lobby"}).json()
    assert [event["type"] for event in both["events"]][:2] == ["location", "route"]


def test_chat_passes_the_selection(client):  # noqa: F811
    session_id = new_session(client)
    plan = client.get(f"/sessions/{session_id}/plan").json()
    room = next(space for space in plan["spaces"] if space["name"] == "Meeting room 3.07")
    response = client.post("/chat", json={"session_id": session_id, "message": "where is it", "selected": room["id"]})
    assert response.status_code == 200


def test_the_figure_point_moves_only_where_the_route_line_starts(client):  # noqa: F811
    session_id = new_session(client)
    plan = client.get(f"/sessions/{session_id}/plan").json()
    lobby = next(space for space in plan["spaces"] if space["name"] == "Main lobby")
    standing = [lobby["label"][0] + 0.3, lobby["label"][1]]
    placed = client.put(f"/sessions/{session_id}/location", json={"space_id": lobby["id"], "point": standing}).json()
    assert placed["location"]["point"] == [round(standing[0], 3), round(standing[1], 3)]
    routed = client.post("/chat", json={"session_id": session_id, "message": "Take me to Meeting room 3.07"}).json()
    route = next(event for event in routed["events"] if event["type"] == "route")
    assert route["line"][0][:2] == placed["location"]["point"]
    off = client.put(f"/sessions/{session_id}/location", json={"space_id": lobby["id"], "point": [1e6, 1e6]}).json()
    assert "point" not in off["location"]  # a point outside the room is not kept
