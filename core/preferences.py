"""Route preferences: soft penalties and avoided room types on top of the exact route model
(docs/product/routing-profiles.md "Soft penalties", archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md).

Only for the app's Guide when a user has set a preference; benchmark answers never pass any. The search runs on
the route graph with each edge's metres plus its penalty; the chosen path is then measured on true metres, so a
route answer always reports real lengths ("12 m longer to avoid the canteen"). The start and destination spaces
are never penalised or avoided."""

from dataclasses import dataclass
from typing import Callable

import networkx as nx

from core.building_map import DOOR_PREFIX, LIFT, BuildingMap

# Heuristic from room_type (routing-profiles.md), said to the user as such.
NOISY = frozenset({"lobby", "canteen", "production_zone", "assembly_zone", "additive_zone", "warehouse_zone",
                   "logistics_zone", "shop"})
HALL = "hall"


@dataclass(frozen=True)
class Penalties:
    stairs_per_flight_m: float = 0.0  # prefer lifts (elderly, pregnant)
    door_m: float = 0.0  # per door passed (crutches, low vision)
    noisy_m: float = 0.0  # per noisy space crossed (sensory-sensitive)
    hall_m: float = 0.0  # per hall crossed (low vision: no walls to follow)
    space_change_m: float = 0.0  # per space crossed (first day, simple routes)
    avoid_room_types: frozenset[str] = frozenset()  # hard: never crossed

    def active(self) -> bool:
        return any((self.stairs_per_flight_m, self.door_m, self.noisy_m, self.hall_m, self.space_change_m,
                    self.avoid_room_types))

    def path_only(self, view: BuildingMap, graph: nx.MultiGraph, start: str, end: str,
                  live_extra: Callable[[dict], float] | None = None) -> nx.MultiGraph:
        """The cheapest path under these penalties, as a graph holding only its edges (true metres), so the
        normal shortest-path code on it returns exactly that path with its real length. Empty graph (just the two
        stops) when there is none."""
        exempt = {start, end}

        def cost(edge: dict) -> float | None:
            space_id = edge.get("space")
            extra = 0.0
            if space_id is not None and space_id not in exempt:
                space = view.spaces.get(space_id, {})
                if space.get("room_type") in self.avoid_room_types:
                    return None
                extra += self.space_change_m
                if space.get("room_type") in NOISY:
                    extra += self.noisy_m
                if space.get("type") == HALL:
                    extra += self.hall_m
            via = edge.get("via")
            if via in view.connectors and view.connectors[via]["kind"] != LIFT:
                extra += self.stairs_per_flight_m
            return edge["weight"] + extra + (live_extra(edge) if live_extra else 0.0)  # core/live.py: wait, wet floor

        def weight(first: str, second: str, edges: dict) -> float | None:
            costs = [value for value in (cost(edge) for edge in edges.values()) if value is not None]
            for node in (first, second):  # half a door's penalty on each walk into or out of it
                if node.startswith(DOOR_PREFIX) and self.door_m:
                    opening = view.openings.get(node.removeprefix(DOOR_PREFIX), {})
                    if opening.get("kind") in ("door", "entrance"):
                        costs = [value + self.door_m / 2 for value in costs]
            return min(costs) if costs else None

        path = nx.MultiGraph()
        path.add_nodes_from([start, end])
        try:
            nodes = nx.dijkstra_path(graph, start, end, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return path
        for first, second in zip(nodes, nodes[1:]):
            options = [(cost(edge), key) for key, edge in graph[first][second].items() if cost(edge) is not None]
            _, key = min(options)
            path.add_edge(first, second, **graph[first][second][key])
        return path
