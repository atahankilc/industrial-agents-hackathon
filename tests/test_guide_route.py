"""Route and session tools: session state feeds routes, closures never leak into the shared map."""

import functools
from pathlib import Path

from agent.guide.tools import TOOLS, Session, run_tool
from core.building_map import BuildingMap
from core.solvers import route as core_solver_route

CAMPUS = Path("data/dev/proc-campus-dev-001")
FACTORY = Path("data/dev/proc-factory-dev-004")
LOBBY = "proc-campus-dev-001-F0-S014"


@functools.cache
def bmap(path: Path) -> BuildingMap:
    return BuildingMap.load(path)


def core_route(b, start, dest, step_free=False, closed=None):
    return core_solver_route(b, start, dest, step_free=step_free, closed=closed)


def lobby_of(path: Path) -> str:
    entrance = next(e for e in bmap(path).overview()["entrances"] if e["step_free"])
    return entrance["into"].split("[")[1].split("]")[0]


def args(**kw):
    return {"from": None, "via": None, "step_free": None, **kw}


def test_route_equals_core_route():
    b = bmap(CAMPUS)
    out = run_tool(b, Session(), "route", args(**{"from": "Main lobby", "to": "Makerspace 1.14"}))
    assert out["status"] == "ok"
    assert out["result"] == core_route(b, LOBBY, "proc-campus-dev-001-F1-S014")
    assert out["summary"].endswith(" m.") and "→" in out["summary"]


def test_route_to_two_printer_rooms_is_ambiguous_but_one_room_is_not():
    s = Session(position=LOBBY)
    out = run_tool(bmap(CAMPUS), s, "route", args(to="3D printer"))
    assert out["status"] == "ambiguous"
    assert all("choices" in o and "summary" in o for o in out["options"])
    s2 = Session(position=lobby_of(FACTORY))
    assert run_tool(bmap(FACTORY), s2, "route", args(to="3D printer"))["status"] == "ok"


def test_no_start_asks_for_it():
    out = run_tool(bmap(CAMPUS), Session(), "route", args(to="1.14"))
    assert out["status"] == "need_start"


def test_unknown_destination_is_not_found():
    out = run_tool(bmap(CAMPUS), Session(position=LOBBY), "route", args(to="zzzz nowhere"))
    assert out["status"] == "not_found"


def test_session_step_free_and_closures_apply_to_later_routes():
    b, s = bmap(CAMPUS), Session()
    run_tool(b, s, "update_session", {"position": "Main lobby", "step_free": True, "close": ["Lift 1"], "reopen": None})
    out = run_tool(b, s, "route", args(to="Lab 2.20"))
    assert out["result"] == core_route(b, LOBBY, "proc-campus-dev-001-F2-S020",
                                       step_free=True, closed="proc-campus-dev-001-V02")
    assert b.closed == set()


def test_reopen_removes_closure():
    b, s = bmap(CAMPUS), Session(position=LOBBY)
    run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": ["Lift 1"], "reopen": None})
    assert s.closures == [["proc-campus-dev-001-V02"]]
    out = run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": None, "reopen": ["Lift 1"]})
    assert out["status"] == "ok" and s.closures == []


def test_ambiguous_closure_only_asks_when_routes_differ():
    b, s = bmap(CAMPUS), Session(position=LOBBY, step_free=True)
    run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": ["the lift"], "reopen": None})
    out = run_tool(b, s, "route", args(to="Lab 2.20"))
    assert out["status"] == "ambiguous"
    assert all(set(o) == {"choices", "summary", "result"} for o in out["options"])
    assert {o["result"]["optimal_length_m"] for o in out["options"]} != {out["options"][0]["result"]["optimal_length_m"]}
    assert "closed" in out["summary"] and "Lift 1" in out["options"][0]["summary"]
    assert b.closed == set()


