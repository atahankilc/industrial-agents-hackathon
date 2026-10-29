"""Organisations' maps (backend/api/maps.py, backend/api/routes/maps.py, docs/product/organizations.md phase 2): who
opens a map (private / link / public), which of its buildings each viewer gets, and who may change it."""

import pytest
from fastapi.testclient import TestClient

from backend.api import deps
from backend.api.access import BuildingAccess
from backend.api.maps import MemoryMaps, OrgMap
from tests.test_orgs import HAUPT, MENSA, OTHER, auth, client, tum  # noqa: F401 (fixtures)


@pytest.fixture
def maps(tum, monkeypatch) -> TestClient:
    """`tum` with a private map `tum-campus` holding HAUPT and MENSA (MENSA unlisted)."""
    monkeypatch.setattr(deps, "maps", MemoryMaps())
    made = tum.post("/orgs/tum/maps", headers=auth("editor"), json={"slug": "tum-campus", "name": "TUM Campus"})
    assert made.status_code == 200 and made.json()["buildings"] == [] and made.json()["can_edit"]
    for building in (HAUPT, MENSA):
        assert tum.put("/maps/tum-campus/buildings", headers=auth("editor"), json={"building": building}).status_code == 200
    tum.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": MENSA, "listing": "unlisted"})
    return tum


def ids(response) -> list[str]:
    return [item["id"] for item in response.json()["buildings"]]


def test_a_private_map_opens_for_its_org_only(maps):
    assert maps.get("/maps/tum-campus").status_code == 404
    assert maps.get("/maps/tum-campus", headers=auth("outsider")).status_code == 404
    seen = maps.get("/maps/tum-campus", headers=auth("student"))
    assert ids(seen) == [HAUPT, MENSA] and seen.json()["can_edit"] is False and "token" not in seen.json()
    assert seen.json()["org"] == {"slug": "tum", "name": "TU München", "verified": False}
    assert maps.get("/orgs/tum/maps", headers=auth("student")).json() == [
        {"slug": "tum-campus", "name": "TUM Campus", "visibility": "private", "buildings": 2}]


def test_a_link_opens_the_map_with_its_unlisted_buildings_until_renewed(maps):
    shared = maps.put("/maps/tum-campus", headers=auth("editor"), json={"visibility": "link"}).json()
    token = shared["token"]
    assert token and maps.get("/maps/tum-campus").status_code == 404
    assert maps.get("/maps/tum-campus", params={"k": "wrong"}).status_code == 404
    opened = maps.get("/maps/tum-campus", params={"k": token})
    assert ids(opened) == [HAUPT, MENSA]  # MENSA is unlisted: not in /buildings, but on the map
    assert MENSA not in {item["id"] for item in maps.get("/buildings").json()}
    assert opened.json()["can_edit"] is False and "token" not in opened.json()
    renewed = maps.post("/maps/tum-campus/link", headers=auth("editor")).json()["token"]
    assert renewed != token and maps.get("/maps/tum-campus", params={"k": token}).status_code == 404
    assert maps.get("/maps/tum-campus", params={"k": renewed}).status_code == 200


def test_a_public_map_leaves_out_private_buildings_for_outsiders(maps):
    maps.put("/maps/tum-campus", headers=auth("editor"), json={"visibility": "public"})
    maps.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": HAUPT, "listing": "private"})
    assert ids(maps.get("/maps/tum-campus")) == [MENSA]
    assert ids(maps.get("/maps/tum-campus", headers=auth("student"))) == [HAUPT, MENSA]


def test_who_changes_a_map_and_what_goes_on_it(maps):
    assert maps.post("/orgs/tum/maps", headers=auth("student"), json={"slug": "x", "name": "X"}).status_code == 403
    assert maps.post("/orgs/tum/maps", headers=auth("editor"), json={"slug": "tum-campus", "name": "X"}).status_code == 409
    assert maps.post("/orgs/tum/maps", headers=auth("editor"),
                     json={"slug": "x", "name": "X", "visibility": "everyone"}).status_code == 422
    assert maps.put("/maps/tum-campus", headers=auth("student"), json={"name": "Mine"}).status_code == 403
    assert maps.put("/maps/tum-campus/buildings", headers=auth("editor"), json={"building": OTHER}).status_code == 200
    # another org's unlisted building cannot be put on it
    maps.post("/orgs", headers=auth("outsider"), json={"slug": "lmu", "name": "LMU"})
    deps.access.store.set_building(OTHER, BuildingAccess(listing="unlisted", org="lmu"))
    maps.put("/maps/tum-campus/buildings", headers=auth("editor"), json={"building": OTHER, "on": False})
    assert maps.put("/maps/tum-campus/buildings", headers=auth("editor"), json={"building": OTHER}).status_code == 403
    assert maps.delete("/maps/tum-campus", headers=auth("editor")).status_code == 403
    assert maps.delete("/maps/tum-campus", headers=auth("owner")).json() == {"deleted": "tum-campus"}
    assert maps.get("/maps/tum-campus", headers=auth("owner")).status_code == 404


