"""Benchmark entry point: question text → parser → solver → reply ending in a deterministic `Answer:` line.

  uv run python -m benchmark.evaluate data/dev --agent agent.answer:answer

The answer line follows benchmark/score.py (D-003): number kinds carry exactly one number (a room ref such as
"1.02" would count as a second number, so refs stay on the explanation lines); space kinds name the room by its
ref, which every train/dev `accept` list contains, and largest_room adds the area. Warm-up kinds: locate names the
room and floor, count gives the number, routes give the step-by-step directions and the length (or "no route")."""

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from agent.parsing import QuestionUnderstanding
from core.building_map import BuildingMap
from core.question_parser import ParsedQuestion, ParseError
from core.solvers_v1 import solve


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def room(result: dict) -> str:
    return f"{result['name']} ({result['ref']}, {result['floor']})"


def explain(kind: str, params: dict, result: dict) -> tuple[str, str]:
    """(explanation, answer-line text) for a solver result."""
    if kind == "largest_room":
        return (f"The largest {params['room_type'].replace('_', ' ')} is {room(result)} "
                f"at {result['area_m2']:.2f} m².", f"{result['ref']}, {result['area_m2']:.2f} m²")
    if kind == "room_stacked":
        return (f"The room directly {params['direction']} it is {room(result)} "
                f"({result['overlap_m2']:.2f} m² of overlap).", result["ref"])
    if kind == "floor_area_total":
        return (f"{result['count']} rooms of that type add up to {result['total_m2']:.2f} m².",
                f"{result['total_m2']:.2f} m²")
    if kind == "straight_line_3d":
        return f"Centre to centre, through floors and walls: {result['distance_m']:.2f} m.", f"{result['distance_m']:.2f} m"
    if kind == "errand":
        return (f"Nearest one is in {room(result['via'])}, {result['first_leg_m']:.2f} m away; from there to "
                f"{room(result['target'])} is {result['second_leg_m']:.2f} m.", f"{result['total_m']:.2f} m")
    if kind == "locate":
        return (f"The {result['asset_name']} ({result['asset_id']}) is in {room(result)}.",
                f"{result['name']} ({result['ref']}), {result['floor']}")
    if kind == "count":
        return f"{result['count']} {params['asset_type'].replace('_', ' ')} items on that floor.", str(result["count"])
    if kind in ("route", "route_step_free", "route_with_closure", "tour"):
        if not result["reachable"]:
            return result["reason"], "no step-free route" if kind == "route_step_free" else "no route"
        return "\n".join(result["steps"]), f"{result['optimal_length_m']:.2f} m"
    if kind == "shared_walls_count":
        names = ", ".join(room(neighbour) for neighbour in result["rooms"]) or "none"
        return f"Rooms sharing at least 1 m of wall: {names}.", str(result["count"])
    names = ", ".join(result["rooms"]) or "none"
    return f"Rooms counted: {names}.", str(result["count"])


@dataclass
class Response:
    reply: str
    kind: str | None = None
    params: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None


def reply(parsed: ParsedQuestion, bmap: BuildingMap, result: dict) -> str:
    explanation, committed = explain(parsed.kind, parsed.params, result)
    lines = [explanation]
    for slot, candidates in parsed.alternatives.items():
        refs = ", ".join(bmap.spaces[candidate]["ref"] for candidate in candidates)
        lines.append(f"Note: several rooms share that name ({refs}); I used {bmap.spaces[candidates[0]]['ref']}.")
    return "\n".join([*lines, f"Answer: {committed}"])


def respond(building_directory: Path, question_text: str) -> Response:
    """The reply plus what produced it (kind, resolved ids, solver result) for structured outputs."""
    bmap = building(Path(building_directory))
    try:
        parsed = QuestionUnderstanding().parse(question_text, bmap)
        result = solve(bmap, parsed.kind, parsed.params)
        return Response(reply(parsed, bmap, result), parsed.kind, parsed.params, result)
    except (ParseError, ValueError, KeyError) as error:
        return Response(f"I could not answer this: {error}", error=str(error))


def answer(building_directory: Path, question_text: str) -> str:
    """benchmark.evaluate agent signature: (building directory, question text) → reply text."""
    return respond(building_directory, question_text).reply
