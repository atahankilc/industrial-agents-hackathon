"""The dev panel's endpoints (backend/api/devtools.py): Guide tools run by hand, session state, reset."""

import pytest
from fastapi.testclient import TestClient

from backend.api.app import app

BUILDING = "proc-campus-train-000"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    return TestClient(app)


def new_session(client: TestClient) -> str:
    return client.post("/sessions", json={"building": BUILDING}).json()["session_id"]


def test_tools_lists_the_guide_tools(client):
    names = {tool["name"] for tool in client.get("/dev/tools").json()}
    assert {"find_route", "search", "locate", "set_profile", "propose_change", "apply_change"} <= names


def test_route_call_returns_result_and_an_event_with_legs_and_line(client):
    session = new_session(client)
    reply = client.post(f"/dev/sessions/{session}/tool",
                        json={"name": "find_route", "arguments": {"start": "outside", "destination": "Office 3.20"}}).json()
    assert reply["result"]["reachable"] is True
    [event] = reply["events"]
    assert event["type"] == "route" and event["legs"][-1]["kind"] == "arrive"
    floors = {point[2] for point in event["line"]}
    assert len(floors) > 1  # Office 3.20 is upstairs: the line visits more than one floor


def test_closing_a_lift_shows_in_state_and_plan_and_reset_clears_it(client):
    session = new_session(client)
    proposal = client.post(f"/dev/sessions/{session}/tool",
                           json={"name": "propose_change", "arguments": {"action": "close", "targets": ["Lift 1"]}}).json()
    change = proposal["result"]["change_id"]
    applied = client.post(f"/dev/sessions/{session}/tool", json={"name": "apply_change", "arguments": {"change_id": change}}).json()
    assert [event["type"] for event in applied["events"]] == ["change"]
    state = client.get(f"/dev/sessions/{session}/state").json()
    assert len(state["closed"]) == 1 and state["entrance_space"]
    assert client.get(f"/sessions/{session}/plan").json()["closed"] == state["closed"]
    client.post(f"/dev/sessions/{session}/reset")
    assert client.get(f"/dev/sessions/{session}/state").json()["closed"] == []


def test_unknown_tool_and_session(client):
    session = new_session(client)
    assert "error" in client.post(f"/dev/sessions/{session}/tool", json={"name": "nope"}).json()["result"]
    assert client.post("/dev/sessions/missing/tool", json={"name": "search", "arguments": {"query": "x"}}).status_code == 404
