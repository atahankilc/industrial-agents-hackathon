"""LLM slots for questions no template matches: the general `route` spec (places that may be items or room types,
stops, combined constraints), the `asks_for` check, kind `other` → the agent, and the decision cache that lets the
benchmark command reproduce its answers without an API key. Offline, with the fake client of tests/fake_llm.py.
Facts about proc-factory-dev-004: see tests/test_route_query.py."""

import json
from pathlib import Path

import pytest

from agent.llm_cache import DecisionCache
from agent.llm_parser import LlmQuestionParser, NeedsAgent
from core.building_map import BuildingMap
from tests.fake_llm import FakeClient, response

DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"
OTHER = DIRECTORY.parent / "proc-campus-dev-001"


@pytest.fixture(scope="module")
def bmap() -> BuildingMap:
    return BuildingMap.load(DIRECTORY)


def space(bmap: BuildingMap, name: str) -> str:
    return next(space_id for space_id, item in bmap.spaces.items() if item["name"] == name)


def place(name: str, floor: str | None = None, is_item: bool = False) -> dict:
    return {"name": name, "floor": floor, "is_item": is_item}


def slots(**values: object) -> str:
    base = dict.fromkeys(["start", "first", "second", "destination", "stops", "floor", "room_type", "asset_type",
                          "min_width_m", "item", "closed", "direction", "may_use_stairs", "step_free", "forklift",
                          "closures"])
    base.update(kind="route", asks_for="route")
    base.update(values)
    return json.dumps(base)


def parse(bmap: BuildingMap, *replies: str, cache: DecisionCache | None = None, text: str = "a question"):
    client = FakeClient(*[response(reply) for reply in replies])
    parsed = LlmQuestionParser(client, cache=cache or DecisionCache(None)).parse(text, bmap)
    return parsed, client


def test_combined_constraints_become_one_route_query(bmap: BuildingMap) -> None:
    parsed, _ = parse(bmap, slots(start=place("Kitchen 1.15"), destination=place("Meeting room 0.22"),
                                  step_free=True, closures=["Office lift"]))
    assert parsed.kind == "route_query"
    assert parsed.params["stops"] == [[space(bmap, "Kitchen 1.15")], [space(bmap, "Meeting room 0.22")]]
    assert parsed.params["step_free"] is True
    assert parsed.params["closed"] == [next(i for i, c in bmap.connectors.items() if c["name"] == "Office lift")]


def test_item_destination_keeps_every_holder_as_a_candidate(bmap: BuildingMap) -> None:
    parsed, _ = parse(bmap, slots(start=place("Main aisle H-B1"),
                                  destination=place("forklift charging station", is_item=True)))
    assert parsed.kind == "route_query"
    assert sorted(parsed.params["stops"][1]) == sorted([space(bmap, "Logistics zone H-C1"),
                                                        space(bmap, "Logistics zone H-C2")])


def test_forklift_and_min_width_go_to_route_query(bmap: BuildingMap) -> None:
    parsed, _ = parse(bmap, slots(start=place("Logistics zone H-C1"), destination=place("Production zone H-A2"),
                                  forklift=True, min_width_m=3.5))
    assert parsed.kind == "route_query"
    assert parsed.params["forklift"] is True and parsed.params["min_width"] == 3.5


@pytest.mark.parametrize(("extra", "kind"), [({}, "route"), ({"step_free": True}, "route_step_free"),
                                             ({"closures": ["Office staircase"]}, "route_with_closure")])
def test_simple_specs_keep_the_warm_up_kinds(bmap: BuildingMap, extra: dict, kind: str) -> None:
    parsed, _ = parse(bmap, slots(start=place("Kitchen 1.12"), destination=place("Office 0.31"), **extra))
    assert parsed.kind == kind
    assert (parsed.params["start"], parsed.params["destination"]) == (space(bmap, "Kitchen 1.12"),
                                                                      space(bmap, "Office 0.31"))


