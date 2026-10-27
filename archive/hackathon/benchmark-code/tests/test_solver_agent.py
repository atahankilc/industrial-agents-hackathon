"""agent.solver_agent offline: the python sandbox, the answer line written by code, the tool loop and the
self-consistency vote, with a fake Claude client (no API calls). proc-factory-dev-004 has 50 spaces; Office 1.04 is
an office on Floor 1."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent import solver_agent
from agent.llm_cache import DecisionCache
from agent.solver_agent import SolverAgent, Submission, answer_line, namespace, run_code
from benchmark.score import score_reply
from core.building_map import BuildingMap

DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"


@pytest.fixture(scope="module")
def bmap() -> BuildingMap:
    return BuildingMap.load(DIRECTORY)


def space(bmap: BuildingMap, name: str) -> str:
    return next(space_id for space_id, item in bmap.spaces.items() if item["name"] == name)


def tool_use(name: str, arguments: dict, use_id: str = "t1") -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    block = SimpleNamespace(type="tool_use", id=use_id, name=name, input=arguments)
    return SimpleNamespace(content=[block], stop_reason="tool_use", usage=usage)


def text(words: str) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=words)], stop_reason="end_turn", usage=usage)


def submit(number: float | None = None, answer_type: str = "number", unit: str | None = None,
           space_id: str | None = None) -> SimpleNamespace:
    return tool_use("submit_answer", {"answer_type": answer_type, "number": number, "unit": unit,
                                      "space_id": space_id, "text": None, "explanation": "Computed with python."})


class FakeClient:
    def __init__(self, *replies: SimpleNamespace) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.requests.append(json.loads(json.dumps(kwargs, default=lambda value: vars(value))))
        return self.replies.pop(0)


def test_python_tool_sees_the_building(bmap: BuildingMap) -> None:
    assert run_code("print(len(b.spaces))", namespace(bmap)) == {"output": "50\n"}


def test_python_tool_keeps_variables_and_reports_errors(bmap: BuildingMap) -> None:
    scope = namespace(bmap)
    run_code("x = 2", scope)
    assert run_code("print(x + 1)", scope)["output"] == "3\n"
    assert "ZeroDivisionError" in run_code("1 / 0", scope)["error"]


def test_python_tool_has_no_files_and_only_whitelisted_imports(bmap: BuildingMap) -> None:
    scope = namespace(bmap)
    assert "NameError" in run_code("open('/etc/hosts')", scope)["error"]
    assert "ImportError" in run_code("import os", scope)["error"]
    assert run_code("import math\nprint(math.floor(2.5))", scope)["output"] == "2\n"


def test_code_that_runs_too_long_is_stopped(bmap: BuildingMap, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_agent, "CODE_TIME_LIMIT_S", 1)
    assert "TimeoutError" in run_code("while True:\n    pass", namespace(bmap))["error"]


def test_helpers_route_and_place_use_the_canonical_core(bmap: BuildingMap) -> None:
    scope = namespace(bmap)
    output = run_code("r = route('Kitchen 1.12', 'Office 0.31')\nprint(r['optimal_length_m'])", scope)["output"]
    assert output == "92.01\n"  # warm-up answer proc-factory-dev-004-Q05
    assert run_code("print(sorted(describe(s) for s in place('toilet')))", scope)["output"].count("Toilet") == 2


def test_answer_line_is_one_number_or_the_room(bmap: BuildingMap) -> None:
    assert answer_line(Submission("number", number=3.0), bmap) == "3"
    assert answer_line(Submission("number", number=12.3456, unit="m"), bmap) == "12.35 m"
    office = space(bmap, "Office 1.04")
    assert answer_line(Submission("space", space_id=office), bmap) == "Office 1.04"
    assert answer_line(Submission("space", space_id=office, number=23.5, unit="m²"), bmap) == "Office 1.04, 23.50 m²"
    assert answer_line(Submission("no_route"), bmap) == "no route"
    renamed = BuildingMap.load(DIRECTORY)
    renamed.spaces[office] = {**renamed.spaces[office], "name": "Corner office"}
    assert answer_line(Submission("space", space_id=office), renamed) == "Corner office (1.04)"


def test_agent_runs_code_then_submits(bmap: BuildingMap) -> None:
    client = FakeClient(tool_use("python", {"code": "print(len(spaces(floor='Floor 1', type='room')))"}),
                        submit(16.0))
    result = SolverAgent(client, runs=1, cache=DecisionCache(None)).solve("How many rooms are on floor 1?", bmap)
    assert result.reply.splitlines()[-1] == "Answer: 16"
    assert score_reply({"type": "number", "value": 16, "relative_tolerance": 0, "absolute_tolerance": 0}, result.reply)
    sent_back = client.requests[1]["messages"][-1]["content"][0]
    assert sent_back["type"] == "tool_result" and json.loads(sent_back["content"])["output"].strip().isdigit()


def test_agreeing_runs_skip_the_tiebreak(bmap: BuildingMap) -> None:
    client = FakeClient(submit(5.0), submit(5.0))
    result = SolverAgent(client, runs=2, cache=DecisionCache(None)).solve("q", bmap)
    assert len(client.requests) == 2 and result.reply.endswith("Answer: 5")


def test_disagreeing_runs_get_a_third_and_the_majority_wins(bmap: BuildingMap) -> None:
    client = FakeClient(submit(5.0), submit(6.0), submit(6.0))
    result = SolverAgent(client, runs=2, cache=DecisionCache(None)).solve("q", bmap)
    assert len(client.requests) == 3 and result.reply.endswith("Answer: 6")


def test_an_invalid_submission_goes_back_to_the_model(bmap: BuildingMap) -> None:
    client = FakeClient(submit(answer_type="space", space_id="no-such-space"),
                        submit(answer_type="space", space_id=space(bmap, "Office 1.04")))
    result = SolverAgent(client, runs=1, cache=DecisionCache(None)).solve("Which office?", bmap)
    rejected = client.requests[1]["messages"][-1]["content"][0]
    assert rejected["is_error"] is True and "no-such-space" in rejected["content"]
    assert result.reply.endswith("Answer: Office 1.04")


def test_model_code_cannot_change_the_cached_building(bmap: BuildingMap) -> None:
    client = FakeClient(tool_use("python", {"code": "b.spaces.clear()\nprint(len(b.spaces))"}), submit(0.0))
    SolverAgent(client, runs=1, cache=DecisionCache(None)).solve("q", bmap)
    assert len(bmap.spaces) == 50


def test_no_submission_is_an_error(bmap: BuildingMap, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_agent, "MAX_ROUNDS", 2)
    client = FakeClient(text("I think it is 4."), text("Still 4."))
    result = SolverAgent(client, runs=1, cache=DecisionCache(None)).solve("q", bmap)
    assert result.error and "Answer:" not in result.reply


def test_a_cached_answer_is_replayed_without_the_model(bmap: BuildingMap, tmp_path: Path) -> None:
    path = tmp_path / "decisions.json"
    first = SolverAgent(FakeClient(tool_use("python", {"code": "print(16)"}), submit(16.0)), runs=1,
                        cache=DecisionCache(path)).solve("How many rooms are on floor 1?", bmap)
    replay_client = FakeClient()
    again = SolverAgent(replay_client, runs=1, cache=DecisionCache(path)).solve("How many rooms are on floor 1?", bmap)
    assert (again.reply, again.cached, replay_client.requests) == (first.reply, True, [])
    assert next(iter(json.loads(path.read_text(encoding="utf-8")).values()))["code"] == ["print(16)"]
