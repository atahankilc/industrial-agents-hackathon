"""run_benchmark end to end on one dev building: every input format, both output formats, scored (no LLM)."""

import csv
import json
from pathlib import Path

import pytest

from agent.run_benchmark import load_questions, run
from benchmark.score import score_reply

BUILDING = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-campus-dev-001"


@pytest.fixture(autouse=True)
def regex_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSER_MODE", "regex")


def expected() -> dict[str, dict]:
    return {question["id"]: question["answer"] for question in load_questions(BUILDING / "questions.jsonl")}


def test_single_building_to_json_scores_all(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    run(BUILDING, BUILDING / "questions.jsonl", answers_path)
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    gold = expected()
    assert [item["question_id"] for item in answers] == list(gold)
    assert all(score_reply(gold[item["question_id"]], item["reply"]) for item in answers)
    assert all(item["error"] is None and item["answer"] and item["result"] for item in answers)


def test_split_directory_and_json_questions_to_csv(tmp_path: Path) -> None:
    questions = [{"question_id": q["id"], "building_id": q["building_id"], "question": q["question"]}
                 for q in load_questions(BUILDING / "questions.jsonl")]
    questions_path = tmp_path / "questions.json"
    questions_path.write_text(json.dumps({"questions": questions}), encoding="utf-8")
    answers_path = tmp_path / "answers.csv"
    run(BUILDING.parent, questions_path, answers_path)
    with answers_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    gold = expected()
    assert rows[0] == ["question_id", "answer"]
    assert len(rows) == len(gold) + 1
    assert all(score_reply(gold[question_id], reply) for question_id, reply in rows[1:])
