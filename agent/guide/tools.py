"""Guide tools: every fact the agent states comes back from one of these functions.

Each tool turns the model's words into ids with `resolve.py`, runs the deterministic core, and returns a dict with
a `status` and a one-sentence `summary` written by code. The model never sees an id it must invent and never does
arithmetic: several readings of a name go through `fan_out`, so code decides whether they differ."""

import difflib
from collections.abc import Callable
from dataclasses import dataclass, field

from agent.guide.resolve import describe, fan_out, nearest_names, resolve_elements, resolve_places
from core.building_map import BuildingMap, MapError
from core.question_parser import ParseError, Resolver, normalise
from core.solvers import area, label, room_stacked, shared_walls, solve

MAX_HITS = 10
MAX_ASSET_NAMES = 15
NULLABLE_TEXT = {"anyOf": [{"type": "string"}, {"type": "null"}]}
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


def not_found(bmap: BuildingMap, text: str, what: str) -> dict:
    nearest = nearest_names(bmap, text)
    hint = f" Closest names: {', '.join(nearest)}." if nearest else ""
    return {"status": "not_found", "nearest": nearest, "summary": f"No {what} matches '{text}'.{hint}"}


# ---------- locate / find_places ----------

def matching_assets(bmap: BuildingMap, thing: str) -> list[dict]:
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

    text = str(args.get("place") or args.get("closed") or "")
    out = fan_out(bmap, slots, run)
    if out["status"] == "ok":
        choice = {slot: candidates[0] for slot, candidates in slots.items()}
        out["summary"] = fact_summary(bmap, kind, solver_inputs(bmap, kind, fixed, choice), out["result"])
        return out
    return finish(bmap, out, text, "place", unwrap)


HANDLERS: dict[str, Callable[[BuildingMap, Session, dict], dict]] = {
    "locate": locate,
    "find_places": find_places,
    "place_info": place_info,
    "building_fact": building_fact,
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
