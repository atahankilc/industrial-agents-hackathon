"""Route models and route rules for core/navigation.py — docs/kit/route-model.md, Q-014.

Two route models, chosen per call:
- `kit` (default): `BuildingMap.graph` unchanged — anchor → door straight lines, stairs 12 m per floor, lift
  15 m + 6 m per floor. Reproduces the dataset's warm-up and errand answers to the cm (and their tie-breaking).
- `geodesic`: the organisers' Sunday route-scoring rule as we understand it (UNVERIFIED, Q-014). Inside each space
  the walk goes door to door along the shortest path kept 0.15 m off the walls (core/geodesic.py). The first and
  last space are left / entered at their anchor (representative point) — UNVERIFIED, Q-014 (2). Stairs cost 2 m
  per metre climbed, a lift 15 m + 1 m per metre of height, both from the floors' `elevation_m`; one lift ride may
  span several floors with one wait (stairs still go floor by floor).

The geodesic graph uses the kit graph's node ids (space ids at their anchors, "door:<opening id>", "outside") plus
door–door edges inside a space (edge attribute `space`). `expand` turns such a path back into the kit
representation (door, space, door), so space_path / element_path / directions look the same for both models.

Rules (`RouteRules`, both models; the organisers' route validity checks):
- production bays (factory halls: production, assembly, logistics, warehouse, additive zones, "bay") are
  destinations only — a leg may start or end in one but never pass through it;
- `outside` is never passed through (leaving by one entrance and re-entering by another); it may be a start or end;
- forklift: openings ≥ 3 m wide only (every opening kind), no stairs, walkway-like spaces removed; lifts allowed
  (no width in the data) — UNVERIFIED, Q-014 (4).
Rules are hard filters: no route under them gives `reachable=False` with a reason, never a rule-breaking route."""

import itertools
import math
from dataclasses import dataclass

import networkx as nx

from core.building_map import DOOR_PREFIX, LIFT, OUTSIDE, BuildingMap
from core.geodesic import space_distances

KIT = "kit"
GEODESIC = "geodesic"
MODELS = (KIT, GEODESIC)
STAIRS_COST_PER_M_CLIMBED = 2.0
LIFT_WAIT_COST_M = 15.0
LIFT_COST_PER_M = 1.0
FORKLIFT_MIN_WIDTH_M = 3.0
BAY_WORDS = {"production", "assembly", "logistics", "warehouse", "additive", "manufacturing", "bay", "bays"}
WALKWAY_WORDS = {"walkway", "walkways", "pedestrian", "footpath", "footway", "sidewalk", "gehweg", "fussweg"}


@dataclass(frozen=True)
class RouteRules:
    bays_destination_only: bool = False
    no_outside: bool = False
    forklift: bool = False

    def describe(self) -> list[str]:
        return [
            text
            for active, text in (
                (self.bays_destination_only, "production bays are destinations only"),
                (self.no_outside, "no shortcut outside the building"),
                (self.forklift, f"forklift: openings at least {FORKLIFT_MIN_WIDTH_M:g} m, no stairs, no walkways"),
            )
            if active
        ]


NO_RULES = RouteRules()
SUNDAY_RULES = RouteRules(bays_destination_only=True, no_outside=True)


def words(*texts: str) -> set[str]:
    return {word for text in texts for word in text.lower().replace("_", " ").replace("-", " ").split()}


def is_production_bay(space: dict) -> bool:
    """A factory hall by `type`/`room_type` words (production_zone, assembly_zone, …), or a hall named "… bay"."""
    if space["room_type"] == "lobby":
        return False
    if words(space["type"], space["room_type"]) & BAY_WORDS:
        return True
    return space["type"] == "hall" and bool(words(space["name"]) & BAY_WORDS)


def is_walkway(space: dict) -> bool:
    """A pedestrian walkway by `type`, `room_type` or name (none in the kit data; Sunday may add them)."""
    return bool(words(space["type"], space["room_type"], space["name"]) & WALKWAY_WORDS)


def endpoint_only(view: BuildingMap, rules: RouteRules) -> frozenset[str]:
    """Nodes a leg may start or end at but never pass through."""
    nodes = {OUTSIDE} if rules.no_outside else set()
    if rules.bays_destination_only:
        nodes |= {space_id for space_id, space in view.spaces.items() if is_production_bay(space)}
    return frozenset(nodes)


# ---------- graphs ----------


