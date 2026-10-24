"""The HTTP backend in offline mode (GUIDE_LLM=offline): sessions, chat, event cursor, OpenAI-compatible SSE."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.app import app, store

BUILDING = "train/proc-campus-train-000"
ROUTE = "from Main lobby to Meeting room 3.07"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    return TestClient(app)


def new_session(client: TestClient) -> str:
    response = client.post("/sessions", json={"building": BUILDING})
    assert response.status_code == 200
    return response.json()["session_id"]


def say(client: TestClient, session_id: str, message: str) -> dict:
    response = client.post("/chat", json={"session_id": session_id, "message": message})
    assert response.status_code == 200
    return response.json()


def sse_deltas(response) -> tuple[list[dict], list[str]]:
    lines = [line for line in response.text.split("\n") if line.startswith("data: ")]
    chunks = [json.loads(line[6:]) for line in lines if line != "data: [DONE]"]
    return chunks, lines


def test_health_and_buildings(client):
    assert client.get("/health").json() == {"ok": True, "llm": "offline"}
    ids = [item["id"] for item in client.get("/buildings").json()]
    assert BUILDING in ids and all(item.count("/") == 1 for item in ids)


@pytest.mark.parametrize("building", ["train/nope", "../pyproject.toml", "/etc", "train/../dev/x"])
def test_invalid_building_is_rejected(client, building):
    assert client.post("/sessions", json={"building": building}).status_code == 422
    session_id = new_session(client)
    assert client.put(f"/sessions/{session_id}/building", json={"building": building}).status_code == 422


def test_unknown_session_is_404(client):
    assert client.post("/chat", json={"session_id": "missing", "message": "hi"}).status_code == 404
    assert client.get("/sessions/missing").status_code == 404
    assert client.get("/events", params={"session_id": "missing"}).status_code == 404


def test_session_overview_and_find(client):
    created = client.post("/sessions", json={"building": BUILDING}).json()
    assert created["building"] == BUILDING and created["overview"]["floors"]
    turn = say(client, created["session_id"], "Where is the printer?")
    assert "print room" in turn["reply"].lower()
    assert turn["tool_calls"][0]["name"] == "locate" and turn["ungrounded"] == []


def test_route_event_via_cursor(client):
    session_id = new_session(client)
    say(client, session_id, "Where is the printer?")
    cursor = client.get("/events", params={"session_id": session_id}).json()["next"]
    turn = say(client, session_id, ROUTE)
    assert [event["type"] for event in turn["events"]] == ["route"]
    polled = client.get("/events", params={"session_id": session_id, "after": cursor}).json()
    assert [event["type"] for event in polled["events"]] == ["route"]
    assert client.get("/events", params={"session_id": session_id, "after": polled["next"]}).json()["events"] == []


def test_profile_and_confirmed_change(client):
    session_id = new_session(client)
    say(client, session_id, "I use a wheelchair")
    state = client.get(f"/sessions/{session_id}").json()
    assert state["profile"]["step_free"] is True and state["profile"]["summary"] == "step-free, doors at least 0.8 m wide (assumed)"
    say(client, session_id, ROUTE)
    say(client, session_id, "Lift 1 is broken")
    assert client.get(f"/sessions/{session_id}").json()["pending"] and not state["applied"]
    say(client, session_id, "yes")
    state = client.get(f"/sessions/{session_id}").json()
    assert [change["summary"] for change in state["applied"]] == ["close Lift 1"] and state["pending"] == []


def test_switch_building_keeps_id_and_resets_state(client):
    session_id = new_session(client)
    say(client, session_id, "I use a wheelchair")
    other = next(item["id"] for item in client.get("/buildings").json() if item["id"] != BUILDING)
    switched = client.put(f"/sessions/{session_id}/building", json={"building": other}).json()
    assert switched["session_id"] == session_id and switched["building"] == other
    assert switched["profile"]["step_free"] is False


def test_completions_non_stream(client):
    body = {"model": "guide", "user": "openai-plain", "messages": [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": [{"type": "text", "text": "Where is the printer?"}]}]}
    result = client.post("/v1/chat/completions", json=body).json()
    assert result["object"] == "chat.completion" and result["model"] == "guide"
    choice = result["choices"][0]
    assert choice["message"]["role"] == "assistant" and choice["finish_reason"] == "stop"
    assert "print room" in choice["message"]["content"].lower()


def test_completions_stream(client):
    body = {"stream": True, "session_id": "stream-test",
            "messages": [{"role": "user", "content": "Where is the printer?"}]}
    with client.stream("POST", "/v1/chat/completions", json=body) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        response.read()
    chunks, lines = sse_deltas(response)
    assert lines[-1] == "data: [DONE]"
    assert chunks[0]["object"] == "chat.completion.chunk"
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant", "content": "... "}
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    spoken = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks[1:])
    assert "print room" in spoken.lower()


def test_session_header_persists_across_completions(client):
    headers = {"X-Session-Id": "voice-call-1"}
    first = {"messages": [{"role": "user", "content": "I use a wheelchair"}]}
    client.post("/v1/chat/completions", json=first, headers=headers)
    second = {"messages": [{"role": "user", "content": "I use a wheelchair"},
                           {"role": "user", "content": ROUTE}]}
    reply = client.post("/v1/chat/completions", json=second, headers=headers).json()
    assert "step-free" in reply["choices"][0]["message"]["content"]
    assert client.get("/sessions/voice-call-1").json()["profile"]["step_free"] is True


def test_points_export(client):
    session_id = new_session(client)
    response = client.get(f"/sessions/{session_id}/points")
    assert response.status_code == 200
    export = response.json()
    assert export["count"] > 0 and len(export["points"]["kind"]) == export["count"]
    assert export["connectors"] and export["openings"] and export["closed"] == []
    assert client.get("/sessions/missing/points").status_code == 404


def test_points_are_gzipped(client):
    session_id = new_session(client)
    response = client.get(f"/sessions/{session_id}/points", headers={"Accept-Encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"


def test_route_event_has_vertices(client):
    session_id = new_session(client)
    turn = say(client, session_id, ROUTE)
    route = next(event for event in turn["events"] if event["type"] == "route")
    assert len(route["vertices"]) >= 2 and all(len(vertex) == 4 for vertex in route["vertices"])
    polled = client.get("/events", params={"session_id": session_id}).json()["events"]
    assert next(event for event in polled if event["type"] == "route")["vertices"] == route["vertices"]


def test_change_event_has_space_ids_and_points_update(client):
    session_id = new_session(client)
    before = client.get(f"/sessions/{session_id}/points").json()
    say(client, session_id, ROUTE)
    say(client, session_id, "Lift 1 is broken")
    turn = say(client, session_id, "yes")
    change = next(event for event in turn["events"] if event["type"] == "change")
    lift = next(item for item in before["connectors"] if item["name"] == "Lift 1")
    assert change["space_ids"] == [before["spaces"][index]["id"] for index in lift["spaces"]]
    assert client.get(f"/sessions/{session_id}/points").json()["closed"] == [lift["id"]]
    polled = client.get("/events", params={"session_id": session_id}).json()["events"]
    assert next(event for event in polled if event["type"] == "change")["space_ids"] == change["space_ids"]
    raw = store.get(session_id).session.events  # the enrichment works on copies
    assert all("vertices" not in event and "space_ids" not in event for event in raw if event["type"] != "highlight")
