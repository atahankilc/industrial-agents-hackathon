"""Adding floors to the building being edited from new plans (backend/core/plan_import/merge.py, edit op `add_floors`,
`draft` on POST /imports/stream) and deleting a saved building (DELETE /buildings/user/{slug})."""

import copy
import json

import pytest
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

import backend.api.app as backend_app
from backend.agents.creator import CreatorResult
from backend.core.plan_import.assemble import assemble, autofix
from backend.core.plan_import.merge import add_floors
from backend.core.plan_import.reference import reference_for
from tests.plan_fixtures import labelled_floor
from tests.test_placement import PLAN, SPOT, api, imported, rotated_ring  # noqa: F401 (api is a fixture)


def one_floor(prefix: str, level: int, stair: bool = True) -> dict:
    floor = labelled_floor(level, stair=stair)
    building = autofix(assemble(prefix, "House", [floor], ["plan.png"]))
    building["building"]["source_ref"]["import"]["floors"][str(level)]["reference"] = reference_for(floor)
    return building


def outline(building: dict, floor_id: str | None = None) -> Polygon:
    return unary_union([Polygon(space["polygon"]).buffer(0) for space in building["spaces"]
                        if floor_id is None or space["floor_id"] == floor_id])


def moved(building: dict, angle: float, dx: float, dy: float) -> dict:
    """The same building drawn turned and shifted, as a second photo of another floor would come out."""
    building = copy.deepcopy(building)
    for space in building["spaces"]:
        shape = affinity.translate(affinity.rotate(Polygon(space["polygon"]), angle, origin=(0, 0)), dx, dy)
        space["polygon"] = [list(point) for point in shape.exterior.coords[:-1]]
    return building


def test_new_floor_is_laid_onto_the_building() -> None:
    old = one_floor("import-aaaa", 0)
    new = moved(one_floor("import-bbbb", 1), 90.0, 40.0, -15.0)  # the floor above, drawn turned and shifted
    merged = add_floors(old, new)
    levels = sorted(floor["level"] for floor in merged["floors"])
    assert levels == [0, 1]
    upper = next(floor for floor in merged["floors"] if floor["level"] == 1)
    assert upper["elevation_m"] > next(f for f in merged["floors"] if f["level"] == 0)["elevation_m"]
    lower_shape, upper_shape = outline(merged, "import-aaaa-F0"), outline(merged, upper["id"])
    assert lower_shape.intersection(upper_shape).area / lower_shape.union(upper_shape).area > 0.9  # aligned


def test_new_floor_is_joined_by_its_stairs_and_keeps_its_plan() -> None:
    merged = add_floors(one_floor("import-aaaa", 0), one_floor("import-bbbb", 1))
    joined = [c for c in merged["vertical_connectors"] if len(set(c["floor_ids"])) == 2]
    assert joined and joined[0]["kind"] == "stairs"
    floors = merged["building"]["source_ref"]["import"]["floors"]
    assert set(floors) == {"0", "1"} and floors["1"]["reference"]["image"].startswith("data:image/jpeg")


def test_the_reference_follows_the_alignment() -> None:
    old, new = one_floor("import-aaaa", 0), one_floor("import-bbbb", 1)
    shifted = moved(new, 0.0, 12.0, 5.0)
    shifted["building"]["source_ref"]["import"]["floors"]["1"]["reference"]["transform"] = [
        [row[0], row[1], row[2] + (12.0 if index == 0 else 5.0)]
        for index, row in enumerate(new["building"]["source_ref"]["import"]["floors"]["1"]["reference"]["transform"])]
    merged = add_floors(old, shifted)
    got = merged["building"]["source_ref"]["import"]["floors"]["1"]["reference"]["transform"]
    want = new["building"]["source_ref"]["import"]["floors"]["1"]["reference"]["transform"]
    assert [value for row in got for value in row] == pytest.approx([value for row in want for value in row], abs=0.3)


class TwoCreators:
    """The first import makes the ground floor, the next one the floor above."""
    count = 0

    def __init__(self, session) -> None:
        self.session, self.on_step = session, None

    def run(self) -> CreatorResult:
        TwoCreators.count += 1
        first = TwoCreators.count == 1
        return CreatorResult("done", one_floor("import-aaaa" if first else "import-bbbb", 0 if first else 1), [])


def test_delete_a_saved_building(api) -> None:
    first = imported(api, {"ring": rotated_ring(0.0)})
    saved = api.post(f"/drafts/{first['draft_id']}/save", json={"name": "Shed"}).json()["building"]
    assert api.delete(f"/buildings/{saved}").status_code == 200
    assert saved not in {item["id"] for item in api.get("/buildings").json()}
    assert api.post("/drafts", json={"base": saved}).status_code == 422  # gone, not only hidden


