"""Read-only Guide tools: overview, search, locate, count, room facts, compute, reachable rooms, solve."""

import copy


from backend.agents.compute import namespace, run_code
from backend.core import navigation
from backend.core.route_query import route_query
from backend.core.route_models import RouteRules
from backend.core.solvers import solve
from backend.core.solvers.geometry import adjacent_floor, centre_3d, polygon
from backend.core.solvers.reachability import is_room, rooms_on_floor
from backend.core.solvers.walls import shared_wall_neighbours

from backend.agents.tools.shared import HERE, MAX_RESULTS, UNALIGNED_SOURCES



class LookupTools:
    def tool_building_overview(self) -> dict:
        overview = self.building.overview()
        overview["profile"] = self.profile.describe()
        overview["applied_changes"] = [change.summary for change in self.applied]
        return overview

    def tool_search(self, query: str, floor_level: int | None = None) -> dict:
        results = self.building.search(query, floor_level)
        shown = results[:MAX_RESULTS]
        self.highlight([r["id"] for r in shown if r["kind"] == "space"], [r["id"] for r in shown if r["kind"] == "asset"])
        result = {"total": len(results), "results": shown}
        if not results and self.campus is not None and self.campus.neighbours():
            result["hint"] = "Nothing here; search_nearby_buildings looks in the buildings next to this one."
        return result

    def tool_locate(self, query: str, floor_id: str | None = None) -> dict:
        result = navigation.locate(self.building, query, floor_id).to_dict()
        self.highlight([], [hit["asset_id"] for hit in result.get("assets") or []])
        if not result.get("total") and self.campus is not None and self.campus.neighbours():
            result["hint"] = "Nothing here; search_nearby_buildings looks in the buildings next to this one."
        return result

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
        self.highlight([space_id])
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

    def tool_compute(self, code: str) -> dict:
        """Run Python over a copy of the building (the solver agent's sandbox): {"output"} or {"output", "error"}.
        Its route() routes as find_route does — the Guide's rules (production bays destination-only), the user's
        profile and its closures — so code and tools never disagree on whether a route exists."""
        view = copy.deepcopy(self.building)
        scope = namespace(view)

        def place(reference: str) -> list[str]:
            if reference.strip().lower() in HERE:
                return [self.resolve(reference)]
            return scope["place"](reference) or [view.resolve_space(reference)]

        def route(start: str, destination: str, stops: list[str] | tuple[str, ...] = (), step_free: bool | None = None,
                  forklift: bool | None = None, min_width: float | None = None,
                  closed: list[str] | tuple[str, ...] = ()) -> dict:
            rules = self.route_rules()
            if forklift is not None:
                rules = RouteRules(bays_destination_only=rules.bays_destination_only, no_outside=rules.no_outside,
                                   forklift=forklift)
            return route_query(view, [place(start), *[place(stop) for stop in stops], place(destination)],
                               step_free=self.profile.step_free if step_free is None else step_free,
                               min_width=min_width, closed=[*self.profile_closures(view), *closed], rules=rules,
                               include_steps=False)

        scope["route"] = route
        return run_code(code, scope)

    def tool_reachable_rooms(self, start: str, floor_id: str | None = None) -> dict:
        """Rooms reachable from `start` under the current profile and changes."""
        start_id = self.resolve(start)
        reached = set(self.space_distances(self.building, start_id))
        rooms = rooms_on_floor(self.building, reached, floor_id) if floor_id else sorted(
            space_id for space_id in reached if is_room(self.building.spaces[space_id]))
        return {"count": len(rooms), "rooms": rooms[:MAX_RESULTS * 4], "profile": self.profile.describe()}

    def tool_solve(self, kind: str, params: dict) -> dict:
        """Run one of the benchmark solvers (areas, largest room, walls, stacking, deliveries, what-ifs...)."""
        return solve(self.building, kind, params).to_dict()
