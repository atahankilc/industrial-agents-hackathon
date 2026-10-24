"""Guide tools: every fact the agent states comes back from one of these functions.

Each tool turns the model's words into ids with `resolve.py`, runs the deterministic core, and returns a dict with
a `status` and a one-sentence `summary` written by code. The model never sees an id it must invent and never does
arithmetic: several readings of a name go through `fan_out`, so code decides whether they differ."""

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field

from agent.guide.resolve import describe, fan_out, nearest_names, resolve_elements, resolve_places, strip_leading
from core.building_map import BuildingMap, MapError
from core.question_parser import ParseError, Resolver, normalise
from core.solvers import area, label, room_stacked, shared_walls, solve
from core.solvers import route as core_route

MAX_HITS = 10
MAX_ASSET_NAMES = 15
NULLABLE_TEXT = {"anyOf": [{"type": "string"}, {"type": "null"}]}
TEXT_LIST = {"type": "array", "items": {"type": "string"}}  # [] = none; strict mode allows <= 16 unions
FACT_KINDS = [
    "largest_room", "floor_area_total", "count", "shared_walls_count", "room_stacked", "straight_line_3d",
    "errand", "wide_delivery_count", "step_free_reachable_count", "what_if_door",
]


@dataclass
class Session:
    position: str | None = None
    step_free: bool = False
    closures: list[list[str]] = field(default_factory=list)  # candidate element ids per stated closure


def tool(name: str, description: str, properties: dict) -> dict:
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": properties, "required": list(properties),
                             "additionalProperties": False}}


TOOLS = [
    tool("locate", "List every room that holds a kind of equipment or a named item, with counts.",
         {"thing": {"type": "string"}}),
    tool("find_places", "Search rooms and equipment by words in their name, ref or type, optionally on one floor.",
         {"query": {"type": "string"}, "floor": NULLABLE_TEXT}),
    tool("place_info", "Facts about one room: area, equipment, neighbours, what is above and below.",
         {"place": {"type": "string"}}),
    tool("building_fact",
         "Measured building facts. kind and the arguments it needs: largest_room(floor, room_type); "
         "floor_area_total(floor, room_type); count(asset_type, floor); shared_walls_count(place); "
         "room_stacked(place, direction); straight_line_3d(place, place2); errand(place, asset_type, floor, "
         "room_type, step_free): nearest asset of that type, then the largest room of that type on the floor; "
         "wide_delivery_count(place, floor, min_width_m); step_free_reachable_count(place, floor, closed); "
         "what_if_door(place, place2, floor): a new door between place and place2 and the rooms on floor that get "
         "closer to an exit. Arguments a kind does not need are null.",
         {"kind": {"type": "string", "enum": FACT_KINDS}, "place": NULLABLE_TEXT, "place2": NULLABLE_TEXT,
          "floor": NULLABLE_TEXT, "room_type": NULLABLE_TEXT, "asset_type": NULLABLE_TEXT,
          "direction": {"anyOf": [{"type": "string", "enum": ["above", "below"]}, {"type": "null"}]},
          "min_width_m": {"anyOf": [{"type": "number"}, {"type": "null"}]}, "closed": NULLABLE_TEXT,
          "step_free": {"anyOf": [{"type": "boolean"}, {"type": "null"}]}}),
    tool("route",
         "Shortest route to a place. `from` null uses the user's current position; step_free null uses the session "
         "setting. Session closures are applied. via lists stops to pass through in order ([] for none).",
         {"to": {"type": "string"}, "from": NULLABLE_TEXT, "via": TEXT_LIST,
          "step_free": {"anyOf": [{"type": "boolean"}, {"type": "null"}]}}),
    tool("update_session",
         "Remember what the user tells you: where they are, whether they need step-free access, and lifts or stairs "
         "that are closed (close) or open again (reopen); doors only by their id. Later routes use this state. "
         "Null / [] leaves a field unchanged. All or nothing: if any part fails, nothing is saved.",
         {"position": NULLABLE_TEXT, "step_free": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
          "close": TEXT_LIST, "reopen": TEXT_LIST}),
]


