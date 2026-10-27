"""Check that backend.core.building_map reproduces every dev warm-up `route` length to 1 cm.

  uv run python scripts/check_routes.py   # exit 1 on any mismatch

Loads the questions_basic.jsonl of each dev building (manifest `split`) with kind == "route" and compares
BuildingMap.load(dir).route(from_space_id, to_space_id).length_m with optimal_length_m (tolerance 0.01)."""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.building_map import BuildingMap  # noqa: E402

TOLERANCE_M = 0.01


def main() -> int:
    total, mismatches = 0, []
    with (ROOT / "data" / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        dev = sorted(row["building_id"] for row in csv.DictReader(handle) if row["split"] == "dev")
    for questions in (ROOT / "data" / "buildings" / building_id / "questions_basic.jsonl" for building_id in dev):
        building = BuildingMap.load(questions.parent)
        for line in questions.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            question = json.loads(line)
            if question.get("kind") != "route":
                continue
            total += 1
            answer = question["answer"]
            got = building.route(answer["from_space_id"], answer["to_space_id"]).length_m
            if abs(got - answer["optimal_length_m"]) > TOLERANCE_M:
                mismatches.append(f"{question['id']}: got {got}, expected {answer['optimal_length_m']}")
    print("\n".join(mismatches + [f"core routes exact to 1cm: {total - len(mismatches)} / {total}"]))
    return 1 if mismatches or total == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
