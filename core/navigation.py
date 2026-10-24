"""Navigation tools: locate assets, count them, route between places, run multi-stop tours.

Pure functions over a `BuildingMap`, designed as the Guide agent's tools and as the data the UI draws. They never
mutate the building: closures are parameters (merged with any `building.closed` already set by an edit session)
and are applied on a shallow view of the map, so `building.closed`, `last_route` and `located_asset_ids` stay
untouched. Routing uses `BuildingMap.graph` unchanged, so lengths are the dataset's route model to the cm
(docs/kit/route-model.md).

Path representation = the warm-up gold answers (docs/kit/route-model.md#path-representations-in-answers):
`space_path` lists space ids (including "outside" when the walk leaves the building), `element_path` lists the
opening/connector traversed by every graph edge — each opening appears twice (into and out of its door node),
a connector once per floor hop.

Unknown or ambiguous place names raise `MapError` (a usage error the agent should repair by searching); a valid
request with no path returns `reachable=False` with a reason.

Route model and rules are chosen per call (core/route_models.py, Q-014): `model="kit"` (default, the dataset's
model) or `"geodesic"` (the Sunday scoring rule), and `rules` (production bays destination-only, no shortcut
outside, forklift). With no rules and the kit model the graph is exactly `BuildingMap.graph`."""

import copy
import itertools
from dataclasses import asdict, dataclass, field

import networkx as nx

from core import route_models
from core.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap, MapError
from core.route_models import KIT, NO_RULES, RouteRules

MAX_LOCATE_RESULTS = 10


