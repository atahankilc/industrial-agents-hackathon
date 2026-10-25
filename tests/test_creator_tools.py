"""The Creator's tools (agent/creator_tools.py): each stage behind a tool, checked by code."""

import json

from agent.creator_tools import CREATOR_TOOLS, CreatorTools, ImportSession
from core.plan_import.ingest import load_sources
from tests.plan_fixtures import FIXTURE_LABELS, STAIR_LABEL, TWO_ROOMS_AND_CORRIDOR, WITH_STAIR, draw_plan, to_png

WHOLE = {"bbox": [0, 0, 1, 1], "photo": False}


def session_from(files) -> ImportSession:
    sources, warnings = load_sources(files)
    return ImportSession(sources, warnings)


def data(blocks) -> dict:
    return json.loads(next(block["text"] for block in blocks if block["type"] == "text"))


def has_image(blocks) -> bool:
    return any(block["type"] == "image" and block["source"]["media_type"] == "image/png" for block in blocks)


def tools_for(*plans) -> CreatorTools:
    return CreatorTools(session_from([(f"plan{i}.png", to_png(draw_plan(*plan))) for i, plan in enumerate(plans)]))


def test_tool_schemas_match_the_dispatch():
    names = {tool["name"] for tool in CREATOR_TOOLS}
    assert names == {"list_sources", "view_source", "register_plan", "segment", "coarse_rooms", "add_rooms",
                     "label_cells", "set_scale", "stack_floors", "finish", "no_plan"}
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    assert all("error" in data(tools.call(name, {})) or name in {"list_sources", "stack_floors", "no_plan"}
               for name in names if name not in {"list_sources"})


def test_list_and_view_sources():
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    listing = tools.call("list_sources", {})
    assert has_image(listing) and data(listing)["sources"][0]["id"] == "s1"
    assert has_image(tools.call("view_source", {"source_id": "s1"}))
    assert "error" in data(tools.call("view_source", {"source_id": "s9"}))


def test_register_label_finish_happy_path():
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    out = tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "Erdgeschoss", **WHOLE})
    assert has_image(out) and data(out)["cells"] == 3
    labelled = tools.call("label_cells", {"level": 0, "cells": FIXTURE_LABELS, "entrances": [3]})
    assert has_image(labelled) and data(labelled)["problems"] == []
    result = data(tools.call("finish", {"name": "Test"}))
    assert result["errors"] == [] and tools.session.finished is not None
    building = tools.session.finished["building"]
    assert len(building["spaces"]) == 3 and building["building"]["name"] == "Test"


def test_second_plan_for_same_level_is_refused():  # Review Focus 3
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    assert "error" in data(tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE}))
    assert "error" not in data(tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG",
                                                            "replace": True, **WHOLE}))


def test_finish_refuses_unlabelled_floor():
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    assert "error" in data(tools.call("finish", {"name": "T"})) and tools.session.finished is None


def test_no_plan_refused_after_a_floor_is_registered():
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    assert "error" in data(tools.call("no_plan", {"reason": "nothing"}))
    fresh = tools_for(TWO_ROOMS_AND_CORRIDOR)
    assert "error" not in data(fresh.call("no_plan", {"reason": "only text"}))
    assert fresh.session.no_plan == "only text"


def test_finish_gives_one_repair_chance_then_accepts():  # two floors, no stairs → unreachable
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR, TWO_ROOMS_AND_CORRIDOR)
    for level, source in ((0, "s1"), (1, "s2")):
        tools.call("register_plan", {"source_id": source, "level": level, "floor_name": f"L{level}", **WHOLE})
        tools.call("label_cells", {"level": level, "cells": FIXTURE_LABELS, "entrances": [3] if level == 0 else []})
    first = data(tools.call("finish", {"name": "T"}))
    assert any(issue["code"] == "unreachable" for issue in first["errors"]) and tools.session.finished is None
    data(tools.call("finish", {"name": "T"}))
    assert tools.session.finished is not None and tools.session.finished["issues"]


def test_stairs_on_both_floors_connect():
    tools = tools_for(WITH_STAIR, WITH_STAIR)
    for level, source in ((0, "s1"), (1, "s2")):
        tools.call("register_plan", {"source_id": source, "level": level, "floor_name": f"L{level}", **WHOLE})
        tools.call("label_cells", {"level": level, "cells": FIXTURE_LABELS + [STAIR_LABEL],
                                   "entrances": [3] if level == 0 else []})
    stacked = tools.call("stack_floors", {})
    assert has_image(stacked) and data(stacked)["connectors"] == 1
    result = data(tools.call("finish", {"name": "T"}))
    assert result["errors"] == []


def test_segment_coarse_and_add_rooms():
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    assert data(tools.call("segment", {"level": 0, "method": "colours"}))["cells"] >= 1
    coarse = data(tools.call("coarse_rooms", {"level": 0, "boxes": [[0.1, 0.1, 0.5, 0.5], [0.5, 0.1, 0.9, 0.5]]}))
    assert coarse["cells"] == 2 and tools.session.floors[0].low_confidence
    tools.call("segment", {"level": 0, "method": "walls"})
    corridor = 3
    carved = data(tools.call("add_rooms", {"level": 0, "cell": corridor, "boxes": [[0.1, 0.55, 0.3, 0.85]]}))
    assert carved["new_cells"] == [4] and 4 in tools.session.floors[0].carved
    assert (3, 4) in tools.session.floors[0].seg.adjacency


def test_set_scale_from_a_bar():
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    width = tools.session.floors[0].image.shape[1]
    out = data(tools.call("set_scale", {"level": 0, "method": "bar", "p0": [0, 0.5], "p1": [100 / width, 0.5],
                                        "length_m": 5}))
    assert abs(out["m_per_px"] - 0.05) < 1e-4 and tools.session.floors[0].scale_method == "bar"


def test_add_rooms_from_outside_adds_an_open_room():  # a foyer the walls did not close
    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    out = data(tools.call("add_rooms", {"level": 0, "cell": 0, "boxes": [[0.0, 0.2, 0.15, 0.6]]}))
    new = out["new_cells"][0]
    assert new == 4 and (1, new) in tools.session.floors[0].seg.adjacency
    assert tools.session.floors[0].seg.cells[0].outside


def test_an_unexpected_failure_is_an_error_not_a_crash(monkeypatch):
    import agent.creator_tools as module

    tools = tools_for(TWO_ROOMS_AND_CORRIDOR)
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "EG", **WHOLE})
    tools.call("label_cells", {"level": 0, "cells": FIXTURE_LABELS, "entrances": [3]})

    def broken(*args, **kwargs):
        raise RuntimeError("geometry exploded")

    monkeypatch.setattr(module, "autofix", broken)
    assert "geometry exploded" in data(tools.call("finish", {"name": "T"}))["error"]
