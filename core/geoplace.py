"""A building's real position: its metres ↔ lat/lon with a bearing, and fitting a generated building onto an OSM
footprint (archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md).

Position = `origin` (lat/lon of the building's (0, 0)) + `bearing` (degrees, counter-clockwise from east to the
building's x axis; 0 for every kit building, whose x is east and y north). Local equirectangular projection with
R = 6378137 m, the convention of scripts/fit_locations.py. The building's own coordinates are never rotated (Edit
mode keeps the plan's orientation); a fit's scale is applied to them by the caller (edit op `scale_building`)."""

import math
from dataclasses import asdict, dataclass

from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

R = 6378137.0
SCALE_MIN, SCALE_MAX = 0.75, 1.25  # a fit may correct the import's own scale estimate by at most ±25 %
LOW_IOU = 0.5
WALL_M = 0.25  # exterior walls around the spaces (core/floorplan.py EXTERIOR_M)


def to_lnglat(origin: dict, bearing_deg: float, x: float, y: float) -> tuple[float, float]:
    b = math.radians(bearing_deg)
    east, north = x * math.cos(b) - y * math.sin(b), x * math.sin(b) + y * math.cos(b)
    lat0 = origin["lat"]
    return (origin["lon"] + math.degrees(east / (R * math.cos(math.radians(lat0)))),
            lat0 + math.degrees(north / R))


def to_metres(origin: dict, bearing_deg: float, lon: float, lat: float) -> tuple[float, float]:
    lat0 = origin["lat"]
    east = math.radians(lon - origin["lon"]) * R * math.cos(math.radians(lat0))
    north = math.radians(lat - lat0) * R
    b = math.radians(bearing_deg)
    return east * math.cos(b) + north * math.sin(b), -east * math.sin(b) + north * math.cos(b)


def footprint(building: dict) -> Polygon:
    """The lowest floor's spaces, united, with the exterior walls (the block the map shows)."""
    lowest = min(building["floors"], key=lambda floor: floor["level"])["id"]
    shapes = [Polygon(space["polygon"]).buffer(0) for space in building["spaces"] if space["floor_id"] == lowest]
    shape = unary_union(shapes).buffer(WALL_M, join_style=2)
    return max(shape.geoms, key=lambda part: part.area) if isinstance(shape, MultiPolygon) else shape


@dataclass
class Placement:
    origin: dict
    bearing_deg: float
    scale: float
    iou: float
    low_confidence: bool


def iou(a: Polygon, b: Polygon) -> float:
    union = a.union(b).area
    return a.intersection(b).area / union if union else 0.0


def axis_angle(shape: Polygon) -> float:
    """Direction (degrees) of the longest side of the minimum rotated rectangle."""
    corners = list(shape.minimum_rotated_rectangle.exterior.coords)
    sides = [(corners[i], corners[i + 1]) for i in range(2)]
    (x0, y0), (x1, y1) = max(sides, key=lambda side: math.dist(*side))
    return math.degrees(math.atan2(y1 - y0, x1 - x0))


def placed(shape: Polygon, bearing: float, scale: float, dx: float, dy: float) -> Polygon:
    turned = affinity.rotate(affinity.scale(shape, scale, scale, origin=(0, 0)), bearing, origin=(0, 0))
    return affinity.translate(turned, dx, dy)


def fit_shape(shape: Polygon, target: Polygon, bearings: list[float] | None = None
              ) -> tuple[float, float, float, float, float]:
    """(bearing °, scale, dx, dy, IoU) that lay `shape` best onto `target` (both in metres; scale clamped).
    `bearings`: the only turns allowed (e.g. the quarter turns that keep walls parallel); default: any."""
    clamp = lambda value: min(SCALE_MAX, max(SCALE_MIN, value))
    start_scale = clamp(math.sqrt(target.area / shape.area))
    best = None
    starts = bearings if bearings is not None else [axis_angle(target) - axis_angle(shape) + 90 * turn for turn in range(4)]
    for bearing in starts:  # the principal axes agree up to a quarter turn
        moved = placed(shape, bearing, start_scale, 0, 0)
        dx, dy = target.centroid.x - moved.centroid.x, target.centroid.y - moved.centroid.y
        candidate = [bearing, start_scale, dx, dy]
        score = iou(placed(shape, *candidate), target)
        if best is None or score > best[1]:
            best = (candidate, score)
    params, score = best
    steps = [0.0 if bearings is not None else 5.0, 0.05, 2.0, 2.0]  # bearing °, scale, dx m, dy m
    while steps[2] > 0.02:
        improved = True
        while improved:
            improved = False
            for index in range(4):
                if not steps[index]:
                    continue
                for sign in (1, -1):
                    trial = list(params)
                    trial[index] += sign * steps[index]
                    trial[1] = clamp(trial[1])
                    trial_score = iou(placed(shape, *trial), target)
                    if trial_score > score + 1e-9:
                        params, score, improved = trial, trial_score, True
        steps = [step / 2 for step in steps]
    bearing, scale, dx, dy = params
    return bearing, scale, dx, dy, score


