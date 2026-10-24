"""Scripted Guide conversations (tests/guide_conversations/*.json): offline checks of the files and of check_turn.
The live run that talks to Claude is scripts/eval_guide.py."""

import json
from pathlib import Path

from agent.guide import GuideTurn
from agent.tools import TOOL_DEFINITIONS, BuildingSession
from scripts.eval_guide import EXPECT_KEYS, check_turn, load_conversation

FILES = sorted(Path("tests/guide_conversations").glob("*.json"))
CAMPUS = Path("data/dev/proc-campus-dev-001")
LOBBY, LAB = "proc-campus-dev-001-F0-S014", "proc-campus-dev-001-F2-S020"
TOOL_NAMES = {tool["name"] for tool in TOOL_DEFINITIONS}


def test_conversation_files_are_valid():
    assert len(FILES) >= 9
    for path in FILES:
        conversation = load_conversation(path)
        assert (Path(conversation["building"]) / "building.json").exists(), path
        assert conversation["turns"], path
        for turn in conversation["turns"]:
            assert turn["user"].strip(), path
            assert set(turn["expect"]) <= EXPECT_KEYS, (path, turn["expect"])
            assert set(turn["expect"].get("tools", [])) <= TOOL_NAMES, (path, turn["expect"])


def test_unknown_expect_key_is_rejected(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"building": str(CAMPUS), "turns": [{"user": "hi", "expect": {"nope": 1}}]}))
    try:
        load_conversation(bad)
    except ValueError as error:
        assert "nope" in str(error)
    else:
        raise AssertionError("unknown key accepted")


def route_turn(session: BuildingSession, route: dict, text: str = "ok") -> GuideTurn:
    return GuideTurn(text, tool_calls=[{"name": "find_route", "input": {}, "result": route}])


def test_check_turn_passes_for_matching_route_and_flags_wrong_length():
    session = BuildingSession.load(CAMPUS)
    route = session.call("find_route", {"start": LOBBY, "destination": LAB})
    expect = {"asked": False, "route_to": LAB, "grounded": True}
    assert check_turn(session, route_turn(session, route), expect) == []
    wrong = {**route, "length_m": route["length_m"] + 5}
    failures = check_turn(session, route_turn(session, wrong), expect)
    assert len(failures) == 1 and "length_m" in failures[0]


def test_check_turn_flags_a_route_computed_before_the_profile_changed():
    session = BuildingSession.load(CAMPUS)
    stairs = session.call("find_route", {"start": LOBBY, "destination": LAB})
    session.call("set_profile", {"preset": "wheelchair"})
    failures = check_turn(session, route_turn(session, stairs), {"route_to": LAB, "step_free": True})
    assert len(failures) == 1 and "!= core" in failures[0]


def test_check_turn_flags_other_expectations():
    session = BuildingSession.load(CAMPUS)
    turn = GuideTurn("Which one do you mean?", tool_calls=[{"name": "locate", "input": {}, "result": {"total": 0}}],
                     ungrounded=["42"])
    failures = check_turn(session, turn, {"asked": False, "tools": ["find_route"], "step_free": True,
                                          "grounded": True, "route_to": LAB, "space_ids_include": [LAB]})
    assert len(failures) == 6
    assert check_turn(session, turn, {"no_route": True, "asked": True}) == []
    assert check_turn(session, turn, {"tools": []}) != []


def test_check_turn_ignores_unreachable_routes():
    session = BuildingSession.load(CAMPUS)
    unreachable = {"reachable": False, "from_space_id": LOBBY, "to_space_id": LAB}
    turn = route_turn(session, unreachable)
    assert "no reachable route" in check_turn(session, turn, {"route_to": LAB})[0]
    assert check_turn(session, turn, {"no_route": True}) == []


def test_check_turn_space_ids_come_from_results_and_events():
    session = BuildingSession.load(CAMPUS)
    turn = GuideTurn("ok", events=[{"type": "highlight", "space_ids": [LAB]}])
    assert check_turn(session, turn, {"space_ids_include": [LAB]}) == []


def test_check_turn_asset_total_compares_tool_total_and_reply():
    session = BuildingSession.load(CAMPUS)
    total = sum(a["type"] == "3d_printer" for a in session.building.assets.values())
    located = [{"name": "locate", "input": {}, "result": {"total": total}}]
    assert check_turn(session, GuideTurn(f"There are {total} 3D printers.", tool_calls=located),
                      {"asset_total": "3d_printer"}) == []
    counted = [{"name": "count_assets", "input": {}, "result": {"count": total}}]
    assert check_turn(session, GuideTurn(f"{total} printers.", tool_calls=counted),
                      {"asset_total": "3d_printer"}) == []
    silent = check_turn(session, GuideTurn("Several.", tool_calls=located), {"asset_total": "3d_printer"})
    assert "does not state" in silent[0]
    off = [{"name": "locate", "input": {}, "result": {"total": total + 1}}]
    assert "core counts" in check_turn(session, GuideTurn(f"{total}", tool_calls=off),
                                       {"asset_total": "3d_printer"})[0]


def test_check_turn_route_to_falls_back_to_the_conversations_last_route():
    session = BuildingSession.load(CAMPUS)
    route = session.call("find_route", {"start": LOBBY, "destination": LAB})
    assert check_turn(session, GuideTurn("Same way as before."), {"route_to": LAB}, earlier=route) == []
    session.call("set_profile", {"preset": "wheelchair"})  # the earlier route is stale now
    stale = check_turn(session, GuideTurn("Same way as before."), {"route_to": LAB}, earlier=route)
    assert len(stale) == 1 and "!= core" in stale[0]


def test_asked_counts_a_question_anywhere_in_the_reply():
    session = BuildingSession.load(CAMPUS)
    mid = GuideTurn("They are in two rooms, so which one do you want? Makerspace 1.14 is about 94 m away.")
    assert check_turn(session, mid, {"asked": True}) == []
    assert check_turn(session, GuideTurn("Lab 2.20 is on Floor 2."), {"asked": False}) == []
