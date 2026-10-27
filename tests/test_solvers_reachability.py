"""Reachability solvers vs the labelled train+dev answers, plus helper behaviour (no mutation, closures)."""

import copy
import json
from functools import cache
from pathlib import Path

import pytest

from tests.kit_oracles.score import score_reply
from backend.core.building_map import BuildingMap
from tests.kit_oracles.formatter import format_reply
from backend.core.solvers import solve
from backend.core.solvers.reachability import is_room, reachable_spaces, rooms_on_floor

DATA = Path(__file__).resolve().parent.parent / "data"
KINDS = ("wide_delivery_count", "step_free_reachable_count")


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def labelled(kind: str) -> list[tuple[Path, dict]]:
    items = []
    for split in ("train", "dev"):
        for path in sorted((DATA / split).glob("*/questions.jsonl")):
            for line in path.open(encoding="utf-8"):
                if line.strip() and (question := json.loads(line))["kind"] == kind:
                    items.append((path.parent, question))
    return items


@pytest.mark.parametrize(("kind", "expected_total"), [("wide_delivery_count", 80), ("step_free_reachable_count", 2)])
def test_all_labelled_answers_pass(kind: str, expected_total: int) -> None:
    items = labelled(kind)
    assert len(items) == expected_total
    failures = []
    for directory, question in items:
        result = solve(building(directory), kind, question["inputs"])
        if not score_reply(question["answer"], format_reply(building(directory), result)):
            failures.append((question["id"], result.value, question["answer"]["value"]))
    assert failures == []


def test_room_definition_matches_manifest_rooms_column() -> None:
    import csv

    for row in csv.DictReader((DATA / "manifest.csv").open(encoding="utf-8")):
        spaces = json.loads((DATA / row["path"] / "building.json").read_text(encoding="utf-8"))["spaces"]
        assert sum(is_room(space) for space in spaces) == int(row["rooms"]), row["building_id"]


def test_solvers_do_not_mutate_building() -> None:
    directory, question = labelled("step_free_reachable_count")[0]
    fresh = BuildingMap.load(directory)
    before = copy.deepcopy(fresh.data)
    solve(fresh, question["kind"], question["inputs"])
    directory_w, question_w = labelled("wide_delivery_count")[0]
    fresh_w = BuildingMap.load(directory_w)
    before_w = copy.deepcopy(fresh_w.data)
    solve(fresh_w, question_w["kind"], question_w["inputs"])
    assert fresh.data == before and fresh.closed == set()
    assert fresh_w.data == before_w and fresh_w.closed == set()


def test_constraints_only_shrink_reachability() -> None:
    directory, question = labelled("wide_delivery_count")[0]
    b = building(directory)
    start = question["inputs"]["start"]
    free = reachable_spaces(b, start, step_free=False)
    step_free = reachable_spaces(b, start, step_free=True)
    wide = reachable_spaces(b, start, step_free=True, min_width=question["inputs"]["min_width"])
    assert start in wide and wide <= step_free <= free


def test_closing_a_space_removes_it() -> None:
    directory, question = labelled("wide_delivery_count")[0]
    b = building(directory)
    start = question["inputs"]["start"]
    reached = reachable_spaces(b, start, step_free=True)
    victim = next(space_id for space_id in sorted(reached) if space_id != start)
    assert victim not in reachable_spaces(b, start, step_free=True, closed=[victim])
    assert reachable_spaces(b, start, step_free=True, closed=[start]) == set()


def test_evidence_lists_counted_rooms() -> None:
    directory, question = labelled("wide_delivery_count")[0]
    result = solve(building(directory), question["kind"], question["inputs"])
    assert len(result.evidence["rooms"]) == result.value
    assert result.evidence["rooms"] == rooms_on_floor(
        building(directory), result.evidence["rooms"], question["inputs"]["floor_id"]
    )
