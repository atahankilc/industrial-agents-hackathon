"""The Guide agent's tool layer: one building session + Anthropic tool definitions over the deterministic core.

  session = BuildingSession.load(Path("data/dev/proc-campus-dev-000"))
  session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
  client.messages.create(..., tools=TOOL_DEFINITIONS)   # then route every tool_use block to session.call

Every fact the agent states comes from these tools (D-003). The session holds what a conversation accumulates:
the user's routing profile (step-free, minimum door width, no lifts, forklift — docs/product/routing-profiles.md),
the route rules every route obeys (production bays destination-only, no shortcut outside — core/route_models.py,
Q-014) and the route model (kit by default, `route_model = "geodesic"` for the Sunday scoring rule), applied
building changes (closures, new doors), pending changes awaiting the user's confirmation, and UI events
(highlight rooms, draw a route). Changes go through propose → confirm → apply so the agent can show what it
understood before it edits the plan (docs/architecture/ai-agents.md#shared-tool-layer).

Errors are returned as {"error": ...} results instead of raised, so the model can repair a vague place name by
searching or ask the user which of the listed candidates they mean."""

import copy
import itertools
from dataclasses import asdict, dataclass, field
from pathlib import Path

from agent import places
from core.directions import about_m, guidance_steps
from core import navigation, route_models
from core.building_map import LIFT, OUTSIDE, BuildingMap, MapError
from core.route_models import FORKLIFT_MIN_WIDTH_M, KIT, RouteRules
from core.solvers import SOLVERS, solve
from core.solvers.geometry import adjacent_floor, centre_3d, polygon
from core.solvers.reachability import is_room, rooms_on_floor
from core.solvers.routing import with_new_door
from core.solvers.walls import shared_wall_neighbours

MAX_RESULTS = 15
# Kit README: some Swiss Dwellings floors are centred per floor rather than aligned (84 of 108 multi-floor Swiss
# buildings have every floor's space-bbox centre within 2 m of the origin on each axis; 82 with a Euclidean 2 m
# radius), so "directly above/below" is meaningless there.
UNALIGNED_SOURCES = {"swiss_dwellings"}


# Persona presets for set_profile, from the "Profiles per persona" table in docs/product/routing-profiles.md.
# Only presets the graph can honour today (hard filters: step-free, minimum door width, no lifts). "assumed" lists
# values the user did not give, so the Guide can say "I assumed 0.8 m; tell me if yours is wider". "needs" lists
# values that have no default and must be asked (trolley width). `avoid_stairs` is not a separate field: every
# stairs connector in the data is step_free: false, so step_free routing already excludes stairs.
PRESETS: dict[str, dict] = {
    "default": {"values": {"step_free": False, "min_door_width_m": None, "avoid_lifts": False}},
    "wheelchair": {"values": {"step_free": True, "min_door_width_m": 0.8}, "assumed": ["min_door_width_m"]},
    "pram": {"values": {"step_free": True, "min_door_width_m": 0.8}, "assumed": ["min_door_width_m"]},
    "trolley": {"values": {"step_free": True}, "needs": ["min_door_width_m"]},
    "no_lifts": {"values": {"avoid_lifts": True}},
    # Organiser rule (Q-014): forklift aisles and openings >= 3 m only, pedestrian walkways don't count.
    "forklift": {"values": {"step_free": True, "min_door_width_m": FORKLIFT_MIN_WIDTH_M, "forklift": True}},
}
PROFILE_FIELDS = ("step_free", "min_door_width_m", "avoid_lifts", "forklift")


@dataclass
class RoutingProfile:
    step_free: bool = False
    min_door_width_m: float | None = None
    avoid_lifts: bool = False
    forklift: bool = False  # no stairs, openings >= 3 m, no walkway-like spaces (route_models.RouteRules)
    preset: str = "default"  # the last preset applied; explicit fields may refine it
    assumed: list[str] = field(default_factory=list)  # fields set from a preset default, not from the user

    def describe(self) -> str:
        parts = ["step-free" if self.step_free else "stairs allowed"]
        if self.min_door_width_m:
            assumed = " (assumed)" if "min_door_width_m" in self.assumed else ""
            parts.append(f"doors at least {self.min_door_width_m} m wide{assumed}")
        if self.avoid_lifts:
            parts.append("no lifts")
        if self.forklift:
            parts.append("forklift (no stairs, no walkways)")
        return ", ".join(parts)


