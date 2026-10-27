"""What the live world does to a viewer's route: blocked walks, the replacement route and a detour no longer
needed (GET /live)."""

import math
import time

from shapely.geometry import LineString, Point

from backend.core.building_map import DOOR_PREFIX, BuildingMap, door_landing, outline
from backend.core.live import LiveEffects
from backend.core.routeline import route_nodes

from backend.api.live.world import REROUTE_GAIN_M, SUGGEST_EVERY_S, LiveWorld, blockers, corners_inside


def route_walks(building: BuildingMap, space_path: list[str], element_path: list[str]) -> list[tuple[str, str, str]]:
    """The walks of a drawn route as (space, first node, second node) in route-graph node names: door to door through
    a space, anchor to door where a route starts (or leaves a lift / stairs), door to anchor where it ends."""
    nodes = route_nodes(building, space_path, element_path)
    walks = []
    for index, (kind, node) in enumerate(nodes):
        if kind != "space":
            continue
        before = nodes[index - 1] if index > 0 and nodes[index - 1][0] == "door" else None
        after = nodes[index + 1] if index + 1 < len(nodes) and nodes[index + 1][0] == "door" else None
        if before and after:
            walks.append((node, DOOR_PREFIX + before[1], DOOR_PREFIX + after[1]))
        elif before:
            walks.append((node, DOOR_PREFIX + before[1], node))
        elif after:
            walks.append((node, node, DOOR_PREFIX + after[1]))
    return walks


def route_blocked(building: BuildingMap, live: LiveEffects, event: dict) -> list[str]:
    """Obstacle ids that now cut a walk of the route on the map (endpoints count as reached from any free door)."""
    space_path = event.get("space_path") or []
    if not space_path:
        return []
    endpoints = {space_path[0], space_path[-1]}
    cut = []
    try:
        walks = route_walks(building, space_path, event.get("element_path") or [])
    except (KeyError, StopIteration):
        return []
    for space_id, first, second in walks:
        cut += live.cut(space_id, first, second, endpoints) or []
    return list(dict.fromkeys(cut))


def blocks(items: list[dict]) -> str:
    """"… blocks" / "… block" for what `names` says."""
    plural = len(items) > 1 or items[0]["name"].split(" · ")[0].endswith("s")
    return "block" if plural else "blocks"


def visible(devices: list[dict], spaces: set[str] | None) -> list[dict]:
    """Devices outside every space or in one of `spaces` (None = all)."""
    if spaces is None:
        return devices
    return [item for item in devices if item["position"]["space_id"] in spaces or item["position"]["space_id"] is None]


def names(items: list[dict]) -> str:
    return ", ".join(f"{item['name'].split(' · ')[0].lower() if item['kind'] in ('pallet', 'cart', 'pallet_jack') else item['name']}"
                     f"{' in ' + item['space'] if item.get('space') else ''}" for item in items)


def live_check(conversation, world: LiveWorld, save) -> dict:
    """The route on this viewer's map against what is reported now: `reroute` (a new route event, already in the
    session's events, when the route on the map just got cut), `alert` (cut with no way round; once per blocker set)
    or `suggestion` (a detour that is no longer needed). Skipped while a Guide turn holds the conversation."""
    session = conversation.session
    route = session.shown_route()
    if route is None or session.live is None:
        return {}
    request = route.get("request")  # what was asked: the route can be asked again (backend/agents/tools/routing.py reroute)
    if not conversation.lock.acquire(blocking=False):
        return {}
    try:
        live = session.live_effects()
        blocked = route_blocked(session.building, live, route) if live is not None else []
        end = (request or {}).get("destination") or (route.get("space_path") or [None])[-1]
        destination = session.building.spaces.get(end, {}).get("name", "the exit" if end == "outside" else "there")
        if blocked:
            who = live.describe(blocked)
            new = session.reroute(request) if request else None
            if new and new.get("reachable"):
                start = new["from_space_id"]
                event = {"type": "route", "space_path": new["space_path"], "element_path": new["element_path"],
                         "length_m": new["length_m"], "profile": session.profile.describe(),
                         **session.start_point(start), **({"live": new["live"]} if new.get("live") else {}),
                         "reroute": {"by": who, "was_m": route.get("length_m")}, "request": request,
                         **({"next_building": route["next_building"]} if route.get("next_building") else {})}
                longer = round(new["length_m"] - (route.get("length_m") or new["length_m"]))
                message = (f"{names(who)[:1].upper()}{names(who)[1:]} now {blocks(who)} the way — new route to {destination}"
                           + (f", about {longer} m longer." if longer > 0 else "."))
                enriched = conversation.view.enrich(session, [event])[0]
                if not enriched.get("line"):  # a path the map can't draw: keep the route shown, say what blocks
                    return {"alert": {"by": who, "message": message}}
                session.events.append(event)
                conversation.guide.live_note = (f"[live note, from the app] {message} The map shows the new route "
                                                f"(about {round(new['length_m'])} m); the step card starts again.")
                try:
                    save(conversation)
                except Exception:  # noqa: BLE001 — a conflict only loses the note, the route is still sent
                    pass
                return {"reroute": {**enriched, "message": message}}
            key = (route.get("length_m"), tuple(sorted(blocked)))
            if getattr(session, "live_alerted", None) != key:
                session.live_alerted = key
                return {"alert": {"by": who, "message": f"{names(who)[:1].upper()}{names(who)[1:]} {blocks(who)} the way to "
                                                        f"{destination} and there is no way round right now. It usually "
                                                        "moves on soon."}}
            return {}
        if request and (route.get("live") or {}).get("avoided"):
            if time.time() - getattr(session, "live_suggest_at", 0.0) < SUGGEST_EVERY_S:
                return {}
            session.live_suggest_at = time.time()
            new = session.reroute(request)
            if new and new.get("reachable") and new["length_m"] < (route.get("length_m") or 0) - REROUTE_GAIN_M:
                blocking = blockers(session.building, live) if live is not None else {}
                gone = [item for item in route["live"]["avoided"] if item["id"] not in blocking]
                if gone:
                    return {"suggestion": {"message": f"The way past {names(gone)} is clear again — about "
                                                      f"{round(route['length_m'] - new['length_m'])} m shorter.",
                                           "save_m": round(route["length_m"] - new["length_m"], 1)}}
        return {}
    finally:
        conversation.lock.release()


