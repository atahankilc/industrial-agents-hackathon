"""core/geoplace.py: building metres ↔ lat/lon with a bearing, and fitting a generated building onto an OSM
footprint (docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md)."""

import math

import pytest
from shapely import affinity
from shapely.geometry import Polygon

from core.geoplace import fit, footprint, location_for, to_lnglat, to_metres

R = 6378137.0
ORIGIN = {"lat": 48.1497, "lon": 11.5679}
L_SHAPE = [[0, 0], [30, 0], [30, 8], [10, 8], [10, 20], [0, 20]]


def building(polygon: list[list[float]] = L_SHAPE) -> dict:
    return {"building": {"id": "b", "name": "B"},
            "floors": [{"id": "b-F0", "level": 0, "elevation_m": 0.0, "height_m": 3.0}],
            "spaces": [{"id": "s1", "floor_id": "b-F0", "polygon": polygon, "type": "room", "room_type": "office",
                        "name": "Room"}],
            "openings": [], "assets": [], "vertical_connectors": []}


def osm_ring(shape: Polygon, bearing: float, scale: float, origin: dict) -> list[list[float]]:
    placed = affinity.rotate(affinity.scale(shape, scale, scale, origin=(0, 0)), bearing, origin=(0, 0))
    return [list(to_lnglat(origin, 0.0, x, y)) for x, y in placed.exterior.coords]


def test_bearing_zero_matches_the_kit_convention() -> None:
    lon, lat = to_lnglat(ORIGIN, 0.0, 10.0, 0.0)
    assert lon == pytest.approx(ORIGIN["lon"] + math.degrees(10 / (R * math.cos(math.radians(ORIGIN["lat"])))))
    assert lat == pytest.approx(ORIGIN["lat"])
    assert to_lnglat(ORIGIN, 0.0, 0.0, 10.0)[1] == pytest.approx(ORIGIN["lat"] + math.degrees(10 / R))


def test_bearing_turns_the_building_counter_clockwise() -> None:
    north = to_lnglat(ORIGIN, 90.0, 10.0, 0.0)  # x axis pointing north
    assert north[0] == pytest.approx(ORIGIN["lon"], abs=1e-9)
    assert north[1] == pytest.approx(ORIGIN["lat"] + math.degrees(10 / R))


def test_round_trip() -> None:
    lon, lat = to_lnglat(ORIGIN, 37.0, 12.5, -4.25)
    assert to_metres(ORIGIN, 37.0, lon, lat) == pytest.approx((12.5, -4.25), abs=1e-3)


def test_fit_recovers_an_l_shaped_building() -> None:
    shape = footprint(building())
    placement = fit(building(), osm_ring(shape, 30.0, 1.1, ORIGIN))
    assert placement.bearing_deg % 360 == pytest.approx(30.0, abs=2.0)
    assert placement.scale == pytest.approx(1.10, abs=0.02)
    assert placement.iou >= 0.95 and not placement.low_confidence


def test_fit_scale_is_bounded() -> None:
    shape = footprint(building())
    placement = fit(building(), osm_ring(shape, 0.0, 1.6, ORIGIN))
    assert placement.scale == pytest.approx(1.25)
    assert placement.low_confidence


def test_poor_overlap_is_flagged() -> None:
    long_thin = [[0, 0], [60, 0], [60, 2], [0, 2]]
    square = Polygon([[0, 0], [20, 0], [20, 20], [0, 20]])
    placement = fit(building(long_thin), osm_ring(square, 0.0, 1.0, ORIGIN))
    assert placement.iou < 0.5 and placement.low_confidence


def test_location_for_places_the_outline_on_the_footprint() -> None:
    shape = footprint(building())
    ring = osm_ring(shape, 30.0, 1.0, ORIGIN)
    placement = fit(building(), ring)
    location = location_for(building(), placement)
    assert location["bearing"] == pytest.approx(placement.bearing_deg)
    assert set(location["origin"]) == {"lat", "lon"} and location["fit"]["iou"] == pytest.approx(placement.iou)
    outline = Polygon([to_metres(ORIGIN, 0.0, lon, lat) for lon, lat in location["outline"][0]])
    target = Polygon([to_metres(ORIGIN, 0.0, lon, lat) for lon, lat in ring])
    assert outline.intersection(target).area / outline.union(target).area >= 0.9
    centre = target.centroid
    assert to_metres(ORIGIN, 0.0, location["lon"], location["lat"]) == pytest.approx((centre.x, centre.y), abs=1.5)
