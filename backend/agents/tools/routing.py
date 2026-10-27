"""Routes under the user's profile and the route rules: find_route, find_nearest, tour, reroute."""



from backend.agents import places
from backend.core.directions import about_m, guidance_steps
from backend.core import navigation
from backend.core.building_map import LIFT, OUTSIDE, BuildingMap
from backend.core.route_query import shortlist
from backend.core.route_models import RouteRules




class RoutingTools:
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

    def destination_options(self, start: str, destination: str, via: list[str]) -> dict | None:
        """A destination phrase that fits several spaces: the route length to each, shortest first (D-012). Of many,
        only the ones nearest in a straight line are routed to (backend/core/route_query.shortlist), as find_nearest does."""
        found = places.candidates(self.building, destination)
        if len(found) < 2 or (len(found) > places.MAX_OPTIONS and start == OUTSIDE):
            return None
        routed = shortlist(self.building, start, found) if len(found) > places.MAX_OPTIONS else found
        options = []
        live = self.live_effects()
        for space_id in routed:
            route = navigation.find_route(self.building, start, space_id, step_free=self.profile.step_free,
                                          closed=self.profile_closures(), via=via, model=self.route_model,
                                          rules=self.route_rules(), penalties=self.profile.penalties(),
                                          live=live).to_dict()
            options.append({**self.space_summary(space_id),
                            "length_m": route["length_m"] if route.get("reachable") else None})
        options.sort(key=lambda option: (option["length_m"] is None, option["length_m"] or 0.0))
        self.highlight([option["id"] for option in options])  # the rooms the Guide is about to ask between
        extras = {option["id"]: f"{option['length_m']} m" if option["length_m"] is not None else "unreachable"
                  for option in options}
        return {"error": places.problem(self.building, destination, [o["id"] for o in options], extras, len(found)),
                "options": options}

    def tool_find_route(self, start: str, destination: str, via: list[str] | None = None,
                        closed: list[str] | None = None) -> dict:
        start, via = self.start_of(start), [self.stop(item) for item in via or ()]
        if destination != OUTSIDE and (options := self.destination_options(start, destination, via)):
            return options
        destination = self.stop(destination)
        route = navigation.find_route(
            self.building,
            start,
            destination,
            step_free=self.profile.step_free,
            closed=[*self.profile_closures(), *(closed or [])],
            via=via or (),
            model=self.route_model,
            rules=self.route_rules(),
            penalties=self.profile.penalties(),
            live=self.live_effects(),
        ).to_dict()
        route["profile"] = self.profile.describe()
        self.guide_steps(route)
        if route.get("reachable") and self.emitting:
            self.last_route = {"start": start, "destination": destination, "via": via or [], "closed": closed or []}
            self.events.append({"type": "route", "space_path": route["space_path"],
                                "element_path": route["element_path"], "length_m": route["length_m"],
                                "profile": route["profile"], **self.start_point(start),
                                **({"live": route["live"]} if route.get("live") else {}),
                                "request": self.last_route})
        return route

    def reroute(self, request: dict | None = None) -> dict | None:
        """A route asked for again under what the live things report now: `request` = a route event's
        {"start", "destination", "via", "closed"} (default: the last find_route), from where the user is when the app
        knows it, else from where it started. The route dict, or None without a request. No event is added."""
        request = request or self.last_route
        if request is None:
            return None
        start = (self.user_location or {}).get("space_id") or request["start"]
        if start == request["destination"]:
            start = request["start"]
        return navigation.find_route(
            self.building, start, request["destination"], step_free=self.profile.step_free,
            closed=[*self.profile_closures(), *request.get("closed", [])],
            via=request.get("via") or (), model=self.route_model, rules=self.route_rules(),
            penalties=self.profile.penalties(), live=self.live_effects()).to_dict()

    def tool_find_nearest(self, start: str, query: str, floor_id: str | None = None,
                          closed: list[str] | None = None) -> dict:
        """The nearest room holding `query` (an item kind like "toilet", or a room kind/name) by walking distance
        under the profile: routes to it (one route event, the map shows only that one) and lists the next ones.
        `closed`: closures for this question only (names or ids). Only the 12 candidates nearest in a straight line
        are routed to (backend/core/route_query.shortlist), so big buildings with many matches stay fast."""
        start = self.start_of(start)
        closures = [*self.profile_closures(), *(closed or [])]
        found = navigation.locate(self.building, query, floor_id).to_dict()
        spaces = list(dict.fromkeys(hit["space_id"] for hit in found.get("assets") or []))
        if not spaces:
            spaces = [hit["id"] for hit in self.building.search(query) if hit["kind"] == "space"
                      and floor_id in (None, self.building.spaces[hit["id"]]["floor_id"])]
        spaces = [space for space in spaces if space != start]
        if spaces and start != OUTSIDE:
            spaces = shortlist(self.building, start, spaces)
        if not spaces:
            result = {"error": f"Nothing matching '{query}' in this building."}
            if self.campus is not None and self.campus.neighbours():
                result["hint"] = "search_nearby_buildings looks in the buildings next to this one."
            return result
        ranked = []
        live = self.live_effects()
        for space_id in spaces:
            route = navigation.find_route(self.building, start, space_id, step_free=self.profile.step_free,
                                          closed=closures, model=self.route_model,
                                          rules=self.route_rules(), penalties=self.profile.penalties(),
                                          live=live).to_dict()
            if route.get("reachable"):
                ranked.append((route["length_m"], space_id))
        if not ranked:
            return {"error": f"No room with '{query}' is reachable from here under the current profile.",
                    "profile": self.profile.describe()}
        ranked.sort()
        route = self.tool_find_route(start, ranked[0][1], closed=closed)
        route["nearest"] = self.space_summary(ranked[0][1])
        route["next_nearest"] = [{**self.space_summary(space_id), "about_m": about_m(length)}
                                 for length, space_id in ranked[1:3]]
        self.highlight([ranked[0][1]])
        return route

    def tool_tour(self, stops: list[str]) -> dict:
        tour = navigation.tour(
            self.building, [self.stop(item) for item in stops], step_free=self.profile.step_free,
            closed=self.profile_closures(), model=self.route_model, rules=self.route_rules(),
            penalties=self.profile.penalties(), live=self.live_effects(),
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
