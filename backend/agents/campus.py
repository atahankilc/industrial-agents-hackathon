"""Buildings next to each other: find a place in a neighbouring building and route there.

Only buildings with a real position (backend/api/locations.json: `lat`/`lon` of the pin, `origin` = lat/lon of the
kit frame's (0, 0), x metres east and y north) have neighbours. A route to another building has three parts:
inside this building to its best entrance, outside in a straight line from that entrance to the other building's
best entrance (no street graph: the outdoor metres are a straight-line estimate and are labelled so), and inside
the other building from that entrance. The pair of entrances is the one with the shortest total.

  campus = Campus("osm-way10053349", catalogue)
  campus.search("Mensa")                                   # neighbours with matches, nearest first
  campus.route(session, "Main lobby", "osm-way19183732", "Mensa")

Neighbour buildings are loaded read-only (cached per path) and never edited; the route inside the other building
uses the user's routing profile but none of this session's closures (those belong to this building)."""

import math
from functools import lru_cache
from pathlib import Path

from backend.agents import places
from backend.core import navigation, route_models
from backend.core.geoplace import to_lnglat
from backend.core.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap, MapError
from backend.core.directions import about_m, guidance_steps

EARTH_R = 6378137.0  # the sphere the map projects with (frontend/src/map/bridge.ts)
NEARBY_M = 600  # neighbours: building pins at most this far apart
MAX_NEIGHBOURS = 8
MAX_HITS = 5
COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")