class Unresolved(Exception):
    """A floor / room type / asset type phrase that matches nothing; becomes a `not_found` result."""

    def __init__(self, text: str, what: str, known: set[str]) -> None:
        super().__init__(f"No {what} matches '{text}'.")
        self.text, self.what = text, what
        self.nearest = difflib.get_close_matches(normalise(text), sorted(known), n=3, cutoff=0.5)


def resolve_floor(bmap: BuildingMap, text: str) -> str:
    try:
        return Resolver(bmap).floor_id(text)
    except ParseError:
        raise Unresolved(text, "floor", {f["name"] for f in bmap.floors.values()}) from None


def resolve_type(bmap: BuildingMap, text: str, what: str) -> str:
    resolver = Resolver(bmap)
    try:
        return resolver.room_type(text) if what == "room type" else resolver.asset_type(text)
    except ParseError:
        spaces = {s["room_type"] for s in bmap.spaces.values()}
        known = spaces if what == "room type" else {a["type"] for a in bmap.assets.values()}
        raise Unresolved(text, what, {k.replace("_", " ") for k in known}) from None


def need(args: dict, key: str):
    value = args.get(key)
    if value is None or value == "":
        raise ValueError(f"missing argument '{key}'")
    return value


def named(bmap: BuildingMap, space_id: str) -> str:
    info = label(bmap, space_id)
    ref = f" ({info['ref']})" if info["ref"] else ""
    return f"{info['name']}{ref} on {info['floor']}"


def slot_text(out: dict, slots: dict[str, list[str]], texts: dict[str, str | None]) -> str:
    """The user's words for the slot(s) a fan_out result is about: the one not found, else the ones that vary."""
    keys = [out["slot"]] if out["status"] == "not_found" else [k for k, ids in slots.items() if len(ids) > 1]
    return "' and '".join(t for k in keys if (t := texts.get(k))) or "' and '".join(t for t in texts.values() if t)


def not_found(bmap: BuildingMap, text: str, what: str) -> dict:
    nearest = nearest_names(bmap, text)
    hint = f" Closest names: {', '.join(nearest)}." if nearest else ""
    return {"status": "not_found", "nearest": nearest, "summary": f"No {what} matches '{text}'.{hint}"}


# ---------- locate / find_places ----------

def matching_assets(bmap: BuildingMap, thing: str) -> list[dict]:
    thing = strip_leading(thing)
    wanted = normalise(thing)
    try:
        asset_type = Resolver(bmap).asset_type(thing)
    except ParseError:
        asset_type = None
    assets = list(bmap.assets.values())
    if asset_type:
        return [a for a in assets if a["type"] == asset_type]
    exact = [a for a in assets if normalise(a["name"]) == wanted]
    if exact:
        return exact
    words = wanted.split()
    return [a for a in assets if all(w in normalise(a["name"]) for w in words)] if words else []


def locate(bmap: BuildingMap, session: Session, args: dict) -> dict:
    thing = need(args, "thing")
    found = matching_assets(bmap, thing)
    if not found:
        return not_found(bmap, thing, "equipment")
    by_space: dict[str, list[str]] = {}
    for asset in sorted(found, key=lambda a: a["id"]):
        by_space.setdefault(asset["space_id"], []).append(asset["name"])
    spaces = sorted(by_space, key=lambda s: (bmap.floors[bmap.spaces[s]["floor_id"]]["level"],
                                             bmap.spaces[s].get("ref") or "", s))
    rooms = [{**describe(bmap, s), "count": len(by_space[s]), "assets": by_space[s]} for s in spaces]
    places = "; ".join(f"{named(bmap, s)} x{len(by_space[s])}" for s in spaces)
    return {"status": "ok", "total": len(found), "rooms": rooms,
            "summary": f"'{thing}': {len(found)} in {len(rooms)} room(s): {places}."}


