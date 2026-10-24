"""Edit-mode drafts over HTTP (backend/drafts.py + /drafts endpoints), local store in a temp directory."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

import backend.app as backend_app
from agent.tools import BuildingSession
from backend.drafts import DraftStore
from backend.sessions import DATA_DIR

BASE = "train/proc-campus-train-000"


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    catalogue = dict(backend_app.store.catalogue)
    monkeypatch.setattr(backend_app.store, "catalogue", catalogue)
    monkeypatch.setattr(backend_app, "drafts", DraftStore(tmp_path, catalogue))
    return TestClient(backend_app.app)


def new_draft(client: TestClient) -> dict:
    response = client.post("/drafts", json={"base": BASE})
    assert response.status_code == 200
    return response.json()


def a_room(building: dict) -> dict:
    return next(space for space in building["spaces"] if space["type"] == "room")


def rename(client: TestClient, draft_id: str, space_id: str, name: str):
    return client.post(f"/drafts/{draft_id}/ops", json={"ops": [{"op": "set_space", "space_id": space_id, "name": name}]})


def test_create_get_ops_undo_roundtrip(client):
    created = new_draft(client)
    draft_id = created["draft"]["id"]
    assert created["draft"] == {"id": draft_id, "base": BASE, "name": created["draft"]["name"], "steps": 0}
    assert created["issues"] == []
    room = a_room(created["building"])
    changed = rename(client, draft_id, room["id"], "Renamed room")
    assert changed.status_code == 200
    assert changed.json()["draft"]["steps"] == 1
    fetched = client.get(f"/drafts/{draft_id}").json()
    assert next(space for space in fetched["building"]["spaces"] if space["id"] == room["id"])["name"] == "Renamed room"
    undone = client.post(f"/drafts/{draft_id}/undo").json()
    assert undone["draft"]["steps"] == 0
    assert next(space for space in undone["building"]["spaces"] if space["id"] == room["id"])["name"] == room["name"]


def test_ops_error_is_422_and_draft_unchanged(client):
    draft_id = new_draft(client)["draft"]["id"]
    response = rename(client, draft_id, "no-such-space", "x")
    assert response.status_code == 422
    assert "no-such-space" in response.text
    assert client.get(f"/drafts/{draft_id}").json()["draft"]["steps"] == 0


def test_undo_empty_is_409(client):
    draft_id = new_draft(client)["draft"]["id"]
    assert client.post(f"/drafts/{draft_id}/undo").status_code == 409


def test_unknown_base_422_unknown_draft_404(client):
    assert client.post("/drafts", json={"base": "train/no-such-building"}).status_code == 422
    assert client.get("/drafts/0123456789abcdef0123456789abcdef").status_code == 404


def test_bad_draft_id_never_touches_fs(client, tmp_path):
    for bad in ("..%2F..%2Fetc", "x" * 5, "../secret"):
        assert client.get(f"/drafts/{bad}").status_code == 404
    assert not any(path.name == "secret" for path in tmp_path.parent.rglob("secret"))


def test_issues_reported_after_a_breaking_op(client):
    created = new_draft(client)
    draft_id = created["draft"]["id"]
    opening = next(item for item in created["building"]["openings"]
                   if "outside" not in item["space_ids"])
    response = client.post(f"/drafts/{draft_id}/ops", json={"ops": [{"op": "delete_opening",
                                                                      "opening_id": opening["id"]}]})
    # deleting one door may or may not cut a room off; the response always carries the validator's verdict
    assert isinstance(response.json()["issues"], list)


def test_save_lists_building_and_guide_routes(client):
    created = new_draft(client)
    draft_id = created["draft"]["id"]
    room = a_room(created["building"])
    rename(client, draft_id, room["id"], "Edited room")
    saved = client.post(f"/drafts/{draft_id}/save", json={"name": "Campus Edited"})
    assert saved.status_code == 200
    building_id = saved.json()["building"]
    assert building_id == "user/campus-edited"
    assert building_id in [item["id"] for item in client.get("/buildings").json()]
    session = client.post("/sessions", json={"building": building_id})
    assert session.status_code == 200
    loaded = BuildingSession.load(backend_app.store.catalogue[building_id]["path"])
    data = loaded.building.data
    assert data["building"]["source"] == "edited"
    assert data["building"]["source_ref"] == {"base": BASE}
    assert data["building"]["name"] == "Campus Edited"
    assert data["building"]["id"] == "campus-edited"
    rooms = [space["id"] for space in data["spaces"] if space["type"] == "room"]
    route = loaded.tool_find_route(rooms[0], rooms[-1])
    assert "error" not in route


def test_save_same_name_twice_suffixes(client):
    first = new_draft(client)["draft"]["id"]
    second = new_draft(client)["draft"]["id"]
    assert client.post(f"/drafts/{first}/save", json={"name": "Foo"}).json()["building"] == "user/foo"
    assert client.post(f"/drafts/{second}/save", json={"name": "Foo"}).json()["building"] == "user/foo-2"


def test_draft_of_saved_building(client):
    draft_id = new_draft(client)["draft"]["id"]
    saved = client.post(f"/drafts/{draft_id}/save", json={"name": "Layer one"}).json()["building"]
    again = client.post("/drafts", json={"base": saved})
    assert again.status_code == 200
    assert again.json()["draft"]["base"] == saved


def test_points_endpoint(client):
    draft_id = new_draft(client)["draft"]["id"]
    response = client.get(f"/drafts/{draft_id}/points")
    assert response.status_code == 200
    assert "points" in response.json()


def test_draft_survives_a_new_store(client, tmp_path):
    draft_id = new_draft(client)["draft"]["id"]
    fresh = DraftStore(tmp_path, dict(backend_app.store.catalogue))
    assert fresh.get(draft_id) is not None


def test_dataset_untouched(client):
    path = DATA_DIR / "train" / "proc-campus-train-000" / "building.json"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    created = new_draft(client)
    draft_id = created["draft"]["id"]
    room = a_room(created["building"])
    shape = Polygon(room["polygon"])
    client.post(f"/drafts/{draft_id}/ops", json={"ops": [{"op": "set_space", "space_id": room["id"], "name": "x"}]})
    client.post(f"/drafts/{draft_id}/save", json={"name": "Untouched check"})
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert json.loads(path.read_text())["spaces"][0]["polygon"]  # still readable
    assert shape.area > 0


def test_concurrent_ops_on_one_draft_lose_nothing(tmp_path):
    """Overlapping requests on one draft (fast drags, R pressed twice) must each land on the latest state."""
    import sys
    import threading

    from core.edits import apply_steps

    store = DraftStore(tmp_path, dict(backend_app.store.catalogue))
    draft = store.create(BASE)
    room = a_room(store.building(draft))["id"]
    centre = Polygon(next(space for space in store.building(draft)["spaces"] if space["id"] == room)["polygon"])
    spot = [centre.representative_point().x, centre.representative_point().y]
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        barrier.wait()
        for i in range(10):
            store.apply(draft, [{"op": "add_asset", "space_id": room, "name": f"w{n}-{i}", "category": "equipment",
                                 "type": "box", "position": spot}])

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # switch threads constantly so an unguarded read-modify-write interleaves
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(interval)
    assert len(draft.steps) == 80
    assert sum(asset["name"].startswith("w") and "-" in asset["name"] for asset in store.building(draft)["assets"]) == 80
    assert store.building(draft) == apply_steps(store.base_building(BASE), draft.steps)
    assert draft.version == 80


def test_plan_endpoint_follows_the_draft(client):
    """The Edit-mode 3D preview (PlanView) reads the draft as a vector plan, in the base building's frame."""
    created = new_draft(client)
    draft_id = created["draft"]["id"]
    before = client.get(f"/drafts/{draft_id}/plan")
    assert before.status_code == 200
    plan = before.json()
    assert {"floors", "spaces", "walls", "openings", "assets", "center"} <= set(plan)
    room = a_room(created["building"])
    rename(client, draft_id, room["id"], "Renamed for the plan")
    after = client.get(f"/drafts/{draft_id}/plan").json()
    assert next(space for space in after["spaces"] if space["id"] == room["id"])["name"] == "Renamed for the plan"
    assert after["center"] == plan["center"]  # stable frame: the preview doesn't jump when the outline changes
    assert client.get("/drafts/0123456789abcdef0123456789abcdef/plan").status_code == 404


