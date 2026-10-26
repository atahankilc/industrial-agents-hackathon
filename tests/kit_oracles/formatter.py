"""SolverResult → reply text ending in the exact `Answer:` line the benchmark scorer parses (D-003).

Number answer lines carry only the number (and maybe a unit): room refs on the same line are numbers too and
would break `tests/kit_oracles/score.py`. See archive/hackathon/docs/challenge/scoring.md#formatting-pitfalls-cost-real-points."""

from backend.core.building_map import BuildingMap
from backend.core.solvers import SolverResult

SPACE_KINDS = {"largest_room", "room_stacked"}


def space_label(building: BuildingMap, space_id: str) -> str:
    """Ref first: it is in every train+dev `accept` list, while repeated OSM names (e.g. "Büro") are not.
    The name follows in parentheses for humans; the ref already comes before any runner-up mention."""
    space = building.spaces[space_id]
    ref = space.get("ref")
    if ref and ref != space["name"]:
        return f"{ref} ({space['name']})"
    return space["name"]


def number_text(value: float | int) -> str:
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def answer_line(building: BuildingMap, result: SolverResult) -> str:
    if result.kind == "largest_room":
        return f"Answer: {space_label(building, result.value)}, {result.area_m2:.2f} m²"
    if result.kind in SPACE_KINDS:
        return f"Answer: {space_label(building, result.value)}"
    unit = f" {result.unit}" if result.unit else ""
    return f"Answer: {number_text(result.value)}{unit}"


def format_reply(building: BuildingMap, result: SolverResult) -> str:
    return "\n".join([*result.explanation, answer_line(building, result)])