def find_places(bmap: BuildingMap, session: Session, args: dict) -> dict:
    query = need(args, "query")
    floor = args.get("floor")
    level = bmap.floors[resolve_floor(bmap, floor)]["level"] if floor else None
    hits = bmap.search(query, level)[:MAX_HITS]
    if not hits:
        return not_found(bmap, query, "place or equipment")
    described = []
    for hit in hits:
        if hit["kind"] == "space":
            described.append({"kind": "space", **describe(bmap, hit["id"])})
        else:
            asset = bmap.assets[hit["id"]]
            described.append({"kind": "asset", "id": asset["id"], "name": asset["name"], "type": asset["type"],
                              "in": describe(bmap, asset["space_id"])})
    where = "; ".join(f"{h['name']} ({h['in']['name']}, {h['in']['floor']})" if h["kind"] == "asset"
                      else f"{h['name']} ({h['ref'] or h['kind']}, {h['floor']})" for h in described)
    return {"status": "ok", "hits": described, "summary": f"{len(described)} match(es) for '{query}': {where}."}


# ---------- place_info ----------

def neighbour_in_direction(bmap: BuildingMap, space_id: str, direction: str) -> str | None:
    try:
        return room_stacked(bmap, space_id, direction)["name"]
    except ValueError:
        return None


def place_facts(bmap: BuildingMap, space_id: str) -> dict:
    info = describe(bmap, space_id)
    assets = sorted(a["name"] for a in bmap.assets.values() if a["space_id"] == space_id)
    walls = shared_walls(bmap, space_id)
    facts = {**info, "area_m2": round(area(bmap, space_id), 2), "assets": assets[:MAX_ASSET_NAMES],
             "assets_total": len(assets), "shared_walls": walls["count"],
             "neighbours": [r["name"] for r in walls["rooms"]],
             "above": neighbour_in_direction(bmap, space_id, "above"),
             "below": neighbour_in_direction(bmap, space_id, "below")}
    ref = f" ({info['ref']})" if info["ref"] else ""
    facts["summary"] = (f"{info['name']}{ref} on {info['floor']} is {facts['area_m2']} m², holds {len(assets)} "
                        f"asset(s) and shares a wall with {walls['count']} room(s).")
    return facts


def place_info(bmap: BuildingMap, session: Session, args: dict) -> dict:
    place = need(args, "place")
    out = fan_out(bmap, {"place": resolve_places(bmap, place)}, lambda c: place_facts(bmap, c["place"]))
    return finish(bmap, out, place, "place", lambda choice, facts: (facts.pop("summary"), facts))


def finish(bmap: BuildingMap, out: dict, text: str, what: str,
           unwrap: Callable[[dict, dict], tuple[str, dict]]) -> dict:
    """One shape for every tool: not_found gets nearest names; ambiguous options become
    {choices, summary, result} (`unwrap` splits a candidate's payload into its summary and flat result).
    Truncated options (too many readings to run) keep only their choices."""
    if out["status"] == "not_found":
        return not_found(bmap, text, what)
    if out["status"] != "ambiguous":
        return out
    for option in out["options"]:
        if "result" not in option:
            continue
        payload = option["result"]
        if payload.get("status") == "error":
            option["summary"] = payload["summary"]
            del option["result"]
        else:
            option["summary"], option["result"] = unwrap(option["choices"], payload)
    if out.get("truncated"):
        shown = "; ".join(", ".join(named(bmap, c["id"]) if c["id"] in bmap.spaces else c["name"]
                                    for c in o["choices"].values()) for o in out["options"])
        out["summary"] = f"'{text}' matches too many {what}s to compare; the first {len(out['options'])} are: {shown}."
    else:
        out["summary"] = f"'{text}' could mean {len(out['options'])} different {what}s with different answers."
    return out


# ---------- building_fact ----------

def floor_of(bmap: BuildingMap, args: dict) -> str:
    return resolve_floor(bmap, need(args, "floor"))


def place_slots(bmap: BuildingMap, args: dict, **keys: str) -> dict[str, list[str]]:
    return {slot: resolve_places(bmap, need(args, arg)) for slot, arg in keys.items()}