def test_unreachable_is_ok_with_reachable_false():
    b, s = bmap(CAMPUS), Session(position=LOBBY, step_free=True)
    run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": ["Lift 1", "Lift 2"], "reopen": None})
    out = run_tool(b, s, "route", args(to="Lab 2.20"))
    assert out["status"] == "ok" and out["result"]["reachable"] is False
    assert "no" in out["summary"].lower() and b.closed == set()


def test_ambiguous_position_leaves_session_untouched():
    s = Session()
    out = run_tool(bmap(CAMPUS), s, "update_session", {"position": "3D printer", "step_free": True, "close": None, "reopen": None})
    assert out["status"] == "ambiguous" and s.position is None and s.step_free is False


def test_close_in_building_without_lifts_is_not_found():
    out = run_tool(bmap(Path("data/dev/resplan-1465")), Session(), "update_session",
                   {"position": None, "step_free": None, "close": ["the lift"], "reopen": None})
    assert out["status"] == "not_found"


def test_tools_registered():
    assert {"route", "update_session"} <= {t["name"] for t in TOOLS}


def test_reopen_unknown_or_not_closed_leaves_session_unchanged():
    b, s = bmap(CAMPUS), Session(position=LOBBY)
    run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": ["Lift 1"], "reopen": None})
    before = [list(c) for c in s.closures]
    nf = run_tool(b, s, "update_session", {"position": None, "step_free": True, "close": None, "reopen": ["zzz"]})
    nc = run_tool(b, s, "update_session", {"position": None, "step_free": True, "close": None, "reopen": ["Lift 2"]})
    assert nf["status"] == "not_found" and nc["status"] == "not_closed"
    assert s.closures == before and s.step_free is False


def test_collapsed_closure_names_every_candidate():
    b = bmap(CAMPUS)
    s = Session(position=LOBBY)
    s.closures = [["proc-campus-dev-001-V02", "proc-campus-dev-001-V04"]]
    out = run_tool(b, s, "route", args(to="Main lobby"))
    assert out["status"] == "ok" and out["closed"] == ["Lift 1 / Lift 2"]
    assert "Lift 1 / Lift 2" in out["summary"]


def test_empty_lists_mean_none():
    """The strict schema makes the model send [] for via / close / reopen; that must behave like null."""
    b, s = bmap(CAMPUS), Session()
    run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": ["Lift 1"], "reopen": None})
    before = list(s.closures)
    out = run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": [], "reopen": []})
    assert out["status"] == "ok" and s.closures == before
    trip = {"to": "1.14", "from": "Main lobby", "step_free": None}
    assert run_tool(b, s, "route", {**trip, "via": []}) == run_tool(b, s, "route", {**trip, "via": None})


def test_ambiguous_route_summary_names_the_varying_slot():
    out = run_tool(bmap(CAMPUS), Session(), "route", args(**{"from": "3D printer", "to": "Main lobby"}))
    assert out["status"] == "ambiguous" and "'3D printer'" in out["summary"] and "'Main lobby'" not in out["summary"]


NOTHING_SAVED = "Nothing was saved; call update_session again with all fields once this is resolved."


def test_failed_session_update_says_nothing_was_saved():
    b = bmap(CAMPUS)
    s = Session(position=LOBBY)
    s.closures = [["proc-campus-dev-001-V02"]]
    calls = [{"position": "3D printer", "step_free": True, "close": None, "reopen": None},
             {"position": None, "step_free": True, "close": ["Lift 2", "zzz"], "reopen": None},
             {"position": None, "step_free": True, "close": None, "reopen": ["Lift 2"]}]
    for call in calls:
        out = run_tool(b, s, "update_session", call)
        assert out["status"] != "ok" and out["summary"].endswith(NOTHING_SAVED)
    assert s.step_free is False and s.closures == [["proc-campus-dev-001-V02"]] and s.position == LOBBY
    assert NOTHING_SAVED not in run_tool(b, s, "update_session", {"position": None, "step_free": True,
                                                                  "close": None, "reopen": None})["summary"]
