"""Where an import stands when the photos know it: EXIF GPS (or the browser's position), the OSM building there
(core/osm_lookup.py, Overpass — faked here, no network), placement without a map tap, the "did you mean" suggestion
when the tapped building is elsewhere, and re-fitting a draft onto another footprint (POST /drafts/{id}/fit)."""

import io
import json

import pytest
from PIL import Image

from core import osm_lookup
from core.plan_import.ingest import median_gps, photo_gps
from tests.test_placement import PLAN, SPOT, api, imported, rotated_ring  # noqa: F401 (api is a fixture)

FAR = {"lat": SPOT["lat"] + 0.002, "lon": SPOT["lon"]}  # about 220 m north


def photo(lat: float, lon: float) -> bytes:
    def dms(value: float) -> tuple[float, float, float]:
        value = abs(value)
        degrees, minutes = int(value), int((abs(value) - int(value)) * 60)
        return float(degrees), float(minutes), round((value - degrees - minutes / 60) * 3600, 4)

    exif = Image.Exif()
    exif[0x8825] = {1: "N" if lat >= 0 else "S", 2: dms(lat), 3: "E" if lon >= 0 else "W", 4: dms(lon)}
    buffer = io.BytesIO()
    Image.open(io.BytesIO(PLAN)).convert("RGB").save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def post(api, files: list[tuple[str, bytes]], **fields: object) -> dict:
    data = {key: json.dumps(value) for key, value in fields.items()}
    response = api.post("/imports/stream", files=[("files", item) for item in files], data=data)
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()][-1]


def test_photo_gps_reads_exif_and_signs() -> None:
    assert photo_gps(photo(48.1497, 11.5679)) == pytest.approx((48.1497, 11.5679), abs=1e-5)
    assert photo_gps(photo(-33.86, -151.2)) == pytest.approx((-33.86, -151.2), abs=1e-5)
    assert photo_gps(PLAN) is None  # a PNG without EXIF


def test_median_gps_ignores_photos_without_one() -> None:
    files = [photo(48.0, 11.0), photo(48.2, 11.2), photo(48.1, 11.1), PLAN]
    assert median_gps(files) == (pytest.approx(48.1), pytest.approx(11.1), 3)
    assert median_gps([PLAN]) is None


def test_no_tap_photos_with_gps_fit_onto_the_building_there(api, monkeypatch) -> None:
    monkeypatch.setattr(osm_lookup, "building_at", lambda lat, lon: {"ring": rotated_ring(20.0), "name": "Urban Colab"})
    done = post(api, [("plan.jpg", photo(SPOT["lat"], SPOT["lon"]))])
    assert done["located_by"] == "photos"
    assert done["location"]["bearing"] == pytest.approx(20.0, abs=2.0) and done["location"]["address"] == "Urban Colab"


def test_no_tap_no_building_there_places_a_point(api, monkeypatch) -> None:
    monkeypatch.setattr(osm_lookup, "building_at", lambda lat, lon: None)
    done = post(api, [("plan.jpg", photo(SPOT["lat"], SPOT["lon"]))])
    assert done["location"]["fit"] is None and done["located_by"] == "photos"


def test_browser_position_when_the_photos_have_none(api, monkeypatch) -> None:
    monkeypatch.setattr(osm_lookup, "building_at", lambda lat, lon: None)
    done = post(api, [("plan.png", PLAN)], device={"lat": SPOT["lat"], "lon": SPOT["lon"]})
    assert done["located_by"] == "device" and done["location"] is not None


def test_nothing_known_stays_unplaced(api) -> None:
    done = post(api, [("plan.png", PLAN)])
    assert done["location"] is None and done["located_by"] is None


def test_tapped_building_far_from_the_photos_gets_a_suggestion(api, monkeypatch) -> None:
    other = {"ring": [[FAR["lon"] - 0.0001, FAR["lat"] - 0.0001], [FAR["lon"] + 0.0001, FAR["lat"] - 0.0001],
                      [FAR["lon"] + 0.0001, FAR["lat"] + 0.0001], [FAR["lon"] - 0.0001, FAR["lat"] - 0.0001]],
             "name": "Other house"}
    monkeypatch.setattr(osm_lookup, "building_at", lambda lat, lon: other)
    done = post(api, [("plan.jpg", photo(FAR["lat"], FAR["lon"]))], place={"ring": rotated_ring(0.0)})
    assert done["suggestion"]["name"] == "Other house" and done["suggestion"]["ring"] == other["ring"]
    assert done["location"]["fit"] is not None  # still placed on the tapped building until the user picks


def test_tapped_building_where_the_photos_were_taken_has_no_suggestion(api, monkeypatch) -> None:
    monkeypatch.setattr(osm_lookup, "building_at", lambda lat, lon: pytest.fail("no lookup needed"))
    done = post(api, [("plan.jpg", photo(SPOT["lat"], SPOT["lon"]))], place={"ring": rotated_ring(0.0)})
    assert done.get("suggestion") is None


def test_fit_a_draft_onto_another_footprint(api) -> None:
    done = imported(api, {"point": [SPOT["lon"], SPOT["lat"]]})
    before = api.get(f"/drafts/{done['draft_id']}").json()["draft"]["steps"]
    response = api.post(f"/drafts/{done['draft_id']}/fit", json={"ring": rotated_ring(30.0), "name": "Urban Colab"})
    assert response.status_code == 200
    state = response.json()
    assert state["draft"]["steps"] == before + 1
    location = state["building"]["building"]["location"]
    assert location["bearing"] == pytest.approx(30.0, abs=2.0) and location["address"] == "Urban Colab"


def test_building_at_picks_the_way_around_the_point(monkeypatch) -> None:
    lat, lon = SPOT["lat"], SPOT["lon"]
    square = lambda dlat, dlon, size: [{"lat": lat + dlat + y, "lon": lon + dlon + x}
                                        for x, y in ((0, 0), (size, 0), (size, size), (0, size), (0, 0))]
    payload = {"elements": [
        {"type": "way", "id": 1, "tags": {"building": "yes", "name": "Next door"}, "geometry": square(0.0003, 0.0003, 0.0002)},
        {"type": "way", "id": 2, "tags": {"building": "yes", "name": "Here"}, "geometry": square(-0.0001, -0.0001, 0.0002)},
    ]}
    monkeypatch.setattr(osm_lookup, "overpass", lambda query: payload)
    found = osm_lookup.building_at(lat, lon)
    assert found["name"] == "Here" and len(found["ring"]) == 5
