"""Sunday probe: reworded questions, new constraints and new kinds with expected answers computed by direct code
(tests/sunday_probe/*.json), run through the benchmark command's own path (hybrid parser → route specs → solver
agent) and scored with benchmark/score.py; a `no_route` expectation needs "no … route" on the answer line.

  uv run python scripts/eval_sunday_probe.py                      # every file in tests/sunday_probe/
  uv run python scripts/eval_sunday_probe.py tests/sunday_probe/proc-factory-dev-004.json --keep-cache

Calls Claude (parser for unseen wording, solver agent for new kinds). Uses its own decision cache in agent_output/,
never the committed llm_cache/; it is cleared first unless --keep-cache (then a rerun replays without the model)."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.run_benchmark_v1 import ENV_FILE, load_env_file, run  # noqa: E402
from benchmark.score import committed_answer, score_reply  # noqa: E402

OUTPUT = ROOT / "agent_output" / "sunday_probe"


def correct(expected: dict, reply: str) -> bool:
    if expected["type"] == "no_route":
        line = (committed_answer(reply) or "").lower()
        return "no" in line.split() and "route" in line
    return score_reply(expected, reply)


def main() -> None:
    parser = argparse.ArgumentParser(prog="eval_sunday_probe")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--keep-cache", action="store_true", help="reuse the probe's decision cache (no model calls)")
    arguments = parser.parse_args()
    load_env_file(ENV_FILE)
    files = arguments.files or sorted((ROOT / "tests" / "sunday_probe").glob("*.json"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cache = OUTPUT / "decisions.json"
    if not arguments.keep_cache:
        cache.unlink(missing_ok=True)
    os.environ["LLM_CACHE"] = str(cache)
    os.environ.setdefault("PARSER_MODE", "hybrid")
    total = passed = 0
    started = time.time()
    for path in files:
        probe = json.loads(path.read_text(encoding="utf-8"))
        questions = OUTPUT / f"{path.stem}.questions.json"
        questions.write_text(json.dumps([{"id": q["id"], "question": q["question"]} for q in probe["questions"]]),
                             encoding="utf-8")
        answers = run(ROOT / probe["building"], questions, OUTPUT / f"{path.stem}.answers.json")
        print(f"\n{path.name}")
        for question, answer in zip(probe["questions"], answers, strict=True):
            ok = correct(question["expected"], answer["reply"])
            total, passed = total + 1, passed + ok
            print(f"  {'PASS' if ok else 'FAIL'} {question['id']:26s} {answer['kind'] or '-':20s} "
                  f"{answer['parser'] or '-':12s} {answer['answer'] or answer['error']}"[:200])
    print(f"\n{passed}/{total} correct in {time.time() - started:.0f} s (answers in {OUTPUT})")


if __name__ == "__main__":
    main()