def route_graph(view: BuildingMap, step_free: bool, model: str = KIT, rules: RouteRules = NO_RULES) -> nx.MultiGraph:
    """The routing graph of `model` with the rules' global filters (forklift). Endpoint-only rules: `leg_graph`."""
    if model not in MODELS:
        raise ValueError(f"Unknown route model '{model}' (use one of {', '.join(MODELS)}).")
    graph = view.graph(step_free) if model == KIT else geodesic_graph(view, step_free)
    if rules.forklift:
        graph.remove_nodes_from(
            [DOOR_PREFIX + o["id"] for o in view.openings.values() if o["width_m"] < FORKLIFT_MIN_WIDTH_M]
            + [space_id for space_id, space in view.spaces.items() if is_walkway(space)]
        )
        stairs = {c["id"] for c in view.connectors.values() if c["kind"] != LIFT}
        graph.remove_edges_from([(u, v, k) for u, v, k, via in graph.edges(keys=True, data="via") if via in stairs])
    return graph


def geodesic_graph(view: BuildingMap, step_free: bool) -> nx.MultiGraph:
    graph = nx.MultiGraph()
    spaces = [space_id for space_id in view.spaces if space_id not in view.closed]
    graph.add_nodes_from(spaces)
    doors: dict[str, list[dict]] = {space_id: [] for space_id in spaces}
    for opening in view.openings.values():
        if opening["id"] in view.closed or (step_free and not opening["step_free"]):
            continue
        for space_id in opening["space_ids"]:
            if space_id == OUTSIDE:
                graph.add_edge(OUTSIDE, DOOR_PREFIX + opening["id"], weight=0.0, via=opening["id"])
            elif space_id in doors:
                doors[space_id].append(opening)
    for space_id, openings in doors.items():
        if not openings:
            continue
        polygon = view.spaces[space_id]["polygon"]
        anchor = view.anchor(space_id)
        points = [anchor, *(tuple(opening["position"]) for opening in openings)]
        matrix = space_distances(polygon, points)
        nodes = [space_id, *(DOOR_PREFIX + opening["id"] for opening in openings)]
        for (i, first), (j, second) in itertools.combinations(enumerate(nodes), 2):
            if i == 0:
                graph.add_edge(first, second, weight=matrix[0][j], via=openings[j - 1]["id"])
            else:
                graph.add_edge(first, second, weight=matrix[i][j], via=None, space=space_id)
    elevations = {floor_id: floor["elevation_m"] for floor_id, floor in view.floors.items()}
    for connector in view.connectors.values():
        if connector["id"] in view.closed or (step_free and not connector["step_free"]):
            continue
        stops = sorted(
            (
                (elevations[floor_id], space_id)
                for floor_id, space_id in zip(connector["floor_ids"], connector["space_ids"], strict=True)
                if space_id in graph and space_id not in view.closed
            ),
        )
        pairs = itertools.combinations(stops, 2) if connector["kind"] == LIFT else itertools.pairwise(stops)
        for (low, low_space), (high, high_space) in pairs:
            graph.add_edge(low_space, high_space, weight=connector_cost(connector, high - low), via=connector["id"])
    return graph


def connector_cost(connector: dict, height_m: float) -> float:
    height_m = abs(height_m)
    if connector["kind"] == LIFT:
        return LIFT_WAIT_COST_M + LIFT_COST_PER_M * height_m
    return STAIRS_COST_PER_M_CLIMBED * height_m


def leg_graph(graph: nx.MultiGraph, endpoints_only: frozenset[str], start: str, end: str) -> nx.MultiGraph:
    """View of `graph` where endpoint-only nodes other than `start`/`end` are gone and can't be crossed inside."""
    if not endpoints_only:
        return graph
    keep = {start, end}
    return nx.subgraph_view(
        graph,
        filter_node=lambda node: node not in endpoints_only or node in keep,
        filter_edge=lambda u, v, k: graph[u][v][k].get("space") not in endpoints_only,
    )


def single_source(
    graph: nx.MultiGraph, endpoints_only: frozenset[str], start: str
) -> dict[str, float]:
    """Route distance from `start` to every node, endpoint-only nodes reached but never passed through."""
    walk = leg_graph(graph, endpoints_only, start, start)
    distances = nx.single_source_dijkstra_path_length(walk, start, weight="weight")
    for node in endpoints_only - {start}:
        if node not in graph:
            continue
        reached = [
            distances[neighbour] + data["weight"]
            for neighbour, edges in graph[node].items()
            if neighbour in distances
            for data in edges.values()
            if data.get("space") not in endpoints_only
        ]
        if reached:
            distances[node] = min(reached)
    return distances


