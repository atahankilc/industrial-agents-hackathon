"""LLM question parser: Claude reads the question and returns the raw slot text; code resolves it to ids.

Claude never produces ids or numbers we score on. It fills the same slots the regex templates capture
(core/question_parser.py), choosing names from the building's own vocabulary, and the shared Resolver turns
them into ids. A resolution error is sent back once so the model can correct its slot text."""

import json
import os
from dataclasses import dataclass

import anthropic

from core.building_map import BuildingMap
from core.question_parser import ANSWER_INSTRUCTION, ParsedQuestion, ParseError, Resolver

MODEL = os.environ.get("PARSER_LLM_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("PARSER_LLM_EFFORT", "medium")
MAX_TOKENS = 16000
MAX_ATTEMPTS = 2
FALLBACK_BETA = "server-side-fallback-2026-07-01"
KINDS = [
    "largest_room",
    "floor_area_total",
    "errand",
    "shared_walls_count",
    "wide_delivery_count",
    "straight_line_3d",
    "room_stacked",
    "step_free_reachable_count",
    "what_if_door",
    "locate",
    "count",
    "route",
    "route_step_free",
    "route_with_closure",
    "tour",
    "unsupported",
]
NULLABLE_TEXT = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_NUMBER = {"anyOf": [{"type": "number"}, {"type": "null"}]}
SPACE_SLOT = {
    "anyOf": [
        {
            "type": "object",
            "properties": {"name": {"type": "string"}, "floor": {"type": "string"}},
            "required": ["name", "floor"],
            "additionalProperties": False,
        },
        {"type": "null"},
    ]
}
SPACE = SPACE_SLOT["anyOf"][0]
SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": KINDS},
        "start": SPACE_SLOT,
        "first": SPACE_SLOT,
        "second": SPACE_SLOT,
        "destination": SPACE_SLOT,
        "stops": {"anyOf": [{"type": "array", "items": SPACE}, {"type": "null"}]},
        "floor": NULLABLE_TEXT,
        "room_type": NULLABLE_TEXT,
        "asset_type": NULLABLE_TEXT,
        "min_width_m": NULLABLE_NUMBER,
        "item": NULLABLE_TEXT,
        "closed": NULLABLE_TEXT,
        "direction": {"anyOf": [{"type": "string", "enum": ["above", "below"]}, {"type": "null"}]},
        "may_use_stairs": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
    },
    "required": [
        "kind", "start", "first", "second", "destination", "stops", "floor", "room_type", "asset_type",
        "min_width_m", "item", "closed", "direction", "may_use_stairs",
    ],
    "additionalProperties": False,
}

INSTRUCTIONS = """You turn one question about a building into structured slots. You do not answer it.

Kinds and the slots each needs (every other slot is null):
- largest_room: room_type, floor. "Which is the largest <room type> on <floor>?"
- floor_area_total: room_type, floor. Total floor area of every <room type> on <floor>.
- errand: start, asset_type, room_type, floor, may_use_stairs. From start, fetch the nearest <asset type>, carry
  it to the largest <room type> on <floor>; total walking distance.
- shared_walls_count: start. How many rooms on the same floor share a wall with start.
- wide_delivery_count: start (the room the entrance opens into), min_width_m, item, floor. How many rooms on
  <floor> a wide load can reach without stairs or steps.
- straight_line_3d: first, second. Straight-line distance between the two room centres.
- room_stacked: start, direction ("above" if something comes from the ceiling / the room above, "below" if it
  leaks down to the room below).
- step_free_reachable_count: closed (the lift or stair out of service), start, floor. Rooms on <floor> a
  wheelchair user can still reach.
- what_if_door: first, second (the two spaces the new door joins), floor (the floor whose rooms are counted).
- locate: asset_type. Where is a piece of equipment ("Where is the coffee machine?").
- count: asset_type, floor. How many items of that type are on <floor>.
- route: start, destination. How to get from start to destination.
- route_step_free: start, destination. The same without stairs or steps (wheelchair, trolley, "step-free").
- route_with_closure: closed (the lift or stair that is closed), start, destination.
- tour: start, stops (the spaces visited in between, in order), destination (the last one).
- unsupported: anything else.

Rules:
- Copy every name, floor, room type, asset type and lift/stair name EXACTLY from the building vocabulary below
  (the canonical spelling, e.g. room_type "meeting_room", floor "Floor 1"). Never invent one.
- A space slot is {"name": <space name as listed>, "floor": <floor name as listed>}.
- Numbers only for min_width_m, in metres as written in the question."""


