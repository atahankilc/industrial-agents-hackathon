"""run_benchmark end to end on one dev building: every input format, both output formats, scored (no LLM)."""

import csv
import json
from pathlib import Path

import pytest

from agent import run_benchmark_v1
from agent.answer import respond
from agent.run_benchmark_v1 import load_env_file, load_questions, main, run
from benchmark.score import score_reply

BUILDING = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-campus-dev-001"
WARM_UP_UNREACHABLE = BUILDING.parent / "osm-way360544293"  # warm-up routes and a tour that are `reachable: false`


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


def test_single_building_answers_say_which_parser_read_them(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    run(BUILDING, BUILDING / "questions.jsonl", answers_path)
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    assert {item["parser"] for item in answers} == {"regex"}


def test_space_answers_carry_the_room_id(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    run(BUILDING, BUILDING / "questions.jsonl", answers_path)
    answers = {item["question_id"]: item for item in json.loads(answers_path.read_text(encoding="utf-8"))}
    largest = [question for question in load_questions(BUILDING / "questions.jsonl")
               if question["kind"] == "largest_room"]
    assert largest
    for question in largest:
        assert answers[question["id"]]["space_id"] == question["answer"]["space_id"]


@pytest.mark.parametrize("directory", [BUILDING, WARM_UP_UNREACHABLE])
def test_warm_up_answers_carry_ids_and_whole_space_paths(tmp_path: Path, directory: Path) -> None:
    answers_path = tmp_path / "answers.json"
    run(directory, directory / "questions_basic.jsonl", answers_path)
    answers = {item["question_id"]: item for item in json.loads(answers_path.read_text(encoding="utf-8"))}
    for question in load_questions(directory / "questions_basic.jsonl"):
        item, gold = answers[question["id"]], question["answer"]
        if question["kind"] == "locate":
            assert (item["item_id"], item["space_id"]) == (gold["asset_id"], gold["space_id"])
        elif question["kind"] == "count":
            assert item["space_path"] is None
        elif gold.get("reachable") is False:
            assert item["reachable"] is False and item["space_path"] is None and item["length_m"] is None
        else:
            legs = gold["legs"] if question["kind"] == "tour" else [gold]
            whole = [legs[0]["space_path"][0], *(space for leg in legs for space in leg["space_path"][1:])]
            assert item["reachable"] is True
            assert item["space_path"] == whole
            assert abs(item["length_m"] - gold["optimal_length_m"]) <= 0.01


def test_dict_layout_keys_answers_by_question_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_benchmark_v1, "ENV_FILE", tmp_path / ".env")  # keep the repo's keys out of the tests
    answers_path = tmp_path / "answers.json"
    main([str(BUILDING), str(BUILDING / "questions.jsonl"), str(answers_path), "--layout", "dict"])
    saved = json.loads(answers_path.read_text(encoding="utf-8"))
    gold = expected()
    assert list(saved) == list(gold)
    assert all(score_reply(gold[question_id], item["reply"]) for question_id, item in saved.items())


def test_interrupted_run_keeps_the_answers_written_so_far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def interrupted_on_third(directory: Path, text: str):
        calls.append(text)
        if len(calls) == 3:
            raise KeyboardInterrupt
        return respond(directory, text)

    monkeypatch.setattr(run_benchmark_v1, "respond", interrupted_on_third)
    answers_path = tmp_path / "answers.json"
    with pytest.raises(KeyboardInterrupt):
        run(BUILDING, BUILDING / "questions.jsonl", answers_path)
    saved = json.loads(answers_path.read_text(encoding="utf-8"))
    assert [item["question_id"] for item in saved] == list(expected())[:2]


def test_env_file_fills_only_missing_variables(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\nKEPT=from-file\nQUOTED='a b'\nexport EXPORTED=1\n\nBROKEN LINE\n", encoding="utf-8")
    environ = {"KEPT": "already-set"}
    load_env_file(env_file, environ)
    assert environ == {"KEPT": "already-set", "QUOTED": "a b", "EXPORTED": "1"}


def test_missing_env_file_is_not_an_error(tmp_path: Path) -> None:
    environ: dict[str, str] = {}
    load_env_file(tmp_path / ".env", environ)
    assert environ == {}
