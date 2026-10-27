"""Live obstacles on top of the exact route model: things that move or are left behind (forklifts, robots, pallets,
carts) and short-lived hazards (a floor a cleaning robot just wet). App only; benchmark answers never pass any.

The route model walks every space door to door (docs/kit/route-model.md). An obstacle does not close a whole space:
it cuts the walks *across* it. A walk inside a space between two of its nodes (the anchor, a door's landing) is cut
when the space's free area — the outline shrunk by half the walker's clearance, minus every footprint grown by the
same — no longer joins the two ends, while it did without the obstacles. So a pallet half-way down a corridor cuts
the corridor between the doors on either side of it, a door just beside it on the near side stays reachable, and in
a wide hall it cuts nothing. A space a route starts or ends in counts as reached from any door whose side is still
free (you can walk in next to the forklift parked inside).

Parked (standing) obstacles cut a walk; moving ones only cost a wait (they drive on). A walk that is still possible
but passes within `NEAR_M` of a footprint is noted as squeezing past (no penalty); one across a hazard zone (wet floor)
costs `WET_M`. Penalties steer the search; reported lengths stay true metres (backend/core/preferences.py `path_only`)."""

import math
from dataclasses import asdict, dataclass, field
from functools import lru_cache

import networkx as nx
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from backend.core.building_map import DOOR_PREFIX, BuildingMap, door_landing, outline

WALKER_CLEARANCE_M = 0.7  # free width a person on foot needs to pass
WAIT_M = 10.0  # a moving object in the way: about 7 s of waiting, in route metres
SQUEEZE_M = 0.0  # passing right beside an obstacle: said, not avoided (a penalty only makes walks hop door to door)
WET_M = 6.0  # crossing a wet floor
NEAR_M = 0.35  # a walk this close to a footprint squeezes past it
BIG_OUTLINE = 100  # an outline with more corners than this (3 mapped OSM corridors in the dataset) is walked straight, for speed
HAZARD_REACH_M = 3.0  # a walk whose straight line is further than this from a hazard is taken not to cross it
REACH_TOLERANCE_M = 0.05


@lru_cache(maxsize=4096)
def _footprint(x: float, y: float, length_m: float, width_m: float, heading_deg: float) -> Polygon:
    """The rectangle `length_m` along the heading × `width_m` across, centred on (x, y)."""
    radians = math.radians(heading_deg)
    ux, uy = math.cos(radians), math.sin(radians)
    vx, vy = -uy, ux
    half_l, half_w = length_m / 2, width_m / 2
    shape = Polygon([(x + sx * half_l * ux + sy * half_w * vx, y + sx * half_l * uy + sy * half_w * vy)
                     for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))])
    shapely.prepare(shape)
    return shape


@dataclass(frozen=True)
class Obstacle:
    id: str
    name: str
    kind: str  # forklift, agv, cleaning_robot, delivery_robot, pallet, cart, scissor_lift, …
    floor_id: str
    x: float
    y: float
    length_m: float  # along the heading
    width_m: float  # across it
    heading_deg: float = 0.0  # plan frame: degrees from +x, counter-clockwise
    moving: bool = False
    state: str = "parked"

    def footprint(self) -> Polygon:
        return _footprint(self.x, self.y, self.length_m, self.width_m, self.heading_deg)

    def summary(self, building: BuildingMap, space_id: str | None = None) -> dict:
        item = {"id": self.id, "name": self.name, "kind": self.kind, "state": self.state}
        if space_id and space_id in building.spaces:
            item["space"] = building.spaces[space_id]["name"]
        return item


@dataclass(frozen=True)
class Hazard:
    id: str
    name: str
    kind: str  # wet_floor
    floor_id: str
    polygon: tuple[tuple[float, float], ...]

    def shape(self) -> BaseGeometry:
        return Polygon(self.polygon).buffer(0) if len(self.polygon) >= 3 else Polygon()


