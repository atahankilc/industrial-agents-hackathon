"""Moving objects (forklifts, robots, AGVs): routes that fit their attributes, and missions as machine-readable steps
(archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md "Moving objects"). App access mode only; deterministic,
no LLM. Coordinates are building metres, the frame of building.json and the plan view.

Attributes use only what building.json can check: opening `width_m`, `step_free` openings/connectors, connector
`kind` (stairs / lift), space `room_type`. Height, weight, lift cabin size and turning radius are not in the data
and are not attributes."""

from dataclasses import asdict, dataclass, field

from shapely.geometry import Point, Polygon

from core import navigation
from core.building_map import LIFT, OUTSIDE, BuildingMap, MapError
from core.preferences import Penalties
from core.route_models import RouteRules
from core.routeline import route_line

KINDS = ("forklift", "robot", "agv", "cart", "other")


@dataclass
class Attributes:
    width_m: float  # openings narrower than this are closed for the object
    step_free_only: bool = True  # wheels: no stepped openings
    can_use_lifts: bool = True
    can_use_stairs: bool = False  # legged robots
    avoid_room_types: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Attributes":
        width = float(data.get("width_m") or 0)
        if not 0 < width <= 20:
            raise ValueError("width_m must be between 0 and 20 m")
        rooms = data.get("avoid_room_types") or []
        if not isinstance(rooms, list):
            raise ValueError("avoid_room_types must be a list")
        return cls(width_m=round(width, 3), step_free_only=bool(data.get("step_free_only", True)),
                   can_use_lifts=bool(data.get("can_use_lifts", True)),
                   can_use_stairs=bool(data.get("can_use_stairs", False)),
                   avoid_room_types=sorted({str(room) for room in rooms}))

    def to_dict(self) -> dict:
        return asdict(self)


def closures(building: BuildingMap, kind: str, attributes: Attributes) -> list[str]:
    """Openings and connectors the object can't use."""
    closed = [o["id"] for o in building.openings.values()
              if o["width_m"] < attributes.width_m or (attributes.step_free_only and not o["step_free"])]
    for connector in building.connectors.values():
        if connector["kind"] == LIFT:
            usable = attributes.can_use_lifts and kind != "forklift"  # no vehicles in lifts (routing-profiles.md)
        else:
            usable = attributes.can_use_stairs and kind != "forklift"
        if not usable:
            closed.append(connector["id"])
    return closed


def space_at(building: BuildingMap, floor_id: str, x: float, y: float) -> str | None:
    """The space on `floor_id` containing the point (the smallest if spaces overlap), else None."""
    point = Point(x, y)
    hits = [(Polygon(space["polygon"]).area, space_id) for space_id, space in building.spaces.items()
            if space["floor_id"] == floor_id and Polygon(space["polygon"]).covers(point)]
    return min(hits)[1] if hits else None


def plan_route(building: BuildingMap, kind: str, attributes: Attributes, start: str, destination: str) -> dict:
    """Route for the object between two space ids (navigation.find_route answer as a dict)."""
    rules = RouteRules(bays_destination_only=True, no_outside=True, forklift=kind == "forklift")
    penalties = Penalties(avoid_room_types=frozenset(attributes.avoid_room_types))
    return navigation.find_route(building, start, destination, step_free=False,
                                 closed=closures(building, kind, attributes), rules=rules,
                                 penalties=penalties if penalties.active() else None, include_steps=False).to_dict()


def mission_steps(building: BuildingMap, route: dict) -> list[dict]:
    """The route as steps a machine can follow: move (waypoints on one floor), pass_opening, call_lift /
    take_stairs (floor to floor), arrive."""
    floors = sorted(building.floors.values(), key=lambda floor: floor["level"])
    line = route_line(building, route["space_path"], route["element_path"])
    elements = [element for element in route["element_path"] if element != OUTSIDE]
    connectors = [element for index, element in enumerate(elements)
                  if element in building.connectors and (index == 0 or elements[index - 1] != element)]
    openings = [element for element in elements if element in building.openings]
    steps: list[dict] = []
    segment: list[list[float]] = []
    connector_index = 0
    for index, (x, y, floor) in enumerate(line):
        if segment and segment[-1][2] != floor:  # floor change: close the segment, ride the connector
            steps += moves(building, floors[segment[-1][2]]["id"], segment, openings)
            connector = building.connectors[connectors[connector_index]] if connector_index < len(connectors) else None
            connector_index += 1
            step = {"op": "call_lift" if connector and connector["kind"] == LIFT else "take_stairs",
                    "from_floor": floors[segment[-1][2]]["id"], "to_floor": floors[floor]["id"]}
            if connector:
                step["connector_id"] = connector["id"]
            steps.append(step)
            segment = []
        segment.append([x, y, floor])
    if segment:
        steps += moves(building, floors[segment[-1][2]]["id"], segment, openings)
    steps.append({"op": "arrive", "space_id": route["to_space_id"],
                  "name": building.spaces[route["to_space_id"]]["name"]})
    return steps


def moves(building: BuildingMap, floor_id: str, segment: list[list[float]], openings: list[str]) -> list[dict]:
    """One floor's waypoints split at each door on the route that lies on this floor."""
    steps: list[dict] = []
    current: list[list[float]] = []
    on_floor = [o for o in openings if building.openings[o]["floor_id"] == floor_id]
    for x, y, _ in segment:
        current.append([round(x, 3), round(y, 3)])
        hit = next((o for o in on_floor if abs(building.openings[o]["position"][0] - x) < 0.01
                    and abs(building.openings[o]["position"][1] - y) < 0.01), None)
        if hit:
            steps.append({"op": "move", "floor_id": floor_id, "waypoints": current})
            steps.append({"op": "pass_opening", "opening_id": hit, "width_m": building.openings[hit]["width_m"]})
            on_floor.remove(hit)
            current = [[round(x, 3), round(y, 3)]]
    if len(current) > 1 or not steps:
        steps.append({"op": "move", "floor_id": floor_id, "waypoints": current})
    return steps


def mission(building: BuildingMap, kind: str, attributes: Attributes, start: str, destination: str) -> dict:
    """{"reachable", "length_m", "steps"} or {"reachable": False, "reason"}."""
    if start == destination:
        raise MapError("The object is already there.")
    route = plan_route(building, kind, attributes, start, destination)
    if not route.get("reachable"):
        return {"reachable": False, "reason": route.get("reason")}
    return {"reachable": True, "length_m": route["length_m"], "space_path": route["space_path"],
            "element_path": route["element_path"], "steps": mission_steps(building, route)}
