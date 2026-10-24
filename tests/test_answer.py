"""Full replies from agent.answer scored by the official benchmark/score.py on every train/dev question (no LLM).

  uv run pytest tests/test_answer.py -q -s     # -s prints the per-kind table

The only misses allowed are questions whose text names a room that several rooms share (the parser's
`ambiguous` flag): the text cannot say which one is meant."""

from collections import Counter

import pytest

from agent.answer import answer
from benchmark.score import committed_answer, score_reply
from core.question_parser import parse_question
from tests.test_question_parser import building, labelled_questions


@pytest.fixture(autouse=True)
def regex_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSER_MODE", "regex")


def test_replies_score_on_train_and_dev() -> None:
    totals, good, unexpected = Counter(), Counter(), []
    for directory, question in labelled_questions():
        reply = answer(directory, question["question"])
        ok = score_reply(question["answer"], reply)
        totals[question["kind"]] += 1
        good[question["kind"]] += ok
        if not ok and not parse_question(question["question"], building(directory)).ambiguous:
            unexpected.append(f"{question['id']}: expected {question['answer']} got {reply!r}"[:400])
    print("\ntrain+dev: score_reply(answer(text))")
    for kind in sorted(totals):
        print(f"  {kind:26s} {good[kind]:4d} / {totals[kind]}")
    print(f"  {'all':26s} {sum(good.values()):4d} / {sum(totals.values())}")
    assert unexpected == []


def test_every_reply_commits_an_answer() -> None:
    directory, question = labelled_questions()[0]
    assert committed_answer(answer(directory, question["question"])) is not None


def test_unparseable_question_has_no_answer_line() -> None:
    directory, _ = labelled_questions()[0]
    assert committed_answer(answer(directory, "What colour is the roof?")) is None