# ---------- M2: Builder stream + proposal apply ----------


def builder_lines(client: TestClient, draft_id: str, text: str) -> list[dict]:
    response = client.post(f"/drafts/{draft_id}/chat/stream", json={"message": text})
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def side_prompt(client: TestClient, draft_id: str) -> str:
    """'make <ref> 1 m wider to the <side>' for an office with a room on that side."""
    from agent.builder_tools import BuilderTools

    tools = BuilderTools(backend_app.drafts, backend_app.drafts.get(draft_id))
    for space in backend_app.drafts.building(tools.draft)["spaces"]:
        if space["room_type"] == "office" and len(space["polygon"]) == 4:
            info = tools.call("space_info", {"space": space["id"]})
            sides = [n["side"] for n in info["neighbours"] if n["side"] in ("east", "west") and n["shared_m"] >= 2]
            if sides:
                return f"make {space['ref']} 1 m wider to the {sides[0]}"
    raise AssertionError("no office with a side neighbour")


def test_builder_stream_offline_proposal(client):
    draft_id = new_draft(client)["draft"]["id"]
    lines = builder_lines(client, draft_id, side_prompt(client, draft_id))
    assert any(line["type"] == "step" for line in lines)
    reply = lines[-1]
    assert reply["type"] == "reply"
    assert reply["proposal"]["ops"][0]["op"] == "move_edge"
    assert reply["state"]["draft"]["steps"] == 0
    assert {"spaces", "openings", "assets"} <= set(reply["proposal"]["building"])
    assert reply["applied"] is None


