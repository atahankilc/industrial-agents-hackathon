"""Guide loop, prompt and REPL, tested offline with a scripted fake Claude client (no API calls)."""

from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2

from agent.guide.__main__ import repl
from agent.guide.guide import Guide
from agent.guide.prompt import system_blocks
from agent.guide.tools import TOOLS
from core.building_map import BuildingMap

CAMPUS = Path("data/dev/proc-campus-dev-001")


def usage() -> SimpleNamespace:
    return SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=None,
                           cache_creation_input_tokens=None)


def text_reply(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason, usage=usage())


def tool_reply(name: str, args: dict, call_id: str = "toolu_1") -> SimpleNamespace:
    content = [SimpleNamespace(type="thinking", thinking="...", signature="sig"),
               SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)]
    return SimpleNamespace(content=content, stop_reason="tool_use", usage=usage())


class FakeClient:
    """Returns the queued replies in order and records every create(**kwargs) call (messages frozen per call)."""

    def __init__(self, *replies: SimpleNamespace, raises: Exception | None = None) -> None:
        self.replies = list(replies)
        self.raises = raises
        self.calls: list[dict] = []
        self.replies_sent: list[SimpleNamespace] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(dict(kwargs, messages=list(kwargs["messages"])))
        if self.raises:
            raise self.raises
        reply = self.replies.pop(0)
        self.replies_sent.append(reply)
        return reply


def test_tool_round_then_answer():
    client = FakeClient(tool_reply("locate", {"thing": "3D printer"}),
                        text_reply("The 3D printers are in Makerspace 1.14 (1.14) and Lab 2.20 (2.20)."))
    result = Guide(CAMPUS, client).turn("Where is the 3D printer?")
    assert result.grounded and not result.asked
    assert "proc-campus-dev-001-F1-S014" in result.space_ids
    assert len(result.asset_ids) == 5 and result.tool_calls[0]["name"] == "locate"
    second = client.calls[1]
    assert second["messages"][-1]["content"][0]["type"] == "tool_result"        # all results in one user message
    assert second["messages"][-2]["content"] is client.replies_sent[0].content   # full content appended


def test_request_shape():
    client = FakeClient(text_reply("Hello."))
    Guide(CAMPUS, client).turn("hi")
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["tools"] == TOOLS
    assert call["betas"] == ["server-side-fallback-2026-07-01"] and call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "medium"}
    assert "thinking" not in call and "tool_choice" not in call
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_system_blocks_are_stable_and_hold_no_room_facts():
    bmap = BuildingMap.load(CAMPUS)
    blocks = system_blocks(bmap)
    assert blocks == system_blocks(BuildingMap.load(CAMPUS))
    assert len(blocks) == 2 and "cache_control" not in blocks[0]
    overview = blocks[1]["text"]
    assert "Lift 1" in overview and "makerspace" in overview and "3d_printer" in overview
    assert "Makerspace 1.14" not in overview


def test_ungrounded_reply_gets_one_repair_then_fallback():
    client = FakeClient(tool_reply("place_info", {"place": "1.14"}), text_reply("It is 999 m²."),
                        text_reply("Still 999 m²."))
    result = Guide(CAMPUS, client).turn("How big is 1.14?")
    assert len(client.calls) == 3 and "999" in client.calls[2]["messages"][-1]["content"]
    assert not result.grounded and "999" not in result.text and "1.14" in result.text   # fallback from summaries


def test_ambiguous_turn_reports_options_and_asked():
    client = FakeClient(tool_reply("route", {"to": "3D printer", "from": "Main lobby", "via": None, "step_free": None}),
                        text_reply("There are 3D printers in Makerspace 1.14 (Floor 1) and Lab 2.20 (Floor 2). "
                                   "Which one?"))
    result = Guide(CAMPUS, client).turn("Take me to the 3D printer, I'm in the main lobby")
    assert result.asked and len(result.options) == 2


def test_ok_route_reports_route_and_connectors():
    client = FakeClient(tool_reply("route", {"to": "1.14", "from": "Main lobby", "via": None, "step_free": None}),
                        text_reply("Take Staircase 2 up to Floor 1; about 94 m."))
    result = Guide(CAMPUS, client).turn("How do I get from the main lobby to 1.14?")
    assert result.grounded and len(result.routes) == 1
    assert result.routes[0]["space_path"][-1] == "proc-campus-dev-001-F1-S014"
    assert result.connector_ids == ["proc-campus-dev-001-V03"]
    assert "proc-campus-dev-001-F0-S001" in result.space_ids


def test_session_survives_turns():
    client = FakeClient(tool_reply("update_session", {"position": "Main lobby", "step_free": True, "close": None,
                                                      "reopen": None}),
                        text_reply("Noted — step-free routes from now on."), text_reply("Hi again."))
    g = Guide(CAMPUS, client)
    g.turn("I'm in a wheelchair, in the main lobby")
    g.turn("hello")
    assert g.session.step_free and g.session.position == "proc-campus-dev-001-F0-S014"
    assert len(client.calls[2]["messages"]) == 5     # user, assistant(tool_use), user(tool_result), assistant, user


