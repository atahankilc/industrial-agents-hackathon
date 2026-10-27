"""shared_walls_count solver + shared-wall helpers (Q-003 rule) against train+dev gold inputs."""

import json
from functools import cache
from pathlib import Path

import pytest
from shapely.geometry import Point

from tests.kit_oracles.score import score_reply
from backend.core.building_map import BuildingMap
from tests.kit_oracles.formatter import format_reply
from backend.core.solvers import solve
from backend.core.solvers.walls import shared_wall_neighbours, shared_wall_segment, space_polygon

DATA = Path(__file__).resolve().parent.parent / "data"


@cache
def load(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def questions() -> list[tuple[Path, dict]]:
    items = []
    for split in ("train", "dev"):
        for path in sorted((DATA / split).glob("*/questions.jsonl")):
            for line in path.open(encoding="utf-8"):
                if line.strip() and (question := json.loads(line))["kind"] == "shared_walls_count":
                    items.append((path.parent, question))
    return items


def test_shared_walls_count_scores_all_train_dev():
    items = questions()
    assert len(items) == 143
    failures = []
    for directory, question in items:
        building = load(directory)
        reply = format_reply(building, solve(building, question["kind"], question["inputs"]))
        if not score_reply(question["answer"], reply):
            failures.append(question["id"])
    assert failures == []


def test_evidence_matches_value_and_is_json():
    directory, question = questions()[0]
    building = load(directory)
    result = solve(building, "shared_walls_count", question["inputs"])
    assert result.value == len(result.evidence["neighbours"])
    json.dumps(result.evidence)
    assert 1 <= len(result.explanation) <= 3


def test_neighbours_symmetric_and_segment_midpoint():
    directory, question = questions()[0]
    building = load(directory)
    start = question["inputs"]["start"]
    neighbours = shared_wall_neighbours(building, start)
    assert neighbours
    for item in neighbours:
        back = {other["id"] for other in shared_wall_neighbours(building, item["id"])}
        assert start in back
        segment = shared_wall_segment(building, start, item["id"])
        assert segment is not None
        assert segment["length_m"] == pytest.approx(item["shared_m"], abs=0.01)
        assert segment["longest_m"] <= segment["length_m"] + 1e-9
        # The midpoint sits in the wall gap: within the tolerance of both outlines.
        point = Point(segment["midpoint"])
        assert space_polygon(building, start).exterior.distance(point) <= 0.35
        assert space_polygon(building, item["id"]).exterior.distance(point) <= 0.35


def test_segment_none_for_far_spaces():
    directory, question = questions()[0]
    building = load(directory)
    start = question["inputs"]["start"]
    near = {item["id"] for item in shared_wall_neighbours(building, start, min_length=1e-9)}
    floor_id = building.spaces[start]["floor_id"]
    far = next(
        s for s in building.spaces if s != start and s not in near and building.spaces[s]["floor_id"] == floor_id
    )
    assert shared_wall_segment(building, start, far) is None
