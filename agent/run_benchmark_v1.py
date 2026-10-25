"""One command for a benchmark run: building(s) + question file in, answers file out. This is the v1 pipeline
(agent.answer + core.solvers_v1), the submission runner (SUBMISSION/BENCHMARK.md); agent.run_benchmark is the second.

  uv run python -m agent.run_benchmark_v1 <building_dir> <questions> <answers> [--layout list|dict]

<building_dir> is one building (holds building.json) or a split directory with one sub-directory per
`building_id`. <questions> is .jsonl, .json (a list, or {"questions": [...]}) or .csv; each question needs an id
(`id` or `question_id`) and its text (`question`). The <answers> extension picks the output: .csv writes the
submission format (question_id,answer with the full reply); .json writes one object per question with the
reply, its `Answer:` line, the question kind, the parser that read it, the resolved ids, the solver's structured
result, the top-level ids the PDF names (`item_id`, `space_id`, the whole route as one ordered `space_path`,
`length_m`, `reachable`) and, for routing kinds, `route` = {optimal_length_m, legs: [{from_space_id, to_space_id,
optimal_length_m, space_path, element_path}]} in the warm-up answer format (Sunday format still open, Q-001).
`--layout dict` keys the .json by question id instead of listing it.

The repo's `.env` is read for variables not already set (the LLM parser's ANTHROPIC_API_KEY). The answers file is
rewritten after every question, so an interrupted run keeps what it answered."""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from collections.abc import MutableMapping
from pathlib import Path

from agent.answer import respond
from benchmark.score import committed_answer

SUBMISSION_COLUMNS = ("question_id", "answer")
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour", "route_query")
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """KEY=VALUE lines (optional `export`, quotes, # comments) into `environ` where the key is not set yet."""
    environ = os.environ if environ is None else environ
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if line.startswith("#") or not separator or not key.isidentifier():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        environ.setdefault(key, value)


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


def write_answers(path: Path, answers: list[dict], layout: str = "list") -> None:
    """Write via a temporary file, so a run killed mid-write leaves the previous complete file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    if path.suffix == ".csv":
        with partial.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(SUBMISSION_COLUMNS)
            writer.writerows((item["question_id"], item["reply"]) for item in answers)
    else:
        content = {item["question_id"]: item for item in answers} if layout == "dict" else answers
        partial.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def route(result: dict | None) -> dict | None:
    """Warm-up answer format (Q-001 working assumption): total length plus one path per stop-to-stop leg."""
    if result and result.get("reachable") is False:
        return {"reachable": False}
    if not result or "legs" not in result:
        return None
    total = result.get("total_m", result.get("optimal_length_m", sum(leg["optimal_length_m"] for leg in result["legs"])))
    return {"optimal_length_m": round(total, 2),
            "legs": result["legs"]}


def top_level_ids(kind: str | None, result: dict | None) -> dict:
    """The PDF's answers.json content (Q-001): the located item and its room (or the answer room), the whole route
    as one ordered list of spaces (legs joined) with its element path and length, and whether a route exists."""
    fields = {"item_id": None, "space_id": None, "reachable": None, "space_path": None, "element_path": None,
              "length_m": None}
    if not result:
        return fields
    if kind == "locate":
        fields.update(item_id=result["asset_id"], space_id=result["space_id"])
    elif "space_id" in result:
        fields["space_id"] = result["space_id"]
    if kind in ROUTE_KINDS and result.get("reachable") is False:
        fields["reachable"] = False
    elif result.get("legs"):
        legs = result["legs"]
        fields.update(
            reachable=True,
            space_path=[legs[0]["space_path"][0], *(space for leg in legs for space in leg["space_path"][1:])],
            element_path=[element for leg in legs for element in leg["element_path"]],
            length_m=round(result.get("total_m", result.get("optimal_length_m", 0.0)), 2),
        )
    return fields


def run(root: Path, questions_path: Path, answers_path: Path, layout: str = "list") -> list[dict]:
    answers = []
    for question in load_questions(questions_path):
        response = respond(building_directory(root, question), question["question"])
        answers.append({
            "question_id": question["id"],
            "reply": response.reply,
            "answer": committed_answer(response.reply),
            "kind": response.kind,
            "parser": response.parser,
            "inputs": response.params,
            **top_level_ids(response.kind, response.result),
            "result": response.result,
            "route": route(response.result),
            "error": response.error,
        })
        write_answers(answers_path, answers, layout)
        status = "ok " if response.error is None else "ERR"
        print(f"[run_benchmark] {question['id']:34s} {response.kind or '-':26s} {response.parser or '-':6s} {status}",
              file=sys.stderr)
    write_answers(answers_path, answers, layout)
    failed = sum(item["error"] is not None for item in answers)
    readers = ", ".join(f"{parser} {count}" for parser, count in Counter(item["parser"] or "-" for item in answers).items())
    print(f"{len(answers)} answers written to {answers_path} ({failed} without an answer; read by: {readers})",
          file=sys.stderr)
    return answers


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agent.run_benchmark_v1")
    parser.add_argument("building_dir", type=Path, help="a building directory, or a split with one per building_id")
    parser.add_argument("questions", type=Path, help="questions as .jsonl, .json or .csv")
    parser.add_argument("answers", type=Path, help="output: .csv (submission) or .json (structured)")
    parser.add_argument("--layout", choices=("list", "dict"), default="list",
                        help=".json output: a list of answers (default) or an object keyed by question id")
    arguments = parser.parse_args(argv)
    load_env_file(ENV_FILE)
    run(arguments.building_dir, arguments.questions, arguments.answers, arguments.layout)


if __name__ == "__main__":
    main()