@dataclass
class EdgeEffect:
    blocked: bool = False
    extra_m: float = 0.0
    effect: str | None = None  # blocked, wait, squeeze, wet_floor
    by: list[str] = field(default_factory=list)  # obstacle / hazard ids

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=4096)
def walk_line(polygon: tuple, start: tuple, first: tuple, last: tuple, end: tuple) -> LineString:
    """The walk inside a space (backend/core/routeline.py walk_corners) from landing `start` to landing `end`, as a line;
    cached by the space's outline and the two points (geometry only, shared by every snapshot). In a space with
    more than BIG_OUTLINE corners it is the straight line (only squeeze / wet / narrow checks use it)."""
    from backend.core.routeline import walk_corners  # backend.core.routeline imports backend.core.floorplan; keep this module light

    corners = walk_corners([list(point) for point in polygon], first, last) if len(polygon) <= BIG_OUTLINE else []
    points = [start, *corners, end]
    return LineString(points) if points[0] != points[-1] or len(points) > 2 else LineString([points[0]] * 2)


class LiveEffects:
    """What the live obstacles and hazards do to the walks of one building, for one walker clearance."""

    def __init__(self, building: BuildingMap, obstacles: list[Obstacle] = (), hazards: list[Hazard] = (),
                 clearance_m: float = WALKER_CLEARANCE_M, notes: bool = True) -> None:
        self.building = building
        self.notes = notes  # route answers say what was avoided / passed (off for a robot's own planning)
        self.obstacles = {item.id: item for item in obstacles}
        self.hazards = {item.id: item for item in hazards}
        self.clearance_m = max(0.3, clearance_m)
        self.in_space: dict[str, list[Obstacle]] = {}
        self.hazards_in: dict[str, list[Hazard]] = {}
        by_floor: dict[str, list[str]] = {}
        for space_id, space in building.spaces.items():
            by_floor.setdefault(space["floor_id"], []).append(space_id)
        for item in self.obstacles.values():
            shape = item.footprint()
            for space_id in by_floor.get(item.floor_id, []):
                if outline(building.spaces[space_id]["polygon"]).intersection(shape).area > 0.01:
                    self.in_space.setdefault(space_id, []).append(item)
        for item in self.hazards.values():
            shape = item.shape()
            for space_id in by_floor.get(item.floor_id, []):
                if outline(building.spaces[space_id]["polygon"]).intersects(shape):
                    self.hazards_in.setdefault(space_id, []).append(item)
        self._free: dict[tuple[str, str], list[BaseGeometry]] = {}
        self._points: dict[tuple[str, str], tuple[float, float]] = {}
        self._reach: dict[tuple, frozenset[int]] = {}
        self._edges: dict[tuple, EdgeEffect | None] = {}
        self._extra: dict[int, float] = {}  # id(edge data) → metres, for the last apply()

    def active(self) -> bool:
        return bool(self.in_space or self.hazards_in)

    def spaces(self) -> set[str]:
        return set(self.in_space) | set(self.hazards_in)

    def space_of(self, item: Obstacle) -> str | None:
        """The space the obstacle stands in most (its footprint's largest overlap)."""
        best = (0.0, None)
        for space_id, items in self.in_space.items():
            if item in items:
                area = outline(self.building.spaces[space_id]["polygon"]).intersection(item.footprint()).area
                best = max(best, (area, space_id), key=lambda pair: pair[0])
        return best[1]

    # ---------- geometry ----------

    def free_parts(self, space_id: str, which: str) -> list[BaseGeometry]:
        """Connected pieces of the space a walker's centre may be in: "none" (no obstacles), "parked", "all"."""
        key = (space_id, which)
        if key not in self._free:
            half = self.clearance_m / 2
            area = outline(self.building.spaces[space_id]["polygon"]).buffer(-half)
            items = self.counted(space_id, which)
            if items and not area.is_empty:
                area = area.difference(unary_union([item.footprint().buffer(half) for item in items]))
            parts = [] if area.is_empty else list(getattr(area, "geoms", [area]))
            self._free[key] = [part for part in parts if part.area > 0.01]
        return self._free[key]

    def counted(self, space_id: str, which: str) -> list[Obstacle]:
        """The obstacles of the space that count for `which`: none, the standing ones ("parked"), or "all"."""
        return [item for item in self.in_space.get(space_id, [])
                if which == "all" or (which == "parked" and not item.moving)]

    def point(self, space_id: str, node: str) -> tuple[float, float]:
        key = (space_id, node)
        if key not in self._points:
            if node.startswith(DOOR_PREFIX):
                opening = self.building.openings[node.removeprefix(DOOR_PREFIX)]
                self._points[key] = door_landing(outline(self.building.spaces[space_id]["polygon"]),
                                                 tuple(opening["position"]))
            else:
                self._points[key] = self.building.anchor(node)
        return self._points[key]

    def reach(self, space_id: str, node: str, which: str, anywhere: bool) -> frozenset[int]:
        """Index of the free piece the node stands on (a set: empty when none is in reach); an endpoint space's
        anchor counts as every piece."""
        key = (space_id, node, which, anywhere and not node.startswith(DOOR_PREFIX))
        if key not in self._reach:
            self._reach[key] = frozenset(self._reach_now(space_id, node, which, key[3]))
        return self._reach[key]

    def _reach_now(self, space_id: str, node: str, which: str, anywhere: bool) -> set[int]:
        parts = self.free_parts(space_id, which)
        if anywhere:
            return set(range(len(parts)))
        here = Point(self.point(space_id, node))
        reach = self.clearance_m / 2 + REACH_TOLERANCE_M + 0.15  # landings are 30 cm in, walls are clearance/2 in
        inside = [item for item in self.counted(space_id, which) if item.footprint().covers(here)]  # stands on it
        if inside:
            return set()
        # one side only: the nearest free piece. A door right beside an obstacle would otherwise touch the free floor
        # on both sides of it, and a route could hop "through" the obstacle by way of that door.
        distances = [(part.distance(here), index) for index, part in enumerate(parts)]
        nearest = min(distances, default=(math.inf, -1))
        return {nearest[1]} if nearest[0] <= reach else set()

    def joined(self, space_id: str, first: str, second: str, which: str, endpoints: set[str]) -> bool:
        anywhere = space_id in endpoints
        return bool(self.reach(space_id, first, which, anywhere) & self.reach(space_id, second, which, anywhere))

    def walk_line(self, space_id: str, first: str, second: str) -> LineString:
        ends = []
        for node in (first, second):
            if node.startswith(DOOR_PREFIX):
                ends.append(tuple(self.building.openings[node.removeprefix(DOOR_PREFIX)]["position"]))
            else:
                ends.append(self.building.anchor(node))
        polygon = tuple(map(tuple, self.building.spaces[space_id]["polygon"]))
        return walk_line(polygon, self.point(space_id, first), ends[0], ends[1], self.point(space_id, second))

    def cut(self, space_id: str, first: str, second: str, endpoints: set[str] = frozenset()) -> list[str] | None:
        """The parked obstacles that cut the walk first → second, or None when it is not cut."""
        effect = self.edge(space_id, first, second, endpoints, squeeze=False)
        return effect.by if effect is not None and effect.blocked else None

    def across(self, space_id: str, first: str, second: str, moving: bool) -> list[str]:
        """For a walk the free area can't judge (the space is narrower than the clearance somewhere, so even empty it
        falls apart): the obstacles whose footprint, grown by half the clearance, lies across the walk itself."""
        line = self.walk_line(space_id, first, second)
        return [item.id for item in self.in_space.get(space_id, []) if item.moving == moving
                and line.intersects(item.footprint().buffer(self.clearance_m / 2))]

    # ---------- effects ----------

    def edge(self, space_id: str, first: str, second: str, endpoints: set[str] = frozenset(),
             squeeze: bool = True) -> EdgeEffect | None:
        """The effect on the walk first → second inside `space_id`, or None (memoised per walk). `squeeze=False`
        skips the squeeze-past check (it never changes a route, only what is said about it)."""
        key = (space_id, *sorted((first, second)), space_id in endpoints, squeeze)
        if key not in self._edges:
            self._edges[key] = self._edge_now(space_id, first, second, endpoints, squeeze)
        return self._edges[key]

    def _edge_now(self, space_id: str, first: str, second: str, endpoints: set[str], squeeze: bool) -> EdgeEffect | None:
        items = self.in_space.get(space_id, [])
        hazards = self.hazards_in.get(space_id, [])
        if not items and not hazards:
            return None
        effect = EdgeEffect()
        if items and self.joined(space_id, first, second, "none", endpoints):
            if not self.joined(space_id, first, second, "parked", endpoints):
                cut = self.cutting(space_id, first, second, endpoints, moving=False)
                return EdgeEffect(blocked=True, effect="blocked", by=cut)
            if not self.joined(space_id, first, second, "all", endpoints):
                effect = EdgeEffect(extra_m=WAIT_M, effect="wait",
                                    by=self.cutting(space_id, first, second, endpoints, moving=True))
        elif items and not (space_id in endpoints and not (first.startswith(DOOR_PREFIX) and second.startswith(DOOR_PREFIX))):
            # the space is too narrow for the free-area test: judge by what stands across the walk line
            if cut := self.across(space_id, first, second, moving=False):
                return EdgeEffect(blocked=True, effect="blocked", by=cut)
            if waiting := self.across(space_id, first, second, moving=True):
                effect = EdgeEffect(extra_m=WAIT_M, effect="wait", by=waiting)
        line = None
        if squeeze and items and effect.effect is None:
            line = self.walk_line(space_id, first, second)
            near = [item.id for item in items if line.distance(item.footprint()) < NEAR_M]
            if near:
                effect = EdgeEffect(extra_m=SQUEEZE_M, effect="squeeze", by=near)
        if hazards:
            straight = LineString([self.point(space_id, first), self.point(space_id, second)])
            near = [item for item in hazards if straight.distance(item.shape()) < HAZARD_REACH_M]  # cheap test first
            line = (line or self.walk_line(space_id, first, second)) if near else None
            wet = [item.id for item in near if line.intersects(item.shape())]
            if wet:
                effect = EdgeEffect(blocked=False, extra_m=effect.extra_m + WET_M,
                                    effect=effect.effect or "wet_floor", by=[*effect.by, *wet])
        return effect if effect.effect else None

    def cutting(self, space_id: str, first: str, second: str, endpoints: set[str], moving: bool) -> list[str]:
        """The obstacles that, on their own, cut the walk (at least one; all of them if only together)."""
        candidates = [item for item in self.in_space.get(space_id, []) if item.moving == moving]
        alone = []
        for item in candidates:
            single = LiveEffects(self.building, [Obstacle(**{**asdict(item), "moving": False})], [], self.clearance_m)
            if not single.joined(space_id, first, second, "parked", endpoints):
                alone.append(item.id)
        return alone or [item.id for item in candidates]

    def apply(self, graph: nx.MultiGraph, endpoints: set[str]) -> tuple[nx.MultiGraph, bool]:
        """A view of `graph` without the cut walks, and whether some walk got a penalty (then `extra(edge)` gives
        its metres and the search must weigh them). Only the walks of spaces with something in them are looked at."""
        blocked: set[int] = set()
        self._extra = {}
        for space_id in self.spaces():
            nodes = [space_id] + [DOOR_PREFIX + opening_id for opening_id in self.doors_of(space_id)]
            nodes = [node for node in nodes if node in graph]
            for first, second, data in graph.edges(nodes, data=True):
                if data.get("space") != space_id:
                    continue
                effect = self.edge(space_id, first, second, endpoints, squeeze=False)
                if effect is None:
                    continue
                if effect.blocked:
                    blocked.add(id(data))
                else:
                    self._extra[id(data)] = effect.extra_m
        if not blocked:
            return graph, bool(self._extra)
        view = nx.subgraph_view(graph, filter_edge=lambda u, v, k: id(graph[u][v][k]) not in blocked)
        return view, bool(self._extra)

    def extra(self, edge: dict) -> float:
        """The live penalty (metres) of an edge of the graph last passed to apply()."""
        return self._extra.get(id(edge), 0.0)

    def doors_of(self, space_id: str) -> list[str]:
        if not hasattr(self, "_doors"):
            self._doors: dict[str, list[str]] = {}
            for opening in self.building.openings.values():
                for space in opening["space_ids"]:
                    self._doors.setdefault(space, []).append(opening["id"])
        return self._doors.get(space_id, [])

    def describe(self, ids: list[str], space_id: str | None = None) -> list[dict]:
        out = []
        for item_id in dict.fromkeys(ids):
            if item_id in self.obstacles:
                item = self.obstacles[item_id]
                out.append(item.summary(self.building, self.space_of(item) or space_id))
            elif item_id in self.hazards:
                hazard = self.hazards[item_id]
                out.append({"id": hazard.id, "name": hazard.name, "kind": hazard.kind,
                            **({"space": self.building.spaces[space_id]["name"]} if space_id else {})})
        return out


