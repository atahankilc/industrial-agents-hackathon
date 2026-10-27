"""Moving objects (backend/core/fleet.py, backend/api/fleet.py): attributes → closures, mission steps, device positions, the
admin's dispatch (API and the Guide's send_object), access mode only."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app as app_module

from backend.api import deps
from backend.api.access import ANONYMOUS, Access, MemoryAccess, Viewer
from backend.api.fleet import MemoryFleet
from backend.core.building_map import BuildingMap
from backend.core.fleet import Attributes, closures, mission

CAMPUS = "proc-campus-train-000"
FACTORY = "proc-factory-train-008"
DATA = Path(__file__).resolve().parent.parent / "data"


def campus() -> BuildingMap:
    return BuildingMap.load(DATA / "buildings" / CAMPUS)


def test_attributes_close_what_the_object_cannot_use():
    building = campus()
    wide = closures(building, "robot", Attributes(width_m=1.5))
    assert all(building.openings[o]["width_m"] < 1.5 or not building.openings[o]["step_free"]
               for o in wide if o in building.openings)
    stairs = {c for c, connector in building.connectors.items() if connector["kind"] == "stairs"}
    assert stairs <= set(wide)  # wheels: no stairs
    assert not stairs & set(closures(building, "robot", Attributes(width_m=0.5, can_use_stairs=True)))
    with pytest.raises(ValueError):
        Attributes.from_dict({"width_m": 0})


def test_mission_steps_follow_the_route():
    building = campus()
    start, end = building.resolve_space("Main lobby"), building.resolve_space("Meeting room 3.07")
    planned = mission(building, "robot", Attributes(width_m=0.7), start, end)
    ops = [step["op"] for step in planned["steps"]]
    assert planned["reachable"] and ops[0] == "move" and ops[-1] == "arrive"
    assert "call_lift" in ops and "take_stairs" not in ops  # wheels: the lift, never the stairs
    lift = next(step for step in planned["steps"] if step["op"] == "call_lift")
    assert building.connectors[lift["connector_id"]]["kind"] == "lift"
    passed = [step["opening_id"] for step in planned["steps"] if step["op"] == "pass_opening"]
    assert passed == [e for e in planned["element_path"] if e in building.openings]
    assert not mission(building, "robot", Attributes(width_m=0.7, can_use_lifts=False), start, end)["reachable"]


class FakeAuth:
    def viewer(self, authorization):
        return Viewer("admin-id", "admin@x.org", True) if authorization == "Bearer admin" else ANONYMOUS


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    monkeypatch.setattr(deps, "access", Access(store=MemoryAccess(), auth=FakeAuth(), enabled=True))
    monkeypatch.setattr(deps.fleet, "store", MemoryFleet())
    return TestClient(app_module.app)


ADMIN = {"Authorization": "Bearer admin"}


def test_off_means_404(monkeypatch):
    monkeypatch.setattr(deps, "access", Access(store=MemoryAccess(), enabled=False))
    assert TestClient(app_module.app).get("/objects", params={"building": CAMPUS}).status_code == 404


def test_create_move_dispatch_follow(client):
    building = campus()
    lobby = building.spaces[building.resolve_space("Main lobby")]
    x, y = lobby["polygon"][0]
    body = {"building": CAMPUS, "name": "R1", "kind": "robot", "attributes": {"width_m": 0.7}}
    assert client.post("/objects", json=body).status_code == 403
    created = client.post("/objects", json=body, headers=ADMIN).json()
    object_id, token = created["id"], created["token"]
    device = {"X-Object-Token": token}
    assert client.post(f"/objects/{object_id}/position", json={"floor_id": lobby["floor_id"], "x": 0, "y": 0},
                       headers={"X-Object-Token": "wrong"}).status_code == 403
    centre = [sum(c) / len(c) for c in zip(*lobby["polygon"])]
    moved = client.post(f"/objects/{object_id}/position", headers=device,
                        json={"floor_id": lobby["floor_id"], "x": centre[0], "y": centre[1]}).json()
    assert moved["space_id"] == lobby["id"]

    sent = client.post(f"/objects/{object_id}/mission", json={"destination": "Meeting room 3.07"},
                       headers=ADMIN).json()
    assert sent["reachable"] and sent["to"] == "Meeting room 3.07"
    task = client.get(f"/objects/{object_id}/mission", headers=device).json()
    assert task["status"] == "active" and task["version"] == 1 and "line" not in task
    listed = client.get("/objects", params={"building": CAMPUS}).json()
    assert listed[0]["mission"]["line"] and listed[0]["position"]["floor"] == 0 and "token" not in listed[0]
    client.post(f"/objects/{object_id}/mission/done", headers=device)
    assert client.get(f"/objects/{object_id}/mission", headers=device).json()["status"] == "done"


def test_import_forklifts_and_guide_send_object(client):
    imported = client.post("/objects/import-forklifts", json={"building": FACTORY}, headers=ADMIN).json()
    assert imported and all(item["kind"] == "forklift" and item["position"]["floor"] is not None for item in imported)
    assert client.post("/objects/import-forklifts", json={"building": FACTORY}, headers=ADMIN).json() == []

    session_id = client.post("/sessions", json={"building": FACTORY}, headers=ADMIN).json()["session_id"]
    conversation = deps.conversation_or_404(session_id, "Bearer admin")
    names = [tool["name"] for tool in conversation.session.tool_definitions()]
    assert "send_object" in names
    unknown = conversation.session.call("send_object", {"object": "nobody", "destination": "Locker room 0.30"})
    assert unknown["error"] and imported[0]["name"] in unknown["objects"]
    anonymous = deps.conversation_or_404(session_id, None)
    assert "send_object" not in [tool["name"] for tool in anonymous.session.tool_definitions()]
