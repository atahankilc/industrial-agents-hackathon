"""Voice channel: speakable text for TTS, the voice style instruction, and the OpenAI-compatible endpoint."""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient

from agent.guide import VOICE_STYLE, Guide, ungrounded
from agent.offline_llm import OfflineClient, message, text_block, tool_use
from agent.speech import SpokenStream, sentences, speakable
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
    assert turn.spoken.startswith("About 58 metres: Walk about 3 metres") and turn.spoken.endswith("continue?")
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


# ---------- speaking while the reply is written (SpokenStream) ----------


def test_sentences_keep_decimals_and_list_markers():
    assert sentences("Room 3.07 is on Floor 3. Go!\n1. Walk 27 m.\n2. Turn") == [
        "Room 3.07 is on Floor 3.", " Go!", "\n", "1. Walk 27 m.", "\n", "2. Turn"]
    assert sentences("Floor 3.") == ["Floor 3."]  # no whitespace yet: the model may still be writing "3.07"


def test_spoken_stream_says_grounded_sentences_as_they_complete():
    said = []
    stream = SpokenStream(said.append, lambda sentence: "99" not in sentence)
    stream.feed("Let me check.")
    assert said == []  # not before whitespace follows the period
    for char in " Room 3.07 is on **Floor 3**. It is 99 m away. Bye.":
        stream.feed(char)
    stream.end_block()
    assert said == ["Let me check.", "Room 3.07 is on Floor 3."]  # held from the ungrounded sentence on
    stream.finish("Let me check. Room 3.07 is on Floor 3. It is 40 m away. Bye.")
    assert said == ["Let me check.", "Room 3.07 is on Floor 3.", "It is 40 metres away.", "Bye."]


def test_spoken_stream_finish_after_a_rewritten_reply_says_only_what_is_new():
    said = []
    stream = SpokenStream(said.append, lambda sentence: True)
    stream.feed("One moment. ")
    stream.hold()
    stream.feed("Never said live. ")
    stream.finish("One moment.\n\nTake Lift 1. One moment.")
    assert said == ["One moment.", "Take Lift 1.", "One moment."]  # a repeat later in the reply is still said


class StreamingClient(anthropic.Anthropic):
    """A real client type whose `beta.messages.stream` replays scripted text deltas (no network)."""

    def __init__(self, replies: list[list[str]]) -> None:
        super().__init__(api_key="test")
        self.replies = replies = list(replies)
        self.delivered: list[str] = []  # every delta handed to the Guide, in order
        create = lambda **request: message(text_block("".join(replies.pop(0))))  # the non-streaming path
        fake = SimpleNamespace(stream=self.stream, create=create)
        object.__setattr__(self, "beta", SimpleNamespace(messages=fake))

    @contextmanager
    def stream(self, **request):
        deltas = self.replies.pop(0)
        client = self

        class Stream:
            def __iter__(self):
                for delta in deltas:
                    client.delivered.append(delta)
                    yield SimpleNamespace(type="content_block_delta",
                                          delta=SimpleNamespace(type="text_delta", text=delta))
                yield SimpleNamespace(type="content_block_stop")

            def get_final_message(self):
                return message(text_block("".join(deltas)))

        yield Stream()


def test_guide_streams_voice_sentences_while_the_model_writes(monkeypatch):
    monkeypatch.setenv("GUIDE_REWRITER", "off")
    client = StreamingClient([["The kitchen is on ", "the ground floor. ", "Shall I ", "take you there?"]])
    guide = Guide(BuildingSession.load(BUILDING), client=client)
    said = []
    guide.on_say = lambda text: said.append((text, len(client.delivered)))
    turn = guide.reply("Where is the kitchen?", channel="voice")
    assert said == [("The kitchen is on the ground floor.", 2), ("Shall I take you there?", 4)]
    assert turn.spoken == "The kitchen is on the ground floor. Shall I take you there?"
    assert guide.speech is None
    guide.on_say = None
    client.replies.append(["Fine."])
    assert guide.reply("ok", channel="voice").text == "Fine."  # no listener: the plain request path


def test_guide_holds_live_speech_until_the_grounding_repair():
    client = ScriptedClient([
        lambda request: message(text_block("One moment. The kitchen is 77 m away.")),
        lambda request: message(text_block("One moment. The kitchen is on the ground floor.")),
    ])
    guide = Guide(BuildingSession.load(BUILDING), client=client)
    said = []
    guide.on_say = said.append
    turn = guide.reply("Where is the kitchen?", channel="voice")
    assert len(client.requests) == 2  # the repair round ran
    assert said == ["One moment.", "The kitchen is on the ground floor."]  # "77 m" was never said
    assert turn.ungrounded == []


def test_guide_holds_live_speech_when_the_profile_safety_net_may_redo_the_reply():
    client = ScriptedClient([lambda request: message(text_block("Noted."))])
    guide = Guide(BuildingSession.load(BUILDING), client=client)
    said = []
    guide.on_say = said.append
    turn = guide.reply("I use a wheelchair", channel="voice")
    assert said and " ".join(said) == turn.spoken  # all said at the end, the confirmation line included
