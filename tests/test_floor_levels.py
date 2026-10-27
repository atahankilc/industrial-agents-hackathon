"""The user says which floor each uploaded plan is (`levels` on POST /imports/stream): every source carries its level,
the Creator is told, and register_plan keeps the user's level whatever it was called with."""

import json

import pytest

from backend.api.routes import imports as import_routes
from backend.agents.creator import Creator
from backend.agents.creator_tools import CreatorTools, ImportSession
from backend.core.plan_import.ingest import load_sources
from backend.core.plan_import.merge import add_floors
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan, to_png
from tests.test_add_floor import TwoCreators, one_floor
from tests.test_placement import PLAN, api, imported, rotated_ring  # noqa: F401 (api is a fixture)

WHOLE = {"bbox": [0, 0, 1, 1], "photo": False}


def test_sources_carry_the_level_the_user_gave() -> None:
    sources, _ = load_sources([("a.png", PLAN), ("b.png", PLAN)], levels=[2, 0])
    assert [source.level for source in sources] == [2, 0]
    unset, _ = load_sources([("a.png", PLAN)])
    assert unset[0].level is None


def test_the_creator_is_told_the_levels() -> None:
    sources, warnings = load_sources([("a.png", PLAN), ("b.png", PLAN)], levels=[1, -1])
    opening = Creator(ImportSession(sources, warnings), client=None).opening()
    assert "s1: a.png — floor 1" in opening and "s2: b.png — floor -1" in opening


def test_register_plan_keeps_the_users_level() -> None:
    sources, warnings = load_sources([("a.png", to_png(draw_plan(*TWO_ROOMS_AND_CORRIDOR)))], levels=[3])
    tools = CreatorTools(ImportSession(sources, warnings))
    tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "Erdgeschoss", **WHOLE})
    assert list(tools.session.floors) == [3]


def post(api, data: dict):
    return api.post("/imports/stream", files=[("files", ("a.png", PLAN)), ("files", ("b.png", PLAN))], data=data)


def test_levels_must_match_the_files_and_differ(api) -> None:
    assert post(api, {"levels": json.dumps([0])}).status_code == 422
    assert post(api, {"levels": json.dumps([1, 1])}).status_code == 422
    assert post(api, {"levels": json.dumps([0, "x"])}).status_code == 422


def test_a_floor_the_draft_has_is_refused_before_the_creator_runs(api, monkeypatch) -> None:
    TwoCreators.count = 0
    monkeypatch.setattr(import_routes, "make_creator", TwoCreators)
    draft = imported(api, {"ring": rotated_ring(0.0)})["draft_id"]  # has floor 0
    response = api.post("/imports/stream", files=[("files", ("a.png", PLAN))],
                        data={"draft": draft, "levels": json.dumps([0])})
    assert response.status_code == 422 and "0" in response.json()["detail"]
    assert TwoCreators.count == 1  # the second Creator never ran


def test_merging_a_level_the_building_has_is_an_error() -> None:
    with pytest.raises(ValueError, match="floor 0"):
        add_floors(one_floor("import-aaaa", 0), one_floor("import-bbbb", 0))