def take_shorter(conversation) -> dict | None:
    """The viewer took the suggestion: the route on the map asked again under what is reported now, as a new
    route event."""
    session = conversation.session
    route = session.shown_route()
    request = (route or {}).get("request")
    new = session.reroute(request) if request else None
    if not new or not new.get("reachable"):
        return None
    event = {"type": "route", "space_path": new["space_path"], "element_path": new["element_path"],
             "length_m": new["length_m"], "profile": session.profile.describe(),
             **session.start_point(new["from_space_id"]), **({"live": new["live"]} if new.get("live") else {}),
             "request": request, **({"next_building": route["next_building"]} if route.get("next_building") else {})}
    session.events.append(event)
    return event


def blocking_spot(world: LiveWorld, building: BuildingMap, route: dict) -> tuple[str, float, float, float, float] | None:
    """Where pallets would cut the route on the map: the middle of its longest walk through a walkway (not its start
    or end space), with the width across that walkway there."""
    space_path = route.get("space_path") or []
    try:
        walks = route_walks(building, space_path, route.get("element_path") or [])
    except (KeyError, StopIteration):
        return None
    best = None
    for space_id, first, second in walks:
        if space_id in (space_path[0], space_path[-1]) or not (first.startswith(DOOR_PREFIX) and second.startswith(DOOR_PREFIX)):
            continue
        a = tuple(building.openings[first.removeprefix(DOOR_PREFIX)]["position"])
        b = tuple(building.openings[second.removeprefix(DOOR_PREFIX)]["position"])
        polygon = outline(building.spaces[space_id]["polygon"])
        points = [door_landing(polygon, a), *corners_inside(building.spaces[space_id]["polygon"], a, b), door_landing(polygon, b)]
        for p, q in zip(points, points[1:]):
            length = math.dist(p, q)
            if best is None or length > best[0]:
                best = (length, space_id, p, q)
    if best is None or best[0] < 2.5:
        return None
    _, space_id, p, q = best
    x, y = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    heading = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
    polygon = outline(building.spaces[space_id]["polygon"])
    normal = (-math.sin(math.radians(heading)), math.cos(math.radians(heading)))
    cross = LineString([(x - normal[0] * 50, y - normal[1] * 50), (x + normal[0] * 50, y + normal[1] * 50)]).intersection(polygon)
    pieces = list(getattr(cross, "geoms", [cross]))
    here = Point(x, y)
    piece = min(pieces, key=lambda item: item.distance(here)) if pieces else None
    width = piece.length if piece is not None and not piece.is_empty else 2.4
    if width > 6:  # a hall: pallets can't cut it, a row of them still makes people go round
        width = 6
    centre = piece.centroid if piece is not None and not piece.is_empty else here
    return building.spaces[space_id]["floor_id"], round(centre.x, 3), round(centre.y, 3), round(heading, 1), round(max(0.8, width - 0.3), 2)
