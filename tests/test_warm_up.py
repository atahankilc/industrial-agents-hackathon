"""Warm-up questions (questions_basic.jsonl) end to end from the question text, against every train/dev answer.

  uv run pytest tests/test_warm_up.py -q -s     # -s prints the per-kind table

text → parse_question → solve, compared field by field: locate (asset, room, floor level, position), count,
route / route_step_free / route_with_closure (length ≤ 1 cm, space_path, element_path, or unreachable) and tour
(every leg). A wrong answer is a failure unless the text names a room that several rooms share (the parser's
`ambiguous` flag: the text cannot say which one is meant); those are counted as wrong and reported separately.
The reply from agent.answer must end in an `Answer:` line."""

import json
from collections import Counter
from pathlib import Path

import pytest

from agent.answer import answer
from benchmark.score import committed_answer
from core.question_parser import ParseError, parse_question
from core.solvers import solve
from tests.test_question_parser import DATA, building

TOLERANCE_M = 0.01


@pytest.fixture(autouse=True)
def regex_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSER_MODE", "regex")


def warm_up_questions() -> list[tuple[Path, dict]]:
    questions = []
    for split in ("train", "dev"):
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            questions += [(path.parent, json.loads(line)) for line in path.open(encoding="utf-8") if line.strip()]
    return questions


def route_problem(result: dict, legs: list[dict], answer: dict) -> str | None:
    if answer.get("reachable") is False:
        return None if result["reachable"] is False else "route found where the answer says unreachable"
    if not result["reachable"]:
        return f"unreachable: {result['reason']}"
    for got, expected in zip(result["legs"], legs, strict=True):
        if abs(got["optimal_length_m"] - expected["optimal_length_m"]) > TOLERANCE_M:
            return f"length {got['optimal_length_m']} != {expected['optimal_length_m']}"
        for key in ("space_path", "element_path"):
            if got[key] != expected[key]:
                return f"{key} differs"
    return None


def problem(kind: str, result: dict, answer: dict) -> str | None:
    """None when the solver result matches the gold answer, else what differs."""
    if kind == "locate":
        got = (result["asset_id"], result["space_id"], result["floor_level"], result["position"])
        expected = (answer["asset_id"], answer["space_id"], answer["floor_level"], answer["position"])
        return None if got == expected else f"{got} != {expected}"
    if kind == "count":
        return None if result["count"] == answer["count"] else f"count {result['count']} != {answer['count']}"
    return route_problem(result, answer["legs"] if kind == "tour" else [answer], answer)


def outcome(directory: Path, question: dict) -> tuple[bool, bool, str]:
    """(correct, ambiguous text, reason)."""
    bmap = building(directory)
    try:
        parsed = parse_question(question["question"], bmap)
    except ParseError as error:
        return False, False, f"ParseError: {error}"
    if parsed.kind != question["kind"]:
        return False, False, f"kind {parsed.kind}"
    reason = problem(parsed.kind, solve(bmap, parsed.kind, parsed.params), question["answer"])
    return reason is None, parsed.ambiguous, reason or ""


def test_warm_up_from_text() -> None:
    totals, good, ambiguous_wrong, failures = Counter(), Counter(), Counter(), []
    for directory, question in warm_up_questions():
        ok, unclear, reason = outcome(directory, question)
        totals[question["kind"]] += 1
        good[question["kind"]] += ok
        ambiguous_wrong[question["kind"]] += unclear and not ok
        if not ok and not unclear:
            failures.append(f"{question['id']}: {question['question'][:90]} → {reason}"[:300])
    print("\ntrain+dev warm-up: solve(parse(question text)) == answer")
    for kind in sorted(totals):
        print(f"  {kind:20s} {good[kind]:4d} / {totals[kind]:<4d} wrong on ambiguous text: {ambiguous_wrong[kind]}")
    print(f"  {'all':20s} {sum(good.values()):4d} / {sum(totals.values()):<4d} "
          f"wrong on ambiguous text: {sum(ambiguous_wrong.values())}")
    for failure in failures[:30]:
        print(f"    FAIL {failure}")
    assert failures == []


def test_every_warm_up_kind_replies_with_an_answer_line() -> None:
    seen = set()
    for directory, question in warm_up_questions():
        if question["kind"] in seen:
            continue
        seen.add(question["kind"])
        assert committed_answer(answer(directory, question["question"])), question["id"]
    assert len(seen) == 6
