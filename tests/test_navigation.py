"""Navigation layer (core/navigation.py + core/basic_parser.py) against every train/dev warm-up question.

  uv run pytest tests/test_navigation.py -q
  uv run python scripts/validate_warmup.py -v     # the per-kind table and every miss"""

import importlib.util
import json
from functools import cache
from pathlib import Path

import pytest

from core.basic_parser import answer_basic, parse_basic
from core.building_map import BuildingMap, MapError
from core.navigation import count_assets, find_route, locate, path_length, tour

ROOT = Path(__file__).resolve().parent.parent
SWISS = next((ROOT / "data").glob("*/swiss-3355"))


@cache
def validation():
    spec = importlib.util.spec_from_file_location("validate_warmup", ROOT / "scripts" / "validate_warmup.py")
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.evaluate()


@cache
def swiss() -> BuildingMap:
    return BuildingMap.load(SWISS)


def gold(question_id: str) -> dict:
    for line in (SWISS / "questions_basic.jsonl").open(encoding="utf-8"):
        question = json.loads(line)
        if question["id"] == question_id:
            return question
    raise KeyError(question_id)


def test_warmup_question_count():
    _, totals, _ = validation()
    assert sum(totals.values()) == 2130


@pytest.mark.parametrize("kind", ["locate", "count"])
def test_search_kinds_perfect(kind):
    passed, totals, _ = validation()
    assert passed[kind]["parse"] == totals[kind]
    assert passed[kind]["answer"] == totals[kind]


@pytest.mark.parametrize("kind", ["route", "route_step_free", "route_with_closure", "tour"])
def test_route_kinds(kind):
    passed, totals, _ = validation()
    n = totals[kind]
    # Navigation alone (fed the gold ids) reproduces every gold route exactly: length, space_path, element_path.
    assert passed[kind]["oracle"] == n
    assert passed[kind]["reachable"] == n
    # End to end from text: the only misses are OSM spaces sharing one name on one floor ("Büro" ×N), where the
    # text cannot pick the gold space; the gold id is then always one of the parser's alternatives.
    misses = n - passed[kind]["answer"]
    assert misses == passed[kind]["gold_in_alternatives"]
    assert passed[kind]["answer"] / n >= 0.98
    for metric in ("length", "space_path", "element_path"):
        assert passed[kind][metric] == passed[kind]["answer"]


def test_overall_accuracy():
    passed, totals, notable = validation()
    answered = sum(counter["answer"] for counter in passed.values())
    assert answered / sum(totals.values()) >= 0.995
    assert all(not outcome.error.startswith("ParseError") for _, outcome in notable)


def test_route_matches_gold_and_does_not_mutate():
    building = swiss()
    question = gold("swiss-3355-Q08")  # Main staircase closed
    answer = question["answer"]
    result = find_route(building, answer["from_space_id"], answer["to_space_id"], closed=["Main staircase"])
    assert result.reachable
    assert result.length_m == answer["optimal_length_m"]
    assert result.space_path == answer["space_path"]
    assert result.element_path == answer["element_path"]
    assert result.closed == [answer["closed_element_id"]]
    assert building.closed == set() and building.last_route is None and building.located_asset_ids == []
    assert path_length(building, answer["space_path"], answer["element_path"], closed=["Main staircase"]) == 41.79
    json.dumps(result.to_dict())


def test_unreachable_is_structured():
    answer = gold("swiss-3355-Q07")["answer"]
    result = find_route(swiss(), answer["from_space_id"], answer["to_space_id"], step_free=True)
    assert result.reachable is False and result.length_m is None and result.reason
    assert "space_path" not in result.to_dict()


def test_tour_legs_and_via():
    answer = gold("swiss-3355-Q09")["answer"]
    result = tour(swiss(), answer["stops"])
    assert result.length_m == answer["optimal_length_m"]
    assert [leg.element_path for leg in result.legs] == [leg["element_path"] for leg in answer["legs"]]
    via = find_route(swiss(), answer["stops"][0], answer["stops"][-1], via=answer["stops"][1:-1])
    assert via.length_m == answer["optimal_length_m"]
    assert via.element_path == [element for leg in answer["legs"] for element in leg["element_path"]]


def test_outside_endpoint_and_bad_reference():
    result = find_route(swiss(), "swiss-3355-F0-S023", "outside")
    assert result.reachable and result.space_path[-1] == "outside" and result.steps[-1].endswith("outside the building.")
    with pytest.raises(MapError):
        find_route(swiss(), "no such room", "swiss-3355-F0-S023")


def test_locate_and_count():
    hit = locate(swiss(), "shoe cabinet")
    assert hit.match == "type" and hit.assets[0].asset_id == "swiss-3355-A00116"
    assert count_assets(swiss(), "kitchen_counter", "swiss-3355-F-1").count == 2


def test_loose_phrasings():
    building = swiss()
    parsed = parse_basic("How do I get step-free from Bedroom 1.10 (apartment 6) to Bedroom 2.25 (apartment 10)?", building)
    assert parsed.kind == "route_step_free" and parsed.params["step_free"] is True
    assert parse_basic("Where can I find a shoe cabinet?", building).params["asset_type"] == "shoe_cabinet"
    parsed, result = answer_basic("How many kitchen counters are on basement 1?", building)
    assert parsed.kind == "count" and result["count"] == 2
