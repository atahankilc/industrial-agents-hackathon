"""routing solvers (errand, what_if_door) — see docs/architecture/solver-plan.md.

Both run on the exact route model of `BuildingMap.graph` (verified to the cm) and never mutate the building:
distances come from our own Dijkstra calls on a freshly built graph, and the what-if door is added to a deep copy.

Rules verified against train+dev labelled answers (scripts/validate_solvers.py):

errand (93/93):
- "I can carry it on the stairs" (the only carry phrase in train/dev/test) → full graph, stairs allowed
  (`step_free=False`); the step-free graph matches only 34/93 (27 have no step-free route at all).
- `via` = the space holding an asset of `asset_type` with the smallest route distance from `start`, on ANY floor
  (3/93 vias are on another floor; a same-floor-only rule matches 90/93). The start counts (distance 0) if it
  holds one. Ties → smaller space id (none in train/dev; smallest 1st/2nd gap is 0.62 m).
- `target` = the largest-area space (shapely polygon area) with `room_type` on `floor_id`; ties → smaller id.
- total = d(start, via) + d(via, target).

what_if_door (4/4):
- Distance "out of the building" = route distance to the `outside` node on the FULL graph (not step-free; the
  step-free graph gives 21 instead of 6 and 0 instead of 2).
- Count spaces with `type == "room"` on `floor_id` whose distance drops by strictly more than 1 m. Rooms that
  cannot reach outside before the change are skipped (none observed in a 1044-pair sweep).
- The new door: 0.9 m, step-free (irrelevant on the full graph), at the middle of the shared wall: for each side,
  the part of its outline within 0.35 m of the other polygon, merged, longest piece, point at half its length;
  the door sits halfway between the two sides' points. Sensitivity: on 1044 random wall pairs in all buildings
  the count (per other floor) changed for 0–3 pairs whichever midpoint variant was used (starter `add_door`
  nearest points: 2) — the rule is robust to the midpoint choice.
"""

import copy
import itertools

import networkx as nx
from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, nearest_points

from core.building_map import DOOR_PREFIX, NEW_DOOR_WIDTH_M, OUTSIDE, BuildingMap, MapError
from core.solvers import SolverResult, solver

ROOM_TYPE = "room"
SHARED_WALL_TOLERANCE_M = 0.35  # README §4: "within 0.35 m of the other room's outline"
IMPROVEMENT_THRESHOLD_M = 1.0


# ---------- route helpers ----------


def path_elements(graph: nx.MultiGraph, nodes: list[str]) -> list[str]:
    """Element id (opening or connector) used by each hop of a node path; cheapest parallel edge wins."""
    return [
        min(graph[a][b].values(), key=lambda edge: edge["weight"])["via"] for a, b in itertools.pairwise(nodes)
    ]


def leg(graph: nx.MultiGraph, start: str, end: str, length: float, nodes: list[str]) -> dict:
    return {
        "from": start,
        "to": end,
        "length_m": round(length, 2),
        "nodes": nodes,  # ordered route node ids: space ids, "door:<opening id>", "outside"
        "spaces": [node for node in nodes if not node.startswith(DOOR_PREFIX) and node != OUTSIDE],
        "elements": list(dict.fromkeys(path_elements(graph, nodes))),  # openings/connectors passed, in order
    }


def space_area(space: dict) -> float:
    return Polygon(space["polygon"]).area


# ---------- errand ----------


@solver("errand")
def errand(
    building: BuildingMap,
    start: str,
    asset_type: str,
    floor_id: str,
    room_type: str,
    step_free: bool = False,
    **_,
) -> SolverResult:
    graph = building.graph(step_free)
    if start not in graph:
        raise MapError(f"{building.describe_space(start)} is closed.")
    distances, paths = nx.single_source_dijkstra(graph, start, weight="weight")
    holders = sorted({asset["space_id"] for asset in building.assets.values() if asset["type"] == asset_type})
    if not holders:
        raise MapError(f"No {asset_type.replace('_', ' ')} in this building.")
    reachable = sorted((distances[space_id], space_id) for space_id in holders if space_id in distances)
    if not reachable:
        raise MapError(f"No {'step-free ' if step_free else ''}route to any {asset_type.replace('_', ' ')}.")
    first_length, via = reachable[0]

    rooms = [s for s in building.spaces.values() if s["floor_id"] == floor_id and s["room_type"] == room_type]
    if not rooms:
        raise MapError(f"No {room_type.replace('_', ' ')} on {building.floor_name(floor_id)}.")
    ranked = sorted(rooms, key=lambda space: (-space_area(space), space["id"]))
    target = ranked[0]["id"]
    try:
        second_length, second_nodes = nx.single_source_dijkstra(graph, via, target, weight="weight")
    except (nx.NetworkXNoPath, nx.NodeNotFound) as error:
        raise MapError(
            f"No {'step-free ' if step_free else ''}route from {building.describe_space(via)} to "
            f"{building.describe_space(target)}."
        ) from error

    total = round(first_length + second_length, 2)
    legs = [
        leg(graph, start, via, first_length, paths[via]),
        leg(graph, via, target, second_length, second_nodes),
    ]
    asset_ids = sorted(
        asset["id"]
        for asset in building.assets.values()
        if asset["type"] == asset_type and asset["space_id"] == via
    )
    runner_up = reachable[1] if len(reachable) > 1 else None
    return SolverResult(
        kind="errand",
        value=total,
        unit="m",
        explanation=[
            f"Nearest {asset_type.replace('_', ' ')}: {building.describe_space(via)}, "
            f"{first_length:.2f} m from {building.describe_space(start)}.",
            f"Largest {room_type.replace('_', ' ')} on {building.floor_name(floor_id)}: "
            f"{building.describe_space(target)} ({space_area(ranked[0]):.2f} m²), {second_length:.2f} m further.",
            f"Total walk {first_length:.2f} + {second_length:.2f} = {total:.2f} m"
            f"{' (step-free)' if step_free else ' (stairs allowed)'}.",
        ],
        evidence={
            "start": start,
            "via": via,
            "via_asset_ids": asset_ids,
            "target": target,
            "target_area_m2": round(space_area(ranked[0]), 2),
            "step_free": step_free,
            "closed": sorted(building.closed),
            "legs": legs,
            "runner_up_via": (
                {"space_id": runner_up[1], "distance_m": round(runner_up[0], 2)} if runner_up else None
            ),
            "runner_up_target": (
                {"space_id": ranked[1]["id"], "area_m2": round(space_area(ranked[1]), 2)}
                if len(ranked) > 1
                else None
            ),
        },
    )