def fact_plan(bmap: BuildingMap, kind: str, args: dict) -> tuple[dict[str, list[str]], dict]:
    """(candidate ids per slot, fixed solver inputs) for a kind."""
    if kind in ("largest_room", "floor_area_total"):
        return {}, {"floor_id": floor_of(bmap, args), "room_type": resolve_type(bmap, need(args, "room_type"), "room type")}
    if kind == "count":
        return {}, {"asset_type": resolve_type(bmap, need(args, "asset_type"), "asset type"), "floor_id": floor_of(bmap, args)}
    if kind == "shared_walls_count":
        return place_slots(bmap, args, start="place"), {}
    if kind == "room_stacked":
        return place_slots(bmap, args, start="place"), {"direction": need(args, "direction")}
    if kind == "straight_line_3d":
        return place_slots(bmap, args, first="place", second="place2"), {}
    if kind == "errand":
        return place_slots(bmap, args, start="place"), {
            "asset_type": resolve_type(bmap, need(args, "asset_type"), "asset type"), "floor_id": floor_of(bmap, args),
            "room_type": resolve_type(bmap, need(args, "room_type"), "room type"), "step_free": bool(args.get("step_free"))}
    if kind == "wide_delivery_count":
        return place_slots(bmap, args, start="place"), {"floor_id": floor_of(bmap, args),
                                                       "min_width": float(need(args, "min_width_m"))}
    if kind == "step_free_reachable_count":
        closed = need(args, "closed")
        return {**place_slots(bmap, args, start="place"), "closed": resolve_elements(bmap, closed)}, {
            "floor_id": floor_of(bmap, args)}
    if kind == "what_if_door":
        return place_slots(bmap, args, first="place", second="place2"), {"floor_id": floor_of(bmap, args)}
    raise ValueError(f"unknown kind '{kind}'")


def solver_inputs(bmap: BuildingMap, kind: str, fixed: dict, choice: dict[str, str]) -> dict:
    inputs = {**fixed, **choice}
    if kind == "what_if_door":
        inputs["door_floor_id"] = bmap.spaces[choice["first"]]["floor_id"]
    return inputs


def plain(text: str) -> str:
    return text.replace("_", " ")


def fact_summary(bmap: BuildingMap, kind: str, inputs: dict, result: dict) -> str:
    floor = bmap.floor_name(inputs["floor_id"]) if "floor_id" in inputs else None
    at = {slot: named(bmap, inputs[slot]) for slot in ("start", "first", "second") if slot in inputs}
    if kind == "largest_room":
        ref = f" ({result['ref']})" if result["ref"] else ""
        return (f"The largest {plain(inputs['room_type'])} on {floor} is {result['name']}{ref} "
                f"at {result['area_m2']} m².")
    if kind == "floor_area_total":
        return (f"{floor} has {result['count']} {plain(inputs['room_type'])} space(s) totalling "
                f"{result['total_m2']} m².")
    if kind == "count":
        return f"{floor} has {result['count']} {plain(inputs['asset_type'])}."
    if kind == "shared_walls_count":
        return f"{at['start']} shares a wall with {result['count']} room(s)."
    if kind == "room_stacked":
        return (f"Directly {inputs['direction']} {at['start']} is {named(bmap, result['space_id'])} "
                f"(overlap {result['overlap_m2']} m²).")
    if kind == "straight_line_3d":
        return f"The straight-line distance from {at['first']} to {at['second']} is {result['distance_m']} m."
    if kind == "errand":
        return (f"From {at['start']}: {result['first_leg_m']} m to {named(bmap, result['via']['space_id'])} "
                f"({plain(inputs['asset_type'])}), then {result['second_leg_m']} m to "
                f"{named(bmap, result['target']['space_id'])}; {result['total_m']} m in total.")
    if kind == "wide_delivery_count":
        return (f"{result['count']} room(s) on {floor} are reachable from {at['start']} step-free through "
                f"doors at least {inputs['min_width']} m wide.")
    if kind == "step_free_reachable_count":
        return (f"{result['count']} room(s) on {floor} are reachable step-free from {at['start']} with "
                f"{describe(bmap, inputs['closed'])['name']} closed.")
    return (f"A new door between {at['first']} and {at['second']} would shorten the way to an exit for "
            f"{result['count']} room(s) on {floor}.")


