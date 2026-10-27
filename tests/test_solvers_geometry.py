"""Geometry solvers (backend/core/solvers/geometry.py) on the gold `inputs` of every train+dev question, scored by
the official tests/kit_oracles/score.py via scripts/validate_solvers.py.

  uv run pytest tests/test_solvers_geometry.py -q"""

import importlib.util
import json
from pathlib import Path

import pytest

from tests.kit_oracles.formatter import answer_line
from backend.core.solvers import solve

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_solvers.py"
spec = importlib.util.spec_from_file_location("validate_solvers", SCRIPT)
validate_solvers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_solvers)

EXPECTED_TOTALS = {"floor_area_total": 181, "largest_room": 96, "straight_line_3d": 30, "room_stacked": 26}


def questions(kind: str) -> list[tuple[Path, dict]]:
    return [(d, q) for d, q in validate_solvers.labelled(["train", "dev"]) if q["kind"] == kind]


@pytest.mark.parametrize("kind", sorted(EXPECTED_TOTALS))
def test_every_train_dev_question_passes(kind: str) -> None:
    items = questions(kind)
    assert len(items) == EXPECTED_TOTALS[kind]
    failures = [q["id"] for d, q in items if not validate_solvers.check(d, q)[0]]
    assert failures == []


@pytest.mark.parametrize("kind", sorted(EXPECTED_TOTALS))
def test_evidence_is_json_and_answer_line_is_clean(kind: str) -> None:
    directory, question = questions(kind)[0]
    building = validate_solvers.building(directory)
    result = solve(building, kind, {**question["inputs"], "unused_extra": 1})
    json.dumps(result.evidence)
    assert 1 <= len(result.explanation) <= 3
    line = answer_line(building, result)
    assert line.startswith("Answer: ") and "\n" not in line


def test_room_stacked_rejects_bad_direction() -> None:
    directory, question = questions("room_stacked")[0]
    with pytest.raises(ValueError):
        solve(validate_solvers.building(directory), "room_stacked", {**question["inputs"], "direction": "beside"})
