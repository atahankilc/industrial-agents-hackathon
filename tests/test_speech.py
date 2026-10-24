"""Voice channel: speakable text for TTS, the voice style instruction, and the OpenAI-compatible endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from agent.guide import VOICE_STYLE, Guide, ungrounded
from agent.offline_llm import OfflineClient, message, text_block, tool_use
from agent.speech import speakable
from agent.tools import BuildingSession
from tests.test_guide import BUILDING, ScriptedClient, results

ROUTE_REPLY = (
    "Main lobby → Meeting room 3.07, step-free, about 124 m:\n"
    "1. Walk about 27 m through the door into **Corridor 0.01**.\n"
    "2. Take Lift 1 [proc-campus-train-000-V02] to Floor 3.\n"
    "- Rooms ≥ 0.8 m doors & 12 m2 storage"
)


def test_speakable_removes_markup_ids_and_symbols():
    spoken = speakable(ROUTE_REPLY)
    assert spoken == (
        "Main lobby to Meeting room 3.07, step-free, about 124 metres: Walk about 27 metres through the door into "
        "Corridor 0.01. Take Lift 1 to Floor 3. Rooms at least 0.8 metres doors and 12 square metres storage."
    )
    for leftover in ("*", "→", "[", "proc-campus", "1.", "≥", "&"):
        assert leftover not in spoken.replace("3.07", "").replace("0.01", "").replace("0.8", "")


def test_speakable_never_adds_numbers():
    corpus = ROUTE_REPLY
    assert ungrounded(speakable(ROUTE_REPLY), corpus) == []
    assert speakable("Room proc-campus-train-000-F3-S007 is on Floor 3") == "Room is on Floor 3."
    assert speakable("") == ""


@pytest.mark.parametrize("model, as_system", [("claude-opus-5-5", True), ("claude-sonnet-5-5", True),
                                               ("claude-sonnet-5", False), ("claude-haiku-4-5", False)])
def test_voice_style_placement(model, as_system):
    client = ScriptedClient([lambda request: message(text_block("Hello."))])
    guide = Guide(BuildingSession.load(BUILDING), client=client, model=model)
    turn = guide.reply("Hi there", channel="voice")
    messages = client.requests[0]["messages"]
    if as_system:  # mid-conversation system message right after the user turn: cached prefix untouched
        assert messages[-2] == {"role": "user", "content": "Hi there"}
        assert messages[-1] == {"role": "system", "content": VOICE_STYLE}
    else:
        assert messages[-1]["role"] == "user" and messages[-1]["content"].startswith(VOICE_STYLE)
    assert turn.spoken == "Hello."


def test_text_channel_is_unchanged():
    client = ScriptedClient([lambda request: message(text_block("**Hi**"))])
    guide = Guide(BuildingSession.load(BUILDING), client=client, model="claude-opus-5-5")
    turn = guide.reply("Hi")
    assert all(item["role"] != "system" for item in client.requests[0]["messages"])
    assert turn.spoken is None and turn.text == "**Hi**"
    with pytest.raises(ValueError):
        guide.reply("Hi", channel="fax")


def test_voice_route_turn_is_grounded_and_speakable():
    def directions(request):
        route = results(request)[0]
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(route["steps"][1:3], 1))
        return message(text_block(f"About {round(route['length_m'])} m:\n{steps}\nShall I continue?"))

    client = ScriptedClient([
        lambda request: message(tool_use("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})),
        directions,
    ])
    guide = Guide(BuildingSession.load(BUILDING), client=client, model="claude-sonnet-5-5")
    turn = guide.reply("How do I get to meeting room 3.07 from the main lobby?", channel="voice")
    assert turn.ungrounded == []
    assert turn.spoken.startswith("About 99 metres: Walk about 27 metres") and turn.spoken.endswith("continue?")
    assert "\n" not in turn.spoken and "[" not in turn.spoken
    # the voice system message stays in history; the next request still sees it before the tool round
    assert {"role": "system", "content": VOICE_STYLE} in client.requests[1]["messages"]


def test_completions_endpoint_speaks(monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    from backend.app import app

    client = TestClient(app)
    body = {"messages": [{"role": "user", "content": "from Main lobby to Meeting room 3.07"}]}
    reply = client.post("/v1/chat/completions", json=body, headers={"X-Session-Id": "voice-test"}).json()
    spoken = reply["choices"][0]["message"]["content"]
    assert "metres" in spoken and "[" not in spoken and "\n" not in spoken and "proc-campus" not in spoken
    stream = client.post("/v1/chat/completions", json={**body, "stream": True}, headers={"X-Session-Id": "voice-test"})
    chunks = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: {")]
    joined = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    assert joined.startswith("... ") and "\n" not in joined


def test_offline_client_ignores_system_messages():
    guide = Guide(BuildingSession.load(BUILDING), client=OfflineClient(), model="claude-opus-5-5")
    assert "Which one" in guide.reply("Where is the printer?", channel="voice").text
