"""backend/agents/builder_tools.py: what the Builder agent can look at, and propose_edit (dry run, never applies)."""

import pytest

import backend.api.app as backend_app
from backend.agents.builder_tools import BUILDER_TOOLS, BuilderTools
from backend.api.drafts import DraftStore

BASE = "train/proc-campus-train-000"


@pytest.fixture
def store(tmp_path) -> DraftStore:
    return DraftStore(tmp_path, dict(backend_app.store.catalogue))


@pytest.fixture
def tools(store) -> BuilderTools:
    return BuilderTools(store, store.create(BASE))


def office_with_neighbour(tools: BuilderTools) -> tuple[dict, dict]:
    """A rectangular office and a neighbour on a side, from space_info."""
    building = tools.store.building(tools.draft)
    for space in building["spaces"]:
        if space["room_type"] != "office" or len(space["polygon"]) != 4:
            continue
        info = tools.call("space_info", {"space": space["id"]})
        rooms = [n for n in info["neighbours"] if n["side"] in ("east", "west") and n["shared_m"] >= 2]
        if rooms:
            return info, rooms[0]
    raise AssertionError("no office with a side neighbour")


def test_tool_definitions_cover_the_tools():
    assert {tool["name"] for tool in BUILDER_TOOLS} == {"overview", "find", "space_info", "floor_plan", "propose_edit"}


def test_overview_counts(tools):
    result = tools.call("overview", {})
    building = tools.store.building(tools.draft)
    assert result["spaces"] == len(building["spaces"])
    assert result["assets"] == len(building["assets"])
    assert len(result["floors"]) == len(building["floors"])
    assert result["problems"] == 0


def test_find_exact_ref_and_did_you_mean(tools):
    building = tools.store.building(tools.draft)
    room = next(space for space in building["spaces"] if space["type"] == "room" and space.get("ref"))
    found = tools.call("find", {"query": room["ref"]})
    assert len(found["matches"]) == 1 and found["matches"][0].startswith(room["id"])
    assert tools.call("find", {"query": "Ofice 0.02"})["did_you_mean"]


def test_find_ambiguous_lists_candidates(tools):
    assert len(tools.call("find", {"query": "office"})["matches"]) >= 2


def test_space_info_edges_and_neighbours(tools):
    info, neighbour = office_with_neighbour(tools)
    assert sorted(edge["side"] for edge in info["edges"]) == ["east", "north", "south", "west"]
    assert neighbour["side"] in ("north", "east", "south", "west")
    assert info["area_m2"] > 0 and len(info["bbox"]) == 4
    assert all({"id", "kind", "to", "position", "width_m"} <= set(opening) for opening in info["openings"])


def test_space_info_ambiguous_is_error(tools):
    assert "ambiguous" in tools.call("space_info", {"space": "office"})["error"]


def test_floor_plan_is_compact(tools):
    building = tools.store.building(tools.draft)
    floor = building["floors"][0]["id"]
    plan = tools.call("floor_plan", {"floor_id": floor})
    assert plan["floor_id"] == floor
    assert all(set(item) == {"id", "name", "type", "bbox"} for item in plan["spaces"])
    assert "error" in tools.call("floor_plan", {"floor_id": "nope"})


def test_propose_edit_parks_and_reports_effect(tools):
    info, neighbour = office_with_neighbour(tools)
    edge = next(edge for edge in info["edges"] if edge["side"] == neighbour["side"])
    result = tools.call("propose_edit", {"summary": "widen", "ops": [
        {"op": "move_edge", "space_id": info["id"], "edge": [edge["from"], edge["to"]], "offset_m": 1.0}]})
    assert result["needs_confirmation"] is True
    changed = {item["id"]: item for item in result["effect"]["changed_spaces"]}
    assert changed[info["id"]]["area_after"] > changed[info["id"]]["area_before"]
    assert changed[neighbour["id"]]["area_after"] < changed[neighbour["id"]]["area_before"]
    assert result["proposal_id"] in tools.pending
    assert tools.draft.steps == []
    assert tools.pending[result["proposal_id"]].draft_version == tools.draft.version


def test_propose_edit_bad_op_returns_error(tools):
    result = tools.call("propose_edit", {"summary": "x", "ops": [{"op": "set_space", "space_id": "nope", "name": "y"}]})
    assert "error" in result and "nope" in result["error"]
    assert tools.pending == {}


def test_propose_edit_reports_new_problems(tools):
    info, _ = office_with_neighbour(tools)
    ops = [{"op": "delete_opening", "opening_id": opening["id"]} for opening in info["openings"]]
    result = tools.call("propose_edit", {"summary": "close it off", "ops": ops})
    assert any("can't be reached" in problem for problem in result["new_problems"])


def test_new_proposal_replaces_old(tools):
    info, _ = office_with_neighbour(tools)
    first = tools.call("propose_edit", {"summary": "a", "ops": [{"op": "set_space", "space_id": info["id"], "name": "A"}]})
    second = tools.call("propose_edit", {"summary": "b", "ops": [{"op": "set_space", "space_id": info["id"], "name": "B"}]})
    assert list(tools.pending) == [second["proposal_id"]] and first["proposal_id"] != second["proposal_id"]


def test_unknown_tool_and_bad_arguments_are_errors(tools):
    assert "error" in tools.call("teleport", {})
    assert "error" in tools.call("space_info", {})


def test_wrong_argument_types_are_errors_not_crashes(tools):
    """Models send numbers for refs like 0.21: answer with a result or an error, never raise."""
    for name, arguments in (("find", {"query": 5}), ("find", {"query": None}), ("space_info", {"space": 5}),
                            ("propose_edit", {"summary": "x", "ops": "not a list"}),
                            ("propose_edit", {"summary": "x", "ops": [5]})):
        assert isinstance(tools.call(name, arguments), dict)
    assert "matches" in tools.call("find", {"query": 0.02}) or "error" in tools.call("find", {"query": 0.02})
