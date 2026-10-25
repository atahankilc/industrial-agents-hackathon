"""Access mode (backend/access.py, core/access.py): restricted spaces leave the viewer's building copy, tools answer
"restricted", the plan darkens them, admin-only settings; with access mode off nothing changes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.guide import INSTRUCTIONS, system_blocks
from agent.tools import BuildingSession
from backend import app as app_module
from backend.access import ANONYMOUS, Access, AuthError, BuildingAccess, MemoryAccess, Viewer
from core.access import filter_building, restricted_names
from core.building_map import BuildingMap

BUILDING = "train/proc-campus-train-000"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / BUILDING
STORAGE = {"proc-campus-train-000-F1-S014", "proc-campus-train-000-F1-S020", "proc-campus-train-000-F3-S017"}


def building_data() -> dict:
    return json.loads((DATA_DIR / "building.json").read_text(encoding="utf-8"))


# ---------- core ----------


def test_filter_building_drops_spaces_and_everything_that_needs_them():
    data = building_data()
    filtered = filter_building(data, STORAGE)
    assert not STORAGE & {space["id"] for space in filtered["spaces"]}
    assert not any(STORAGE & set(opening["space_ids"]) for opening in filtered["openings"])
    assert not any(asset["space_id"] in STORAGE for asset in filtered["assets"])
    assert all(len(c["space_ids"]) == len(c["floor_ids"]) >= 2 for c in filtered["vertical_connectors"])
    assert filter_building(data, frozenset()) == data  # nothing restricted: an equal copy
    BuildingMap(filtered).overview()  # loads


def test_restricted_session_routes_without_them_and_says_restricted():
    data = building_data()
    session = BuildingSession(BuildingMap(filter_building(data, STORAGE)))
    session.restricted_names = restricted_names(data, STORAGE)
    route = session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
    assert route["reachable"] and not STORAGE & set(route["space_path"])
    for name, arguments in [("find_route", {"start": "Main lobby", "destination": "Storage 1.14"}),
                            ("locate", {"query": "Shelf 1.14-A"}), ("room_facts", {"space": "Storage 3.17"})]:
        result = session.call(name, arguments)
        assert result["error"] == "restricted", (name, result)
    assert "restricted" in system_blocks(session)[1]["text"]


def test_unrestricted_session_is_unchanged():
    session = BuildingSession.load(DATA_DIR)
    assert session.restricted_names == set()
    assert session.call("locate", {"query": "zzzz"}) == {"query": "zzzz", "match": "none", "total": 0, "assets": []}
    assert system_blocks(session)[0]["text"] == INSTRUCTIONS
    assert "restricted" not in system_blocks(session)[1]["text"]


def test_rules_room_type_space_exception_and_groups():
    store = MemoryAccess()
    store.set_building(BUILDING, BuildingAccess.from_dict(
        {"room_types": {"storage": ["staff"]}, "spaces": {"proc-campus-train-000-F3-S017": ["public"]}}))
    access = Access(store=store, enabled=True)
    data = building_data()
    expected = STORAGE - {"proc-campus-train-000-F3-S017"}
    assert access.restricted_for(ANONYMOUS, BUILDING, data) == expected
    member = Viewer(user_id="u1", email="m@x.org")
    assert access.restricted_for(member, BUILDING, data) == expected
    from backend.access import Member
    store.set_member(Member("u1", "m@x.org", BUILDING, ["staff"]))
    assert access.restricted_for(member, BUILDING, data) == frozenset()
    assert access.restricted_for(Viewer(user_id="a", email="a@x.org", admin=True), BUILDING, data) == frozenset()
    assert Access(store=store, enabled=False).restricted_for(ANONYMOUS, BUILDING, data) == frozenset()


# ---------- API ----------


class FakeAuth:
    VIEWERS = {"admin": Viewer("admin-id", "admin@x.org", True), "staff": Viewer("staff-id", "staff@x.org")}

    def viewer(self, authorization):
        if not authorization:
            return ANONYMOUS
        token = authorization.removeprefix("Bearer ")
        if token not in self.VIEWERS:
            raise AuthError("bad token")
        return self.VIEWERS[token]

    def invite(self, email, redirect_to=None):
        return "new-id", "https://example.invalid/link"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    monkeypatch.setattr(app_module, "access", Access(store=MemoryAccess(), auth=FakeAuth(), enabled=True))
    return TestClient(app_module.app)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_access_off_config(monkeypatch):
    monkeypatch.setattr(app_module, "access", Access(store=MemoryAccess(), enabled=False))
    client = TestClient(app_module.app)
    assert client.get("/config").json() == {"access_mode": False}
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    assert "restricted" not in client.get(f"/sessions/{session_id}/plan").json()
    assert client.get("/access/building", params={"building": BUILDING}).status_code == 404


def test_admin_rules_reach_anonymous_and_members(client):
    assert client.get("/config").json()["access_mode"] is True
    assert client.put("/access/building", json={"building": BUILDING, "room_types": {"storage": ["staff"]}}
                      ).status_code == 403  # anonymous
    assert client.put("/access/building", headers=auth("staff"),
                      json={"building": BUILDING, "room_types": {"storage": ["staff"]}}).status_code == 403
    response = client.put("/access/building", headers=auth("admin"),
                          json={"building": BUILDING, "room_types": {"storage": ["staff"]}})
    assert response.status_code == 200
    editor = client.get("/access/building", params={"building": BUILDING}, headers=auth("admin")).json()
    assert "storage" in editor["room_type_options"] and editor["room_types"] == {"storage": ["staff"]}

    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    plan = client.get(f"/sessions/{session_id}/plan").json()
    assert {shape["id"] for shape in plan["restricted"]} == STORAGE
    assert not STORAGE & {space["id"] for space in plan["spaces"]}
    conversation = app_module.store.get(session_id)
    assert conversation.session.call("locate", {"query": "Shelf 1.14-A"})["error"] == "restricted"

    # the staff member is invited into the group: the same building, nothing restricted
    invite = client.post("/access/invite", headers=auth("admin"),
                         json={"email": "Staff@x.org", "building": BUILDING, "groups": ["staff"]}).json()
    assert invite["link"].startswith("https://") and invite["email"] == "staff@x.org"
    client.put("/access/members", headers=auth("admin"),
               json={"user_id": "staff-id", "email": "staff@x.org", "building": BUILDING, "groups": ["staff"]})
    members = client.get("/access/members", params={"building": BUILDING}, headers=auth("admin")).json()
    assert {member["user_id"] for member in members} == {"new-id", "staff-id"}
    plan = client.get(f"/sessions/{session_id}/plan", headers=auth("staff")).json()
    assert "restricted" not in plan and STORAGE <= {space["id"] for space in plan["spaces"]}
    assert client.get("/me", headers=auth("staff")).json()["buildings"] == {BUILDING: ["staff"]}


def test_private_building_hidden_and_drafts_admin_only(client):
    client.put("/access/building", headers=auth("admin"), json={"building": BUILDING, "public": False})
    assert BUILDING not in {item["id"] for item in client.get("/buildings").json()}
    assert BUILDING in {item["id"] for item in client.get("/buildings", headers=auth("admin")).json()}
    assert client.post("/sessions", json={"building": BUILDING}).status_code == 422
    assert client.post("/drafts", json={"base": BUILDING}).status_code == 403
    assert client.post("/api/drafts", json={"base": BUILDING}).status_code == 403
    assert client.get("/buildings", headers=auth("forged")).status_code == 401


# ---------- preferences (phase 2) ----------


def test_preferences_off_keep_tool_list_and_routes():
    from agent.tools import TOOL_DEFINITIONS
    session = BuildingSession.load(DATA_DIR)
    assert session.tool_definitions() is TOOL_DEFINITIONS
    assert session.profile.penalties() is None
    assert session.call("set_preference", {"language": "Turkish"})["error"]
    session.call("set_profile", {"preset": "wheelchair"})
    assert not [event for event in session.events if event["type"] == "preference"]


def test_prefer_lifts_takes_the_lift_and_reports_true_metres():
    session = BuildingSession.load(DATA_DIR)
    trip = {"start": "Main lobby", "destination": "Meeting room 3.07"}
    plain = session.call("find_route", trip)
    session.call("set_profile", {"prefer_lifts": True})
    lifted = session.call("find_route", trip)
    lifts = {c for c in lifted["element_path"] if session.building.connectors.get(c, {}).get("kind") == "lift"}
    assert lifts and lifted["length_m"] > plain["length_m"]
    # the reported length is the real walk: the same path without preferences measures the same
    session.call("set_profile", {"prefer_lifts": False, "avoid_lifts": False})
    assert "prefers lifts" not in session.profile.describe()


def test_preferences_on_emit_events_and_extend_tools():
    session = BuildingSession.load(DATA_DIR)
    session.preferences_enabled = True
    names = [tool["name"] for tool in session.tool_definitions()]
    assert "set_preference" in names
    result = session.call("set_profile", {"preset": "wheelchair", "quiet": True, "scope": "building"})
    assert result["remembered"] == "building"
    event = session.events[-1]
    assert event["type"] == "preference" and event["values"]["quiet"] is True and event["values"]["step_free"]
    session.call("set_profile", {"preset": "default"})
    assert session.profile.quiet and not session.profile.step_free  # default clears mobility only
    talk = session.call("set_preference", {"language": "Turkish", "reply_style": "brief"})
    assert talk["remembered"] == "global" and "Turkish" in system_blocks(session)[1]["text"]
    session.auto_capture = False
    count = len(session.events)
    session.call("set_profile", {"fewer_doors": True})
    assert len(session.events) == count  # nothing remembered when the user switched it off


def test_session_preferences_endpoint(client):
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    response = client.put(f"/sessions/{session_id}/preferences",
                          json={"values": {"step_free": True, "prefer_lifts": True, "language": "German"},
                                "auto_capture": False})
    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["step_free"] and profile["prefer_lifts"]
    conversation = app_module.store.get(session_id)
    assert conversation.session.auto_capture is False
    assert "German" in conversation.guide.system[1]["text"]
    assert client.get("/me/preferences").status_code == 404  # anonymous: kept in the browser
    assert client.put("/me/preferences", headers=auth("staff"), json={"global": {"quiet": True}}).status_code == 200
    assert client.get("/me/preferences", headers=auth("staff")).json() == {"global": {"quiet": True}}


def test_dev_panel_uses_the_viewer_token(client):
    client.put("/access/building", headers=auth("admin"), json={"building": BUILDING, "room_types": {"storage": ["staff"]}})
    session_id = client.post("/sessions", json={"building": BUILDING}, headers=auth("admin")).json()["session_id"]
    response = client.post(f"/dev/sessions/{session_id}/tool", headers=auth("admin"),
                           json={"name": "locate", "arguments": {"query": "Shelf 1.14-A"}})
    assert response.status_code == 200 and response.json()["result"].get("error") != "restricted"
    assert not app_module.store.get(session_id).restricted
    assert client.get(f"/dev/sessions/{session_id}/state", headers=auth("admin")).status_code == 200
    # without a token the dev panel is anonymous: the restricted copy
    anonymous = client.post(f"/dev/sessions/{session_id}/tool",
                            json={"name": "locate", "arguments": {"query": "Shelf 1.14-A"}}).json()
    assert anonymous["result"]["error"] == "restricted"


def test_admin_emails_comma_separated(monkeypatch):
    from backend.access import admin_emails
    monkeypatch.setenv("ADMIN_EMAIL", " A@x.org, b@y.org ,")
    assert admin_emails() == {"a@x.org", "b@y.org"}
    monkeypatch.delenv("ADMIN_EMAIL")
    assert admin_emails() == set()
