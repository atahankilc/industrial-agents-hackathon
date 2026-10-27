"""Building changes: propose → confirm → apply, and what a change does to routes and reachable rooms."""

from dataclasses import dataclass, field


from backend.core import navigation, route_models
from backend.core.building_map import BuildingMap, MapError
from backend.core.solvers.reachability import is_room
from backend.core.solvers.routing import with_new_door

from backend.agents.tools.shared import IMPACT_KEYS, MAX_RESULTS


@dataclass
class Change:
    id: str
    action: str  # close | reopen | add_door
    targets: list[str]
    summary: str
    effect: dict = field(default_factory=dict)



class ChangeTools:
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
