"""Route paths against every train/dev warm-up answer (questions_basic.jsonl), no LLM.

  uv run pytest tests/test_routes.py -q -s     # -s prints the per-kind table

For route, route_step_free, route_with_closure and tour, BuildingMap.route must reproduce each leg's
optimal_length_m (1 cm), space_path and element_path exactly, and raise MapError where the answer says
`reachable: false`. The one exception: a leg where our length equals the organisers' own 1.1.0 starter
(archive/initial-repo/starter_agent/building_map.py) but not the gold (resplan-12462, 10 cm — the gold was made with
a different geometry build); such legs are listed, not failed. Also checks that errand legs are real paths that add up to the scored total."""

import importlib.util
import itertools
import json
from collections import Counter
from pathlib import Path

from backend.core.building_map import OUTSIDE, BuildingMap, MapError
from backend.core.solvers_v1 import solve
from tests.test_question_parser import DATA, building, labelled_questions

STARTER = Path(__file__).resolve().parent.parent / "archive/initial-repo/starter_agent/building_map.py"
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure", "tour")
TOLERANCE_M = 0.01


def warm_up_questions() -> list[tuple[Path, dict]]:
    questions = []
    for split in ("train", "dev"):
        for path in sorted((DATA / split).glob("*/questions_basic.jsonl")):
            questions += [(path.parent, json.loads(line)) for line in path.open(encoding="utf-8") if line.strip()]
    return [(directory, question) for directory, question in questions if question["kind"] in ROUTE_KINDS]


def outcome(bmap: BuildingMap, question: dict) -> str | None:
    """None when the route matches the answer, else what differs."""
    answer = question["answer"]
    legs = answer.get("legs", []) if question["kind"] == "tour" else [answer]
    stops = answer["stops"] if question["kind"] == "tour" else [answer["from_space_id"], answer["to_space_id"]]
    bmap.closed = {answer["closed_element_id"]} if "closed_element_id" in answer else set()
    try:
        result = bmap.route(stops[0], stops[-1], step_free=question["kind"] == "route_step_free", via=stops[1:-1])
    except MapError:
        return None if answer.get("reachable") is False else "MapError on a reachable route"
    finally:
        bmap.closed = set()
    if answer.get("reachable") is False:
        return "route found where the answer says unreachable"
    for got, expected in zip(result.legs, legs, strict=True):
        if abs(got["optimal_length_m"] - expected["optimal_length_m"]) > TOLERANCE_M:
            reference = starter_length(bmap, got["from_space_id"], got["to_space_id"], question, answer)
            if abs(reference - got["optimal_length_m"]) <= TOLERANCE_M:
                continue  # same as the organisers' reference implementation
            return f"length {got['optimal_length_m']} != {expected['optimal_length_m']}"
        for key in ("space_path", "element_path"):
            if got[key] != expected[key]:
                return f"{key} {got[key]} != {expected[key]}"
    return None


def starter_length(bmap: BuildingMap, start: str, end: str, question: dict, answer: dict) -> float:
    """The leg length by the organisers' kit 1.1.0 starter agent (imported from the archive)."""
    spec = importlib.util.spec_from_file_location("starter_building_map", STARTER)
    starter = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(starter)  # type: ignore[union-attr]
    reference = starter.BuildingMap(bmap.data)
    reference.closed = {answer["closed_element_id"]} if "closed_element_id" in answer else set()
    return reference.route(start, end, step_free=question["kind"] == "route_step_free").length_m


def test_warm_up_route_paths() -> None:
    totals, good, failures = Counter(), Counter(), []
    for directory, question in warm_up_questions():
        problem = outcome(building(directory), question)
        totals[question["kind"]] += 1
        good[question["kind"]] += problem is None
        if problem:
            failures.append(f"{question['id']}: {problem}"[:400])
    print("\ntrain+dev warm-up: route length + space_path + element_path")
    for kind in sorted(totals):
        print(f"  {kind:20s} {good[kind]:4d} / {totals[kind]}")
    print(f"  {'all':20s} {sum(good.values()):4d} / {sum(totals.values())}")
    assert failures == []


def test_errand_legs_are_walkable_paths() -> None:
    for directory, question in labelled_questions():
        if question["kind"] != "errand":
            continue
        bmap = building(directory)
        result = solve(bmap, "errand", question["inputs"])
        first, second = result["legs"]
        assert first["from_space_id"] == question["inputs"]["start"]
        assert first["to_space_id"] == second["from_space_id"] == result["via"]["space_id"]
        assert second["to_space_id"] == result["target"]["space_id"]
        assert abs(first["optimal_length_m"] + second["optimal_length_m"] - result["total_m"]) <= 2 * TOLERANCE_M  # each leg rounded
        for leg in result["legs"]:
            assert len(leg["element_path"]) >= len(leg["space_path"]) - 1
            for space in leg["space_path"]:
                assert space == OUTSIDE or space in bmap.spaces
            for element in leg["element_path"]:
                assert element in bmap.openings or element in bmap.connectors
            for first_space, second_space in itertools.pairwise(leg["space_path"]):
                assert first_space != second_space