def test_apply_proposal_endpoint(client):
    draft_id = new_draft(client)["draft"]["id"]
    proposal = builder_lines(client, draft_id, side_prompt(client, draft_id))[-1]["proposal"]
    response = client.post(f"/drafts/{draft_id}/proposals/{proposal['id']}/apply")
    assert response.status_code == 200
    assert response.json()["draft"]["steps"] == 1


def test_apply_stale_proposal_409(client):
    created = new_draft(client)
    draft_id = created["draft"]["id"]
    proposal = builder_lines(client, draft_id, side_prompt(client, draft_id))[-1]["proposal"]
    rename(client, draft_id, a_room(created["building"])["id"], "by hand")
    response = client.post(f"/drafts/{draft_id}/proposals/{proposal['id']}/apply")
    assert response.status_code == 409 and "changed since" in response.text


def test_yes_in_stream_applies(client):
    draft_id = new_draft(client)["draft"]["id"]
    builder_lines(client, draft_id, side_prompt(client, draft_id))
    reply = builder_lines(client, draft_id, "yes")[-1]
    assert reply["applied"] and reply["state"]["draft"]["steps"] == 1 and reply["proposal"] is None


def test_builder_stream_unknown_draft_404(client):
    assert client.post("/drafts/0123456789abcdef0123456789abcdef/chat/stream", json={"message": "hi"}).status_code == 404
    draft_id = new_draft(client)["draft"]["id"]
    assert client.post(f"/drafts/{draft_id}/proposals/P9/apply").status_code == 409


def test_proposal_payload_skips_a_stale_proposal(client):
    """A hand edit while the Builder was thinking: the reply still goes out, the outdated proposal does not."""
    from agent.builder_tools import Proposal

    created = new_draft(client)
    draft = backend_app.drafts.get(created["draft"]["id"])
    room = a_room(created["building"])
    proposal = Proposal("P1", "rename", [{"op": "delete_space", "space_id": room["id"]}], draft.version,
                        preview=backend_app.drafts.building(draft))
    assert backend_app.proposal_payload(draft, proposal)["building"] is proposal.preview
    backend_app.drafts.apply(draft, [{"op": "delete_space", "space_id": room["id"]}])
    assert backend_app.proposal_payload(draft, proposal) is None


def test_hand_edit_drops_the_builders_open_proposal(client):
    draft_id = new_draft(client)["draft"]["id"]
    builder_lines(client, draft_id, side_prompt(client, draft_id))
    building = client.get(f"/drafts/{draft_id}").json()["building"]
    rename(client, draft_id, a_room(building)["id"], "by hand")
    assert builder_lines(client, draft_id, "yes")[-1]["applied"] is None


def test_cancel_proposal_endpoint(client):
    draft_id = new_draft(client)["draft"]["id"]
    proposal = builder_lines(client, draft_id, side_prompt(client, draft_id))[-1]["proposal"]
    assert client.post(f"/drafts/{draft_id}/proposals/{proposal['id']}/cancel").status_code == 200
    assert client.post(f"/drafts/{draft_id}/proposals/{proposal['id']}/apply").status_code == 409