def collapse_hops(graph: nx.MultiGraph, nodes: list[str]) -> list[str]:
    """Drop a door the path only touches: door a → door b → door c all inside one space (a penalty steering round a
    wet patch can do that) becomes a → c when that walk exists, so the path stays one a person can follow and the
    route's space_path / element_path stay well-formed."""
    out = list(nodes)
    index = 0
    while index + 2 < len(out):
        first, middle, last = out[index], out[index + 1], out[index + 2]
        here = graph.get_edge_data(first, middle) or {}
        there = graph.get_edge_data(middle, last) or {}
        spaces = {data.get("space") for data in here.values()} & {data.get("space") for data in there.values()}
        direct = graph.get_edge_data(first, last) or {}
        if middle.startswith(DOOR_PREFIX) and spaces - {None} and any(data.get("space") in spaces for data in direct.values()):
            del out[index + 1]
            continue
        index += 1
    return out


def path_graph(graph: nx.MultiGraph, nodes: list[str]) -> tuple[nx.MultiGraph, float]:
    """The cheapest edge (true metres) between consecutive nodes, as a graph of its own, and the total."""
    path = nx.MultiGraph()
    path.add_nodes_from(nodes)
    total = 0.0
    for first, second in zip(nodes, nodes[1:]):
        data = min(graph.get_edge_data(first, second).values(), key=lambda item: item["weight"])
        path.add_edge(first, second, **data)
        total += data["weight"]
    return path, total


