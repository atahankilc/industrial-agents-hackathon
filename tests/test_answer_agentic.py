"""agent.answer and the benchmark runner with the agentic layers, offline: reworded route questions answered from
LLM slots, questions the parser hands over answered by the solver agent, and a second run with no model at all that
reproduces the first from the decision cache (what the organisers get when they re-run our command without a key)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent import llm_parser, solver_agent
from agent.answer import respond
from agent.run_benchmark_v1 import run
from tests.test_parsing_modes import FakeClient, response

FACTORY = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"


def place(name: str) -> dict:
    return {"name": name, "floor": None, "is_item": False}


def slots(**values: object) -> str:
    base = dict.fromkeys(["start", "first", "second", "destination", "stops", "floor", "room_type", "asset_type",
                          "min_width_m", "item", "closed", "direction", "may_use_stairs", "step_free", "forklift",
                          "closures"])
    base.update(kind="route", asks_for="route")
    base.update(values)
    return json.dumps(base)


def tool_use(name: str, arguments: dict) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", id="t1", name=name, input=arguments)],
                           stop_reason="tool_use", usage=usage)


def submission(number: float) -> SimpleNamespace:
    return tool_use("submit_answer", {"answer_type": "number", "number": number, "unit": None, "space_id": None,
                                      "text": None, "explanation": "Counted the rooms on Floor 1."})


def no_model():
    raise RuntimeError("no API access in this run")


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    cache = tmp_path / "decisions.json"
    monkeypatch.setenv("PARSER_MODE", "hybrid")
    monkeypatch.setenv("LLM_CACHE", str(cache))
    monkeypatch.setattr(solver_agent, "RUNS", 1)
    monkeypatch.setattr(llm_parser, "make_client", no_model)
    monkeypatch.setattr(solver_agent, "make_client", no_model)
    return cache


def use_models(monkeypatch: pytest.MonkeyPatch, parser: FakeClient | None = None,
               agent: FakeClient | None = None) -> None:
    if parser is not None:
        monkeypatch.setattr(llm_parser, "make_client", lambda: parser)
    if agent is not None:
        monkeypatch.setattr(solver_agent, "make_client", lambda: agent)


def test_reworded_route_is_answered_from_llm_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    use_models(monkeypatch, parser=FakeClient(response(slots(start=place("Kitchen 1.12"),
                                                             destination=place("Office 0.31")))))
    result = respond(FACTORY, "Kitchen 1.12 to Office 0.31, which way?")
    assert (result.kind, result.parser) == ("route", "llm")
    assert result.reply.endswith("Answer: 92.01 m")  # warm-up answer proc-factory-dev-004-Q05


def test_combined_constraints_without_a_route_say_so(monkeypatch: pytest.MonkeyPatch) -> None:
    use_models(monkeypatch, parser=FakeClient(response(slots(
        start=place("Kitchen 1.15"), destination=place("Meeting room 0.22"), step_free=True,
        closures=["Office lift"]))))
    result = respond(FACTORY, "The office lift is out of order. Step-free from Kitchen 1.15 to Meeting room 0.22?")
    assert result.kind == "route_query" and result.result["reachable"] is False
    assert result.reply.endswith("Answer: no route")


def test_questions_the_parser_hands_over_are_answered_by_the_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    use_models(monkeypatch, parser=FakeClient(response(slots(kind="other", asks_for="count"))),
               agent=FakeClient(tool_use("python", {"code": "print(len(spaces(floor='Floor 1', type='room')))"}),
                                submission(16.0)))
    result = respond(FACTORY, "How many rooms are on floor 1?")
    assert (result.kind, result.parser, result.error) == ("agent", "agent", None)
    assert result.reply.endswith("Answer: 16")
    assert "no solver kind" in result.result["parser_failure"]  # why the parser path gave up, for triage


def test_regex_mode_never_asks_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSER_MODE", "regex")
    result = respond(FACTORY, "How many rooms are on floor 1?")
    assert result.error and "Answer:" not in result.reply


def test_without_a_model_or_a_cached_decision_the_question_fails_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    result = respond(FACTORY, "How many rooms are on floor 1?")
    assert result.error and "Answer:" not in result.reply


def test_a_second_run_without_any_model_reproduces_the_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                             isolated: Path) -> None:
    questions = tmp_path / "questions.json"
    questions.write_text(json.dumps([
        {"id": "template", "question": "How do I get from Kitchen 1.12 (Floor 1) to Office 0.31 (Ground floor)?"},
        {"id": "reworded", "question": "Fastest way from Main aisle H-B1 to a forklift charging station?"},
        {"id": "new-kind", "question": "How many rooms are on floor 1?"},
    ]), encoding="utf-8")
    use_models(monkeypatch,
               parser=FakeClient(response(slots(start=place("Main aisle H-B1"),
                                                destination={"name": "forklift charging station", "floor": None,
                                                             "is_item": True})),
                                 response(slots(kind="other", asks_for="count"))),
               agent=FakeClient(tool_use("python", {"code": "print(len(spaces(floor='Floor 1', type='room')))"}),
                                submission(16.0)))
    first = run(FACTORY, questions, tmp_path / "first.json")
    assert [item["parser"] for item in first] == ["regex", "llm", "agent"]
    assert isolated.exists()

    monkeypatch.setattr(llm_parser, "make_client", no_model)
    monkeypatch.setattr(solver_agent, "make_client", no_model)
    second = run(FACTORY, questions, tmp_path / "second.json")
    assert [item["parser"] for item in second] == ["regex", "llm-cache", "agent-cache"]
    keys = ("question_id", "reply", "answer", "kind", "inputs", "result", "route", "space_path", "length_m", "error")
    assert [{key: item[key] for key in keys} for item in second] == [{key: item[key] for key in keys} for item in first]