def test_the_guide_keeps_neighbours_of_an_unlisted_building_opened_by_link(maps):
    maps.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": HAUPT, "listing": "unlisted"})
    session_id = maps.post("/sessions", headers=auth("outsider"), json={"building": HAUPT}).json()["session_id"]
    campus = deps.conversation_or_404(session_id, "Bearer outsider").session.campus
    assert HAUPT in campus.catalogue and MENSA not in campus.catalogue  # its own place stays, the hidden one does not


def test_the_guide_gets_the_maps_unlisted_buildings_as_neighbours_on_the_map(maps):
    maps.put("/orgs/tum/buildings", headers=auth("editor"), json={"building": HAUPT, "listing": "unlisted"})
    token = maps.put("/maps/tum-campus", headers=auth("editor"), json={"visibility": "link"}).json()["token"]
    session_id = maps.post("/sessions", json={"building": HAUPT}).json()["session_id"]

    def campus(headers: dict) -> set[str]:
        assert maps.get(f"/sessions/{session_id}", headers=headers).status_code == 200  # rebuilds it for this request
        return set(deps.store.get(session_id).session.campus.catalogue)

    assert MENSA not in campus({})  # unlisted and not on a map: not a neighbour
    assert MENSA in campus({"X-Steward-Map": "tum-campus", "X-Steward-Map-Key": token})  # the map's link opens it
    assert MENSA not in campus({"X-Steward-Map": "tum-campus", "X-Steward-Map-Key": "wrong"})
    assert MENSA not in campus({"X-Steward-Map": "nope"})
    assert MENSA in campus({"X-Steward-Map": "tum-campus", **auth("student")})  # the org's people need no key


def test_map_row_opens_with():
    row = OrgMap("m", "o", "M", "link", token="abc")
    assert row.opens_with("abc") and not row.opens_with("abd") and not row.opens_with(None)
    assert not OrgMap("m", "o", "M", "private", token="abc").opens_with("abc")
    assert OrgMap("m", "o", "M", "public").opens_with(None)


def test_editors_arrange_and_name_the_islands(maps):
    layout = {"sites": [{"buildings": [HAUPT, MENSA, HAUPT], "name": "  Stammgelände ", "dx": 120, "dy": -40},
                        {"buildings": [OTHER], "name": "", "dx": 5},  # half a move: placed by the app
                        {"buildings": [], "name": "empty"}]}  # no buildings: dropped
    saved = maps.put("/maps/tum-campus", headers=auth("editor"), json={"layout": layout})
    assert saved.status_code == 200
    assert saved.json()["layout"] == {"sites": [
        {"buildings": [HAUPT, MENSA], "name": "Stammgelände", "dx": 120, "dy": -40, "area": None},
        {"buildings": [OTHER], "name": None, "dx": None, "dy": None, "area": None}]}
    assert maps.get("/maps/tum-campus", headers=auth("student")).json()["layout"]["sites"][0]["name"] == "Stammgelände"
    assert maps.put("/maps/tum-campus", headers=auth("student"), json={"layout": {"sites": []}}).status_code == 403
    too_long = {"sites": [{"buildings": [HAUPT], "name": "x" * 61}]}
    assert maps.put("/maps/tum-campus", headers=auth("editor"), json={"layout": too_long}).status_code == 422
    far = {"sites": [{"buildings": [HAUPT], "dx": 2**27, "dy": 0}]}
    assert maps.put("/maps/tum-campus", headers=auth("editor"), json={"layout": far}).status_code == 422
    # a name or visibility change keeps the layout
    maps.put("/maps/tum-campus", headers=auth("editor"), json={"name": "Campus"})
    assert deps.maps.get("tum-campus").layout["sites"][0]["dx"] == 120


def test_a_drawn_area_is_a_rectangle_on_the_grid(maps):
    area = {"x0": 35_700_000, "y0": 23_000_000, "x1": 35_703_000, "y1": 23_002_000}
    saved = maps.put("/maps/tum-campus", headers=auth("editor"),
                     json={"layout": {"sites": [{"buildings": [HAUPT], "area": area}]}})
    assert saved.json()["layout"]["sites"][0]["area"] == area
    for bad in ({**area, "x1": area["x0"]},  # no width
                {**area, "x1": area["x0"] + 20_001},  # too long a side
                {**area, "y1": 2**26 + 1}):  # off the world
        refused = maps.put("/maps/tum-campus", headers=auth("editor"), json={"layout": {"sites": [{"buildings": [HAUPT], "area": bad}]}})
        assert refused.status_code == 422, bad
