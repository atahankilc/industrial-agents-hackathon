"""Scripted Guide conversations (tests/guide_conversations/*.json): offline checks of the files and of check_turn.
The live run that talks to Claude is scripts/eval_guide.py."""

import json
from pathlib import Path

from agent.guide_v1.guide import Guide, TurnResult
from agent.llm_parser import LlmUsage
from core.building_map import BuildingMap
from core.solvers_v1 import route as core_route
from scripts.eval_guide import EXPECT_KEYS, check_turn, load_conversation

FILES = sorted(Path("tests/guide_conversations").glob("*.json"))
CAMPUS = Path("data/dev/proc-campus-dev-001")
LOBBY, LAB = "proc-campus-dev-001-F0-S014", "proc-campus-dev-001-F2-S020"


def test_conversation_files_are_valid():
    assert len(FILES) >= 9
    for path in FILES:
        conversation = load_conversation(path)
        assert (Path(conversation["building"]) / "building.json").exists(), path
        assert conversation["turns"], path
        for turn in conversation["turns"]:
            assert turn["user"].strip(), path
            assert set(turn["expect"]) <= EXPECT_KEYS, (path, turn["expect"])


def test_unknown_expect_key_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"building": str(CAMPUS), "turns": [{"user": "hi", "expect": {"nope": 1}}]}))
    try:
        load_conversation(bad)
    except ValueError as error:
        assert "nope" in str(error)
    else:
        raise AssertionError("unknown key accepted")


class Offline(Guide):
    def __init__(self) -> None:  # no client: check_turn never calls the API
        super().__init__(CAMPUS, client=object())


def turn_result(route: dict | None, **kwargs) -> TurnResult:
    fields = dict(text="ok", asked=False, space_ids=[], asset_ids=[], connector_ids=[], routes=[route] if route else [],
                  options=[], tool_calls=[], usage=LlmUsage(), grounded=True)
    return TurnResult(**{**fields, **kwargs})


def test_check_turn_passes_for_matching_route_and_flags_wrong_length():
    guide = Offline()
    guide.session.position = LOBBY
    route = core_route(BuildingMap.load(CAMPUS), LOBBY, LAB)
    expect = {"asked": False, "route_to": LAB, "grounded": True}
    assert check_turn(guide, turn_result(route), expect) == []
    wrong = {**route, "optimal_length_m": route["optimal_length_m"] + 5}
    failures = check_turn(guide, turn_result(wrong), expect)
    assert len(failures) == 1 and "optimal_length_m" in failures[0]


def test_check_turn_flags_other_expectations():
    guide = Offline()
    result = turn_result(None, asked=True, grounded=False, tool_calls=[{"name": "locate"}])
    failures = check_turn(guide, result, {"asked": False, "tools": ["route"], "step_free": True, "grounded": True,
                                          "route_to": LAB, "space_ids_include": [LAB]})
    assert len(failures) == 6
    assert check_turn(guide, result, {"no_route": True}) == []
    assert check_turn(guide, result, {"tools": []}) != []


def test_check_turn_multi_candidate_closure_compares_every_reading():
    guide, bmap = Offline(), BuildingMap.load(CAMPUS)
    lifts = ["proc-campus-dev-001-V02", "proc-campus-dev-001-V04"]  # "the lift" = Lift 1 or Lift 2
    guide.session.closures = [lifts]
    expect = {"route_to": LAB}
    same = core_route(bmap, LOBBY, LAB)  # stairs win, every reading gives the same length
    assert check_turn(guide, turn_result(same), expect) == []
    guide.session.step_free = True  # closing Lift 1 vs Lift 2 now gives different routes: the Guide should ask
    failures = check_turn(guide, turn_result(core_route(bmap, LOBBY, LAB, step_free=True)), expect)
    assert len(failures) == 1 and "should have asked" in failures[0]


def test_check_turn_rejects_unreachable_routes():
    guide = Offline()
    unreachable = {"reachable": False, "from_space_id": LOBBY, "to_space_id": LAB}
    failures = check_turn(guide, turn_result(unreachable), {"route_to": LAB})
    assert len(failures) == 1 and "not reachable" in failures[0]


def test_check_turn_asset_total_compares_locate_total_and_reply():
    guide = Offline()
    total = sum(a["type"] == "3d_printer" for a in guide.bmap.assets.values())
    calls = [{"name": "locate"}]
    guide.tool_results = [{"status": "ok", "total": total}]
    good = turn_result(None, text=f"There are {total} 3D printers.", tool_calls=calls)
    assert check_turn(guide, good, {"asset_total": "3d_printer"}) == []
    silent = turn_result(None, text="Several.", tool_calls=calls)
    assert "does not state" in check_turn(guide, silent, {"asset_total": "3d_printer"})[0]
    guide.tool_results = [{"status": "ok", "total": total + 1}]
    assert "core counts" in check_turn(guide, good, {"asset_total": "3d_printer"})[0]
