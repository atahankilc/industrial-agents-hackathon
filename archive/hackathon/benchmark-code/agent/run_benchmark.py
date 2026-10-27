"""Answer a question file for one building (Sunday) or a split of buildings (test), deterministically.

  uv run python -m agent.run_benchmark <building_or_split_dir> <questions file> <answers.json> [--csv out.csv]

- building_or_split_dir: a directory with building.json (every question is about it), or a directory holding
  one sub-directory per building_id (e.g. data/test).
- questions file: .jsonl / .json (list, or {"questions": [...]}) with `id` and `question` (+ `building_id`), or
  .csv with `question_id`/`id`, `question` (+ `building_id`) — e.g. data/test/questions.csv.
- answers.json: {question_id: {kind, params, answer, unit, area_m2, evidence, reply, error, note}}.
- --csv: also write `question_id,answer` with the full replies (the test-set submission format).

The Sunday output format is not announced yet (Q-001); answers.json keeps every structured field so the final
format can be produced from it without re-running."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from agent.benchmark_agent import answer_question
from benchmark.evaluate import write_submission_csv


def load_questions(path: Path) -> list[dict]:
    if path.suffix == ".csv":
        with path.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("questions", data) if isinstance(data, dict) else data
    return [{**row, "id": row.get("id") or row.get("question_id")} for row in rows]


def building_directory(root: Path, question: dict) -> Path:
    if (root / "building.json").exists():
        return root
    return root / question["building_id"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent.run_benchmark")
    parser.add_argument("building", type=Path, help="building directory, or a directory of building directories")
    parser.add_argument("questions", type=Path)
    parser.add_argument("answers", type=Path, help="answers.json to write")
    parser.add_argument("--csv", type=Path, default=None, help="also write question_id,answer (full replies)")
    arguments = parser.parse_args()

    answers: dict[str, dict] = {}
    outcomes: Counter[str] = Counter()
    for question in load_questions(arguments.questions):
        result = answer_question(building_directory(arguments.building, question), question["question"])
        answers[question["id"]] = result.as_record()
        outcomes["error" if result.error else (result.note or "ok")] += 1
    arguments.answers.parent.mkdir(parents=True, exist_ok=True)
    arguments.answers.write_text(json.dumps(answers, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(answers)} answers saved to {arguments.answers}  {dict(outcomes)}")
    if arguments.csv is not None:
        write_submission_csv(arguments.csv, [(question_id, item["reply"]) for question_id, item in answers.items()])


if __name__ == "__main__":
    main()
