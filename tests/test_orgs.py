"""Organisations (backend/api/access.py, backend/api/routes/orgs.py, docs/product/organizations.md): an org owns
buildings, its editors administer them, listings (listed / unlisted / private) decide who finds and opens them, and the
Guide's neighbours leave out what the viewer may not list."""

import pytest
from fastapi.testclient import TestClient

from backend.api import app as app_module
from backend.api import deps
from backend.api.access import ANONYMOUS, Access, AuthError, BuildingAccess, MemoryAccess, Viewer, building_row
from backend.api.fleet import MemoryFleet

HAUPT = "osm-way10053349"  # TUM's main building: modelled neighbours on the campus (tests/test_campus.py)
MENSA = "osm-way19183732"  # one of them
OTHER = "proc-campus-train-000"  # stays the platform's


class FakeAuth:
    VIEWERS = {"admin": Viewer("admin-id", "admin@x.org", True), "owner": Viewer("owner-id", "owner@tum.de"),
               "editor": Viewer("editor-id", "editor@tum.de"), "student": Viewer("student-id", "student@tum.de"),
               "outsider": Viewer("outsider-id", "someone@x.org")}

    def viewer(self, authorization):
        if not authorization:
            return ANONYMOUS
        token = authorization.removeprefix("Bearer ")
        if token not in self.VIEWERS:
            raise AuthError("bad token")
        return self.VIEWERS[token]

    def invite(self, email, redirect_to=None):
        return {"editor@tum.de": "editor-id", "student@tum.de": "student-id"}.get(email, "new-id"), "https://x.invalid/l"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    monkeypatch.setattr(deps, "access", Access(store=MemoryAccess(), auth=FakeAuth(), enabled=True))
    return TestClient(app_module.app)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tum(client) -> TestClient:
    """Org `tum`: owner, an editor and a viewer; the admin gave it HAUPT and MENSA."""
    assert client.post("/orgs", headers=auth("owner"), json={"slug": "tum", "name": "TU München"}).status_code == 200
    for email, role in (("editor@tum.de", "editor"), ("student@tum.de", "viewer")):
        assert client.post("/orgs/tum/invite", headers=auth("owner"), json={"email": email, "role": role}).status_code == 200
    for building in (HAUPT, MENSA):
        assert client.put("/orgs/tum/buildings", headers=auth("admin"), json={"building": building}).status_code == 200
    return client


def listed(client: TestClient, token: str | None = None) -> set[str]:
    return {item["id"] for item in client.get("/buildings", headers=auth(token) if token else {}).json()}


# ---------- rules ----------


def test_listing_replaces_public_and_older_rows_still_read():
    assert BuildingAccess.from_dict({"public": False}).listing == "private"
    assert BuildingAccess.from_dict({}).listing == "listed"
    unlisted = BuildingAccess.from_dict({"listing": "unlisted", "public": False})
    assert unlisted.public and unlisted.to_dict()["public"] is True
    with pytest.raises(ValueError):
        BuildingAccess.from_dict({"listing": "secret"})
    # a row written by code from before the migration: only `public` changed, so `public` wins
    assert building_row(False, "listed", None, {}).listing == "private"
    assert building_row(True, "unlisted", "tum", {}).listing == "unlisted"
    assert building_row(True, None, None, None).listing == "listed"


def test_org_roles_decide_admin_and_visibility():
    store = MemoryAccess()
    access = Access(store=store, enabled=True)
    from backend.api.access import Org, OrgMember
    assert store.insert_org(Org("tum", "TUM"), OrgMember("tum", "o", "o@tum.de", "owner"))
    assert not store.insert_org(Org("tum", "Other"), OrgMember("tum", "x", "x@x.org", "owner"))
    store.set_org_member(OrgMember("tum", "v", "v@tum.de", "viewer"))
    store.set_building(HAUPT, BuildingAccess(listing="private", org="tum"))
    owner, member, outsider = Viewer("o", "o@tum.de"), Viewer("v", "v@tum.de"), Viewer("x", "x@x.org")
    assert access.can_admin(owner, HAUPT) and not access.can_admin(member, HAUPT)
    assert not access.can_admin(owner, OTHER)  # the platform's
    assert access.visible(member, HAUPT) and not access.visible(outsider, HAUPT) and not access.visible(ANONYMOUS, HAUPT)
    assert access.hidden_buildings(outsider) == {HAUPT} and access.hidden_buildings(member) == set()
    assert access.restricted_for(owner, HAUPT, {"spaces": [{"id": "s", "room_type": "lab"}]}) == frozenset()


