"""Parser accuracy against the `inputs` of every train/dev benchmark question, and parse coverage on test.

  uv run pytest tests/test_question_parser.py -q -s     # -s prints the per-kind table"""

import csv
import json
from collections import Counter
from functools import cache
from pathlib import Path

from backend.core.building_map import BuildingMap
from tests.kit_oracles.question_parser import ParseError, parse_question

DATA = Path(__file__).resolve().parent.parent / "data"


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def labelled_questions() -> list[tuple[Path, dict]]:
    questions = []
    for split in ("train", "dev"):
        for path in sorted((DATA / split).glob("*/questions.jsonl")):
            questions += [(path.parent, json.loads(line)) for line in path.open(encoding="utf-8") if line.strip()]
    return questions


def unlabelled_test_questions() -> list[tuple[Path, dict]]:
    with (DATA / "test" / "questions.csv").open(encoding="utf-8") as handle:
        return [(DATA / "test" / row["building_id"], row) for row in csv.DictReader(handle)]


def outcome(directory: Path, question: dict) -> tuple[bool, str]:
    try:
        parsed = parse_question(question["question"], building(directory))
    except ParseError as error:
        return False, f"ParseError: {error}"
    if parsed.ambiguous and expected_in(question, parsed):
        return True, ""
    if parsed.kind != question["kind"]:
        return False, f"kind {parsed.kind} != {question['kind']}"
    expected = question.get("inputs")
    if expected is None:
        return True, ""
    wrong = {key: (parsed.params.get(key), value) for key, value in expected.items() if parsed.params.get(key) != value}
    return not wrong, f"wrong slots {wrong}" if wrong else ""


def expected_in(question: dict, parsed) -> bool:
    """Ambiguous text: count as correct when the gold space is among the candidates (text cannot say which)."""
    expected = question.get("inputs")
    if expected is None:
        return True
    return parsed.kind == question["kind"] and all(
        value in parsed.alternatives.get(key, [parsed.params.get(key)]) for key, value in expected.items()
    )


def report(label: str, questions: list[tuple[Path, dict]]) -> list[str]:
    totals, correct, ambiguous, failures = Counter(), Counter(), Counter(), []
    for directory, question in questions:
        ok, reason = outcome(directory, question)
        try:
            ambiguous[question["kind"]] += parse_question(question["question"], building(directory)).ambiguous
        except ParseError:
            pass
        totals[question["kind"]] += 1
        correct[question["kind"]] += ok
        if not ok:
            failures.append(f"{question.get('id') or question['question_id']}: {reason}")
    print(f"\n{label}")
    for kind in sorted(totals):
        print(f"  {kind:26s} {correct[kind]:4d} / {totals[kind]:<4d} ambiguous text: {ambiguous[kind]}")
    print(f"  {'all':26s} {sum(correct.values()):4d} / {sum(totals.values()):<4d} ambiguous text: {sum(ambiguous.values())}")
    for failure in failures[:30]:
        print(f"    FAIL {failure}")
    return failures


def test_train_dev_inputs_match() -> None:
    assert report("train+dev: parsed params == inputs", labelled_questions()) == []


def test_every_test_question_parses() -> None:
    assert report("test: parses and resolves", unlabelled_test_questions()) == []