def fit(building: dict, ring: list[list[float]]) -> Placement:
    """Shift, bearing and (bounded) scale that lay the building's footprint best onto an OSM ring ([lon, lat])."""
    lons, lats = [point[0] for point in ring], [point[1] for point in ring]
    centre = {"lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons)}
    target = Polygon([to_metres(centre, 0.0, lon, lat) for lon, lat in ring]).buffer(0)
    bearing, scale, dx, dy, score = fit_shape(footprint(building), target)
    origin_lon, origin_lat = to_lnglat(centre, 0.0, dx, dy)  # where the building's (0, 0) lands
    at_bound = math.isclose(scale, SCALE_MIN) or math.isclose(scale, SCALE_MAX)
    return Placement({"lat": origin_lat, "lon": origin_lon}, bearing % 360, scale, score, score < LOW_IOU or at_bound)


def location_for(building: dict, placement: Placement, address: str | None = None) -> dict:
    """`building.location` in the shape of a backend/locations.json entry, plus `bearing` and the fit's numbers."""
    shape = affinity.scale(footprint(building), placement.scale, placement.scale, origin=(0, 0))
    outline = [[list(to_lnglat(placement.origin, placement.bearing_deg, x, y)) for x, y in shape.exterior.coords]]
    centre_lon, centre_lat = to_lnglat(placement.origin, placement.bearing_deg, shape.centroid.x, shape.centroid.y)
    tops = [floor["elevation_m"] + floor["height_m"] for floor in building["floors"]]
    bottom = min(floor["elevation_m"] for floor in building["floors"])
    fitted = asdict(placement)
    return {"lat": centre_lat, "lon": centre_lon, "address": address, "origin": placement.origin,
            "bearing": placement.bearing_deg, "outline": outline, "height_m": round(max(tops) - bottom, 2),
            "fit": {key: fitted[key] for key in ("scale", "iou", "low_confidence")}}


def placement_ops(building: dict, ring: list[list[float]] | None = None, point: list[float] | None = None,
                  address: str | None = None) -> list[dict]:
    """The draft ops that place `building` on the map: fitted onto an OSM `ring` (`scale_building` for the fit's scale,
    then `set_location`), or centred on a `point` ([lon, lat]) with bearing 0 and no fit."""
    from core.edits import apply_op  # core.edits does not import this module; keep it that way

    if ring is not None:
        placement = fit(building, ring)
        ops = [] if math.isclose(placement.scale, 1.0) else [{"op": "scale_building", "factor": placement.scale}]
        scaled = apply_op(building, ops[0]) if ops else building
        location = location_for(scaled, Placement(placement.origin, placement.bearing_deg, 1.0, placement.iou,
                                                  placement.low_confidence), address=address)
        location["fit"]["scale"] = placement.scale
        return [*ops, {"op": "set_location", "location": location}]
    centre = footprint(building).centroid
    lon, lat = to_lnglat({"lat": point[1], "lon": point[0]}, 0.0, -centre.x, -centre.y)
    location = location_for(building, Placement({"lat": lat, "lon": lon}, 0.0, 1.0, 0.0, False), address=address)
    location["fit"] = None
    return [{"op": "set_location", "location": location}]


def place(building: dict, ring: list[list[float]] | None = None, point: list[float] | None = None,
          address: str | None = None) -> dict:
    """A copy of `building` placed on the map (`placement_ops` applied)."""
    from core.edits import apply_op

    for operation in placement_ops(building, ring, point, address):
        building = apply_op(building, operation)
    return building


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metres between two (lat, lon) points (local projection, fine for a few km)."""
    x, y = to_metres({"lat": a[0], "lon": a[1]}, 0.0, b[1], b[0])
    return math.hypot(x, y)