@lru_cache(maxsize=16)
def load_map(path: str) -> BuildingMap:
    return BuildingMap.load(Path(path))


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle metres between two (lon, lat) points."""
    (lon1, lat1), (lon2, lat2) = (map(math.radians, a)), (map(math.radians, b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def heading(a: tuple[float, float], b: tuple[float, float]) -> str:
    """Compass direction from a to b, in eight points."""
    lat = math.radians((a[1] + b[1]) / 2)
    east = math.radians(b[0] - a[0]) * math.cos(lat)
    north = math.radians(b[1] - a[1])
    return COMPASS[round(math.degrees(math.atan2(east, north)) % 360 / 45) % 8]


def lnglat(origin: dict, x: float, y: float, bearing: float = 0.0) -> tuple[float, float]:
    """Building metres → [lon, lat] (backend/core/geoplace.py; `bearing` 0 for kit buildings, x east / y north)."""
    return to_lnglat(origin, bearing, x, y)


class Campus:
    def __init__(self, building_id: str, catalogue: dict[str, dict]) -> None:
        self.building_id = building_id
        self.catalogue = catalogue

    def location(self, building_id: str) -> dict | None:
        entry = self.catalogue.get(building_id)
        return entry.get("location") if entry else None

    def neighbours(self) -> list[dict]:
        """{"building_id", "name", "distance_m"} of the buildings with a model and a position near this one."""
        here = self.location(self.building_id)
        if not here:
            return []
        found = []
        for building_id, entry in self.catalogue.items():
            there = entry.get("location")
            if building_id == self.building_id or not there or "path" not in entry:
                continue
            metres = distance_m((here["lon"], here["lat"]), (there["lon"], there["lat"]))
            if metres <= NEARBY_M:
                found.append({"building_id": building_id, "name": entry.get("name") or building_id,
                              "distance_m": about_m(metres)})
        found.sort(key=lambda item: item["distance_m"])
        return found[:MAX_NEIGHBOURS]

    def building(self, building_id: str) -> BuildingMap:
        entry = self.catalogue.get(building_id)
        if entry is None or "path" not in entry or building_id not in {n["building_id"] for n in self.neighbours()}:
            names = ", ".join(f"{n['name']} ({n['building_id']})" for n in self.neighbours())
            raise MapError(f"'{building_id}' is not a building nearby. Nearby: {names or 'none'}.")
        return load_map(str(entry["path"]))

    def resolve_building(self, reference: str) -> str:
        """A neighbour's id from its id or (part of) its name."""
        wanted = reference.strip().lower()
        nearby = self.neighbours()
        for item in nearby:
            if wanted in (item["building_id"].lower(), item["name"].lower()):
                return item["building_id"]
        partial = [item for item in nearby if wanted and wanted in item["name"].lower()]
        if len(partial) == 1:
            return partial[0]["building_id"]
        names = ", ".join(f"{n['name']} ({n['building_id']})" for n in nearby)
        raise MapError(f"No single nearby building matches '{reference}'. Nearby: {names or 'none'}.")

    def search(self, query: str) -> dict:
        """Matches for `query` in each neighbour, nearest building first; only buildings with a match. A query that
        names the building itself ("the Mensa") matches it as a whole (`building_match`)."""
        buildings = []
        words = [word for word in query.lower().split() if word not in ("the", "building")]
        for item in self.neighbours():
            results = self.building(item["building_id"]).search(query)
            named = bool(words) and all(word in item["name"].lower() for word in words)
            if results or named:
                buildings.append({**item, "building_match": named, "total": len(results),
                                  "results": results[:MAX_HITS]})
        return {"query": query, "searched": len(self.neighbours()), "buildings": buildings}

    def entrances(self, building_id: str, building: BuildingMap, distances: dict[str, float]) -> list[dict]:
        """Open entrances reachable in `distances` (route metres to their door node), with their map position."""
        location = self.location(building_id) or {}
        origin, bearing = location.get("origin"), location.get("bearing", 0.0)
        if not origin:
            return []
        out = []
        for opening in building.openings.values():
            door = DOOR_PREFIX + opening["id"]
            if OUTSIDE in opening["space_ids"] and door in distances and opening.get("position"):
                out.append({"id": opening["id"], "metres": distances[door],
                            "lnglat": lnglat(origin, *opening["position"][:2], bearing=bearing)})
        return out

    def route(self, session: "BuildingSession", start: str, building: str, destination: str) -> dict:  # noqa: F821
        """Inside here → straight across outside → inside there, through the entrance pair with the shortest total."""
        target_id = self.resolve_building(building)
        there = self.building(target_id)
        name = self.catalogue[target_id].get("name") or target_id
        whole = destination.strip().lower() in ("", "entrance", "the entrance", "building", name.lower())
        found = [] if whole else places.candidates(there, destination)
        if not whole and len(found) != 1:
            raise MapError(places.problem(there, destination, found))
        start_id, end_id = session.stop(start), None if whole else found[0]
        rules = session.route_rules()
        step_free = session.profile.step_free

        def reach(building_map: BuildingMap, closed: list[str], origin: str) -> dict[str, float]:
            view = navigation.routing_view(building_map, closed)
            graph = route_models.route_graph(view, step_free, session.route_model, rules)
            return route_models.single_source(graph, route_models.endpoint_only(view, rules), origin)

        here_closed = session.profile_closures()
        there_closed = session.profile_closures(there)
        exits = self.entrances(self.building_id, session.building, reach(session.building, here_closed, start_id))
        # to the building itself: any open entrance will do, each costs nothing inside
        doors = ({DOOR_PREFIX + o["id"]: 0.0 for o in there.openings.values()
                  if OUTSIDE in o["space_ids"] and o["id"] not in there.closed} if end_id is None
                 else reach(there, there_closed, end_id))
        entries = self.entrances(target_id, there, doors)
        if not exits or not entries:
            side = "this building" if not exits else self.catalogue[target_id].get("name") or target_id
            return {"reachable": False, "reason": f"no open entrance reachable in {side} under the user's profile"}
        best = min(((a, b, distance_m(a["lnglat"], b["lnglat"])) for a in exits for b in entries),
                   key=lambda pair: pair[0]["metres"] + pair[2] + pair[1]["metres"])
        exit_door, entry_door, outdoor = best

        entrance_space = next(s for s in there.openings[entry_door["id"]]["space_ids"] if s != OUTSIDE)
        end_id = end_id or entrance_space

        def only(building_map: BuildingMap, keep: str) -> list[str]:
            return [o["id"] for o in building_map.openings.values() if OUTSIDE in o["space_ids"] and o["id"] != keep]

        options = dict(step_free=step_free, model=session.route_model, rules=rules, penalties=session.profile.penalties())
        inside_here = navigation.find_route(session.building, start_id, OUTSIDE,
                                            closed=here_closed + only(session.building, exit_door["id"]),
                                            **options).to_dict()
        inside_there = navigation.find_route(there, OUTSIDE, end_id,
                                             closed=there_closed + only(there, entry_door["id"]), **options).to_dict()
        if not inside_here.get("reachable") or not inside_there.get("reachable"):
            return {"reachable": False, "reason": inside_here.get("reason") or inside_there.get("reason")}
        total = inside_here["length_m"] + outdoor + inside_there["length_m"]
        if session.emitting:
            session.events.append({
                "type": "route", "space_path": inside_here["space_path"], "element_path": inside_here["element_path"],
                "length_m": inside_here["length_m"], "profile": session.profile.describe(),
                **session.start_point(start_id),
                # what the app may ask again when something live blocks the way (backend/api/live/)
                "request": {"start": start_id, "destination": OUTSIDE, "via": [],
                            "closed": here_closed + only(session.building, exit_door["id"])},
                "next_building": {
                    "building": target_id, "name": name, "destination": end_id,
                    "destination_name": there.spaces[end_id]["name"], "entrance": entry_door["id"],
                    "entrance_space": entrance_space, "outdoor_m": about_m(outdoor),
                    "heading": heading(exit_door["lnglat"], entry_door["lnglat"]),
                    "from": list(exit_door["lnglat"]), "to": list(entry_door["lnglat"]),
                },
            })
        return {
            "reachable": True,
            "to_building": name,
            "destination": {"id": end_id, "name": there.spaces[end_id]["name"],
                            "floor": there.floor_name(there.spaces[end_id]["floor_id"])},
            "about_m": about_m(total),
            "profile": session.profile.describe(),
            "inside_here": {"about_m": about_m(inside_here["length_m"]),
                            "steps": guidance_steps(session.building, inside_here["space_path"],
                                                    inside_here["element_path"])},
            "outside": {"about_m": about_m(outdoor), "heading": heading(exit_door["lnglat"], entry_door["lnglat"]),
                        "note": "straight line between the two entrances; the street path may be a little longer"},
            "inside_there": {"about_m": about_m(inside_there["length_m"]),
                             "entrance_into": there.describe_space(entrance_space),
                             "steps": guidance_steps(there, inside_there["space_path"], inside_there["element_path"])},
            "app": "The map shows the way to the exit, with a Continue button. When the user is at the exit or wants "
                   "to go on, call open_nearby_building: the app opens the other building with its part of the route.",
        }


