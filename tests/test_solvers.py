"""Solver accuracy against the expected answers of every train/dev benchmark question (no LLM, free).

  uv run pytest tests/test_solvers.py -q -s     # -s prints the per-kind table

Two levels: the solver alone on the gold `inputs`, and the full pipeline question text → parser → solver."""

from collections import Counter
from pathlib import Path

from core.question_parser import ParseError, parse_question
from core.solvers import solve
from tests.test_question_parser import building, labelled_questions

# kind -> result field holding the number the answer is compared with
NUMBER_FIELD = {"floor_area_total": "total_m2", "errand": "total_m", "straight_line_3d": "distance_m"}


def within(value: float, answer: dict) -> bool:
    expected = float(answer["value"])
    tolerance = max(abs(expected) * answer["relative_tolerance"], answer["absolute_tolerance"])
    return abs(value - expected) <= tolerance


def correct(kind: str, answer: dict, result: dict) -> bool:
    if answer["type"] == "space":
        return result["space_id"] == answer["space_id"] and (
            "area" not in answer or within(result["area_m2"], answer["area"])
        )
    return within(result[NUMBER_FIELD.get(kind, "count")], answer)


def outcome(directory: Path, question: dict, from_text: bool) -> tuple[bool, str]:
    bmap = building(directory)
    if from_text:
        try:
            parsed = parse_question(question["question"], bmap)
        except ParseError as error:
            return False, f"ParseError: {error}"
        if parsed.ambiguous:
            return True, ""  # the text names several equal rooms; the parser test covers these
        kind, params = parsed.kind, parsed.params
    else:
        kind, params = question["kind"], question["inputs"]
    try:
        result = solve(bmap, kind, params)
    except ValueError as error:
        return False, f"{type(error).__name__}: {error}"
    return correct(question["kind"], question["answer"], result), f"got {result}"


def report(label: str, from_text: bool) -> list[str]:
    totals, good, failures = Counter(), Counter(), []
    for directory, question in labelled_questions():
        ok, reason = outcome(directory, question, from_text)
        totals[question["kind"]] += 1
        good[question["kind"]] += ok
        if not ok:
            failures.append(f"{question['id']}: expected {question['answer']} {reason}"[:400])
    print(f"\n{label}")
    for kind in sorted(totals):
        print(f"  {kind:26s} {good[kind]:4d} / {totals[kind]}")
    print(f"  {'all':26s} {sum(good.values()):4d} / {sum(totals.values())}")
    for failure in failures[:30]:
        print(f"    FAIL {failure}")
    return failures


def test_solvers_on_gold_inputs() -> None:
    assert report("train+dev: solver(inputs) == answer", from_text=False) == []


def test_parser_then_solver() -> None:
    assert report("train+dev: solver(parse(question text)) == answer", from_text=True) == []