# ---------- API ----------


def test_creating_an_org(client):
    assert client.post("/orgs", json={"slug": "tum", "name": "TUM"}).status_code == 401  # anonymous
    assert client.post("/orgs", headers=auth("owner"), json={"slug": "TU M!", "name": "TUM"}).status_code == 422
    made = client.post("/orgs", headers=auth("owner"), json={"slug": "TUM", "name": " TU München "}).json()
    assert made == {"slug": "tum", "name": "TU München", "verified": False, "role": "owner", "buildings": [],
                    "members": [{"org": "tum", "user_id": "owner-id", "email": "owner@tum.de", "role": "owner"}]}
    assert client.post("/orgs", headers=auth("outsider"), json={"slug": "tum", "name": "Fake"}).status_code == 409
    assert client.get("/orgs/tum", headers=auth("outsider")).status_code == 404  # not theirs: as if not there
    assert [org["slug"] for org in client.get("/orgs", headers=auth("admin")).json()] == ["tum"]
    assert client.get("/orgs", headers=auth("outsider")).json() == []
    assert client.get("/me", headers=auth("owner")).json()["orgs"] == {"tum": "owner"}


def test_only_the_admin_gives_buildings_and_verifies(tum):
    assert tum.put("/orgs/tum/buildings", headers=auth("owner"), json={"building": OTHER}).status_code == 403
    assert tum.put("/orgs/tum/buildings", headers=auth("student"),
                   json={"building": HAUPT, "listing": "private"}).status_code == 403  # a viewer
    assert tum.put("/orgs/tum", headers=auth("owner"), json={"verified": True}).status_code == 403
    org = tum.get("/orgs/tum", headers=auth("editor")).json()
    assert org["buildings"] == [{"id": HAUPT, "listing": "listed"}, {"id": MENSA, "listing": "listed"}]
    assert "members" not in org  # the owner's view only
    assert {item["id"]: item["org"] for item in tum.get("/buildings").json()}[HAUPT] == "tum"


def test_an_org_cannot_change_buildings_it_does_not_own(tum):
    # a platform building: an outsider's own org cannot hide it, whatever `owned` says
    assert tum.post("/orgs", headers=auth("outsider"), json={"slug": "mine", "name": "Mine"}).status_code == 200
    for owned in (False, True):
        hide = {"building": OTHER, "owned": owned, "listing": "private"}
        assert tum.put("/orgs/mine/buildings", headers=auth("outsider"), json=hide).status_code == 403
    assert OTHER in listed(tum)
    # another org's building: the tum editor and owner cannot change it through /orgs/tum
    assert tum.put("/orgs/mine/buildings", headers=auth("admin"), json={"building": MENSA}).status_code == 200
    for token in ("editor", "owner"):
        for owned in (False, True):
            edit = {"building": MENSA, "owned": owned, "listing": "private"}
            assert tum.put("/orgs/tum/buildings", headers=auth(token), json=edit).status_code == 403
    assert MENSA in listed(tum)
    assert {item["id"]: item["org"] for item in tum.get("/buildings").json()}[MENSA] == "mine"


def test_unverified_org_cannot_list_on_the_main_map(tum):
    edit = {"building": MENSA, "listing": "unlisted"}
    assert tum.put("/orgs/tum/buildings", headers=auth("editor"), json=edit).status_code == 200
    assert MENSA not in listed(tum) and MENSA not in listed(tum, "outsider")
    assert MENSA in listed(tum, "student")  # its org finds it
    assert tum.post("/sessions", json={"building": MENSA}).status_code == 200  # unlisted: anyone with the link opens it
    back = {"building": MENSA, "listing": "listed"}
    assert tum.put("/orgs/tum/buildings", headers=auth("editor"), json=back).status_code == 403
    assert tum.put("/access/building", headers=auth("editor"), json={"building": MENSA, "listing": "listed"}
                   ).status_code == 403
    assert tum.put("/orgs/tum", headers=auth("admin"), json={"verified": True}).json()["verified"] is True
    assert tum.put("/orgs/tum/buildings", headers=auth("editor"), json=back).status_code == 200
    assert MENSA in listed(tum)