def test_stops_of_named_rooms_keep_the_tour_kind(bmap: BuildingMap) -> None:
    parsed, _ = parse(bmap, slots(start=place("Office 0.19"), stops=[place("Kitchen 1.10", "Floor 1")],
                                  destination=place("Office 0.29")))
    assert parsed.kind == "tour"
    assert parsed.params["stops"] == [space(bmap, "Office 0.19"), space(bmap, "Kitchen 1.10"),
                                      space(bmap, "Office 0.29")]


@pytest.mark.parametrize("kind", ["other", "unsupported"])
def test_other_kinds_go_to_the_agent(bmap: BuildingMap, kind: str) -> None:
    with pytest.raises(NeedsAgent):
        parse(bmap, slots(kind=kind, asks_for="other"))


def test_a_kind_that_does_not_answer_what_is_asked_goes_to_the_agent(bmap: BuildingMap) -> None:
    with pytest.raises(NeedsAgent, match="distance_m"):
        parse(bmap, slots(kind="count", asks_for="distance_m", asset_type="sink", floor="Ground floor"))


def test_benchmark_kind_space_without_a_floor_is_found_by_name(bmap: BuildingMap) -> None:
    parsed, _ = parse(bmap, slots(kind="shared_walls_count", asks_for="count", start=place("Office 0.31")))
    assert parsed.kind == "shared_walls_count" and parsed.params["start"] == space(bmap, "Office 0.31")


def test_a_closure_that_names_nothing_is_sent_back_once(bmap: BuildingMap) -> None:
    good = slots(start=place("Kitchen 1.15"), destination=place("Meeting room 0.22"), closures=["Office lift"],
                 step_free=True)
    bad = slots(start=place("Kitchen 1.15"), destination=place("Meeting room 0.22"), closures=["Lift East"],
                step_free=True)
    parsed, client = parse(bmap, bad, good)
    assert client.calls == 2 and parsed.kind == "route_query"


def test_cached_decisions_replay_without_the_model(bmap: BuildingMap, tmp_path: Path) -> None:
    cache = DecisionCache(tmp_path / "decisions.json")
    first, _ = parse(bmap, slots(start=place("Kitchen 1.15"), destination=place("Meeting room 0.22"),
                                 step_free=True, closures=["Office lift"]), cache=cache, text="Lift broken, step-free?")
    replay, client = parse(bmap, cache=DecisionCache(tmp_path / "decisions.json"), text="Lift broken, step-free?")
    assert client.calls == 0
    assert (replay.kind, replay.params) == (first.kind, first.params)
    assert replay.notes["parser"] == "llm-cache"


def test_the_cache_is_per_building_and_question(bmap: BuildingMap, tmp_path: Path) -> None:
    cache = DecisionCache(tmp_path / "decisions.json")
    with pytest.raises(NeedsAgent):
        parse(bmap, slots(kind="other", asks_for="other"), cache=cache, text="q1")
    _, other_question = parse(bmap, slots(start=place("Kitchen 1.12"), destination=place("Office 0.31")),
                              cache=cache, text="q2")
    assert other_question.calls == 1
    campus = BuildingMap.load(OTHER)  # same text, another building: its own decision, not the factory's
    client = FakeClient(response(slots(kind="count", asks_for="count", asset_type="chair", floor="Ground floor")))
    parsed = LlmQuestionParser(client, cache=cache).parse("q1", campus)
    assert (parsed.kind, client.calls) == ("count", 1)


def union_parameters(schema: object) -> int:
    """Parameters typed as a union (anyOf or a type list), counted the way the structured-output API counts them."""
    if not isinstance(schema, dict):
        return 0
    own = int("anyOf" in schema or isinstance(schema.get("type"), list))
    nested = sum(union_parameters(sub) for sub in schema.get("properties", {}).values())
    nested += union_parameters(schema.get("items"))
    nested += sum(union_parameters(sub) for sub in schema.get("anyOf", []))
    return own + nested


def test_the_slot_schema_stays_within_the_api_union_limit() -> None:
    # A schema with more than 16 union-typed parameters is rejected with HTTP 400 on every call (seen live
    # 2026-10-25: 21 parameters); the solver agent then silently answered everything instead of the parser.
    from agent.llm_parser import SCHEMA

    assert union_parameters(SCHEMA) <= 16
