"""Deterministic parser for benchmark questions: question text + building → kind and resolved parameters.

The benchmark questions (questions.jsonl) and the warm-up questions (questions_basic.jsonl: locate, count, route,
route_step_free, route_with_closure, tour) are generated from one template per kind. Each template is a regex whose named groups
are resolved against the building (space names → space ids, floor phrases → floor ids, type phrases → room or
asset types). The parameter keys match the `inputs` dict in the train/dev question files.

Measured accuracy and the template table: docs/research/question-parsing.md."""

import re
from dataclasses import dataclass, field

from core.building_map import BuildingMap

ANSWER_INSTRUCTION = re.compile(r"\s*Finish with a line 'Answer:.*$", flags=re.DOTALL)
SPACE = r"(?P<{name}>.+?) \((?P<{name}_floor>Ground floor|Floor -?\d+|Basement \d+)\)"
FLOOR_PHRASE = r"(?:the )?(?P<{name}>ground floor|floor -?\d+|basement \d+)"
TYPE_PHRASE = r"(?P<{name}>[a-z][a-z0-9 ]*?)"


def space(name: str) -> str:
    return SPACE.format(name=name)


def floor(name: str) -> str:
    return FLOOR_PHRASE.format(name=name)


def type_phrase(name: str) -> str:
    return TYPE_PHRASE.format(name=name)


TEMPLATES: dict[str, re.Pattern] = {
    kind: re.compile(pattern, flags=re.IGNORECASE)
    for kind, pattern in {
        "largest_room": rf"^Which is the largest {type_phrase('room_type')} on {floor('floor')}, "
        r"and how big is it in m²\?$",
        "floor_area_total": rf"^Facilities want the total floor area of every {type_phrase('room_type')} on "
        rf"{floor('floor')} added together\. How many square metres is that\?$",
        "errand": rf"^I'm in {space('start')}\. I need to grab an? {type_phrase('asset_type')} from the room "
        rf"that has one closest to me, then carry it to the largest {type_phrase('room_type')} on "
        rf"{floor('floor')}\. (?P<carry>[^.]*)\. How far will I walk in total, in metres\?$",
        "shared_walls_count": rf"^We're soundproofing {space('start')}\. How many other rooms on that floor "
        r"share a wall with it\?",
        "wide_delivery_count": r"^I'm moving an? (?P<width>\d+(?:\.\d+)?) m wide (?P<item>[^.]+?)\. "
        r"It can't go on stairs or steps \(lifts are fine\), and every door it passes through must be at "
        rf"least (?P<min_width>\d+(?:\.\d+)?) m wide\. It arrives through the entrance into {space('start')}\. "
        rf"Into how many rooms on {floor('floor')} can it be delivered\?$",
        "straight_line_3d": rf"^We're planning a wireless sensor link between {space('first')} and "
        rf"{space('second')}\. What is the straight-line distance",
        "room_stacked_above": rf"^There's water dripping from the ceiling in {space('start')}\. "
        r"Which room is directly above it\?$",
        "room_stacked_below": rf"^A washing machine is leaking onto the floor of {space('start')}\. "
        r"Which room directly below it will the water reach\?$",
        "step_free_reachable_count": r"^(?P<closed>.+?) is out of service\. A wheelchair user comes in through "
        rf"the entrance into {space('start')}\. How many rooms on {floor('floor')} can they still reach\?$",
        "what_if_door": rf"^What if we add a door between {space('first')} and {space('second')}, in the "
        rf"middle of the wall they share\? How many rooms on {floor('floor')} would then have a shorter walk "
        r"out of the building, to their nearest entrance, by more than 1 m\?$",
        # warm-up kinds (questions_basic.jsonl)
        "locate": rf"^Where is (?:the |an? )?{type_phrase('asset_type')}\?$",
        "count": rf"^How many {type_phrase('asset_type')} items are on {floor('floor')}\?$",
        "route": rf"^How do I get from {space('start')} to {space('destination')}\?$",
        "route_step_free": rf"^Is there a step-free route from {space('start')} to {space('destination')}\?$",
        "route_with_closure": rf"^(?P<closed>.+?) is closed for maintenance\. How do I get from {space('start')} "
        rf"to {space('destination')}\?$",
        "tour": rf"^Starting at {space('start')}, visit (?P<stops>.+), then {space('destination')} in this order\. "
        r"What is the route\?$",
    }.items()
}
STOP = re.compile(SPACE.format(name="stop"), flags=re.IGNORECASE)


class ParseError(ValueError):
    """The text matches no template, or a slot names nothing in this building."""


@dataclass
class ParsedQuestion:
    kind: str
    params: dict[str, object]
    notes: dict[str, str] = field(default_factory=dict)
    alternatives: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ambiguous(self) -> bool:
        """The text names a space that several spaces share (OSM duplicates); params holds the first one."""
        return bool(self.alternatives)


def parse_question(text: str, building_map: BuildingMap) -> ParsedQuestion:
    body = ANSWER_INSTRUCTION.sub("", text.strip())
    for template_name, template in TEMPLATES.items():
        match = template.search(body)
        if match:
            return Resolver(building_map).build(template_name, match.groupdict())
    raise ParseError(f"No template matches: {body[:120]}")


