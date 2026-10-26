"""Run backend.core.validate over every dataset building and count issues per (source, code) — the validator calibration.

  uv run python scripts/validate_dataset.py

Every count printed here is an issue the *unchanged* dataset has; backend/core/validate.py treats issues already present in
the base building as warnings, so edits are only flagged for what they introduce."""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.core.validate import validate  # noqa: E402


def main() -> None:
    counts: Counter = Counter()
    buildings = sorted(path for split in ("train", "dev", "test") for path in (ROOT / "data" / split).glob("*/building.json"))
    for path in buildings:
        building = json.loads(path.read_text(encoding="utf-8"))
        for item in validate(building):
            counts[(building["building"]["source"], item["code"], item["severity"])] += 1
    print(f"{len(buildings)} buildings")
    for (source, code, severity), count in sorted(counts.items()):
        print(f"{source:16} {code:18} {severity:8} {count}")


if __name__ == "__main__":
    main()
