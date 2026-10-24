"""reachability solvers — see docs/architecture/solver-plan.md.

Reachability is plain connectivity (no costs), so we build our own filtered adjacency over spaces instead of the
weighted route graph: every opening joins its two spaces (or a space and `outside`), every connector joins its
consecutive stops. Filters: step-free, minimum opening width, closed element ids. The building is never mutated.

Rules verified against train+dev labelled answers (scripts/validate_solvers.py):
- a "room" is a space with `type == "room"` (halls, corridors, stairs, lifts, outdoor/balconies excluded); this
  is also exactly the manifest's `rooms` column in all 280 buildings;
- the minimum width applies to every opening (door, leafless opening, entrance) with `width_m >= min_width`;
  connectors (lifts) carry no width and are not width-limited;
- `outside` is a node: entrances join the building to one shared outside, as in the route model;
- the start space counts if it is a room on the target floor.
"""

from collections import deque
from collections.abc import Iterable

from core.building_map import OUTSIDE, BuildingMap
from core.solvers import SolverResult, solver

ROOM_TYPE = "room"


def is_room(space: dict) -> bool:
    """A space that counts as a "room" in count questions: coarse `type == "room"`."""
    return space["type"] == ROOM_TYPE


def adjacency(
    building: BuildingMap,
    *,
    step_free: bool,
    min_width: float | None = None,
    closed: Iterable[str] = (),
) -> dict[str, set[str]]:
    """Undirected space adjacency (plus `outside`) after step-free / width / closure filters.

    Closures combine the building's own `closed` set with `closed` (opening, connector or space ids)."""
    shut = set(building.closed) | set(closed)
    graph: dict[str, set[str]] = {space_id: set() for space_id in building.spaces if space_id not in shut}
    graph[OUTSIDE] = set()

    def link(first: str, second: str) -> None:
        if first in graph and second in graph and first != second:
            graph[first].add(second)
            graph[second].add(first)

    for opening in building.openings.values():
        if opening["id"] in shut or (step_free and not opening["step_free"]):
            continue
        if min_width is not None and opening["width_m"] < min_width:
            continue
        link(*opening["space_ids"])
    for connector in building.connectors.values():
        if connector["id"] in shut or (step_free and not connector["step_free"]):
            continue
        levels = {floor_id: building.floors[floor_id]["level"] for floor_id in connector["floor_ids"]}
        stops = sorted(
            zip(connector["floor_ids"], connector["space_ids"], strict=True), key=lambda stop: levels[stop[0]]
        )
        for (_, low), (_, high) in zip(stops, stops[1:]):
            link(low, high)
    return graph


def reachable_spaces(
    building: BuildingMap,
    start: str,
    *,
    step_free: bool,
    min_width: float | None = None,
    closed: Iterable[str] = (),
) -> set[str]:
    """Every space id reachable from `start` (start included, `outside` excluded) under the given filters."""
    graph = adjacency(building, step_free=step_free, min_width=min_width, closed=closed)
    if start not in graph:
        return set()
    seen = {start}
    queue = deque([start])
    while queue:
        for neighbour in graph[queue.popleft()]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    seen.discard(OUTSIDE)
    return seen


def rooms_on_floor(building: BuildingMap, space_ids: Iterable[str], floor_id: str) -> list[str]:
    return sorted(
        space_id
        for space_id in space_ids
        if building.spaces[space_id]["floor_id"] == floor_id and is_room(building.spaces[space_id])
    )


def narrow_openings(building: BuildingMap, reached: set[str], min_width: float) -> list[str]:
    """Step-free openings too narrow for the load that lead from a reached space to an unreached one."""
    return sorted(
        opening["id"]
        for opening in building.openings.values()
        if opening["step_free"]
        and opening["width_m"] < min_width
        and len({space_id in reached for space_id in opening["space_ids"] if space_id != OUTSIDE}) == 2
    )


@solver("wide_delivery_count")
def wide_delivery_count(building: BuildingMap, start: str, floor_id: str, min_width: float, **_) -> SolverResult:
    reached = reachable_spaces(building, start, step_free=True, min_width=float(min_width))
    rooms = rooms_on_floor(building, reached, floor_id)
    floor_rooms = rooms_on_floor(building, building.spaces, floor_id)
    floor = building.floor_name(floor_id)
    return SolverResult(
        kind="wide_delivery_count",
        value=len(rooms),
        unit="rooms",
        explanation=[
            f"Step-free from {building.spaces[start]['name']} (lifts allowed, no stairs or steps), "
            f"through openings at least {float(min_width):g} m wide.",
            f"{len(rooms)} of the {len(floor_rooms)} rooms on {floor} can be reached.",
        ],
        evidence={
            "start": start,
            "floor_id": floor_id,
            "min_width": float(min_width),
            "rooms": rooms,
            "blocking_openings": narrow_openings(building, reached, float(min_width)),
        },
    )


@solver("step_free_reachable_count")
def step_free_reachable_count(
    building: BuildingMap, closed: str | list[str], start: str, floor_id: str, **_
) -> SolverResult:
    closures = [closed] if isinstance(closed, str) else list(closed)
    reached = reachable_spaces(building, start, step_free=True, closed=closures)
    rooms = rooms_on_floor(building, reached, floor_id)
    floor = building.floor_name(floor_id)
    names = ", ".join(building.connectors[c]["name"] if c in building.connectors else c for c in closures)
    return SolverResult(
        kind="step_free_reachable_count",
        value=len(rooms),
        unit="rooms",
        explanation=[
            f"Step-free from {building.spaces[start]['name']} with {names} out of service.",
            f"{len(rooms)} rooms on {floor} can still be reached.",
        ],
        evidence={"start": start, "floor_id": floor_id, "closed": closures, "rooms": rooms},
    )