# ---------- paths ----------


def cheapest(graph: nx.MultiGraph, first: str, second: str) -> dict:
    return min(graph[first][second].values(), key=lambda edge: edge["weight"])


def expand(graph: nx.MultiGraph, nodes: list[str]) -> tuple[list[str], nx.MultiGraph]:
    """A Dijkstra node path → (kit-style node path, graph of the hops walked) for space/element paths + directions.

    Kit paths come back unchanged with `graph` itself. In a geodesic path a door–door hop inside space S becomes
    door → S (0 m) → door (the in-space metres), so directions report the walk when leaving S."""
    if not any(cheapest(graph, a, b).get("space") for a, b in itertools.pairwise(nodes)):
        return nodes, graph
    walked = nx.MultiGraph()
    expanded = [nodes[0]]

    def hop(first: str, second: str, weight: float, via: str) -> None:
        walked.add_edge(first, second, weight=weight, via=via)
        expanded.append(second)

    for first, second in itertools.pairwise(nodes):
        edge = cheapest(graph, first, second)
        if edge.get("space"):
            hop(first, edge["space"], 0.0, first.removeprefix(DOOR_PREFIX))
            hop(edge["space"], second, edge["weight"], second.removeprefix(DOOR_PREFIX))
        else:
            hop(first, second, edge["weight"], edge["via"])
    return expanded, walked


def sequence_length(
    view: BuildingMap,
    space_path: list[str],
    *,
    step_free: bool = False,
    model: str = GEODESIC,
    rules: RouteRules = NO_RULES,
) -> float | None:
    """Shortest length of a walk that visits exactly `space_path` in order — how the organisers re-measure an answer.

    Each consecutive pair must be joined by an open opening (an entrance when one side is `outside`) or a stair/lift
    hop, and the walk must obey `rules` (endpoint-only nodes only first or last); otherwise None (scored 0). Door
    choices between the same two spaces are optimised; the first/last space starts/ends at its anchor."""
    graph = route_graph(view, step_free, model, rules)
    blocked = endpoint_only(view, rules) - {space_path[0], space_path[-1]}
    if any(space not in graph or space in blocked for space in space_path):
        return None
    best = {space_path[0]: 0.0}  # entry node into the current space → cost so far
    for index, (here, there) in enumerate(itertools.pairwise(space_path)):
        exits: dict[str, tuple[str, float]] = {}  # entry node into `there` → (exit node of `here`, hop cost)
        for opening in view.openings.values():
            if set(opening["space_ids"]) == {here, there} and DOOR_PREFIX + opening["id"] in graph:
                door = DOOR_PREFIX + opening["id"]
                exits[door] = (door, 0.0)
        hops = [
            edge["weight"]
            for edge in graph.get_edge_data(here, there, default={}).values()
            if edge["via"] in view.connectors
        ]
        if hops:
            exits[there] = (here, min(hops))
        following: dict[str, float] = {}
        for entry, cost in best.items():
            for arrival, (leave, hop) in exits.items():
                inside = inside_cost(graph, here, entry, leave)
                if inside is not None:
                    total = cost + inside + hop
                    if total < following.get(arrival, math.inf):
                        following[arrival] = total
        if not following:
            return None
        best = following
    last = space_path[-1]
    finals = [
        cost + inside
        for entry, cost in best.items()
        if (inside := inside_cost(graph, last, entry, last)) is not None
    ]
    return round(min(finals), 2) if finals else None


def inside_cost(graph: nx.MultiGraph, space: str, entry: str, leave: str) -> float | None:
    """Metres walked inside `space` from `entry` to `leave` (door nodes or the space's own anchor node)."""
    if entry == leave:
        return 0.0
    if space == OUTSIDE:
        return 0.0 if graph.has_node(OUTSIDE) else None
    options = [
        data["weight"]
        for data in graph.get_edge_data(entry, leave, default={}).values()
        if data.get("space") == space or space in (entry, leave)
    ]
    if space not in (entry, leave) and graph.has_edge(entry, space) and graph.has_edge(space, leave):
        options.append(cheapest(graph, entry, space)["weight"] + cheapest(graph, space, leave)["weight"])
    return min(options) if options else None
