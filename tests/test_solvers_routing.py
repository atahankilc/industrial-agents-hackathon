"""errand + what_if_door solvers against every labelled train/dev question (rules: backend/core/solvers/routing.py).

  uv run pytest tests/test_solvers_routing.py -q"""

import copy
import itertools
import json
from functools import cache
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from tests.kit_oracles.score import score_reply
from backend.core.building_map import OUTSIDE, BuildingMap
from tests.kit_oracles.formatter import format_reply
from backend.core.solvers import solve
from backend.core.solvers.routing import shared_wall_midpoint

DATA = Path(__file__).resolve().parent.parent / "data"


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def labelled(kind: str) -> list[tuple[Path, dict]]:
    questions = []
    for path in sorted((DATA / "buildings").glob("*/questions.jsonl")):  # test-split questions have no answer
        for line in path.open(encoding="utf-8"):
            if line.strip() and (question := json.loads(line))["kind"] == kind and "answer" in question:
                questions.append((path.parent, question))
    return questions


def test_errand_all_labelled_pass_with_gold_via_and_target():
    questions = labelled("errand")
    assert len(questions) == 93
    passed = vias = targets = 0
    for directory, question in questions:
        result = solve(building(directory), "errand", question["inputs"])
        passed += score_reply(question["answer"], format_reply(building(directory), result))
        vias += result.evidence["via"] == question["answer"]["via"]
        targets += result.evidence["target"] == question["answer"]["target"]
    assert (passed, vias, targets) == (93, 93, 93)


def test_errand_evidence_legs_are_walkable_and_sum():
    """Every labelled errand: two legs chained start → via → target, real spaces and elements, adding up to the total."""
    for directory, question in labelled("errand"):
        bmap = building(directory)
        result = solve(bmap, "errand", question["inputs"])
        first, second = result.evidence["legs"]
        assert first["nodes"][0] == question["inputs"]["start"]
        assert first["nodes"][-1] == second["nodes"][0] == result.evidence["via"]
        assert second["nodes"][-1] == result.evidence["target"]
        assert abs(first["length_m"] + second["length_m"] - result.value) <= 0.011  # each leg rounded
        for leg in (first, second):
            assert all(space == OUTSIDE or space in bmap.spaces for space in leg["spaces"])
            assert all(element in bmap.openings or element in bmap.connectors for element in leg["elements"])
            assert all(a != b for a, b in itertools.pairwise(leg["spaces"]))


def test_what_if_door_all_labelled_pass():
    questions = labelled("what_if_door")
    assert len(questions) == 4
    passed = 0
    for directory, question in questions:
        result = solve(building(directory), "what_if_door", question["inputs"])
        passed += score_reply(question["answer"], format_reply(building(directory), result))
    assert passed == 4


@pytest.mark.parametrize("kind", ["errand", "what_if_door"])
def test_solvers_do_not_mutate_building(kind):
    directory, question = labelled(kind)[0]
    fresh = BuildingMap.load(directory)
    snapshot = copy.deepcopy(fresh.data)
    solve(fresh, kind, question["inputs"])
    assert fresh.data == snapshot
    assert len(fresh.openings) == len(snapshot["openings"])
    assert fresh.closed == set() and fresh.last_route is None


def test_shared_wall_midpoint_is_middle_of_common_edge():
    # Two 4 m squares side by side with a 0.2 m wall gap: shared wall runs x≈4.1, y∈[0, 4].
    left = Polygon([(0, 0), (4, 0), (4, 4), (0, 4)])
    right = Polygon([(4.2, 0), (8.2, 0), (8.2, 4), (4.2, 4)])
    x, y = shared_wall_midpoint(left, right)
    assert abs(x - 4.1) < 1e-6 and abs(y - 2.0) < 1e-6
    # Partly overlapping wall (right square shifted up by 3 m): common stretch y∈[3, 4] → middle y = 3.5.
    shifted = Polygon([(4.2, 3), (8.2, 3), (8.2, 7), (4.2, 7)])
    x, y = shared_wall_midpoint(left, shifted)
    assert abs(x - 4.1) < 0.2 and abs(y - 3.5) < 0.2