def test_follow_up_may_restate_earlier_tool_numbers():
    client = FakeClient(tool_reply("place_info", {"place": "1.14"}), text_reply("Makerspace 1.14 holds tools."),
                        text_reply("As I said, it is Makerspace 1.14."))
    g = Guide(CAMPUS, client)
    g.turn("Tell me about 1.14")
    assert g.turn("Which room was that?").grounded and len(client.calls) == 3


def test_refusal_falls_back_to_tool_summaries():
    client = FakeClient(tool_reply("locate", {"thing": "3D printer"}), text_reply("", stop_reason="refusal"))
    result = Guide(CAMPUS, client).turn("Where is the 3D printer?")
    assert "Makerspace 1.14" in result.text and not result.grounded


def test_too_many_tool_rounds_falls_back():
    client = FakeClient(*[tool_reply("locate", {"thing": "3D printer"})] * 9)
    result = Guide(CAMPUS, client).turn("loop")
    assert result.text and len(client.calls) == 8


def test_blank_turn_makes_no_call():
    client = FakeClient()
    result = Guide(CAMPUS, client).turn("   ")
    assert result.text == "" and client.calls == []


def test_repl_ignores_blank_input_and_survives_api_errors(capsys):
    client = FakeClient(raises=anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")))
    guide = Guide(CAMPUS, client)
    repl(guide, ["", "   ", "hi"])                      # agent.guide.__main__.repl
    assert len(client.calls) == 1 and "error" in capsys.readouterr().out.lower()
    assert guide.messages == []        # failed turn rolled back, session still usable


def test_repl_prints_tools_and_cost(capsys):
    client = FakeClient(tool_reply("locate", {"thing": "3D printer"}), text_reply("In Makerspace 1.14."))
    repl(Guide(CAMPUS, client), ["Where is the 3D printer?"], show_tools=True)
    out = capsys.readouterr().out
    assert "locate" in out and "In Makerspace 1.14." in out and "$" in out


def test_tools_fit_the_strict_union_limit():
    """The API rejects strict tool sets with more than 16 nullable/union parameters (found in the live smoke test)."""
    unions = sum("anyOf" in prop or isinstance(prop.get("type"), list)
                 for tool in TOOLS for prop in tool["input_schema"]["properties"].values())
    assert unions <= 16


def test_cut_off_tool_use_gets_error_results_so_next_turn_is_valid():
    cut = tool_reply("locate", {"thing": "3D printer"}, call_id="toolu_cut")
    cut.stop_reason = "max_tokens"
    client = FakeClient(cut, text_reply("Hi."))
    g = Guide(CAMPUS, client)
    assert not g.turn("Where is the 3D printer?").grounded
    g.turn("hello")
    sent = client.calls[1]["messages"]
    used = {b.id for m in sent if m["role"] == "assistant" for b in m["content"] if b.type == "tool_use"}
    answered = {b["tool_use_id"] for m in sent if m["role"] == "user" and isinstance(m["content"], list)
                for b in m["content"] if b["type"] == "tool_result" and b["is_error"]}
    assert used == answered == {"toolu_cut"}
    assert [m["role"] for m in sent] == ["user", "assistant", "user", "user"]


def test_any_tool_exception_becomes_an_error_result(monkeypatch):
    def boom(*_args):
        raise RuntimeError("core blew up")

    monkeypatch.setattr("agent.guide.guide.run_tool", boom)
    client = FakeClient(tool_reply("locate", {"thing": "3D printer"}), text_reply("Sorry, that failed."))
    result = Guide(CAMPUS, client).turn("Where is the 3D printer?")
    answer = client.calls[1]["messages"][-1]["content"][0]
    assert answer["tool_use_id"] == "toolu_1" and answer["is_error"] and "core blew up" in answer["content"]
    assert result.tool_calls[0]["status"] == "error" and result.text == "Sorry, that failed."


def test_any_exception_rolls_the_turn_back(monkeypatch):
    client = FakeClient(tool_reply("update_session", {"position": "Main lobby", "step_free": True, "close": None,
                                                      "reopen": None}), text_reply("Noted."))
    g = Guide(CAMPUS, client)
    monkeypatch.setattr("agent.guide.guide.ungrounded", lambda *_a: (_ for _ in ()).throw(RuntimeError("bug")))
    try:
        g.turn("I'm in a wheelchair in the main lobby")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the exception to propagate")
    assert g.messages == [] and g.tool_results == [] and g.session.step_free is False and g.session.position is None


def test_repl_survives_any_exception(capsys):
    client = FakeClient(raises=RuntimeError("unexpected"))
    guide = Guide(CAMPUS, client)
    repl(guide, ["hi", "again"])
    out = capsys.readouterr().out
    assert out.count("error: unexpected") == 2 and len(client.calls) == 2 and guide.messages == []


def test_prompt_rules_for_constraints_and_clarifying_questions():
    from agent.guide.prompt import RULES
    text = " ".join(RULES.split())
    assert "only after update_session returned ok" in text.lower()
    assert "at most 3" in text and "door is closed" not in text
    session_tool = next(t for t in TOOLS if t["name"] == "update_session")
    assert "doors" not in session_tool["description"].split("(")[0]
