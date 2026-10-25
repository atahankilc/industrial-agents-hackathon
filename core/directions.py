"""Turn-by-turn legs of a route for guidance UIs (camera walk mode, route card).

The walk is space anchor → door → next anchor (a connector hop between floors), kept as structured legs. Each leg
reads "turn …, walk about N m through the door into X": the turn is the heading change at the current space's
anchor, from "door we came in by → anchor" to "anchor → next door", taken from the plan geometry. Turns are relative, so no compass or north reference is needed; the first leg and the first leg after a
floor change have no heading to turn from ("straight"). Distances are straight segments between those points, the
same "about N m" as `BuildingMap.directions`, not the route cost."""

import math

from core.building_map import DOOR_PREFIX, OUTSIDE, BuildingMap

STRAIGHT_DEG = 25.0  # |turn| below this reads as "straight on"
SHARP_DEG = 120.0  # |turn| above this reads as "turn around"


def turn_word(degrees: float | None) -> str:
    """Signed heading change (positive = left, building plan frame x→east, y→north) → a word for arrows."""
    if degrees is None or abs(degrees) < STRAIGHT_DEG:
        return "straight"
    if abs(degrees) > SHARP_DEG:
        return "back"
    return "left" if degrees > 0 else "right"


def heading_change(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float | None:
    """Degrees from heading a→b to heading b→c (positive = left); None when a segment has no length."""
    first = (b[0] - a[0], b[1] - a[1])
    second = (c[0] - b[0], c[1] - b[1])
    if math.hypot(*first) < 1e-6 or math.hypot(*second) < 1e-6:
        return None
    cross = first[0] * second[1] - first[1] * second[0]
    dot = first[0] * second[0] + first[1] * second[1]
    return math.degrees(math.atan2(cross, dot))


def route_legs(building: BuildingMap, space_path: list[str], element_path: list[str]) -> list[dict]:
    """[{kind, to, to_id, floor, distance_m, turn, turn_deg, via?, via_kind?, up?, floors?}, …] ending with "arrive".

    kind: "door" (through an opening into the next space), "connector" (stairs/lift; `up`, `floors` when it spans
    more than one), "exit" (leave the building), "arrive". `turn` (left/right/straight/back) is made at the start of
    the leg; `distance_m` is the route model's walk (kit 1.1.0, door to door round corners): inside the current
    space from where we entered it to this door, plus — when the next space is the destination or a stair/lift stop
    — the walk from the door to that space's centre, like the kit's step text. Door legs + stair/lift costs = the
    route's length. `floor` is the floor name of the space the leg ends in."""
    if not space_path:
        return []
    legs: list[dict] = []
    spaces = iter(space_path[1:])
    current = space_path[0]
    here = building.anchor(current) if current != OUTSIDE else None
    entered: tuple[float, float] | None = None  # the door we came in through: heading entered → here
    entry = current  # route node we entered `current` at: its centre, or "door:<id>"
    index = 0
    while index < len(element_path):
        element = element_path[index]
        target = next(spaces)
        after = building.anchor(target) if target != OUTSIDE else None
        if element in building.openings:
            index += 2 if element_path[index + 1: index + 2] == [element] else 1
            opening = building.openings[element]
            door = tuple(opening["position"])
            node = DOOR_PREFIX + element
            walked = walk_m(building, current, entry, node)
            following = element_path[index] if index < len(element_path) else None
            if target != OUTSIDE and (following is None or following in building.connectors):
                walked += walk_m(building, target, node, target)  # on to the centre: the end, or a stair/lift stop
            entry = node
            degrees = heading_change(entered, here, door) if entered is not None and here is not None else None
            legs.append({"kind": "exit" if target == OUTSIDE else "door",
                         "to": "outside" if target == OUTSIDE else building.spaces[target]["name"], "to_id": target,
                         "floor": None if target == OUTSIDE else floor_of(building, target),
                         "distance_m": round(walked, 1), "turn": turn_word(degrees),
                         "turn_deg": None if degrees is None else round(degrees),
                         "via": element, "via_kind": opening["kind"]})
            entered = door
        else:
            index += 1
            connector = building.connectors.get(element, {})
            legs.append({"kind": "connector", "to": building.spaces[target]["name"], "to_id": target,
                         "floor": floor_of(building, target), "distance_m": 0.0, "turn": "straight",
                         "turn_deg": None, "via": connector.get("name", element),
                         "via_kind": connector.get("kind", "connector"),
                         "up": elevation(building, target) >= elevation(building, current)})
            entered = None  # a new floor: no heading to turn from
            entry = target  # stairs and lifts join the stops' centres
        here, current = after, target
    last = space_path[-1]
    legs.append({"kind": "arrive", "to": "outside" if last == OUTSIDE else building.spaces[last]["name"],
                 "to_id": last, "floor": None if last == OUTSIDE else floor_of(building, last),
                 "distance_m": 0.0, "turn": "straight", "turn_deg": None})
    return merge_connector_hops(legs)


def walk_m(building: BuildingMap, space_id: str, first: str, second: str) -> float:
    """Route-model metres walked inside `space_id` between two of its nodes (its id = centre, "door:<id>")."""
    if space_id == OUTSIDE or first == second:
        return 0.0
    return next((length for a, b, length in building.space_walks(space_id) if {a, b} == {first, second}), 0.0)


def floor_of(building: BuildingMap, space_id: str) -> str:
    return building.floor_name(building.spaces[space_id]["floor_id"])


def elevation(building: BuildingMap, space_id: str) -> float:
    return building.floors[building.spaces[space_id]["floor_id"]]["elevation_m"] if space_id != OUTSIDE else 0.0


def merge_connector_hops(legs: list[dict]) -> list[dict]:
    """Ground → 3 by stairs is one instruction, not three: consecutive hops on one connector become one leg
    (`floors` = how many floors it spans)."""
    merged: list[dict] = []
    for leg in legs:
        last = merged[-1] if merged else None
        if (leg["kind"] == "connector" and last and last["kind"] == "connector" and last["via"] == leg["via"]
                and last["up"] == leg["up"]):
            merged[-1] = {**leg, "floors": last.get("floors", 1) + 1}
        else:
            merged.append(leg)
    return merged


# ---------- spoken/written steps for the Guide ----------
# The kit's step text ("Walk about 26 m through the door into Corridor 0.01", with ids on the first and last line)
# has no turns and no landmarks. These steps come from the same legs: a relative turn, a rounded distance, the
# door, and the most recognisable item standing next to that door, so a person can follow them on the spot.

# Asset types a person notices while walking, most recognisable first; furniture like chairs and desks is not.
LANDMARK_TYPES = (
    "reception_desk", "vending_machine", "coffee_machine", "water_dispenser", "multifunction_printer", "printer",
    "display_screen", "defibrillator", "3d_printer", "industrial_3d_printer", "laser_cutter", "press_brake",
    "conveyor", "compressor", "forklift_charging_station", "coordinate_measuring_machine", "kitchen_counter",
    "lectern", "bench", "plant", "coat_rack", "whiteboard", "fire_extinguisher",
)
LANDMARK_RADIUS_M = 4.0  # an item further than this from the door doesn't mark it
TURN_PHRASE = {"left": "Turn left and walk", "right": "Turn right and walk", "back": "Turn around and walk",
               "straight": "Walk"}
DOOR_WORD = {"door": "door", "entrance": "entrance", "opening": "opening"}
FLOOR_COUNT = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def about_m(metres: float) -> int:
    """How a person says a distance: whole metres below 10, then steps of 5, then of 10 from 100 (half up)."""
    step = 1 if metres < 10 else 5 if metres < 100 else 10
    return max(1, int(math.floor(metres / step + 0.5)) * step)


def landmark(building: BuildingMap, opening_id: str) -> str | None:
    """The most recognisable landmark-type asset within LANDMARK_RADIUS_M of the opening, in a space it joins."""
    opening = building.openings[opening_id]
    door = opening["position"]
    found = [(LANDMARK_TYPES.index(asset["type"]), math.dist(door, asset["position"][:2]), asset["type"])
             for asset in building.assets.values()
             if asset["type"] in LANDMARK_TYPES and asset["space_id"] in opening["space_ids"]
             and math.dist(door, asset["position"][:2]) <= LANDMARK_RADIUS_M]
    return min(found)[2].replace("_", " ").replace("3d ", "3D ") if found else None


def guidance_steps(building: BuildingMap, space_path: list[str], element_path: list[str]) -> list[str]:
    """Followable steps for a route: turn, rounded metres, the door and a landmark next to it; one line per
    staircase or lift ride; no ids. The start line, then the `text` of each `guidance` step."""
    if not space_path:
        return []
    start = space_path[0]
    first = ("Start outside the building." if start == OUTSIDE
             else f"Start in {building.spaces[start]['name']} ({floor_of(building, start)}).")
    return [first] + [step["text"] for step in maneuvers(guidance(building, space_path, element_path))]


def guidance(building: BuildingMap, space_path: list[str], element_path: list[str]) -> list[dict]:
    """The same steps as data, for the app's route bar and step card: [{kind, turn, metres, to, to_id, floor, door?,
    landmark?, via?, via_kind?, up?, floors?, text}, …], one per leg, ending with "arrive"; kind as in `route_legs`.

    The turn is taken where a person makes it: coming through the last door (heading = previous room's anchor →
    that door), which way is the next door. `route_legs` turns at the room's anchor instead, which reads "turn
    around" when the next door is next to the one you came in by. No turn on the first leg or after a ride."""
    if not space_path:
        return []
    steps: list[dict] = []
    behind: tuple[float, float] | None = None  # a point before the last door, on the walking line through it
    entered: tuple[float, float] | None = None  # the last door we came through
    current = space_path[0]
    for leg in route_legs(building, space_path, element_path):
        base = {"kind": leg["kind"], "to": leg["to"], "to_id": leg["to_id"], "floor": leg["floor"]}
        if leg["kind"] == "connector":
            floors = leg.get("floors", 1)
            span = f" {FLOOR_COUNT.get(floors, str(floors))} floors" if floors > 1 else ""
            steps.append({**base, "turn": "straight", "metres": 0, "via": leg["via"], "via_kind": leg.get("via_kind"),
                          "up": leg["up"], "floors": floors,
                          "text": f"Take {leg['via']} {'up' if leg['up'] else 'down'}{span} to {leg['floor']}."})
            behind = entered = None
        elif leg["kind"] == "arrive":
            steps.append({**base, "turn": "straight", "metres": 0,
                          "text": "You are now outside the building." if leg["to_id"] == OUTSIDE
                          else f"You have arrived at {leg['to']} ({leg['floor']})."})
        else:
            door_at = tuple(building.openings[leg["via"]]["position"])
            degrees = heading_change(behind, entered, door_at) if behind and entered else None
            turn = turn_word(degrees)
            door = DOOR_WORD.get(leg["via_kind"], "opening")
            mark = landmark(building, leg["via"])
            by = f" (by the {mark})" if mark else ""
            where = "and leave the building" if leg["kind"] == "exit" else f"into {leg['to']}"
            short = leg["distance_m"] < 1
            metres = 0 if short else about_m(leg["distance_m"])
            text = (f"Go through the {door}{by} {where}." if short
                    else f"{TURN_PHRASE[turn]} about {metres} m through the {door}{by} {where}.")
            steps.append({**base, "turn": "straight" if short else turn, "metres": metres, "door": door, "landmark": mark,
                          "distance_m": leg["distance_m"], "text": text})
            behind = building.anchor(current) if current != OUTSIDE else entered
            entered = door_at
        current = leg["to_id"]
    return steps


PLURAL = {"door": "doors", "entrance": "entrances", "opening": "openings"}


def maneuvers(steps: list[dict]) -> list[dict]:
    """`guidance` steps joined into the moves a person makes: a door step straight on, on the same floor, joins the
    step before it ("walk about 6 m through 2 doors into …"), so a new step starts only at a turn, a ride, an exit
    and the arrival. Each step says how many of the route's legs it covers (`legs`), for the app to place it on the
    route line; the landmark is the last door's, where the step ends."""
    out: list[dict] = []
    for step in steps:
        last = out[-1] if out else None
        if (last and step["kind"] == "door" and step["turn"] == "straight" and last["kind"] == "door"
                and last["floor"] == step["floor"]):
            doors = last["doors"] + 1
            distance = last["distance_m"] + step["distance_m"]
            metres = about_m(distance) if distance >= 1 else 0
            mark = step.get("landmark")
            by = f" (the last one by the {mark})" if mark else ""
            through = f"through {doors} {PLURAL.get(step['door'], 'openings')}"
            text = (f"Go {through} into {step['to']}{by}." if not metres
                    else f"{TURN_PHRASE[last['turn']]} about {metres} m {through} into {step['to']}{by}.")
            out[-1] = {**last, "to": step["to"], "to_id": step["to_id"], "metres": metres, "distance_m": distance,
                       "door": step["door"], "landmark": mark, "doors": doors, "legs": last["legs"] + 1, "text": text}
        else:
            out.append({**step, "distance_m": step.get("distance_m", 0.0), "doors": 1 if step["kind"] in ("door", "exit") else 0,
                        "legs": 1})
    return out
