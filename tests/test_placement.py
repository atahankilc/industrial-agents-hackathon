"""A building at a place on the map: edit ops `scale_building` / `set_location`, `place` on POST /imports/stream,
PUT /drafts/{id}/location, positions in /buildings and supersede on re-save
(archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md)."""

import json

import pytest
from fastapi.testclient import TestClient
from shapely import affinity

import backend.api.app as backend_app
from backend.agents.creator import CreatorResult
from backend.api.drafts import DraftStore
from backend.core.edits import apply_op
from backend.core.geoplace import footprint, to_lnglat, to_metres
from backend.core.plan_import.assemble import assemble, autofix
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan, labelled_floor, to_png

PLAN = to_png(draw_plan(*TWO_ROOMS_AND_CORRIDOR))
SPOT = {"lat": 48.1497, "lon": 11.5679}


def fake_building() -> dict:
    return autofix(assemble("import-abc", "Fake house", [labelled_floor()], ["plan.png"]))


class FakeCreator:
    def __init__(self, session) -> None:
        self.session, self.on_step = session, None

    def run(self) -> CreatorResult:
        return CreatorResult("done", fake_building(), [])


@pytest.fixture
def api(monkeypatch, tmp_path) -> TestClient:
    catalogue = dict(backend_app.store.catalogue)
    monkeypatch.setattr(backend_app.store, "catalogue", catalogue)
    store = DraftStore(tmp_path, catalogue)
    monkeypatch.setattr(backend_app, "drafts", store)
    monkeypatch.setattr(backend_app.store, "user_buildings", store)
    monkeypatch.setattr(backend_app, "make_creator", FakeCreator)
    return TestClient(backend_app.app)


def rotated_ring(bearing: float) -> list[list[float]]:
    shape = affinity.rotate(footprint(fake_building()), bearing, origin=(0, 0))
    return [list(to_lnglat(SPOT, 0.0, x, y)) for x, y in shape.exterior.coords]


def imported(api: TestClient, place: dict | None) -> dict:
    data = {"place": json.dumps(place)} if place is not None else {}
    response = api.post("/imports/stream", files=[("files", ("plan.png", PLAN))], data=data)
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()][-1]


def test_scale_building_scales_polygons_and_positions() -> None:
    building = fake_building()
    scaled = apply_op(building, {"op": "scale_building", "factor": 1.1})
    assert scaled["spaces"][0]["polygon"][1] == pytest.approx([value * 1.1 for value in building["spaces"][0]["polygon"][1]])
    assert scaled["openings"][0]["position"] == pytest.approx([value * 1.1 for value in building["openings"][0]["position"]])
    assert scaled["openings"][0]["width_m"] == building["openings"][0]["width_m"]


def test_scale_building_refuses_silly_factors() -> None:
    from backend.core.edits import EditError

    with pytest.raises(EditError):
        apply_op(fake_building(), {"op": "scale_building", "factor": 0})


def test_import_with_a_place_is_fitted_and_located(api: TestClient) -> None:
    done = imported(api, {"ring": rotated_ring(20.0)})
    assert done["type"] == "done"
    assert done["location"]["bearing"] == pytest.approx(20.0, abs=2.0)
    building = api.get(f"/drafts/{done['draft_id']}").json()["building"]
    assert building["building"]["location"]["bearing"] == pytest.approx(done["location"]["bearing"])


def test_point_place_centres_without_fit(api: TestClient) -> None:
    done = imported(api, {"point": [SPOT["lon"], SPOT["lat"]]})
    location = done["location"]
    assert location["bearing"] == 0 and location["fit"] is None
    assert to_metres(SPOT, 0.0, location["lon"], location["lat"]) == pytest.approx((0, 0), abs=0.5)


def test_bad_place_is_422(api: TestClient) -> None:
    response = api.post("/imports/stream", files=[("files", ("plan.png", PLAN))],
                        data={"place": json.dumps({"ring": [[11.5, 48.1], [11.6, 48.1]]})})
    assert response.status_code == 422


def test_put_location_is_one_undo_step(api: TestClient) -> None:
    done = imported(api, {"point": [SPOT["lon"], SPOT["lat"]]})
    before = api.get(f"/drafts/{done['draft_id']}").json()
    response = api.put(f"/drafts/{done['draft_id']}/location",
                       json={"origin": SPOT, "bearing_deg": 45.0, "scale": 1.1})
    assert response.status_code == 200
    after = response.json()
    assert after["draft"]["steps"] == before["draft"]["steps"] + 1
    assert after["building"]["building"]["location"]["bearing"] == pytest.approx(45.0)
    assert after["building"]["spaces"][0]["polygon"][1][0] == pytest.approx(before["building"]["spaces"][0]["polygon"][1][0] * 1.1)
    undone = api.post(f"/drafts/{done['draft_id']}/undo").json()
    assert undone["building"]["building"]["location"]["bearing"] == 0
    assert api.put(f"/drafts/{done['draft_id']}/location",
                   json={"origin": SPOT, "bearing_deg": 0.0, "scale": 1.6}).status_code == 422


def located_ids(api: TestClient) -> dict[str, dict | None]:
    return {item["id"]: item["location"] for item in api.get("/buildings").json()}


def test_saved_positioned_building_is_on_the_map_and_resave_supersedes(api: TestClient) -> None:
    done = imported(api, {"ring": rotated_ring(0.0)})
    first = api.post(f"/drafts/{done['draft_id']}/save", json={"name": "Placed house"}).json()["building"]
    shown = located_ids(api)[first]
    assert shown["origin"] and "bearing" in shown and shown["outline"]
    again = api.post("/drafts", json={"base": first}).json()["draft"]["id"]
    api.put(f"/drafts/{again}/location", json={"origin": SPOT, "bearing_deg": 10.0, "scale": 1.0})
    second = api.post(f"/drafts/{again}/save", json={"name": "Placed house"}).json()["building"]
    shown = located_ids(api)
    assert shown[first] is None and shown[second]["bearing"] == pytest.approx(10.0)


def test_kit_building_second_version_keeps_both(api: TestClient) -> None:
    kit_id, kit = next((key, entry) for key, entry in backend_app.store.catalogue.items()
                       if (entry.get("location") or {}).get("outline"))
    done = imported(api, {"ring": kit["location"]["outline"][0]})
    saved = api.post(f"/drafts/{done['draft_id']}/save", json={"name": "Second version"}).json()["building"]
    shown = located_ids(api)
    assert shown[kit_id] == json.loads(json.dumps(kit["location"])) and shown[saved] is not None