def arrive(session: "BuildingSession", entrance: str, destination: str) -> dict:  # noqa: F821
    """The user came over from a neighbour (route_to_building's Continue): they stand at `entrance` (an opening id
    of this building). Their position becomes the room inside it, and the route from that entrance to
    `destination` is emitted like find_route's, so the map draws it."""
    opening = session.building.openings.get(entrance)
    if opening is None or OUTSIDE not in opening["space_ids"]:
        raise MapError(f"'{entrance}' is not an entrance of this building")
    inside = next(space for space in opening["space_ids"] if space != OUTSIDE)
    session.set_location(inside)
    others = [o["id"] for o in session.building.openings.values() if OUTSIDE in o["space_ids"] and o["id"] != entrance]
    route = navigation.find_route(
        session.building, OUTSIDE, session.stop(destination), step_free=session.profile.step_free,
        closed=session.profile_closures() + others, model=session.route_model, rules=session.route_rules(),
        penalties=session.profile.penalties()).to_dict()
    route["profile"] = session.profile.describe()
    session.guide_steps(route)
    if route.get("reachable") and session.emitting:
        session.events.append({"type": "route", "space_path": route["space_path"],
                               "element_path": route["element_path"], "length_m": route["length_m"],
                               "profile": route["profile"],
                               "request": {"start": OUTSIDE, "destination": route["to_space_id"], "via": [],
                                           "closed": others}})
    return route