def test_deleting_the_newest_version_brings_the_older_back_to_the_map(api) -> None:
    first = imported(api, {"ring": rotated_ring(0.0)})
    old = api.post(f"/drafts/{first['draft_id']}/save", json={"name": "Barn"}).json()["building"]
    again = api.post("/drafts", json={"base": old}).json()["draft"]["id"]
    api.put(f"/drafts/{again}/location", json={"origin": SPOT, "bearing_deg": 5.0, "scale": 1.0})
    new = api.post(f"/drafts/{again}/save", json={"name": "Barn"}).json()["building"]
    assert api.delete(f"/buildings/{new}").status_code == 200
    shown = {item["id"]: item for item in api.get("/buildings").json()}
    assert shown[old]["location"] is not None


def test_only_saved_buildings_can_be_deleted(api) -> None:
    assert api.delete("/buildings/train/osm-way10053349").status_code in (403, 404)
    assert api.delete("/buildings/user/nope").status_code == 404


def test_import_into_an_open_draft_adds_the_floor_as_one_undo_step(api, monkeypatch) -> None:
    TwoCreators.count = 0
    monkeypatch.setattr(backend_app, "make_creator", TwoCreators)
    first = imported(api, {"ring": rotated_ring(0.0)})
    draft = first["draft_id"]
    space = api.get(f"/drafts/{draft}").json()["building"]["spaces"][0]["id"]
    assert api.post(f"/drafts/{draft}/ops", json={"ops": [{"op": "set_space", "space_id": space, "name": "Kept"}]}).status_code == 200
    before = api.get(f"/drafts/{draft}").json()["draft"]["steps"]
    response = api.post("/imports/stream", files=[("files", ("plan.png", PLAN))], data={"draft": draft})
    done = [json.loads(line) for line in response.text.splitlines() if line.strip()][-1]
    assert done["type"] == "done" and done["draft_id"] == draft
    state = api.get(f"/drafts/{draft}").json()
    assert state["draft"]["steps"] == before + 1
    assert sorted(floor["level"] for floor in state["building"]["floors"]) == [0, 1]
    assert next(item for item in state["building"]["spaces"] if item["id"] == space)["name"] == "Kept"  # edits stay
    assert len(api.get(f"/drafts/{draft}/references").json()["floors"]) == 2
    api.post(f"/drafts/{draft}/undo")
    assert len(api.get(f"/drafts/{draft}").json()["building"]["floors"]) == 1


def test_import_into_an_unknown_draft_is_refused(api) -> None:
    response = api.post("/imports/stream", files=[("files", ("plan.png", PLAN))], data={"draft": "0" * 32})
    assert response.status_code == 404


def wall_angle_of(building: dict, floor_id: str) -> float:
    from backend.core.plan_import.merge import wall_angle

    return wall_angle([space for space in building["spaces"] if space["floor_id"] == floor_id])


def test_an_added_floor_keeps_its_walls_parallel_to_the_building() -> None:
    old = one_floor("import-aaaa", 0)
    new = moved(one_floor("import-bbbb", 1), 97.0, 30.0, -10.0)  # drawn 7° off a quarter turn
    merged = add_floors(old, new)
    upper = next(floor["id"] for floor in merged["floors"] if floor["level"] == 1)
    off = (wall_angle_of(merged, upper) - wall_angle_of(merged, "import-aaaa-F0")) % 90
    assert min(off, 90 - off) < 0.5


def test_straighten_floor_turns_it_parallel_to_the_lowest_floor() -> None:
    from backend.core.edits import apply_op

    building = add_floors(one_floor("import-aaaa", 0), one_floor("import-bbbb", 1))
    upper = next(floor["id"] for floor in building["floors"] if floor["level"] == 1)
    crooked = copy.deepcopy(building)
    for space in crooked["spaces"]:
        if space["floor_id"] == upper:
            space["polygon"] = [list(p) for p in affinity.rotate(Polygon(space["polygon"]), 8.0, origin=(10, 10)).exterior.coords[:-1]]
    before = outline(crooked, upper).centroid
    straight = apply_op(crooked, {"op": "straighten_floor", "floor_id": upper})
    off = (wall_angle_of(straight, upper) - wall_angle_of(straight, "import-aaaa-F0")) % 90
    assert min(off, 90 - off) < 0.5
    assert outline(straight, upper).centroid.distance(before) < 0.5  # turned in place
    reference = straight["building"]["source_ref"]["import"]["floors"]["1"]["reference"]["transform"]
    assert reference != crooked["building"]["source_ref"]["import"]["floors"]["1"]["reference"]["transform"]