@dataclass
class Change:
    id: str
    action: str  # close | reopen | add_door
    targets: list[str]
    summary: str
    effect: dict = field(default_factory=dict)


class BuildingSession:
    def __init__(self, building: BuildingMap) -> None:
        # The session owns a private copy: applied changes never leak into other sessions or cached maps.
        self.building = BuildingMap(copy.deepcopy(building.data))
        self.profile = RoutingProfile()
        self.pending: dict[str, Change] = {}
        self.applied: list[Change] = []
        self.snapshots: dict[str, tuple[BuildingMap, BuildingMap]] = {}  # applied change id → (before, after)
        self.events: list[dict] = []
        self.emitting = True  # off while predicting, so hypothetical routes never reach the UI
        self.last_route: dict | None = None
        self.route_model = KIT  # "geodesic" = the Sunday scoring rule (Q-014); kit until the organisers answer
        self._ids = itertools.count(1)

    @classmethod
    def load(cls, directory: Path) -> "BuildingSession":
        return cls(BuildingMap.load(directory))

    # ---------- dispatch ----------

    def call(self, name: str, arguments: dict) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return handler(**arguments)
        except KeyError as error:
            return {"error": str(error.args[0]) if error.args else "Unknown id"}
        except (MapError, ValueError, TypeError) as error:
            return {"error": str(error)}

    # ---------- profile → routing constraints ----------

    def profile_closures(self, building: BuildingMap | None = None) -> list[str]:
        """Openings narrower than the profile's minimum width and lifts (if avoided) act as closed."""
        building = building or self.building
        closed = []
        if self.profile.min_door_width_m:
            closed += [
                opening["id"]
                for opening in building.openings.values()
                if opening["width_m"] < self.profile.min_door_width_m
            ]
        if self.profile.avoid_lifts:
            closed += [c["id"] for c in building.connectors.values() if c["kind"] == LIFT]
        return closed

    def route_rules(self) -> RouteRules:
        """Rules every Guide route obeys; the forklift rule follows the profile."""
        return RouteRules(bays_destination_only=True, no_outside=True, forklift=self.profile.forklift)

    def space_summary(self, space_id: str) -> dict:
        space = self.building.spaces[space_id]
        return {
            "id": space_id,
            "name": space["name"],
            "ref": space.get("ref"),
            "room_type": space["room_type"],
            "floor": self.building.floor_name(space["floor_id"]),
        }

    def resolve(self, reference: str) -> str:
        """One space id for a phrase, else MapError listing the candidates or near-miss names (agent/places.py)."""
        found = places.candidates(self.building, reference)
        if len(found) != 1:
            raise MapError(places.problem(self.building, reference, found))
        return found[0]

    def stop(self, reference: str) -> str:
        return OUTSIDE if reference == OUTSIDE else self.resolve(reference)

    def destination_options(self, start: str, destination: str, via: list[str]) -> dict | None:
        """A destination phrase that fits several spaces: the route length to each, shortest first (D-012)."""
        found = places.candidates(self.building, destination)
        if not 1 < len(found) <= places.MAX_OPTIONS:
            return None
        options = []
        for space_id in found:
            route = navigation.find_route(self.building, start, space_id, step_free=self.profile.step_free,
                                          closed=self.profile_closures(), via=via, model=self.route_model,
                                          rules=self.route_rules()).to_dict()
            options.append({**self.space_summary(space_id),
                            "length_m": route["length_m"] if route.get("reachable") else None})
        options.sort(key=lambda option: (option["length_m"] is None, option["length_m"] or 0.0))
        extras = {option["id"]: f"{option['length_m']} m" if option["length_m"] is not None else "unreachable"
                  for option in options}
        return {"error": places.problem(self.building, destination, [o["id"] for o in options], extras),
                "options": options}

    # ---------- read-only tools ----------

    def tool_building_overview(self) -> dict:
        overview = self.building.overview()
        overview["profile"] = self.profile.describe()
        overview["applied_changes"] = [change.summary for change in self.applied]
        return overview

    def tool_search(self, query: str, floor_level: int | None = None) -> dict:
        results = self.building.search(query, floor_level)
        return {"total": len(results), "results": results[:MAX_RESULTS]}

    def tool_locate(self, query: str, floor_id: str | None = None) -> dict:
        return navigation.locate(self.building, query, floor_id).to_dict()

    def tool_count_assets(self, asset_type: str, floor_id: str | None = None) -> dict:
        resolved = navigation.resolve_asset_type(self.building, asset_type)
        if resolved is None:
            return {"error": f"No asset type matches '{asset_type}'"}
        return navigation.count_assets(self.building, resolved, floor_id).to_dict()

    def tool_room_facts(self, space: str) -> dict:
        space_id = self.resolve(space)
        record = self.building.spaces[space_id]
        x, y, z = centre_3d(self.building, space_id)
        stacked: dict = {}
        if self.building.data["building"]["source"] in UNALIGNED_SOURCES:
            stacked["note"] = "floors of this building are not aligned in the data, so rooms above/below are unknown"
        for direction in ("above", "below") if not stacked else ():
            if adjacent_floor(self.building, record["floor_id"], direction) is not None:
                stacked[direction] = self.space_summary(solve(self.building, "room_stacked", {
                    "start": space_id, "direction": direction}).value)
        doors = [
            {
                "id": opening["id"],
                "kind": opening["kind"],
                "to": opening["space_ids"][1] if opening["space_ids"][0] == space_id else opening["space_ids"][0],
                "width_m": opening["width_m"],
                "step_free": opening["step_free"],
            }
            for opening in self.building.openings.values()
            if space_id in opening["space_ids"]
        ]
        self.events.append({"type": "highlight", "space_ids": [space_id]})
        return {
            **self.space_summary(space_id),
            "area_m2": round(polygon(record).area, 2),
            "centre": [round(x, 2), round(y, 2), round(z, 2)],
            "shared_walls": [
                {"id": item["id"], "name": item["name"], "shared_m": item["shared_m"]}
                for item in shared_wall_neighbours(self.building, space_id)
            ],
            "doors": doors,
            "stacked": stacked,
            "assets": [
                asset["name"] for asset in self.building.assets.values() if asset["space_id"] == space_id
            ][:MAX_RESULTS],
        }

    def tool_find_route(self, start: str, destination: str, via: list[str] | None = None) -> dict:
        start, via = self.stop(start), [self.stop(item) for item in via or ()]
        if destination != OUTSIDE and (options := self.destination_options(start, destination, via)):
            return options
        destination = self.stop(destination)
        route = navigation.find_route(
            self.building,
            start,
            destination,
            step_free=self.profile.step_free,
            closed=self.profile_closures(),
            via=via or (),
            model=self.route_model,
            rules=self.route_rules(),
        ).to_dict()
        route["profile"] = self.profile.describe()
        self.guide_steps(route)
        if route.get("reachable") and self.emitting:
            self.last_route = {"start": start, "destination": destination, "via": via or []}
            self.events.append({"type": "route", "space_path": route["space_path"],
                                "element_path": route["element_path"], "length_m": route["length_m"],
                                "profile": route["profile"]})
        return route

    def tool_tour(self, stops: list[str]) -> dict:
        tour = navigation.tour(
            self.building, [self.stop(item) for item in stops], step_free=self.profile.step_free,
            closed=self.profile_closures(), model=self.route_model, rules=self.route_rules(),
        ).to_dict()
        if tour.get("reachable"):
            tour["about_m"] = about_m(tour["length_m"])
            for leg in tour.get("legs") or []:
                self.guide_steps(leg)
        return tour

    def guide_steps(self, route: dict) -> None:
        """Followable steps (turns, landmarks, rounded metres, no ids) instead of the kit's step text, plus the
        rounded total a person would say (`about_m`; `length_m` stays exact)."""
        if route.get("reachable") and route.get("space_path"):
            route["steps"] = guidance_steps(self.building, route["space_path"], route["element_path"])
            route["about_m"] = about_m(route["length_m"])

    def tool_reachable_rooms(self, start: str, floor_id: str | None = None) -> dict:
        """Rooms reachable from `start` under the current profile and changes."""
        start_id = self.resolve(start)
        reached = set(self.space_distances(self.building, start_id))
        rooms = rooms_on_floor(self.building, reached, floor_id) if floor_id else sorted(
            space_id for space_id in reached if is_room(self.building.spaces[space_id]))
        return {"count": len(rooms), "rooms": rooms[:MAX_RESULTS * 4], "profile": self.profile.describe()}

    def tool_solve(self, kind: str, params: dict) -> dict:
        """Run one of the benchmark solvers (areas, largest room, walls, stacking, deliveries, what-ifs...)."""
        result = solve(self.building, kind, params)
        return {"value": result.value, "unit": result.unit, "area_m2": result.area_m2,
                "explanation": result.explanation, "evidence": result.evidence}

    # ---------- profile ----------

    def tool_set_profile(
        self, preset: str | None = None, step_free: bool | None = None, min_door_width_m: float | None = None,
        avoid_lifts: bool | None = None, forklift: bool | None = None,
    ) -> dict:
        """Apply a persona preset (its fields only; others are kept), then explicit fields, which override it.
        preset "default" resets everything. The result says what changed and which values are assumed."""
        if preset is not None and preset not in PRESETS:
            raise ValueError(f"Unknown preset '{preset}'; use one of {', '.join(PRESETS)}")
        if min_door_width_m is not None and min_door_width_m < 0:
            raise ValueError("min_door_width_m must be ≥ 0 (0 clears it)")
        before = {name: getattr(self.profile, name) for name in PROFILE_FIELDS}
        needs: list[str] = []
        if preset == "default":
            self.profile = RoutingProfile()
        elif preset is not None:
            spec = PRESETS[preset]
            for name, value in spec["values"].items():
                setattr(self.profile, name, value)
                if name in self.profile.assumed:
                    self.profile.assumed.remove(name)
            self.profile.assumed += [name for name in spec.get("assumed", []) if name not in self.profile.assumed]
            self.profile.preset = preset
            needs = [name for name in spec.get("needs", []) if min_door_width_m is None]
        explicit = {"step_free": step_free, "min_door_width_m": min_door_width_m, "avoid_lifts": avoid_lifts,
                    "forklift": forklift}
        for name, value in explicit.items():
            if value is None:
                continue
            setattr(self.profile, name, (value or None) if name == "min_door_width_m" else value)
            if name in self.profile.assumed:
                self.profile.assumed.remove(name)
        changed = {name: getattr(self.profile, name) for name in PROFILE_FIELDS
                   if getattr(self.profile, name) != before[name]}
        result = {"profile": asdict(self.profile), "summary": self.profile.describe(), "changed": changed,
                  "assumed": list(self.profile.assumed)}
        if preset is not None:
            result["preset"] = preset
        if needs:
            result["needs"] = needs  # ask the user, e.g. how wide the trolley is
        return result

    # ---------- changes: propose → confirm → apply ----------

    def tool_propose_change(self, action: str, targets: list[str]) -> dict:
        if action in ("close", "reopen"):
            element_ids = [self.building.find_element(target) for target in targets]
            summary = f"{action} " + ", ".join(self.element_name(element) for element in element_ids)
            change = Change(f"C{next(self._ids)}", action, element_ids, summary)
        elif action == "add_door":
            if len(targets) != 2:
                return {"error": "add_door needs exactly two spaces"}
            first, second = (self.resolve(target) for target in targets)
            _, opening = with_new_door(self.building, first, second)
            summary = f"add a door between {self.building.describe_space(first)} and " \
                f"{self.building.describe_space(second)}"
            change = Change(f"C{next(self._ids)}", action, [first, second], summary,
                            {"door_position": opening["position"]})
        else:
            return {"error": "action must be close, reopen or add_door"}
        change.effect.update(self.predict(change))
        self.pending[change.id] = change
        try:
            comparison, _ = self.comparison(change.id)
            change.effect.update({key: comparison[key] for key in IMPACT_KEYS})
        except MapError:  # no last route and no entrance to compare from: the route prediction is all we have
            pass
        return {"change_id": change.id, "summary": summary, "effect": change.effect, "needs_confirmation": True}

    def tool_apply_change(self, change_id: str) -> dict:
        change = self.pending.pop(change_id, None)
        if change is None:
            return {"error": f"No pending change '{change_id}'; pending: {sorted(self.pending) or 'none'}"}
        before = self.building
        self.building = self.changed_building(change)
        self.snapshots[change.id] = (before, self.building)
        self.applied.append(change)
        self.events.append({"type": "change", "summary": change.summary, "targets": change.targets})
        return {"applied": change.summary, "applied_changes": [item.summary for item in self.applied]}

    def changed_building(self, change: Change) -> BuildingMap:
        if change.action == "add_door":
            changed, opening = with_new_door(self.building, *change.targets)
            opening["id"] = f"{opening['floor_id']}-O-new{len(self.applied) + 1}"
            changed.openings = {item["id"]: item for item in changed.data["openings"]}
            return changed
        changed = BuildingMap(self.building.data)
        changed.closed = set(self.building.closed)
        if change.action == "close":
            changed.closed |= set(change.targets)
        else:
            changed.closed -= set(change.targets)
        return changed

    def predict(self, change: Change) -> dict:
        """Effect of a change on the last route the user asked for (before → after), without applying it."""
        if self.last_route is None:
            return {}
        return self.predict_between(self.building, self.changed_building(change))

    def tool_compare_routes(self, change_id: str, start: str | None = None) -> dict:
        """Before → after a pending or applied change, from `start` under the user's profile: rooms that lost (or
        gained) access and the routes that got longer, in route-model metres."""
        result, lost = self.comparison(change_id, start)
        if lost:
            self.events.append({"type": "highlight", "space_ids": lost, "style": "lost_access"})
        return result

    def comparison(self, change_id: str, start: str | None = None) -> tuple[dict, list[str]]:
        """compare_routes without UI events: (result, ids of rooms that lost access)."""
        if change_id in self.pending:
            before, after = self.building, self.changed_building(self.pending[change_id])
            status = "pending"
        elif change_id in self.snapshots:
            before, after = self.snapshots[change_id]
            status = "applied"
        else:
            known = sorted(self.pending) + [change.id for change in self.applied]
            return {"error": f"No pending or applied change '{change_id}'; known: {known or 'none'}"}, []
        if start is None:
            start = self.last_route["start"] if self.last_route else self.main_entrance_space()
        start_id = self.resolve(start)
        old, new = self.room_distances(before, start_id), self.room_distances(after, start_id)
        longer = sorted(
            (
                {"room": self.space_summary(room)["name"], "id": room, "floor": self.space_summary(room)["floor"],
                 "before_m": round(old[room], 2), "after_m": round(new[room], 2),
                 "extra_m": round(new[room] - old[room], 2)}
                for room in old.keys() & new.keys()
                if new[room] - old[room] > 0.005
            ),
            key=lambda item: (-item["extra_m"], item["id"]),
        )
        lost = sorted(old.keys() - new.keys())
        gained = sorted(new.keys() - old.keys())
        result = {
            "change": (self.pending.get(change_id) or next(c for c in self.applied if c.id == change_id)).summary,
            "status": status,
            "from": self.building.describe_space(start_id),
            "profile": self.profile.describe(),
            "reachable_rooms_before": len(old),
            "reachable_rooms_after": len(new),
            "lost_access_count": len(lost),
            "lost_access_by_floor": self.names_by_floor(lost),
            "gained_access_count": len(gained),
            "longer_routes_count": len(longer),
            "max_extra_m": longer[0]["extra_m"] if longer else 0.0,
            "longer_routes": longer[:MAX_RESULTS],
        }
        if self.last_route and start == self.last_route["start"]:
            result["last_route"] = self.predict_between(before, after)
        return result, lost

    def names_by_floor(self, space_ids: list[str]) -> dict[str, dict]:
        """Floor name → {"count", "rooms": names}, floors bottom-up: complete, compact, counts from code."""
        grouped: dict[str, dict] = {}
        for floor in sorted(self.building.floors.values(), key=lambda floor: floor["level"]):
            names = sorted(self.building.spaces[space]["name"] for space in space_ids
                           if self.building.spaces[space]["floor_id"] == floor["id"])
            if names:
                grouped[floor["name"]] = {"count": len(names), "rooms": names}
        return grouped

    def space_distances(self, building: BuildingMap, start_id: str) -> dict[str, float]:
        """Route-model metres from `start_id` to every reachable space under the profile and rules in `building`."""
        view = navigation.routing_view(building, self.profile_closures(building))
        rules = self.route_rules()
        graph = route_models.route_graph(view, self.profile.step_free, self.route_model, rules)
        if start_id not in graph:
            return {}
        lengths = route_models.single_source(graph, route_models.endpoint_only(view, rules), start_id)
        return {node: length for node, length in lengths.items() if node in building.spaces}

    def room_distances(self, building: BuildingMap, start_id: str) -> dict[str, float]:
        """Route-model metres from `start_id` to every reachable room under the profile in `building`."""
        return {
            node: length for node, length in self.space_distances(building, start_id).items()
            if is_room(building.spaces[node])
        }

    def predict_between(self, before: BuildingMap, after: BuildingMap) -> dict:
        """The last route on `before` and on `after`; emits no events and keeps the session's last route."""
        current, last = self.building, self.last_route
        self.emitting = False
        try:
            self.building = before
            old = self.tool_find_route(**last)
            self.building = after
            new = self.tool_find_route(**last)
        finally:
            self.building, self.emitting = current, True
        effect = {"last_route": f"{last['start']} → {last['destination']}", "before_m": old.get("length_m"),
                  "after_m": new.get("length_m"), "still_reachable": new.get("reachable", False)}
        if effect["before_m"] is not None and effect["after_m"] is not None:
            effect["extra_m"] = round(effect["after_m"] - effect["before_m"], 2)
        return effect

    def main_entrance_space(self) -> str:
        entrances = [o for o in self.building.openings.values() if o["kind"] == "entrance"]
        entrances.sort(key=lambda o: (not o["step_free"], o["id"]))
        if not entrances:
            raise MapError("The building has no entrance; give a start place.")
        return next(space for space in entrances[0]["space_ids"] if space in self.building.spaces)

    def element_name(self, element_id: str) -> str:
        if element_id in self.building.connectors:
            return self.building.connectors[element_id]["name"]
        if element_id in self.building.spaces:
            return self.building.describe_space(element_id)
        return f"opening {element_id}"

    # ---------- UI ----------

    def tool_show_on_map(self, space_ids: list[str]) -> dict:
        resolved = [self.resolve(item) for item in space_ids]
        self.events.append({"type": "highlight", "space_ids": resolved})
        return {"shown": resolved}


