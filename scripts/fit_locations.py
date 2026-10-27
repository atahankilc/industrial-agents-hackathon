"""Fit the kit's OSM buildings onto their OpenStreetMap ways and write the map fields of backend/api/locations.json.

For each `osm-way<id>` in locations.json: fetch the way from the OSM API (cached in .cache/osm/), shift the kit
footprint (ground floor spaces + 0.25 m exterior walls) to the overlap maximum with the way and move `origin` (kit
(0, 0)) by that shift, then rewrite `outline` (all floors, outset 0.6 m) and `height_m` from the kit. Where the kit
footprint is about the size of the way (area ratio >= 0.75) the shift maximises IoU; where the kit models only part
of the building, IoU would drag it to the way's middle, so the shift is the smallest that brings the kit inside the
way (e.g. Mensa: its north wing stuck ~7 m out of the way). A rotation search changed nothing (<= 0.05 IoU), so the
fit is translation only. `lat`/`lon` (the pin, the outline's centre in OSM) are not touched.
Run from the repo root: uv run python scripts/fit_locations.py"""

import json
import math
import time
import urllib.request
from pathlib import Path

from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
LOCATIONS = ROOT / "backend" / "locations.json"
CACHE = ROOT / ".cache" / "osm"
R = 6378137.0
MIN_RATIO = 0.75  # kit footprint area / OSM way area below which the kit is a part of the building: fit inside
OUTSET_M = 0.6  # exterior walls (backend/core/floorplan.py EXTERIOR_M 0.25) plus a margin, so the map block wraps the OSM one


def way(key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{key}.json"
    if not cached.exists():
        url = f"https://api.openstreetmap.org/api/0.6/way/{key.removeprefix('osm-way')}/full.json"
        request = urllib.request.Request(url, headers={"User-Agent": "steward/0.1"})
        with urllib.request.urlopen(request, timeout=30) as response:
            cached.write_bytes(response.read())
        time.sleep(1)  # OSM API usage policy
    return json.loads(cached.read_text())


def footprint(building: dict, floors: set[str], outset: float):
    spaces = [Polygon(s["polygon"]).buffer(0) for s in building["spaces"] if s["floor_id"] in floors and len(s["polygon"]) >= 3]
    return unary_union(spaces).buffer(0.5).buffer(-0.5).buffer(outset, join_style=2)


def best_shift(kit, osm) -> tuple[float, float, float]:
    """(IoU, dx, dy): coarse-to-fine grid over ±20 m."""
    iou = lambda shape: shape.intersection(osm).area / shape.union(osm).area
    best = (iou(kit), 0.0, 0.0)
    for step, span in [(2.0, 20.0), (0.5, 2.0), (0.1, 0.5)]:
        _, bx, by = best
        n = int(span / step)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                dx, dy = bx + i * step, by + j * step
                score = iou(affinity.translate(kit, dx, dy))
                if score > best[0]:
                    best = (score, dx, dy)
    return best


def smallest_inside(kit, osm) -> tuple[float, float, float]:
    """(share of the kit inside the way, dx, dy): the smallest shift over ±20 m (0.5 m grid) within 0.5 % of the
    best share, so a partial model moves only as far as it must."""
    inside = lambda dx, dy: affinity.translate(kit, dx, dy).intersection(osm).area / kit.area
    shifts = [(i * 0.5, j * 0.5) for i in range(-40, 41) for j in range(-40, 41)]
    shares = {shift: inside(*shift) for shift in shifts}
    top = max(shares.values())
    dx, dy = min((s for s in shifts if shares[s] >= top - 0.005), key=lambda s: math.hypot(*s))
    return shares[(dx, dy)], dx, dy


def main() -> None:
    document = json.loads(LOCATIONS.read_text(encoding="utf-8"))
    paths = {f.parent.name: f for f in (ROOT / "data" / "buildings").glob("*/building.json")}
    for key, entry in document["buildings"].items():
        building = json.loads(paths[key].read_text(encoding="utf-8"))
        lat0, lon0 = entry["origin"]["lat"], entry["origin"]["lon"]
        to_m = lambda lat, lon: (math.radians(lon - lon0) * R * math.cos(math.radians(lat0)), math.radians(lat - lat0) * R)
        data = way(key)
        nodes = {e["id"]: e for e in data["elements"] if e["type"] == "node"}
        ring = next(e for e in data["elements"] if e["type"] == "way")["nodes"]
        osm = Polygon([to_m(nodes[n]["lat"], nodes[n]["lon"]) for n in ring]).buffer(0)
        ground = min(building["floors"], key=lambda f: abs(f["level"]))["id"]
        kit = footprint(building, {ground}, 0.25)
        ratio = kit.area / osm.area
        before = kit.intersection(osm).area / kit.union(osm).area
        score, dx, dy = best_shift(kit, osm) if ratio >= MIN_RATIO else smallest_inside(kit, osm)
        lat0, lon0 = lat0 + math.degrees(dy / R), lon0 + math.degrees(dx / (R * math.cos(math.radians(lat0))))
        entry["origin"] = {"lat": round(lat0, 7), "lon": round(lon0, 7)}
        shape = footprint(building, {f["id"] for f in building["floors"]}, OUTSET_M).simplify(0.3)
        to_lonlat = lambda x, y: [round(lon0 + math.degrees(x / (R * math.cos(math.radians(lat0)))), 7), round(lat0 + math.degrees(y / R), 7)]
        entry["outline"] = [[to_lonlat(x, y) for x, y in part.exterior.coords] for part in getattr(shape, "geoms", [shape]) if part.area > 4]
        floors = building["floors"]
        entry["height_m"] = round(max(f["elevation_m"] + f["height_m"] for f in floors) - min(f["elevation_m"] for f in floors), 1)
        note = f"shift {dx:+.1f} m E {dy:+.1f} m N" if (dx or dy) else "kept"
        fit = "IoU" if ratio >= MIN_RATIO else "inside"
        start = before if ratio >= MIN_RATIO else kit.intersection(osm).area / kit.area
        print(f"{key:18} area ratio {ratio:4.2f}  {fit} {start:.3f} -> {score:.3f}  {note}")
    document["about"] = (
        "Real-world position of the kit's OpenStreetMap buildings. `lat`/`lon`: centre of the OSM outline (the pin). "
        "`origin`: lat/lon of the kit frame's (0, 0) (x metres east, y north), first from the archived twin-lab "
        "georef.py, then shifted onto the OSM way by scripts/fit_locations.py (best overlap; a kit modelling under 75 % of "
        "the way is moved the least that puts it inside). "
        "`outline`: the kit footprint as [lon, lat] rings (spaces of every floor, outset 0.6 m for the exterior walls), "
        "placed by `origin`. `height_m`: lowest floor to the top of the highest in the kit. Other sources have no position."
    )
    LOCATIONS.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