def building_fact(bmap: BuildingMap, session: Session, args: dict) -> dict:
    kind = need(args, "kind")
    slots, fixed = fact_plan(bmap, kind, args)

    def run(choice: dict[str, str]) -> dict:
        return {"result": solve(bmap, kind, solver_inputs(bmap, kind, fixed, choice))}

    def unwrap(choices: dict, payload: dict) -> tuple[str, dict]:
        full = {slot: choices[slot]["id"] if slot in choices else candidates[0] for slot, candidates in slots.items()}
        return fact_summary(bmap, kind, solver_inputs(bmap, kind, fixed, full), payload["result"]), payload["result"]

    texts = {"start": args.get("place"), "first": args.get("place"), "second": args.get("place2"),
             "closed": args.get("closed")}
    out = fan_out(bmap, slots, run)
    if out["status"] == "ok":
        choice = {slot: candidates[0] for slot, candidates in slots.items()}
        out["summary"] = fact_summary(bmap, kind, solver_inputs(bmap, kind, fixed, choice), out["result"])
        return out
    return finish(bmap, out, slot_text(out, slots, texts), "place", unwrap)


# ---------- route / update_session ----------

def route_summary(bmap: BuildingMap, combo: dict[str, str], step_free: bool, result: dict, closed: list[str]) -> str:
    start, end = named(bmap, combo["from"]), named(bmap, combo["to"])
    if not result["reachable"]:
        kind = "step-free " if step_free else ""
        suffix = " with the current closures" if closed else ""
        return f"No {kind}route from {start} to {end}{suffix}."
    extras = (", step-free" if step_free else "") + (f", avoiding {', '.join(closed)}" if closed else "")
    return f"{start} → {end}: {round(result['optimal_length_m'])} m{extras}."


def route(bmap: BuildingMap, session: Session, args: dict) -> dict:
    start_text, end = args.get("from"), need(args, "to")
    if not start_text and not session.position:
        return {"status": "need_start", "summary": "Ask where the user is starting from."}
    step_free = session.step_free if args.get("step_free") is None else bool(args["step_free"])
    via_texts = list(args.get("via") or [])
    slots = {"from": resolve_places(bmap, start_text) if start_text else [session.position],
             "to": resolve_places(bmap, end),
             **{f"via{i}": resolve_places(bmap, t) for i, t in enumerate(via_texts)},
             **{f"closure{i}": ids for i, ids in enumerate(session.closures)}}
    texts = {"from": start_text, "to": end, **{f"via{i}": t for i, t in enumerate(via_texts)}}
    saved = set(bmap.closed)

    def run(combo: dict[str, str]) -> dict:
        bmap.closed = saved | {v for k, v in combo.items() if k.startswith("closure")}
        try:
            vias = [combo[f"via{i}"] for i in range(len(via_texts))]
            return {"result": core_route(bmap, combo["from"], combo["to"], step_free=step_free, via=vias or None)}
        finally:
            bmap.closed = saved

    def closed_names(choices: dict) -> list[str]:
        """Each closure by the name it is known by: the chosen reading, else every candidate it could be."""
        return [describe(bmap, choices[slot]["id"])["name"] if slot in choices else
                " / ".join(describe(bmap, i)["name"] for i in candidates)
                for slot, candidates in slots.items() if slot.startswith("closure")]

    def full(choices: dict) -> dict[str, str]:
        return {slot: choices[slot]["id"] if slot in choices else candidates[0] for slot, candidates in slots.items()}

    out = fan_out(bmap, slots, run)
    if out["status"] == "ok":
        combo = full({})
        out.update({"summary": route_summary(bmap, combo, step_free, out["result"], closed_names({})), "from": describe(bmap, combo["from"]),
                    "to": describe(bmap, combo["to"]), "step_free": step_free,
                    "closed": closed_names({})})
        return out
    if out["status"] == "not_found":
        return not_found(bmap, texts[out["slot"]], "place")
    out = finish(bmap, out, slot_text(out, slots, texts), "place",
                 lambda choices, payload: (route_summary(bmap, full(choices), step_free, payload["result"], closed_names(choices)),
                                payload["result"]))
    if not out.get("truncated") and all(k.startswith("closure") for o in out["options"] for k in o["choices"]):
        out["summary"] = f"A closed lift or stairs is unclear: {len(out['options'])} readings give different routes."
    return out