def normalise(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").split())


def compact(value: object) -> object:
    """Drop None values recursively so tool results stay small."""
    if isinstance(value, dict):
        return {key: compact(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


class Serialisable:
    def to_dict(self) -> dict:
        return compact(asdict(self))  # type: ignore[call-overload]


# ---------- locate / count ----------


@dataclass
class AssetHit(Serialisable):
    asset_id: str
    name: str
    type: str
    space_id: str
    space_name: str
    floor_id: str
    floor_level: int
    position: list[float]


@dataclass
class LocateResult(Serialisable):
    query: str
    match: str  # "id" | "type" | "name" | "words" | "none"
    total: int
    assets: list[AssetHit]


def asset_hit(building: BuildingMap, asset: dict) -> AssetHit:
    space = building.spaces[asset["space_id"]]
    return AssetHit(
        asset_id=asset["id"],
        name=asset["name"],
        type=asset["type"],
        space_id=asset["space_id"],
        space_name=space["name"],
        floor_id=asset["floor_id"],
        floor_level=building.floors[asset["floor_id"]]["level"],
        position=list(asset["position"]),
    )


def type_candidates(phrase: str) -> list[str]:
    wanted = normalise(phrase).replace(" ", "_")
    return [wanted, wanted.removesuffix("s"), wanted.removesuffix("es")]


def match_assets(building: BuildingMap, query: str) -> tuple[str, list[dict]]:
    """Assets for an asset id, a type ('single bed', plurals ok), a name, or words in name/type — best tier first."""
    if query in building.assets:
        return "id", [building.assets[query]]
    assets = list(building.assets.values())
    known_types = {asset["type"] for asset in assets}
    for candidate in type_candidates(query):
        if candidate in known_types:
            return "type", [asset for asset in assets if asset["type"] == candidate]
    wanted = normalise(query)
    named = [asset for asset in assets if normalise(asset["name"]) == wanted]
    if named:
        return "name", named
    words = wanted.split()
    singular = [word.removesuffix("s") if len(word) > 3 else word for word in words]
    for tokens in (words, singular):
        hits = [
            asset
            for asset in assets
            if all(token in normalise(f"{asset['name']} {asset['type']}") for token in tokens)
        ]
        if hits:
            return "words", hits
    return "none", []


def locate(
    building: BuildingMap, query: str, floor_id: str | None = None, limit: int = MAX_LOCATE_RESULTS
) -> LocateResult:
    """Where is an asset? `query` is an asset id, type, name or a few words. Results sorted by floor then id."""
    match, assets = match_assets(building, query)
    if floor_id is not None:
        assets = [asset for asset in assets if asset["floor_id"] == floor_id]
    assets.sort(key=lambda asset: (building.floors[asset["floor_id"]]["level"], asset["id"]))
    return LocateResult(
        query=query,
        match=match if assets else "none",
        total=len(assets),
        assets=[asset_hit(building, asset) for asset in assets[:limit]],
    )


def resolve_asset_type(building: BuildingMap, phrase: str) -> str | None:
    """An asset type from a type phrase, or the single type of the assets the phrase names; None if unknown."""
    match, assets = match_assets(building, phrase)
    types = sorted({asset["type"] for asset in assets})
    return types[0] if match != "none" and len(types) == 1 else None


@dataclass
class CountResult(Serialisable):
    asset_type: str
    count: int
    floor_id: str | None = None
    floor_level: int | None = None
    asset_ids: list[str] = field(default_factory=list)


def count_assets(building: BuildingMap, asset_type: str, floor_id: str | None = None) -> CountResult:
    """Number of assets whose `type` equals `asset_type` exactly (optionally on one floor; None = whole building)."""
    ids = sorted(
        asset["id"]
        for asset in building.assets.values()
        if asset["type"] == asset_type and (floor_id is None or asset["floor_id"] == floor_id)
    )
    return CountResult(
        asset_type=asset_type,
        count=len(ids),
        floor_id=floor_id,
        floor_level=building.floors[floor_id]["level"] if floor_id is not None else None,
        asset_ids=ids,
    )


# ---------- routing ----------


@dataclass
class RouteAnswer(Serialisable):
    reachable: bool
    from_space_id: str
    to_space_id: str
    length_m: float | None = None
    space_path: list[str] | None = None
    element_path: list[str] | None = None
    steps: list[str] | None = None
    step_free: bool = False
    closed: list[str] = field(default_factory=list)
    via: list[str] = field(default_factory=list)
    reason: str | None = None
    model: str | None = None  # None = kit route model
    rules: list[str] | None = None  # active route rules, None = none


@dataclass
class TourAnswer(Serialisable):
    reachable: bool
    stops: list[str]
    length_m: float | None = None
    legs: list[RouteAnswer] = field(default_factory=list)
    step_free: bool = False
    closed: list[str] = field(default_factory=list)
    reason: str | None = None
    model: str | None = None
    rules: list[str] | None = None


def routing_view(building: BuildingMap, closed: tuple[str, ...] | list[str]) -> BuildingMap:
    """Shallow copy whose `closed` set = the building's closures + `closed` (names or ids). The original is untouched."""
    view = copy.copy(building)
    view.closed = set(building.closed)
    for reference in closed:
        view.closed.add(view.find_element(reference))
    return view


def resolve_stop(view: BuildingMap, reference: str) -> str:
    return OUTSIDE if reference == OUTSIDE else view.resolve_space(reference)


def edge_element(graph: nx.MultiGraph, first: str, second: str) -> str:
    """The element of the cheapest edge between two nodes (same rule as BuildingMap.directions)."""
    return min(graph[first][second].values(), key=lambda edge: edge["weight"])["via"]


def directions(view: BuildingMap, graph: nx.MultiGraph, nodes: list[str]) -> list[str]:
    """BuildingMap.directions, also when the walk starts or ends outside the building."""
    if OUTSIDE not in (nodes[0], nodes[-1]):
        return view.directions(graph, nodes)
    if len(nodes) == 1:
        return ["You are already outside."]
    named = copy.copy(view)  # placeholder entry so directions() can run; its first/last lines are replaced below
    named.spaces = {**view.spaces, OUTSIDE: {"name": "outside", "floor_id": next(iter(view.floors))}}
    steps = named.directions(graph, nodes)
    if nodes[0] == OUTSIDE:
        steps[0] = "Start outside the building."
    if nodes[-1] == OUTSIDE:
        steps[-1] = "You are now outside the building."
    return steps


def leg(
    view: BuildingMap,
    graph: nx.MultiGraph,
    start: str,
    destination: str,
    step_free: bool,
    include_steps: bool,
    model: str = KIT,
    rules: RouteRules = NO_RULES,
) -> RouteAnswer:
    closed = sorted(view.closed)
    labels = {"model": None if model == KIT else model, "rules": rules.describe() or None}
    walk = route_models.leg_graph(graph, route_models.endpoint_only(view, rules), start, destination)
    try:
        length, nodes = nx.single_source_dijkstra(walk, start, destination, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        blocked = [stop for stop in (start, destination) if stop in view.closed]
        reason = (
            f"{', '.join(blocked)} is closed"
            if blocked
            else f"no {'step-free ' if step_free else ''}path with the current closures"
        )
        if not blocked and labels["rules"]:
            reason = f"no route under these rules ({'; '.join(labels['rules'])}): " + reason
        return RouteAnswer(
            reachable=False,
            from_space_id=start,
            to_space_id=destination,
            step_free=step_free,
            closed=closed,
            reason=reason,
            **labels,
        )
    nodes, walked = route_models.expand(walk, nodes)
    return RouteAnswer(
        reachable=True,
        from_space_id=start,
        to_space_id=destination,
        length_m=round(length, 2),
        space_path=[node for node in nodes if not node.startswith(DOOR_PREFIX)],
        element_path=[edge_element(walked, first, second) for first, second in itertools.pairwise(nodes)],
        steps=directions(view, walked, nodes) if include_steps else None,
        step_free=step_free,
        closed=closed,
        **labels,
    )


def find_route(
    building: BuildingMap,
    start: str,
    destination: str,
    *,
    step_free: bool = False,
    closed: tuple[str, ...] | list[str] = (),
    via: tuple[str, ...] | list[str] = (),
    include_steps: bool = True,
    model: str = KIT,
    rules: RouteRules = NO_RULES,
) -> RouteAnswer:
    """Shortest route (route-model metres). Places are ids, refs, exact names, asset ids/names, or "outside".

    `closed`: connectors/openings/spaces (ids or names) to avoid, on top of `building.closed`. `via`: ordered
    intermediate stops; the result then concatenates the legs (use `tour` to keep them separate). `model`/`rules`:
    core/route_models.py."""
    view = routing_view(building, closed)
    stops = [resolve_stop(view, reference) for reference in (start, *via, destination)]
    graph = route_models.route_graph(view, step_free, model, rules)
    legs = [
        leg(view, graph, first, second, step_free, include_steps, model, rules)
        for first, second in itertools.pairwise(stops)
    ]
    if len(legs) == 1:
        return legs[0]
    failed = next((item for item in legs if not item.reachable), None)
    if failed:
        failed.reason = f"leg {failed.from_space_id} → {failed.to_space_id}: {failed.reason}"
        failed.from_space_id, failed.to_space_id, failed.via = stops[0], stops[-1], stops[1:-1]
        return failed
    return RouteAnswer(
        reachable=True,
        from_space_id=stops[0],
        to_space_id=stops[-1],
        length_m=round(sum(item.length_m for item in legs), 2),  # type: ignore[misc]
        space_path=[stops[0], *(space for item in legs for space in item.space_path[1:])],  # type: ignore[index]
        element_path=[element for item in legs for element in item.element_path],  # type: ignore[union-attr]
        steps=[
            step
            for index, item in enumerate(legs)
            for step in item.steps or []
            if index == 0 or not step.startswith(("Start in", "Start outside"))
        ]
        if include_steps
        else None,
        step_free=step_free,
        closed=sorted(view.closed),
        via=stops[1:-1],
        model=legs[0].model,
        rules=legs[0].rules,
    )


def tour(
    building: BuildingMap,
    stops: list[str] | tuple[str, ...],
    *,
    step_free: bool = False,
    closed: tuple[str, ...] | list[str] = (),
    include_steps: bool = False,
    model: str = KIT,
    rules: RouteRules = NO_RULES,
) -> TourAnswer:
    """Visit `stops` in the given order; one shortest leg per consecutive pair. Total = sum of the legs."""
    if len(stops) < 2:
        raise MapError("A tour needs at least two stops.")
    view = routing_view(building, closed)
    resolved = [resolve_stop(view, reference) for reference in stops]
    graph = route_models.route_graph(view, step_free, model, rules)
    legs = [
        leg(view, graph, first, second, step_free, include_steps, model, rules)
        for first, second in itertools.pairwise(resolved)
    ]
    failed = next((item for item in legs if not item.reachable), None)
    return TourAnswer(
        reachable=failed is None,
        stops=resolved,
        length_m=None if failed else round(sum(item.length_m for item in legs), 2),  # type: ignore[misc]
        legs=legs,
        step_free=step_free,
        closed=sorted(view.closed),
        reason=None if failed is None else f"leg {failed.from_space_id} → {failed.to_space_id}: {failed.reason}",
        model=None if model == KIT else model,
        rules=rules.describe() or None,
    )


def path_length(
    building: BuildingMap,
    space_path: list[str],
    element_path: list[str],
    *,
    step_free: bool = False,
    closed: tuple[str, ...] | list[str] = (),
) -> float | None:
    """Route-model cost of a given (space_path, element_path); None if it is not a valid walk on the graph.

    Used to confirm that a different path of the same length as ours (a tie) is genuinely valid."""
    view = routing_view(building, closed)
    graph = view.graph(step_free)
    nodes = [space_path[0]]
    spaces = iter(space_path[1:])
    index = 0
    while index < len(element_path):
        element = element_path[index]
        if element in view.openings:
            if element_path[index + 1 : index + 2] != [element]:
                return None
            nodes += [DOOR_PREFIX + element, next(spaces, "")]
            index += 2
        else:
            nodes.append(next(spaces, ""))
            index += 1
    if "" in nodes or next(spaces, None) is not None:
        return None
    total = 0.0
    for (first, second), element in zip(itertools.pairwise(nodes), element_path, strict=True):
        weights = [
            edge["weight"] for edge in graph.get_edge_data(first, second, default={}).values() if edge["via"] == element
        ]
        if not weights:
            return None
        total += min(weights)
    return round(total, 2)