def test_private_org_building_opens_only_for_its_people(tum):
    assert tum.put("/orgs/tum/buildings", headers=auth("editor"),
                   json={"building": HAUPT, "listing": "private"}).status_code == 200
    assert HAUPT not in listed(tum, "outsider") and HAUPT in listed(tum, "student")
    assert tum.post("/sessions", headers=auth("outsider"), json={"building": HAUPT}).status_code == 422
    assert tum.post("/sessions", headers=auth("student"), json={"building": HAUPT}).status_code == 200


def test_org_editor_administers_its_buildings_only(tum):
    rules = {"building": HAUPT, "room_types": {"office": ["staff"]}}
    assert tum.put("/access/building", headers=auth("editor"), json=rules).status_code == 200
    got = tum.get("/access/building", params={"building": HAUPT}, headers=auth("editor")).json()
    assert got["room_types"] == {"office": ["staff"]} and got["org"] == "tum" and got["listing"] == "listed"
    assert tum.put("/access/building", headers=auth("student"), json=rules).status_code == 403
    assert tum.get("/access/building", params={"building": OTHER}, headers=auth("editor")).status_code == 403
    assert tum.get("/access/members", params={"building": HAUPT}, headers=auth("editor")).status_code == 200
    # the old app sends only `public`: an unlisted building stays unlisted while public stays true
    tum.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": HAUPT, "listing": "unlisted"})
    kept = tum.put("/access/building", headers=auth("editor"), json={"building": HAUPT, "public": True}).json()
    assert kept["listing"] == "unlisted" and kept["org"] == "tum"


def test_an_org_keeps_an_owner(tum):
    leave = {"user_id": "owner-id", "email": "owner@tum.de", "role": None}
    assert tum.put("/orgs/tum/members", headers=auth("owner"), json=leave).status_code == 409
    assert tum.put("/orgs/tum/members", headers=auth("editor"),
                   json={"user_id": "editor-id", "email": "editor@tum.de", "role": "owner"}).status_code == 403
    promote = {"user_id": "editor-id", "email": "editor@tum.de", "role": "owner"}
    assert tum.put("/orgs/tum/members", headers=auth("owner"), json=promote).status_code == 200
    assert tum.put("/orgs/tum/members", headers=auth("owner"), json=leave).status_code == 200
    assert tum.get("/orgs/tum", headers=auth("owner")).status_code == 404
    assert tum.post("/orgs/tum/invite", headers=auth("owner"), json={"email": "a@b.c", "role": "boss"}).status_code == 404
    assert tum.post("/orgs/tum/invite", headers=auth("editor"), json={"email": "a@b.c", "role": "boss"}).status_code == 422


def test_the_guide_does_not_name_buildings_the_viewer_may_not_list(tum):
    tum.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": MENSA, "listing": "unlisted"})
    for token, sees in (("outsider", False), ("student", True)):
        session_id = tum.post("/sessions", headers=auth(token), json={"building": HAUPT}).json()["session_id"]
        campus = deps.conversation_or_404(session_id, f"Bearer {token}").session.campus
        assert (MENSA in {item["building_id"] for item in campus.neighbours()}) is sees, token
        assert (MENSA in campus.catalogue) is sees


def test_org_editor_runs_its_buildings_objects(tum, monkeypatch):
    monkeypatch.setattr(deps.fleet, "store", MemoryFleet())
    body = {"name": "Robot", "kind": "robot", "attributes": {"width_m": 0.6}}
    made = tum.post("/objects", headers=auth("editor"), json={**body, "building": HAUPT})
    assert made.status_code == 200
    assert tum.post("/objects", headers=auth("editor"), json={**body, "building": OTHER}).status_code == 403
    assert tum.delete(f"/objects/{made.json()['id']}", headers=auth("student")).status_code == 403
    assert tum.delete(f"/objects/{made.json()['id']}", headers=auth("editor")).status_code == 200
