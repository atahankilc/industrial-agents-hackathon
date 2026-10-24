"""Place resolution and candidate fan-out for the Guide tools (dev buildings as fixtures)."""

import functools
from pathlib import Path

from agent.guide.resolve import MAX_OPTIONS, describe, fan_out, nearest_names, resolve_elements, resolve_places
from core.building_map import BuildingMap

FACTORY = Path("data/dev/proc-factory-dev-004")   # two 3D printers, both in F0-S004
CAMPUS = Path("data/dev/proc-campus-dev-001")     # 3D printers in F1-S014 (Makerspace 1.14) and F2-S020; Lift 1, Lift 2
OSM_DUP = Path("data/dev/osm-way27917482")        # three "Generic room 03.08.033" on Floor 3 (S015, S016, S017)


@functools.cache
def bmap(path: Path) -> BuildingMap:
    return BuildingMap.load(path)


def test_asset_type_phrase_resolves_to_rooms_holding_it():
    assert resolve_places(bmap(FACTORY), "the 3D printer") == ["proc-factory-dev-004-F0-S004"]
    assert sorted(resolve_places(bmap(CAMPUS), "3D printer")) == ["proc-campus-dev-001-F1-S014", "proc-campus-dev-001-F2-S020"]


def test_type_phrase_does_not_pull_in_substring_types():
    spaces = resolve_places(bmap(CAMPUS), "printer")
    assert spaces
    assert all(any(a["type"] == "printer" and a["space_id"] == s for a in bmap(CAMPUS).assets.values()) for s in spaces)


def test_ref_and_room_prefix_resolve_to_the_space():
    assert resolve_places(bmap(CAMPUS), "1.14") == ["proc-campus-dev-001-F1-S014"]
    assert resolve_places(bmap(CAMPUS), "room 1.14") == ["proc-campus-dev-001-F1-S014"]
    assert resolve_places(bmap(CAMPUS), "Makerspace 1.14") == ["proc-campus-dev-001-F1-S014"]


def test_duplicate_names_return_every_candidate():
    assert resolve_places(bmap(OSM_DUP), "Generic room 03.08.033") == [f"osm-way27917482-F3-S0{n}" for n in (15, 16, 17)]


def test_unknown_place_returns_nothing_and_nearest_names():
    assert resolve_places(bmap(CAMPUS), "room 9.99") == []
    assert resolve_places(bmap(FACTORY), "espresso robot") == []
    assert len(nearest_names(bmap(CAMPUS), "Makerspace 1.41")) >= 1


def test_closure_elements():
    assert resolve_elements(bmap(CAMPUS), "the lift") == ["proc-campus-dev-001-V02", "proc-campus-dev-001-V04"]
    stairs = ["proc-campus-dev-001-V01", "proc-campus-dev-001-V03"]
    assert resolve_elements(bmap(CAMPUS), "the stairs") == stairs
    assert resolve_elements(bmap(CAMPUS), "stairs") == stairs
    assert resolve_elements(bmap(CAMPUS), "Lift 2") == ["proc-campus-dev-001-V04"]
    assert resolve_elements(bmap(Path("data/dev/resplan-1465")), "the lift") == []


def test_describe_space_connector_and_opening():
    campus = bmap(CAMPUS)
    assert describe(campus, "proc-campus-dev-001-F1-S014")["ref"] == "1.14"
    lift = describe(campus, "proc-campus-dev-001-V02")
    assert lift["kind"] == "lift" and lift["name"] == "Lift 1" and "," in lift["floor"]
    opening_id = next(iter(campus.openings))
    assert describe(campus, opening_id)["id"] == opening_id


def test_fan_out_agrees_when_results_match():
    out = fan_out(bmap(CAMPUS), {"place": ["a", "b"]}, lambda c: {"summary": "same", "x": 1})
    assert out == {"status": "ok", "summary": "same", "x": 1}


def test_fan_out_ambiguous_lists_options_with_their_results():
    out = fan_out(bmap(CAMPUS), {"place": ["proc-campus-dev-001-F1-S014", "proc-campus-dev-001-F2-S020"]},
                  lambda c: {"summary": c["place"]})
    assert out["status"] == "ambiguous" and len(out["options"]) == 2
    assert out["options"][0]["choices"]["place"]["ref"] == "1.14"
    assert out["options"][0]["result"]["summary"] == "proc-campus-dev-001-F1-S014"


def test_fan_out_not_found_and_too_many():
    assert fan_out(bmap(CAMPUS), {"place": []}, lambda c: {})["status"] == "not_found"
    many = fan_out(bmap(CAMPUS), {"a": list("123"), "b": list("12")}, lambda c: {"summary": str(c)})
    assert many["status"] == "ambiguous" and len(many["options"]) <= MAX_OPTIONS
    assert many["truncated"] is True


def test_fan_out_turns_map_errors_into_error_results():
    def run(choice):
        raise ValueError("no route")
    out = fan_out(bmap(CAMPUS), {"place": ["proc-campus-dev-001-F1-S014"]}, run)
    assert out == {"status": "error", "summary": "no route"}
