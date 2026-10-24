"""Lookup tools: locate, find_places, place_info, building_fact (dev buildings as fixtures)."""

import functools
from pathlib import Path

from agent.guide.tools import TOOLS, Session, run_tool
from core.building_map import BuildingMap
from core.solvers import area, shared_walls, solve
from tests.test_question_parser import labelled_questions

FACTORY = Path("data/dev/proc-factory-dev-004")
CAMPUS = Path("data/dev/proc-campus-dev-001")
OSM_DUP = Path("data/dev/osm-way27917482")
FACT_KINDS = {"largest_room", "floor_area_total", "count", "shared_walls_count", "room_stacked", "straight_line_3d",
              "errand", "wide_delivery_count", "step_free_reachable_count", "what_if_door"}


@functools.cache
def bmap(path: Path) -> BuildingMap:
    return BuildingMap.load(path)


def dev_benchmark_questions() -> list[tuple[Path, dict]]:
    return [(d, q) for d, q in labelled_questions()
            if d.parent.name == "dev" and q["kind"] in FACT_KINDS and q.get("inputs")]


def place_text(b: BuildingMap, space_id: str) -> str:
    """The space's name, or its ref when another space on the same floor shares the name."""
    space = b.spaces[space_id]
    twins = [s for s in b.spaces.values() if s["floor_id"] == space["floor_id"] and s["name"] == space["name"]]
    return space["ref"] if len(twins) > 1 and space.get("ref") else space["name"]


def args_from_gold(b: BuildingMap, q: dict) -> dict:
    i = q["inputs"]
    args: dict = {"kind": q["kind"]}
    if "start" in i:
        args["place"] = place_text(b, i["start"])
    if "first" in i:
        args["place"], args["place2"] = place_text(b, i["first"]), place_text(b, i["second"])
    if "floor_id" in i:
        args["floor"] = b.floor_name(i["floor_id"])
    for key in ("room_type", "asset_type", "direction"):
        if key in i:
            args[key] = i[key].replace("_", " ") if key != "direction" else i[key]
    if "min_width" in i:
        args["min_width_m"] = i["min_width"]
    if "closed" in i:
        args["closed"] = b.connectors[i["closed"]]["name"]
    return args


def test_locate_lists_every_room_with_counts():
    out = run_tool(bmap(CAMPUS), Session(), "locate", {"thing": "3D printer"})
    assert out["status"] == "ok"
    assert {(r["ref"], r["count"]) for r in out["rooms"]} == {("1.14", 4), ("2.20", 1)}


def test_locate_ignores_leading_article():
    out = run_tool(bmap(CAMPUS), Session(), "locate", {"thing": "the 3D printer"})
    assert out["status"] == "ok" and out["total"] == 5


def test_locate_unknown_thing_is_not_found_with_nearest():
    out = run_tool(bmap(FACTORY), Session(), "locate", {"thing": "espresso robot"})
    assert out["status"] == "not_found" and "nearest" in out and out["summary"]


def test_find_places_describes_hits_and_reports_none():
    out = run_tool(bmap(CAMPUS), Session(), "find_places", {"query": "makerspace", "floor": None})
    assert out["status"] == "ok" and 0 < len(out["hits"]) <= 10 and out["summary"]
    none = run_tool(bmap(CAMPUS), Session(), "find_places", {"query": "zzzqqq", "floor": None})
    assert none["status"] == "not_found" and "nearest" in none


def test_place_info_matches_core():
    b = bmap(CAMPUS)
    out = run_tool(b, Session(), "place_info", {"place": "1.14"})
    assert out["area_m2"] == round(area(b, "proc-campus-dev-001-F1-S014"), 2)
    assert out["shared_walls"] == shared_walls(b, "proc-campus-dev-001-F1-S014")["count"]
    assert "3D printer 1.14-A" in out["assets"]
    assert out["name"] in out["summary"] and out["ref"] in out["summary"] and out["floor"] in out["summary"]