def walk_edges(nodes: list[str], graph: nx.MultiGraph) -> list[tuple[str, str, dict]]:
    """The cheapest edge data between consecutive nodes of a Dijkstra path."""
    edges = []
    for first, second in zip(nodes, nodes[1:]):
        options = graph.get_edge_data(first, second) or {}
        if options:
            edges.append((first, second, min(options.values(), key=lambda data: data["weight"])))
    return edges


def route_notes(live: LiveEffects, base: nx.MultiGraph, base_nodes: list[str] | None, chosen: nx.MultiGraph,
                chosen_nodes: list[str] | None, endpoints: set[str]) -> dict:
    """What the live state did to one leg: obstacles avoided (they cut or slowed the route that would have been
    taken without them) and passed (effects on the route taken)."""
    notes: dict = {}
    avoided: list[str] = []
    space_of: dict[str, str] = {}
    if base_nodes:
        for first, second, data in walk_edges(base_nodes, base):
            if "space" not in data:
                continue
            effect = live.edge(data["space"], first, second, endpoints)
            if effect is not None and (effect.blocked or chosen_nodes != base_nodes):
                avoided += effect.by
                for item in effect.by:
                    space_of.setdefault(item, data["space"])
    passing: list[dict] = []
    if chosen_nodes:
        for first, second, data in walk_edges(chosen_nodes, chosen):
            effect = live.edge(data["space"], first, second, endpoints) if "space" in data else None
            if effect is not None:
                for item in live.describe(effect.by, data.get("space")):
                    passing.append({**item, "effect": effect.effect})
    if chosen_nodes is not None and chosen_nodes == base_nodes:
        avoided = []
    if avoided:
        notes["avoided"] = [item for item in live.describe(avoided, None)]
        for item in notes["avoided"]:
            if "space" not in item and item["id"] in space_of:
                item["space"] = live.building.spaces[space_of[item["id"]]]["name"]
    if passing:
        unique = {}
        for item in passing:
            unique.setdefault((item["id"], item["effect"]), item)
        notes["passing"] = list(unique.values())
    return notes
