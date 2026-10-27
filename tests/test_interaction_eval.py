"""Interaction eval (scripts/interaction_eval.py) offline: scenario files, the simulated user / judge plumbing with a
fake client, and one full run with the offline Guide. The live run is the script itself."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agents.offline_llm import OfflineClient
from scripts.interaction_eval import (CRITERIA, SCENARIOS, SimulatedUser, load_scenario, run_scenario,
                                      transcript_text)

FILES = sorted(SCENARIOS.glob("*.json"))


class FakeClient:
    """`messages.create` answers with the next scripted JSON object as a text block."""

    def __init__(self, replies: list[dict]) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **request: object) -> object:
        self.requests.append({**request, "messages": list(request["messages"])})
        reply = self.replies.pop(0)
        usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0)
        if reply == "refusal":
            return SimpleNamespace(content=[], stop_reason="refusal", usage=usage)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(reply))], stop_reason="end_turn",
                               usage=usage)


def verdict(score: int = 4) -> dict:
    return {**{name: {"score": score, "evidence": "e"} for name in CRITERIA}, "goal_reached": True, "issues": []}


def args(**overrides: object) -> argparse.Namespace:
    return argparse.Namespace(**{"model": None, "effort": None, "user_model": "claude-opus-5-5",
                                 "judge_model": "claude-opus-5-5", "judge_effort": "medium", **overrides})


def test_scenario_files_are_valid():
    assert len(FILES) >= 6
    for path in FILES:
        scenario = load_scenario(path)
        assert (Path(scenario["building"]) / "building.json").exists(), path
        assert scenario["persona"].strip() and scenario["goal"].strip(), path
    assert any(load_scenario(path)["channel"] == "voice" for path in FILES)


def test_unknown_or_missing_scenario_keys_are_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"building": "x", "persona": "p", "goal": "g", "nope": 1}))
    with pytest.raises(ValueError, match="nope"):
        load_scenario(bad)
    bad.write_text(json.dumps({"building": "x", "persona": "p"}))
    with pytest.raises(ValueError, match="goal"):
        load_scenario(bad)


def test_simulated_user_flips_roles_and_keeps_its_own_replies():
    client = FakeClient([{"message": "Where is the coffee?", "done": False, "goal_reached": False}])
    user = SimulatedUser(load_scenario(FILES[0]), client, "claude-opus-5-5")
    assert user.next()["message"] == "Where is the coffee?"
    user.hear("Where are you now?")
    roles = [message["role"] for message in user.messages]
    assert roles == ["user", "assistant", "user"]
    request = client.requests[0]
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert "Your goal" in request["system"][1]["text"]


def test_full_run_with_offline_guide_scores_and_stops_when_done():
    scenario = FILES[0]
    client = FakeClient([
        {"message": "I'm in the main lobby. Where can I get a coffee?", "done": False, "goal_reached": False},
        {"message": "", "done": True, "goal_reached": True},
        verdict(4),
    ])
    run = run_scenario(scenario, OfflineClient(), client, args())
    assert run.error is None and len(run.turns) == 1
    assert run.user_goal_reached and run.scores() == {name: 4 for name in CRITERIA}
    judged = client.requests[-1]["messages"][0]["content"]
    assert "USER: I'm in the main lobby" in judged and "GUIDE" in judged


def test_refusal_is_reported_as_an_error_not_a_score():
    run = run_scenario(FILES[0], OfflineClient(), FakeClient(["refusal"]), args())
    assert run.verdict is None and "refusal" in run.error


def test_transcript_marks_spoken_replies_and_ungrounded_values():
    text = transcript_text([{"user": "the press", "reply": "1. Go…", "spoken": "Go left.", "tools": ["locate(…)"],
                             "ungrounded": ["42"]}])
    assert "GUIDE (spoken): Go left." in text and "UNGROUNDED: ['42']" in text and "TOOLS: locate" in text


def test_tool_line_shows_the_result_and_cuts_long_ones():
    from scripts.interaction_eval import TOOL_RESULT_CHARS, tool_line

    route = {"name": "find_route", "input": {"start": "a"}, "result": {
        "length_m": 12.5, "steps": ["Walk 5 m"], "space_path": ["x"], "element_path": ["y"]}}
    line = tool_line(route)
    assert '"steps":["Walk 5 m"]' in line and "space_path" not in line
    long = {"name": "search", "input": {}, "result": {"results": ["r" * 50] * 100}}
    assert tool_line(long).endswith("…(cut)") and len(tool_line(long)) < TOOL_RESULT_CHARS + 100
