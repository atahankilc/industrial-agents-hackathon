"""Run every solver on the gold `inputs` of train+dev benchmark questions and score the formatted reply.

  uv run python scripts/validate_solvers.py                  # all kinds, per-kind table
  uv run python scripts/validate_solvers.py --kinds errand -v   # show failures

No parsing and no LLM: this isolates solver + formatter correctness."""

import argparse
import json
import sys
import traceback
from collections import Counter
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmark.score import score_reply  # noqa: E402
from core.building_map import BuildingMap  # noqa: E402
from core.formatter import format_reply  # noqa: E402
from core.solvers import solve  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def labelled(splits: list[str]) -> list[tuple[Path, dict]]:
    items = []
    for split in splits:
        for path in sorted((DATA / split).glob("*/questions.jsonl")):
            items += [(path.parent, json.loads(line)) for line in path.open(encoding="utf-8") if line.strip()]
    return items


def check(directory: Path, question: dict) -> tuple[bool, str]:
    try:
        result = solve(building(directory), question["kind"], question["inputs"])
        reply = format_reply(building(directory), result)
    except Exception:  # noqa: BLE001 — report every failure, keep going
        return False, traceback.format_exc(limit=3)
    return score_reply(question["answer"], reply), reply


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kinds", nargs="+")
    parser.add_argument("--splits", nargs="+", default=["train", "dev"])
    parser.add_argument("-v", "--verbose", action="store_true")
    arguments = parser.parse_args()
    results: Counter[tuple[str, bool]] = Counter()
    for directory, question in labelled(arguments.splits):
        if arguments.kinds and question["kind"] not in arguments.kinds:
            continue
        correct, reply = check(directory, question)
        results[(question["kind"], correct)] += 1
        if arguments.verbose and not correct:
            print(f"--- {question['id']} expected {json.dumps(question['answer'], ensure_ascii=False)}\n{reply}")
    print("\nkind                        correct / total")
    for kind in sorted({kind for kind, _ in results}):
        print(f"  {kind:26s} {results[(kind, True)]:4d} / {results[(kind, True)] + results[(kind, False)]}")
    total = sum(results.values())
    good = sum(count for (_, ok), count in results.items() if ok)
    print(f"  {'all':26s} {good:4d} / {total}")


if __name__ == "__main__":
    main()
