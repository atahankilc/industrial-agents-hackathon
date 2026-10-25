"""The import keeps each floor's straightened plan + its px → metres transform for Edit mode
(core/plan_import/reference.py, GET /drafts/{id}/references), never inside other payloads."""

import base64
import copy
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import backend.app as backend_app
from agent.creator import CreatorResult
from backend.drafts import DraftStore
from core.plan_import.assemble import assemble, autofix
from core.plan_import.reference import reference_for, strip_references
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan, labelled_floor, to_png

PLAN = to_png(draw_plan(*TWO_ROOMS_AND_CORRIDOR))


def decoded(data_url: str) -> np.ndarray:
    raw = base64.b64decode(data_url.split(",", 1)[1])
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def test_reference_is_a_capped_jpeg_with_a_scaled_transform() -> None:
    floor = labelled_floor()
    floor.image = np.zeros((1000, 3000, 3), np.uint8)
    floor.transform = np.array([[0.01, 0.0, 0.0], [0.0, -0.01, 10.0]])
    reference = reference_for(floor)
    assert reference["image"].startswith("data:image/jpeg;base64,")
    assert max(decoded(reference["image"]).shape[:2]) == 1600
    factor = 3000 / 1600
    assert reference["transform"][0][0] == pytest.approx(0.01 * factor)
    assert reference["transform"][1][1] == pytest.approx(-0.01 * factor)
    assert reference["transform"][1][2] == pytest.approx(10.0)


def test_small_images_are_kept_at_their_size() -> None:
    floor = labelled_floor()
    floor.image = np.full((300, 400, 3), 90, np.uint8)  # no white margin to crop
    floor.transform = np.array([[0.02, 0.0, 1.0], [0.0, -0.02, 8.0]])
    reference = reference_for(floor)
    assert decoded(reference["image"]).shape[:2] == floor.image.shape[:2]
    assert reference["transform"] == [[0.02, 0.0, 1.0], [0.0, -0.02, 8.0]]


def test_white_margins_are_cropped_and_the_transform_follows() -> None:
    floor = labelled_floor()
    floor.image = np.full((400, 600, 3), 255, np.uint8)
    floor.image[100:300, 200:500] = 40  # the drawing; the rest is empty paper
    floor.transform = np.array([[0.02, 0.0, 1.0], [0.0, -0.02, 8.0]])
    reference = reference_for(floor)
    height, width = decoded(reference["image"]).shape[:2]
    assert width < 340 and height < 240  # the drawing plus a thin edge, not the page
    t = np.array(reference["transform"])
    original = floor.transform @ np.array([200, 100, 1.0])  # the drawing's top-left corner, in metres
    corner = np.argwhere(decoded(reference["image"]).mean(axis=2) < 128).min(axis=0)  # (row, col) in the stored image
    assert t @ np.array([corner[1], corner[0], 1.0]) == pytest.approx(original, abs=0.05)


def with_references(levels: tuple[int, ...] = (0,)) -> dict:
    floors = [labelled_floor(level) for level in (0, 1)]
    building = autofix(assemble("import-ref", "Reference house", floors, ["plan.png"]))
    for floor in floors:
        if floor.level in levels:
            building["building"]["source_ref"]["import"]["floors"][str(floor.level)]["reference"] = reference_for(floor)
    return building


def has_reference(value: object) -> bool:
    return "reference" in json.dumps(value)


@pytest.fixture
def drafts(tmp_path) -> DraftStore:
    return DraftStore(tmp_path, dict(backend_app.store.catalogue))


def test_state_never_carries_reference_images(drafts: DraftStore) -> None:
    draft = drafts.create_import(with_references())
    assert not has_reference(drafts.state(draft)["building"])
    assert has_reference(drafts.building(draft))  # kept in the data, only left out of the payload


def test_strip_references_leaves_the_building_alone() -> None:
    building = with_references()
    before = copy.deepcopy(building)
    assert not has_reference(strip_references(building))
    assert building == before


def test_floor_without_reference_is_left_out(drafts: DraftStore) -> None:
    draft = drafts.create_import(with_references(levels=(1,)))
    references = drafts.references(draft)
    assert [item["level"] for item in references] == [1]
    assert references[0]["floor_id"].endswith("-F1") and references[0]["image"].startswith("data:image/jpeg")