# What propose_change adds from compare_routes, so a proposal already says who loses access and how much longer.
IMPACT_KEYS = ("from", "reachable_rooms_before", "reachable_rooms_after", "lost_access_count",
               "lost_access_by_floor", "longer_routes_count", "max_extra_m")
PLACE = {"type": "string", "description": "Space id, room ref, exact room name, or asset name/id"}
TOOL_DEFINITIONS: list[dict] = [
    {"name": "building_overview", "description": "Floors, stairs/lifts, entrances, the user's routing profile and "
     "applied changes. Call once at the start.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "search", "description": "Find spaces and assets whose name, ref or type contains every word.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                      "floor_level": {"type": "integer"}}, "required": ["query"]}},
    {"name": "locate", "description": "Where an item is: asset type (plural ok), name or id → rooms and floors.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                      "floor_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "count_assets", "description": "How many assets of a type, on one floor or the whole building.",
     "input_schema": {"type": "object", "properties": {"asset_type": {"type": "string"},
                      "floor_id": {"type": "string"}}, "required": ["asset_type"]}},
    {"name": "room_facts", "description": "Area, centre, shared walls, doors with widths, rooms above/below "
     "(omitted where floors aren't aligned), items in a room.",
     "input_schema": {"type": "object", "properties": {"space": PLACE}, "required": ["space"]}},
    {"name": "find_route", "description": "Shortest walk under the user's profile and current closures: metres, "
     "rooms passed, followable steps (turns, landmarks, rounded metres) and about_m (the rounded total). Routes never pass through production bays (destinations only) or outside "
     "the building; reachable=false + reason means no route under these rules — tell the user so.", "input_schema": {"type": "object", "properties": {
         "start": PLACE, "destination": PLACE, "via": {"type": "array", "items": PLACE}},
         "required": ["start", "destination"]}},
    {"name": "tour", "description": "Visit several places in the given order.", "input_schema": {
        "type": "object", "properties": {"stops": {"type": "array", "items": PLACE}}, "required": ["stops"]}},
    {"name": "reachable_rooms", "description": "Rooms the user can reach from a place under their profile.",
     "input_schema": {"type": "object", "properties": {"start": PLACE, "floor_id": {"type": "string"}},
                      "required": ["start"]}},
    {"name": "solve", "description": "Exact building analytics. kind ∈ " + ", ".join(sorted(SOLVERS)) + ". params "
     "use ids: floor_area_total/largest_room {floor_id, room_type}; shared_walls_count {start}; room_stacked "
     "{start, direction: above|below}; straight_line_3d {first, second}; wide_delivery_count {start, floor_id, "
     "min_width}; errand {start, asset_type, floor_id, room_type}; what_if_door {first, second, floor_id}; "
     "step_free_reachable_count {closed, start, floor_id}.", "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": sorted(SOLVERS)}, "params": {"type": "object"}},
         "required": ["kind", "params"]}},
    {"name": "set_profile", "description": "Remember the user's mobility constraints for every later route. "
     "preset: wheelchair or pram = step-free + doors ≥ 0.8 m (assumed); trolley = step-free, also give "
     "min_door_width_m (ask if unknown); no_lifts; forklift = openings ≥ 3 m, no stairs, no pedestrian walkways; "
     "default = clear all constraints. A preset changes only its own "
     "fields; explicit fields override it. The result lists assumed values: name them to the user.",
     "input_schema": {"type": "object", "properties": {
         "preset": {"type": "string", "enum": list(PRESETS)}, "step_free": {"type": "boolean"},
         "min_door_width_m": {"type": "number"}, "avoid_lifts": {"type": "boolean"},
         "forklift": {"type": "boolean"}}}},
    {"name": "propose_change", "description": "Prepare (not apply) a building change and predict its effect: the "
     "last route before/after and, from that route's start, rooms that lose access and routes that get longer. "
     "Show the summary to the user and apply only after they confirm.", "input_schema": {
         "type": "object", "properties": {"action": {"type": "string", "enum": ["close", "reopen", "add_door"]},
                                          "targets": {"type": "array", "items": {"type": "string"}}},
         "required": ["action", "targets"]}},
    {"name": "apply_change", "description": "Apply a proposed change the user confirmed.", "input_schema": {
        "type": "object", "properties": {"change_id": {"type": "string"}}, "required": ["change_id"]}},
    {"name": "compare_routes", "description": "Before → after a pending or applied change, from a start place "
     "(default: the last route's start, else the main entrance) under the user's profile: rooms that lost access, "
     "routes that got longer and by how many metres.", "input_schema": {"type": "object", "properties": {
         "change_id": {"type": "string"}, "start": PLACE}, "required": ["change_id"]}},
    {"name": "show_on_map", "description": "Highlight spaces in the user's map view.", "input_schema": {
        "type": "object", "properties": {"space_ids": {"type": "array", "items": PLACE}},
        "required": ["space_ids"]}},
]
