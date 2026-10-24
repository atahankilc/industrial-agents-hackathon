"""Turn the words a person uses into building ids, and run a question for every plausible reading.

The Guide must never guess which room or lift is meant. `resolve_*` return every candidate, `fan_out` runs the
same lookup for each and lets code (not the model) decide: identical answers collapse to one, different answers
come back as an `ambiguous` list of options (at most MAX_OPTIONS) for the model to ask about."""

import difflib
import itertools
import json
from collections.abc import Callable

from core.building_map import BuildingMap, MapError
from core.question_parser import ParseError, Resolver
from core.solvers import label

MAX_OPTIONS = 5
LEADING_WORDS = ("the ", "a ", "room ")
CONNECTOR_KINDS = {
    **dict.fromkeys(("stair", "stairs", "staircase", "staircases", "stairway", "stairways"), "stairs"),
    **dict.fromkeys(("lift", "lifts", "elevator", "elevators"), "lift"),
}


def strip_leading(text: str) -> str:
    lowered = text.strip().lower()
    changed = True
    while changed:
        changed = False
        for word in LEADING_WORDS:
            if lowered.startswith(word):
                lowered, changed = lowered[len(word):].strip(), True
    return lowered


def unique(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def resolve_places(bmap: BuildingMap, text: str) -> list[str]:
    """Candidate space ids for a place phrase: id, ref/name, asset type, asset name, then free search."""
    phrase = text.strip()
    if phrase in bmap.spaces:
        return [phrase]
    if phrase in bmap.assets:
        return [bmap.assets[phrase]["space_id"]]
    wanted = strip_leading(phrase)
    exact = [s["id"] for s in bmap.spaces.values()
             if wanted in ((s.get("ref") or "").lower(), s["name"].lower())]
    if exact:
        return unique(exact)
    try:
        asset_type = Resolver(bmap).asset_type(wanted)
    except ParseError:
        pass
    else:
        return sorted({a["space_id"] for a in bmap.assets.values() if a["type"] == asset_type})
    named = [a["space_id"] for a in bmap.assets.values() if a["name"].lower() == wanted]
    if named:
        return unique(named)
    hits = bmap.search(wanted)
    return unique([h["id"] if h["kind"] == "space" else bmap.assets[h["id"]]["space_id"] for h in hits])


def resolve_elements(bmap: BuildingMap, text: str) -> list[str]:
    """Connector or opening ids a phrase can mean: one exact id/name, else every connector of that kind."""
    wanted = strip_leading(text)
    for element in (*bmap.connectors.values(), *bmap.openings.values()):
        if wanted in (element["id"].lower(), (element.get("name") or "").lower()):
            return [element["id"]]
    words = wanted.split()
    if not words:
        return []
    kind = CONNECTOR_KINDS.get(words[-1])
    return sorted(c["id"] for c in bmap.connectors.values() if c["kind"] == kind)


def nearest_names(bmap: BuildingMap, text: str, n: int = 3) -> list[str]:
    names = {s["name"] for s in bmap.spaces.values()}
    names |= {s["ref"] for s in bmap.spaces.values() if s.get("ref")}
    names |= {a["name"] for a in bmap.assets.values()}
    return difflib.get_close_matches(text.strip(), sorted(names), n=n, cutoff=0.6)


def describe(bmap: BuildingMap, element_id: str) -> dict:
    """Uniform {id, name, ref, floor, kind} for a space, vertical connector or opening (bare id if unknown)."""
    if element_id in bmap.spaces:
        space = label(bmap, element_id)
        return {"id": element_id, "name": space["name"], "ref": space["ref"], "floor": space["floor"],
                "kind": bmap.spaces[element_id]["room_type"]}
    if element_id in bmap.connectors:
        connector = bmap.connectors[element_id]
        floors = ", ".join(bmap.floor_name(floor_id) for floor_id in connector["floor_ids"])
        return {"id": element_id, "name": connector["name"], "ref": None, "floor": floors, "kind": connector["kind"]}
    if element_id not in bmap.openings:
        return {"id": element_id, "name": element_id, "ref": None, "floor": None, "kind": None}
    opening = bmap.openings[element_id]
    return {"id": element_id, "name": element_id, "ref": None, "floor": bmap.floor_name(opening["floor_id"]),
            "kind": opening["kind"]}


def run_safely(run: Callable[[dict[str, str]], dict], choice: dict[str, str]) -> dict:
    try:
        return run(choice)
    except (MapError, ValueError) as error:
        return {"status": "error", "summary": str(error)}


def fan_out(bmap: BuildingMap, slots: dict[str, list[str]], run: Callable[[dict[str, str]], dict]) -> dict:
    """Run `run` for every combination of candidates; collapse identical answers, else list the options."""
    for slot, candidates in slots.items():
        if not candidates:
            return {"status": "not_found", "slot": slot}
    names = list(slots)
    combos = [dict(zip(names, values, strict=True)) for values in itertools.product(*slots.values())]
    if len(combos) > MAX_OPTIONS:
        options = [{"choices": {slot: describe(bmap, i) for slot, i in combo.items()}}
                   for combo in combos[:MAX_OPTIONS]]
        return {"status": "ambiguous", "options": options, "truncated": True}
    results = [run_safely(run, combo) for combo in combos]
    if len({json.dumps(r, sort_keys=True) for r in results}) == 1:
        return {"status": "ok", **results[0]}
    varying = [slot for slot in names if len(slots[slot]) > 1]
    options = [{"choices": {slot: describe(bmap, combo[slot]) for slot in varying}, "result": result}
               for combo, result in zip(combos, results, strict=True)]
    return {"status": "ambiguous", "options": options}