def test_references_survive_save_and_reopen(drafts: DraftStore) -> None:
    draft = drafts.create_import(with_references(levels=(0, 1)))
    saved = drafts.save(draft, "Reference house")
    again = drafts.create(saved)
    assert [item["level"] for item in drafts.references(again)] == [0, 1]


class FloorsCreator:
    def __init__(self, session) -> None:
        self.session, self.on_step = session, None

    def run(self) -> CreatorResult:
        floor = labelled_floor()
        building = autofix(assemble("import-abc", "Fake house", [floor], ["plan.png"]))
        self.session.floors[floor.level] = floor
        return CreatorResult("done", building, [])


def test_import_stream_keeps_references_and_the_endpoint_serves_them(tmp_path, monkeypatch) -> None:
    catalogue = dict(backend_app.store.catalogue)
    monkeypatch.setattr(backend_app.store, "catalogue", catalogue)
    store = DraftStore(tmp_path, catalogue)
    monkeypatch.setattr(backend_app, "drafts", store)
    monkeypatch.setattr(backend_app.store, "user_buildings", store)
    monkeypatch.setattr(backend_app, "make_creator", FloorsCreator)
    api = TestClient(backend_app.app)
    lines = [json.loads(line) for line in
             api.post("/imports/stream", files=[("files", ("plan.png", PLAN))]).text.splitlines() if line.strip()]
    done = lines[-1]
    assert done["type"] == "done"
    floors = api.get(f"/drafts/{done['draft_id']}/references").json()["floors"]
    assert len(floors) == 1 and floors[0]["level"] == 0 and len(floors[0]["transform"]) == 2
    assert not has_reference(api.get(f"/drafts/{done['draft_id']}").json())
    assert api.get("/drafts/0123456789abcdef0123456789abcdef/references").status_code == 404


def test_scale_building_scales_the_reference_with_it() -> None:
    from core.edits import apply_op

    building = with_references()
    floors = building["building"]["source_ref"]["import"]["floors"]
    before = np.array(floors["0"]["reference"]["transform"])
    scaled = apply_op(building, {"op": "scale_building", "factor": 1.1})
    after = np.array(scaled["building"]["source_ref"]["import"]["floors"]["0"]["reference"]["transform"])
    assert after == pytest.approx(before * 1.1)


def test_set_reference_moves_a_floors_plan() -> None:
    from core.edits import EditError, apply_op

    building = with_references()
    floor_id = next(floor["id"] for floor in building["floors"] if floor["level"] == 0)
    moved = apply_op(building, {"op": "set_reference", "floor_id": floor_id, "transform": [[0.1, 0, 2], [0, -0.1, 30]]})
    assert moved["building"]["source_ref"]["import"]["floors"]["0"]["reference"]["transform"] == [[0.1, 0, 2], [0, -0.1, 30]]
    with pytest.raises(EditError):
        apply_op(building, {"op": "set_reference", "floor_id": floor_id, "transform": [[0.1, 0], [0, 1]]})
    other = next(floor["id"] for floor in building["floors"] if floor["level"] == 1)  # this floor has no plan kept
    with pytest.raises(EditError):
        apply_op(building, {"op": "set_reference", "floor_id": other, "transform": [[1, 0, 0], [0, 1, 0]]})


def test_reference_edits_and_added_floors_survive_save_and_a_second_save(drafts: DraftStore) -> None:
    from tests.test_add_floor import one_floor

    draft = drafts.create_import(with_references())
    floor_id = next(floor["id"] for floor in drafts.building(draft)["floors"] if floor["level"] == 0)
    moved = [[0.1, 0.0, 2.0], [0.0, -0.1, 30.0]]
    drafts.apply(draft, [{"op": "set_reference", "floor_id": floor_id, "transform": moved}])
    drafts.apply(draft, [{"op": "add_floors", "building_with_floors": one_floor("import-cccc", 5)}])
    first = drafts.save(draft, "Kept plans")
    again = drafts.create(first)
    by_level = {item["level"]: item for item in drafts.references(again)}
    assert by_level[0]["transform"] == moved  # the trace as adjusted (i)
    assert 5 in by_level  # the added floor's plan (iii)
    drafts.apply(again, [{"op": "scale_building", "factor": 1.1}])
    second = drafts.save(again, "Kept plans")
    reopened = {item["level"]: item for item in drafts.references(drafts.create(second))}
    assert set(reopened) == set(by_level)  # a second save keeps them (iv)
    assert reopened[0]["transform"][0][0] == pytest.approx(moved[0][0] * 1.1)  # scaled with the building (ii)