# ---------- what_if_door ----------


def _lines(geometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [line for part in geometry.geoms for line in _lines(part)]
    return []  # points: touching corners are not walls


def _wall_side_midpoint(outline_of: Polygon, other: Polygon) -> tuple[float, float] | None:
    """Middle of the longest stretch of `outline_of`'s outline lying within 0.35 m of `other`."""
    pieces = _lines(outline_of.exterior.intersection(other.buffer(SHARED_WALL_TOLERANCE_M)))
    if not pieces:
        return None
    merged = _lines(linemerge(pieces))  # rejoins a wall split at the ring's start vertex
    longest = max(merged, key=lambda line: line.length)
    point = longest.interpolate(0.5, normalized=True)
    return (point.x, point.y)


def shared_wall_midpoint(first: Polygon, second: Polygon) -> tuple[float, float]:
    """Middle of the wall two spaces share: halfway between the midpoints of the two facing outline stretches.

    Falls back to the starter's nearest-points midpoint when the outlines never come within 0.35 m."""
    sides = [_wall_side_midpoint(first, second), _wall_side_midpoint(second, first)]
    sides = [side for side in sides if side is not None]
    if not sides:
        point_a, point_b = nearest_points(first, second)
        return ((point_a.x + point_b.x) / 2, (point_a.y + point_b.y) / 2)
    return (sum(x for x, _ in sides) / len(sides), sum(y for _, y in sides) / len(sides))


def with_new_door(building: BuildingMap, first: str, second: str) -> tuple[BuildingMap, dict]:
    """Deep copy of the building (closures kept) with a door at the middle of the first/second shared wall."""
    first_space, second_space = building.spaces[first], building.spaces[second]
    if first_space["floor_id"] != second_space["floor_id"]:
        raise MapError("A door can only join two spaces on the same floor.")
    x, y = shared_wall_midpoint(Polygon(first_space["polygon"]), Polygon(second_space["polygon"]))
    changed = BuildingMap(copy.deepcopy(building.data))
    changed.closed = set(building.closed)
    opening = {
        "id": f"{first_space['floor_id']}-O-whatif",
        "floor_id": first_space["floor_id"],
        "space_ids": [first, second],
        "kind": "door",
        "position": [round(x, 3), round(y, 3)],
        "width_m": NEW_DOOR_WIDTH_M,
        "step_free": True,
        "synthetic": True,
    }
    changed.openings[opening["id"]] = opening
    changed.data["openings"].append(opening)
    return changed, opening


def distances_out(building: BuildingMap) -> dict[str, float]:
    """Route distance from every space to the nearest entrance (the shared `outside` node), stairs allowed."""
    graph = building.graph(step_free=False)
    if OUTSIDE not in graph:
        return {}
    return nx.single_source_dijkstra_path_length(graph, OUTSIDE, weight="weight")


@solver("what_if_door")
def what_if_door(
    building: BuildingMap, first: str, second: str, floor_id: str, door_floor_id: str | None = None, **_
) -> SolverResult:
    changed, opening = with_new_door(building, first, second)
    before, after = distances_out(building), distances_out(changed)
    rooms = sorted(
        space_id
        for space_id, space in building.spaces.items()
        if space["floor_id"] == floor_id and space["type"] == ROOM_TYPE
    )
    per_room = []
    improved = []
    for space_id in rooms:
        old, new = before.get(space_id), after.get(space_id)
        per_room.append(
            [space_id, None if old is None else round(old, 2), None if new is None else round(new, 2)]
        )
        if old is not None and new is not None and new < old - IMPROVEMENT_THRESHOLD_M:
            improved.append(space_id)
    unreachable = [space_id for space_id, old, _ in per_room if old is None]
    return SolverResult(
        kind="what_if_door",
        value=len(improved),
        unit=None,
        explanation=[
            f"New 0.9 m door between {building.describe_space(first)} and {building.describe_space(second)} "
            f"at ({opening['position'][0]:.2f}, {opening['position'][1]:.2f}), the middle of their shared wall.",
            f"Compared each room's walk to the nearest entrance on {building.floor_name(floor_id)} before and "
            f"after: {len(improved)} of {len(rooms)} rooms get more than 1 m shorter.",
        ],
        evidence={
            "door": {
                "space_ids": [first, second],
                "floor_id": opening["floor_id"],
                "position": opening["position"],
                "width_m": opening["width_m"],
                "step_free": opening["step_free"],
            },
            "floor_id": floor_id,
            "threshold_m": IMPROVEMENT_THRESHOLD_M,
            "improved": improved,
            "rooms": per_room,  # [space id, metres to outside before, after] — None = no route out
            "unreachable_before": unreachable,
            "closed": sorted(building.closed),
        },
    )