def state_names(bmap: BuildingMap, session: Session) -> dict:
    return {"position": describe(bmap, session.position) if session.position else None,
            "step_free": session.step_free,
            "closed": [[describe(bmap, i)["name"] for i in ids] for ids in session.closures]}


def state_summary(bmap: BuildingMap, session: Session) -> str:
    where = named(bmap, session.position) if session.position else "unknown"
    closed = "; ".join(" or ".join(names) for names in state_names(bmap, session)["closed"]) or "none"
    return f"Position: {where}. Step-free: {'yes' if session.step_free else 'no'}. Closed: {closed}."


NOTHING_SAVED = "Nothing was saved; call update_session again with all fields once this is resolved."


def update_session(bmap: BuildingMap, session: Session, args: dict) -> dict:
    """All or nothing: every part is checked before any is saved, and a failure says so in its summary."""
    out = apply_session_update(bmap, session, args)
    if out["status"] != "ok":
        out["summary"] = f"{out['summary']} {NOTHING_SAVED}"
    return out


def apply_session_update(bmap: BuildingMap, session: Session, args: dict) -> dict:
    position = args.get("position")
    reopening = []
    for phrase in args.get("reopen") or []:
        ids = set(resolve_elements(bmap, phrase))
        if not ids:
            return not_found(bmap, phrase, "lift or stairs")
        if not any(ids & set(c) for c in session.closures):
            return {"status": "not_closed", "summary": f"'{phrase}' is not among the closures I know about, so there is nothing to reopen."}
        reopening.append(ids)
    if position:
        out = fan_out(bmap, {"position": resolve_places(bmap, position)}, lambda c: {"result": {"position": c["position"]}})
        if out["status"] != "ok":
            return finish(bmap, out, position, "place", lambda choices, payload: (
                f"Position could be {named(bmap, choices['position']['id'])}.", payload["result"]))
    closing = []
    for phrase in args.get("close") or []:
        ids = resolve_elements(bmap, phrase)
        if not ids:
            return not_found(bmap, phrase, "lift or stairs")
        closing.append(ids)
    if position:
        session.position = out["result"]["position"]
    if args.get("step_free") is not None:
        session.step_free = bool(args["step_free"])
    for ids in reopening:
        session.closures = [c for c in session.closures if not ids & set(c)]
    session.closures.extend(closing)
    return {"status": "ok", "session": state_names(bmap, session), "summary": state_summary(bmap, session)}


HANDLERS: dict[str, Callable[[BuildingMap, Session, dict], dict]] = {
    "locate": locate,
    "find_places": find_places,
    "place_info": place_info,
    "building_fact": building_fact,
    "route": route,
    "update_session": update_session,
}


def run_tool(bmap: BuildingMap, session: Session, name: str, args: dict) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        return {"status": "error", "summary": f"Unknown tool '{name}'."}
    try:
        return handler(bmap, session, args)
    except Unresolved as error:
        nearest = error.nearest
        hint = f" Closest: {', '.join(nearest)}." if nearest else ""
        return {"status": "not_found", "nearest": nearest, "summary": f"{error}{hint}"}
    except (ValueError, KeyError, TypeError, MapError) as error:
        return {"status": "error", "summary": f"Could not run {name}: {error}"}