def test_place_info_ambiguous_place_asks():
    out = run_tool(bmap(OSM_DUP), Session(), "place_info", {"place": "Generic room 03.08.033"})
    assert out["status"] == "ambiguous" and len(out["options"]) == 3 and out["summary"]


def test_building_fact_equals_solver_on_gold_inputs():
    questions = dev_benchmark_questions()
    assert questions
    ambiguous = 0
    for directory, q in questions:
        b = bmap(directory)
        out = run_tool(b, Session(), "building_fact", args_from_gold(b, q))
        assert out["status"] in ("ok", "ambiguous"), (q["id"], out)
        if out["status"] == "ok":
            assert out["result"] == solve(b, q["kind"], q["inputs"]), q["id"]
            assert out["summary"]
        else:
            ambiguous += 1
            assert all({"choices", "summary", "result"} <= set(o) for o in out["options"]), q["id"]
            assert any(o["result"] == solve(b, q["kind"], q["inputs"]) for o in out["options"]), q["id"]
    assert ambiguous < len(questions) // 4


def test_building_fact_count_and_errand_step_free():
    b = bmap(CAMPUS)
    out = run_tool(b, Session(), "building_fact", {"kind": "count", "asset_type": "3D printer", "floor": "Floor 1"})
    assert out["status"] == "ok" and out["result"]["count"] == 4


def test_tools_schema_is_strict_and_stable():
    assert [t["name"] for t in TOOLS][:4] == ["locate", "find_places", "place_info", "building_fact"]
    for tool in TOOLS:
        schema = tool["input_schema"]
        assert schema["additionalProperties"] is False and tool["strict"] is True
        assert set(schema["required"]) == set(schema["properties"])


def test_bad_args_never_raise():
    assert run_tool(bmap(CAMPUS), Session(), "building_fact", {"kind": "largest_room"})["status"] == "error"
    assert run_tool(bmap(CAMPUS), Session(), "nope", {})["status"] == "error"
    assert run_tool(bmap(CAMPUS), Session(), "locate", {})["status"] == "error"


def test_unresolvable_floor_or_type_is_not_found_with_nearest():
    b = bmap(CAMPUS)
    floor = run_tool(b, Session(), "building_fact", {"kind": "count", "asset_type": "chair", "floor": "Floor 99"})
    assert floor["status"] == "not_found" and "Floor 1" in floor["nearest"] and floor["summary"]
    kind = run_tool(b, Session(), "building_fact", {"kind": "count", "asset_type": "3d printr", "floor": "Floor 1"})
    assert kind["status"] == "not_found" and "3d printer" in kind["nearest"]
    room = run_tool(b, Session(), "building_fact",
                    {"kind": "largest_room", "room_type": "lbaoratory", "floor": "Floor 1"})
    assert room["status"] == "not_found"
    assert run_tool(b, Session(), "find_places", {"query": "lab", "floor": "Floor 99"})["status"] == "not_found"


def test_ambiguous_options_share_one_shape_in_every_tool():
    b = bmap(OSM_DUP)
    info = run_tool(b, Session(), "place_info", {"place": "Generic room 03.08.033"})
    fact = run_tool(b, Session(), "building_fact", {"kind": "shared_walls_count", "place": "Generic room 03.08.033"})
    for out in (info, fact):
        assert out["status"] == "ambiguous"
        assert all({"choices", "summary", "result"} <= set(o) and "summary" not in o["result"] for o in out["options"])
    assert "count" in fact["options"][0]["result"] and "area_m2" in info["options"][0]["result"]


def test_too_many_readings_are_listed_not_crashed():
    b = bmap(OSM_DUP)
    out = run_tool(b, Session(), "building_fact", {"kind": "shared_walls_count", "place": "toilet"})
    assert out["status"] == "ambiguous" and out["truncated"] and "too many" in out["summary"]
    assert len(out["options"]) == 5 and all(set(o) == {"choices"} for o in out["options"])
    assert run_tool(b, Session(), "place_info", {"place": "toilet"})["status"] == "ambiguous"
