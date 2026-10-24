"""One command for a benchmark run: building(s) + question file in, answers file out. This is the v1 pipeline
(agent.answer + core.solvers_v1), the submission runner (SUBMISSION/BENCHMARK.md); agent.run_benchmark is the second.

  uv run --env-file .env python -m agent.run_benchmark_v1 <building_dir> <questions> <answers>

<building_dir> is one building (holds building.json) or a split directory with one sub-directory per
`building_id`. <questions> is .jsonl, .json (a list, or {"questions": [...]}) or .csv; each question needs an id
(`id` or `question_id`) and its text (`question`). The <answers> extension picks the output: .csv writes the
submission format (question_id,answer with the full reply); .json writes one object per question with the
reply, its `Answer:` line, the question kind, the resolved ids, the solver's structured result and, for
routing kinds, `route` = {optimal_length_m, legs: [{from_space_id, to_space_id, optimal_length_m, space_path,
element_path}]} in the warm-up answer format (Sunday format still open, Q-001)."""

import argparse
import csv
import json
import sys
from pathlib import Path

from agent.answer import respond
from benchmark.score import committed_answer

SUBMISSION_COLUMNS = ("question_id", "answer")


def load_questions(path: Path) -> list[dict]:
    if path.suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["questions"] if isinstance(data, dict) else data
    return [{**row, "id": row.get("id") or row["question_id"]} for row in rows]


def building_directory(root: Path, question: dict) -> Path:
    if (root / "building.json").exists():
        return root
    directory = root / question["building_id"]
    if not (directory / "building.json").exists():
        raise FileNotFoundError(f"no building.json for {question['id']} under {root}")
    return directory


def write_answers(path: Path, answers: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(SUBMISSION_COLUMNS)
            writer.writerows((item["question_id"], item["reply"]) for item in answers)
    else:
        path.write_text(json.dumps(answers, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def route(result: dict | None) -> dict | None:
    """Warm-up answer format (Q-001 working assumption): total length plus one path per stop-to-stop leg."""
    if result and result.get("reachable") is False:
        return {"reachable": False}
    if not result or "legs" not in result:
        return None
    total = result.get("total_m", result.get("optimal_length_m", sum(leg["optimal_length_m"] for leg in result["legs"])))
    return {"optimal_length_m": round(total, 2),
            "legs": result["legs"]}


def run(root: Path, questions_path: Path, answers_path: Path) -> list[dict]:
    answers = []
    for question in load_questions(questions_path):
        response = respond(building_directory(root, question), question["question"])
        answers.append({
            "question_id": question["id"],
            "reply": response.reply,
            "answer": committed_answer(response.reply),
            "kind": response.kind,
            "inputs": response.params,
            "result": response.result,
            "route": route(response.result),
            "error": response.error,
        })
        status = "ok " if response.error is None else "ERR"
        print(f"[run_benchmark] {question['id']:34s} {response.kind or '-':26s} {status}", file=sys.stderr)
    write_answers(answers_path, answers)
    failed = sum(item["error"] is not None for item in answers)
    print(f"{len(answers)} answers written to {answers_path} ({failed} without an answer)", file=sys.stderr)
    return answers


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent.run_benchmark_v1")
    parser.add_argument("building_dir", type=Path, help="a building directory, or a split with one per building_id")
    parser.add_argument("questions", type=Path, help="questions as .jsonl, .json or .csv")
    parser.add_argument("answers", type=Path, help="output: .csv (submission) or .json (structured)")
    arguments = parser.parse_args()
    run(arguments.building_dir, arguments.questions, arguments.answers)


if __name__ == "__main__":
    main()