@dataclass
class LlmUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def building_vocabulary(building_map: BuildingMap) -> str:
    floors = sorted(building_map.floors.values(), key=lambda floor: floor["level"])
    lines = ["Floors: " + "; ".join(floor["name"] for floor in floors)]
    lines.append("Room types: " + ", ".join(sorted({s["room_type"] for s in building_map.spaces.values()})))
    lines.append("Asset types: " + ", ".join(sorted({a["type"] for a in building_map.assets.values()})))
    lines.append("Lifts and stairs: " + "; ".join(sorted(c["name"] for c in building_map.connectors.values())))
    for floor in floors:
        names = sorted({s["name"] for s in building_map.spaces.values() if s["floor_id"] == floor["id"]})
        lines.append(f"Spaces on {floor['name']}: " + "; ".join(names))
    return "\n".join(lines)


def slots_to_groups(slots: dict) -> tuple[str, dict[str, str | None]]:
    """Map the LLM's slots onto the Resolver's regex-group names."""
    kind = slots["kind"]
    if kind == "unsupported":
        raise ParseError("The LLM parser classified the question as unsupported")
    groups: dict[str, str | None] = {}
    for slot in ("start", "first", "second", "destination"):
        if slots.get(slot):
            groups[slot] = slots[slot]["name"]
            groups[f"{slot}_floor"] = slots[slot]["floor"]
    if kind == "tour":
        groups["stops"] = [(stop["name"], stop["floor"]) for stop in slots.get("stops") or []]
    for slot in ("floor", "room_type", "asset_type", "item", "closed"):
        groups[slot] = slots.get(slot)
    if slots.get("min_width_m") is not None:
        groups["min_width"] = str(slots["min_width_m"])
        groups["item"] = groups["item"] or "load"
    if kind == "errand":
        groups["carry"] = "I can carry it on the stairs" if slots.get("may_use_stairs") is not False else (
            "I can't use the stairs"
        )
    template_name = kind
    if kind == "room_stacked":
        if slots.get("direction") not in ("above", "below"):
            raise ParseError("room_stacked needs direction above or below")
        template_name = f"room_stacked_{slots['direction']}"
    return template_name, groups


class LlmQuestionParser:
    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.usage = LlmUsage()

    def parse(self, text: str, building_map: BuildingMap) -> ParsedQuestion:
        system = [
            {"type": "text", "text": INSTRUCTIONS},
            {
                "type": "text",
                "text": "Building vocabulary:\n" + building_vocabulary(building_map),
                "cache_control": {"type": "ephemeral"},
            },
        ]
        messages: list[dict] = [{"role": "user", "content": ANSWER_INSTRUCTION.sub("", text.strip())}]
        error: ParseError | None = None
        for _ in range(MAX_ATTEMPTS):
            reply = self.request(system, messages)
            try:
                template_name, groups = slots_to_groups(json.loads(reply))
                parsed = Resolver(building_map).build(template_name, groups)
                parsed.notes["parser"] = "llm"
                return parsed
            except (ParseError, KeyError, TypeError) as caught:
                error = ParseError(str(caught))
                messages += [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"Those slots could not be resolved: {caught}. Correct them."},
                ]
        raise error or ParseError("LLM parser failed")

    def request(self, system: list[dict], messages: list[dict]) -> str:
        response = self.client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self.track(response.usage)
        if response.stop_reason == "refusal":
            raise ParseError("The model declined to parse the question")
        if response.stop_reason == "max_tokens":
            raise ParseError("The parser response was cut off")
        return next(block.text for block in response.content if block.type == "text")

    def track(self, usage: object) -> None:
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cache_read_input_tokens += usage.cache_read_input_tokens or 0
        self.usage.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0
