"""Organisations phase 2c (docs/product/organizations.md): an org's editors open Edit mode on its buildings, save the
result into the org (and onto the map they made it from), create buildings from plans only in a verified org, and
nobody else reaches their drafts."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api import deps
from backend.api.drafts import DraftStore
from backend.api.maps import MemoryMaps, OrgMap
from tests.test_import_drafts import fixture_building
from tests.test_orgs import FakeAuth, HAUPT, OTHER, auth, client, tum  # noqa: F401 (fixtures)


@pytest.fixture
def org(tum, monkeypatch, tmp_path) -> TestClient:
    """`tum` (owns HAUPT and MENSA), drafts in a temporary folder, a map `tum-campus`; "outsider" owns org `lmu`."""
    catalogue = dict(deps.store.catalogue)
    monkeypatch.setattr(deps.store, "catalogue", catalogue)
    monkeypatch.setattr(deps, "drafts", DraftStore(tmp_path, catalogue))
    monkeypatch.setattr(deps, "maps", MemoryMaps())
    assert tum.post("/orgs/tum/maps", headers=auth("editor"), json={"slug": "tum-campus", "name": "Campus"}).status_code == 200
    assert tum.post("/orgs", headers=auth("outsider"), json={"slug": "lmu", "name": "LMU"}).status_code == 200
    return tum


def draft_of(client: TestClient, token: str, base: str):
    return client.post("/drafts", headers=auth(token), json={"base": base})


def draft_id(response) -> str:
    return response.json()["draft"]["id"]


def test_an_org_editor_edits_its_buildings_only(org):
    assert draft_of(org, "editor", OTHER).status_code == 403  # the platform's
    assert draft_of(org, "student", HAUPT).status_code == 403  # a viewer: stopped at the gate
    assert draft_of(org, "outsider", HAUPT).status_code == 403  # another org's owner
    made = draft_of(org, "editor", HAUPT)
    assert made.status_code == 200
    draft = draft_id(made)
    assert org.get(f"/drafts/{draft}", headers=auth("editor")).status_code == 200
    assert org.get(f"/drafts/{draft}", headers=auth("outsider")).status_code == 404  # past the gate, not theirs
    assert org.get(f"/drafts/{draft}/plan", headers=auth("owner")).status_code == 200
    assert org.get(f"/drafts/{draft}").status_code == 403  # anonymous


def test_a_saved_edit_belongs_to_the_org_and_goes_on_its_map(org):
    org.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": HAUPT, "listing": "unlisted"})
    draft = draft_id(draft_of(org, "editor", HAUPT))
    saved = org.post(f"/drafts/{draft}/save", headers=auth("editor"), json={"name": "Haupt edited", "map": "tum-campus"})
    assert saved.status_code == 200
    building = saved.json()["building"]
    access = deps.access.store.building(building)
    assert (access.org, access.listing) == ("tum", "unlisted")  # an edit keeps its base's listing
    assert building in deps.maps.get("tum-campus").buildings
    # deleting it: its org's editors, not another org
    path = f"/buildings/{building}"
    assert org.delete(path, headers=auth("outsider")).status_code == 403
    assert org.delete(path, headers=auth("editor")).json() == {"deleted": building}


def test_saving_onto_a_map_needs_its_editor(org):
    deps.maps.insert(OrgMap("lmu-map", "lmu", "LMU map"))
    draft = draft_id(draft_of(org, "editor", HAUPT))
    saved = org.post(f"/drafts/{draft}/save", headers=auth("editor"), json={"name": "Elsewhere", "map": "lmu-map"})
    assert saved.status_code == 200 and deps.maps.get("lmu-map").buildings == []


def test_who_creates_a_building_from_plans(org):
    owner, editor, student = (FakeAuth.VIEWERS[name] for name in ("owner", "editor", "student"))
    for viewer, name, status in ((student, "tum", 403), (editor, "tum", 403), (editor, None, 403), (editor, "nope", 422)):
        with pytest.raises(HTTPException) as refused:
            deps.creator_org_or_403(viewer, name)
        assert refused.value.status_code == status, (viewer.email, name)
    assert deps.creator_org_or_403(FakeAuth.VIEWERS["admin"], None) is None
    org.put("/orgs/tum", headers=auth("admin"), json={"verified": True})
    assert deps.creator_org_or_403(editor, "tum") == "tum" and deps.creator_org_or_403(owner, "tum") == "tum"
    assert org.post("/imports/stream", headers=auth("editor"), data={"org": "lmu"},
                    files={"files": ("plan.png", b"x", "image/png")}).status_code == 403  # not their org


def test_a_building_from_plans_opens_for_its_org_and_saves_unlisted(org):
    draft = deps.drafts.create_import(fixture_building())
    deps.own_import(draft.base, "tum")
    assert org.get(f"/drafts/{draft.id}", headers=auth("editor")).status_code == 200
    assert org.get(f"/drafts/{draft.id}", headers=auth("outsider")).status_code == 404
    saved = org.post(f"/drafts/{draft.id}/save", headers=auth("editor"), json={"name": "New lab"}).json()["building"]
    access = deps.access.store.building(saved)
    assert (access.org, access.listing) == ("tum", "unlisted")
    assert saved not in {item["id"] for item in org.get("/buildings").json()}
    assert saved in {item["id"] for item in org.get("/buildings", headers=auth("student")).json()}


def test_the_admin_still_edits_and_imports_platform_buildings(org):
    made = draft_of(org, "admin", OTHER)
    assert made.status_code == 200
    saved = org.post(f"/drafts/{draft_id(made)}/save", headers=auth("admin"), json={"name": "Platform edit"}).json()["building"]
    assert deps.access.store.building(saved).org is None  # no row: the platform's, listed as before
    assert saved in {item["id"] for item in org.get("/buildings").json()}
