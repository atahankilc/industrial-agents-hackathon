"""The OpenStreetMap building at a point (Overpass API), for placing an import where its photos were taken
(archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md). Read-only; only the coordinate is sent.
Any network or parse failure returns None — the import is then placed on the point itself."""

import json
import urllib.parse
import urllib.request

from shapely.geometry import Point, Polygon

ENDPOINT = "https://overpass-api.de/api/interpreter"
TIMEOUT_S = 10
RADIUS_M = 40  # photos taken inside a building: phone GPS is often 10–30 m off


def overpass(query: str) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(ENDPOINT, data=data, headers={"User-Agent": "talk-to-your-building/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 (fixed https endpoint)
        return json.loads(response.read())


def building_at(lat: float, lon: float, radius_m: float = RADIUS_M) -> dict | None:
    """{"ring": [[lon, lat], …] closed, "name", "osm_id"} of the building way around the point (else the nearest one
    within `radius_m`), or None."""
    query = f'[out:json][timeout:8];way(around:{radius_m},{lat},{lon})["building"];out geom;'
    try:
        elements = overpass(query).get("elements", [])
    except Exception:  # noqa: BLE001 — offline, rate limited, bad JSON: no building, the point is used
        return None
    here = Point(lon, lat)
    best = None
    for element in elements:
        geometry = element.get("geometry") or []
        ring = [[node["lon"], node["lat"]] for node in geometry]
        if len(ring) < 4:
            continue
        shape = Polygon(ring).buffer(0)
        rank = (0 if shape.contains(here) else 1, shape.distance(here), shape.area)  # inside first, then nearest
        if best is None or rank < best[0]:
            best = (rank, {"ring": ring, "name": (element.get("tags") or {}).get("name"), "osm_id": element.get("id")})
    return best[1] if best else None