def normalise(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").split())


class Resolver:
    def __init__(self, building_map: BuildingMap) -> None:
        self.map = building_map
        self.alternatives: dict[str, list[str]] = {}

    def build(self, template_name: str, groups: dict[str, str | None]) -> ParsedQuestion:
        """Resolve raw slot text (regex groups, or the same slots extracted by the LLM parser) to ids."""
        kind = template_name.removesuffix("_above").removesuffix("_below")
        params: dict[str, object] = {}
        notes: dict[str, str] = {}
        for slot in ("start", "first", "second", "destination"):
            if groups.get(slot) is not None:
                candidates = self.space_ids(groups[slot], groups[f"{slot}_floor"])
                params[slot] = candidates[0]
                if len(candidates) > 1:
                    self.alternatives[slot] = candidates
        if groups.get("stops") is not None:
            params["stops"] = [params["start"], *self.stop_ids(groups["stops"]), params["destination"]]
        if groups.get("closed") is not None:
            params["closed"] = self.connector_id(groups["closed"])
        if groups.get("asset_type") is not None:
            params["asset_type"] = self.asset_type(groups["asset_type"])
        if groups.get("floor") is not None:
            params["floor_id"] = self.floor_id(groups["floor"])
        if groups.get("room_type") is not None:
            params["room_type"] = self.room_type(groups["room_type"])
        if groups.get("min_width") is not None:
            params["min_width"] = float(groups["min_width"])
            notes["item"] = groups["item"]
        if kind == "room_stacked":
            params["direction"] = template_name.rsplit("_", 1)[1]
        if kind == "what_if_door":
            params["door_floor_id"] = self.map.spaces[params["first"]]["floor_id"]
        if groups.get("carry") is not None:
            notes["carry"] = groups["carry"]
            params["step_free"] = "stairs" not in groups["carry"].lower() or "can't" in groups["carry"].lower()
        return ParsedQuestion(
            kind, {key: value for key, value in params.items() if value is not None}, notes, self.alternatives
        )

    def floor_id(self, phrase: str) -> str:
        wanted = normalise(phrase)
        matches = [floor_id for floor_id, floor in self.map.floors.items() if normalise(floor["name"]) == wanted]
        if len(matches) != 1:
            raise ParseError(f"Floor '{phrase}' matches {len(matches)} floors")
        return matches[0]

    def space_ids(self, name: str, floor_phrase: str) -> list[str]:
        """Spaces on that floor with this name, best match first; several only when names truly repeat."""
        floor_id = self.floor_id(floor_phrase)
        on_floor = [space for space in self.map.spaces.values() if space["floor_id"] == floor_id]
        for candidates in (
            [space for space in on_floor if space["name"] == name],
            [space for space in on_floor if normalise(space["name"]) == normalise(name)],
            [space for space in on_floor if (space.get("ref") or "") == name],
        ):
            if candidates:
                return sorted(space["id"] for space in candidates)
        raise ParseError(f"No space named '{name}' on {floor_phrase}")

    def stop_ids(self, stops: str | list[tuple[str, str]]) -> list[str]:
        """Intermediate tour stops: "A (Floor 1), B (Ground floor)" from the regex, or (name, floor) pairs."""
        if isinstance(stops, str):
            stops = [(match["stop"], match["stop_floor"]) for match in STOP.finditer(stops)]
        if not stops:
            raise ParseError("A tour needs at least one stop between start and destination")
        resolved = []
        for index, (name, floor_phrase) in enumerate(stops):
            candidates = self.space_ids(name, floor_phrase)
            resolved.append(candidates[0])
            if len(candidates) > 1:
                self.alternatives[f"stop{index + 1}"] = candidates
        return resolved

    def connector_id(self, name: str) -> str:
        matches = [
            connector_id
            for connector_id, connector in self.map.connectors.items()
            if normalise(connector["name"]) == normalise(name)
        ]
        if len(matches) != 1:
            raise ParseError(f"Connector '{name}' matches {len(matches)} connectors")
        return matches[0]

    def room_type(self, phrase: str) -> str:
        return self.type_from(phrase, {space["room_type"] for space in self.map.spaces.values()}, "room type")

    def asset_type(self, phrase: str) -> str:
        """Exact or plural type first; then the label people use: the start of the asset names ("air compressor"
        → compressor, name "Air compressor H-C2") or the end of the type ("seating row" → lecture_seating_row)."""
        known = {asset["type"] for asset in self.map.assets.values()}
        try:
            return self.type_from(phrase, known, "asset type")
        except ParseError:
            wanted = normalise(phrase)
            for matches in (
                {asset["type"] for asset in self.map.assets.values() if normalise(asset["name"]).startswith(wanted + " ")
                 or normalise(asset["name"]) == wanted},
                {kind for kind in known if normalise(kind).endswith(" " + wanted)},
            ):
                if len(matches) == 1:
                    return matches.pop()
            raise

    @staticmethod
    def type_from(phrase: str, known: set[str], label: str) -> str:
        wanted = normalise(phrase)
        for candidate in (wanted, wanted.removesuffix("s"), wanted.removesuffix("es")):
            if candidate.replace(" ", "_") in known:
                return candidate.replace(" ", "_")
        raise ParseError(f"Unknown {label} '{phrase}'")
