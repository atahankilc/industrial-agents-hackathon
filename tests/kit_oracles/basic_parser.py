"""Deterministic parser for warm-up (navigation) question text → kind + resolved ids.

Covers the six warm-up templates found in every train/dev `questions_basic.jsonl` (locate, count, route,
route_step_free, route_with_closure, tour) plus a few looser phrasings for the same intents, since the Sunday
question wording is unseen. Name → id resolution reuses `Resolver` from tests/kit_oracles/question_parser.py; anything that
matches no pattern raises `ParseError` so the caller can fall back to the LLM parser.

Params (ids, ready for backend/core/navigation.py):
  locate:              query (asset phrase), asset_type (if it resolves), floor_id (optional)
  count:               asset_type, floor_id (None = whole building), asset_type_known=False if no asset has it
  route / route_step_free: start, destination (+ step_free=True when the text asks for it)
  route_with_closure:  closed (element id), start, destination (+ step_free)
  tour:                stops (list of space ids)"""

import copy
import re
from dataclasses import dataclass, field

from backend.core import navigation
from backend.core.building_map import BuildingMap, MapError
from backend.core.navigation import resolve_asset_type
from tests.kit_oracles.question_parser import ANSWER_INSTRUCTION, ParseError, Resolver, normalise
from backend.core.route_models import KIT, NO_RULES, RouteRules

FLOOR_NAME = r"Ground floor|Floor -?\d+|Basement \d+"
# A place: "<name> (<floor name>)" as the generator writes it, or a bare name/ref (looser phrasings).
PLACE = rf"(?P<{{name}}>.+?)(?: \((?P<{{name}}_floor>{FLOOR_NAME})\))?"
FLOOR = r"(?:the )?(?P<floor>ground floor|floor -?\d+|basement \d+|level -?\d+)"
STEP_FREE_HINT = re.compile(r"step[- ]free|wheelchair|without (?:any )?(?:stairs|steps)|accessible", re.IGNORECASE)


def place(name: str) -> str:
    return PLACE.format(name=name)


ROUTE_VERB = (
    r"(?:how (?:do|can|should) i (?:get|go|walk)|(?:give me |show me )?directions|(?:find |show me )?(?:the |a )?"
    r"(?:best |shortest |fastest )?(?:step-free |accessible )?(?:route|way)|what is the (?:best |shortest )?route)"
)
ROUTE_MODIFIER = r"(?: step[- ]free| without (?:any )?(?:stairs|steps)| by wheelchair)?"
ROUTE_TAIL = rf"from {place('start')} to {place('destination')}"
CLOSURE = r"(?P<closed>.+?) (?:is|are) (?:closed|out of service|out of order|blocked|unavailable)[^.]*\.\s*"

PATTERNS: list[tuple[str, re.Pattern]] = [
    (kind, re.compile(pattern, flags=re.IGNORECASE))
    for kind, pattern in [
        (
            "count",
            rf"^how many (?P<asset>.+?)(?: items?)? (?:are|is) (?:there )?(?:on|in) {FLOOR}\s*\??$",
        ),
        ("count", r"^how many (?P<asset>.+?)(?: items?)? (?:are|is) (?:there )?(?:in the building)?\s*\??$"),
        (
            "tour",
            rf"^(?:starting|start) (?:at|from|in) {place('s0')}, (?:visit|go to) {place('s1')},? "
            rf"(?:then|and then) {place('s2')}(?: in this order)?\.(?: what is the route\?)?$",
        ),
        ("route_with_closure", rf"^{CLOSURE}{ROUTE_VERB}{ROUTE_MODIFIER} {ROUTE_TAIL}\s*[?.]?$"),
        ("route_step_free", rf"^is there a step-free route {ROUTE_TAIL}\s*\?$"),
        ("route", rf"^{ROUTE_VERB}{ROUTE_MODIFIER} {ROUTE_TAIL}\s*[?.]?$"),
        ("locate", r"^(?:where is|where are|where can i find|find|locate) (?:the |an? |my )?(?P<query>.+?)\s*\??$"),
    ]
]


@dataclass
class ParsedBasic:
    kind: str
    params: dict[str, object]
    alternatives: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ambiguous(self) -> bool:
        """A place name is shared by several spaces on that floor; params holds the first (sorted) id."""
        return bool(self.alternatives)


def parse_basic(text: str, building: BuildingMap) -> ParsedBasic:
    body = " ".join(ANSWER_INSTRUCTION.sub("", text.strip()).split())
    for kind, pattern in PATTERNS:
        match = pattern.match(body)
        if match:
            return BasicResolver(building).build(kind, match.groupdict(), body)
    raise ParseError(f"No warm-up template matches: {body[:120]}")


class BasicResolver(Resolver):
    def build(self, kind: str, groups: dict[str, str | None], body: str = "") -> ParsedBasic:  # type: ignore[override]
        params: dict[str, object] = {}
        if kind == "locate":
            params["query"] = groups["query"]
            asset_type = resolve_asset_type(self.map, groups["query"])
            if asset_type is not None:
                params["asset_type"] = asset_type
        elif kind == "count":
            asset_type = resolve_asset_type(self.map, groups["asset"])
            if asset_type is None:  # no such asset here: count the singular type phrase (answer 0)
                asset_type = normalise(groups["asset"]).replace(" ", "_").removesuffix("s")
                params["asset_type_known"] = False
            params["asset_type"] = asset_type
            params["floor_id"] = self.floor_id(groups["floor"]) if groups.get("floor") else None
        elif kind == "tour":
            params["stops"] = [self.place(f"s{index}", groups) for index in range(3)]
        else:
            if kind == "route_with_closure":
                params["closed"] = self.element_id(groups["closed"])
            params["start"] = self.place("start", groups)
            params["destination"] = self.place("destination", groups)
            if kind == "route" and STEP_FREE_HINT.search(body):
                kind = "route_step_free"
            if kind == "route_step_free" or STEP_FREE_HINT.search(body):
                params["step_free"] = True
        return ParsedBasic(kind, params, self.alternatives)

    def floor_id(self, phrase: str) -> str:
        level = re.fullmatch(r"(?:the )?level (-?\d+)", phrase.strip(), flags=re.IGNORECASE)
        if level:
            matches = [fid for fid, floor in self.map.floors.items() if floor["level"] == int(level.group(1))]
            if len(matches) == 1:
                return matches[0]
        return super().floor_id(phrase)

    def place(self, slot: str, groups: dict[str, str | None]) -> str:
        name, floor_phrase = groups[slot], groups.get(f"{slot}_floor")
        assert name is not None
        if floor_phrase:
            candidates = self.space_ids(name, floor_phrase)
            if len(candidates) > 1:
                self.alternatives[slot] = candidates
            return candidates[0]
        try:
            return copy.copy(self.map).resolve_space(name.strip())
        except MapError as error:
            raise ParseError(str(error)) from error

    def element_id(self, name: str) -> str:
        """Closable element: connector by name first (the generator's wording), then any id/opening/space."""
        try:
            return self.connector_id(name)
        except ParseError:
            pass
        stripped = re.sub(r"^the ", "", name.strip(), flags=re.IGNORECASE)
        try:
            return copy.copy(self.map).find_element(stripped)
        except MapError as error:
            raise ParseError(f"Unknown closed element '{name}': {error}") from error


def run_parsed(
    parsed: ParsedBasic,
    building: BuildingMap,
    include_steps: bool = True,
    model: str = KIT,
    rules: RouteRules = NO_RULES,
) -> dict:
    """Execute a parsed warm-up question with backend/core/navigation.py; returns the tool result as a dict.

    `model`/`rules` (backend/core/route_models.py): the kit 1.1.0 model without rules reproduces the warm-up gold answers;
    `rules=SUNDAY_RULES` (+ `forklift`) adds the organisers' bay/forklift rules (not in the kit answers). No route
    under the rules → `reachable: false` with a reason starting "no route under these rules"."""
    params = parsed.params
    if parsed.kind == "locate":
        return navigation.locate(building, str(params.get("asset_type") or params["query"])).to_dict()
    if parsed.kind == "count":
        return navigation.count_assets(building, str(params["asset_type"]), params.get("floor_id")).to_dict()  # type: ignore[arg-type]
    step_free = bool(params.get("step_free", False))
    closed = (str(params["closed"]),) if "closed" in params else ()
    if parsed.kind == "tour":
        return navigation.tour(
            building, params["stops"], step_free=step_free, closed=closed, include_steps=include_steps,  # type: ignore[arg-type]
            model=model, rules=rules,
        ).to_dict()
    return navigation.find_route(
        building, str(params["start"]), str(params["destination"]), step_free=step_free, closed=closed,
        include_steps=include_steps, model=model, rules=rules,
    ).to_dict()


def answer_basic(
    text: str, building: BuildingMap, include_steps: bool = True, model: str = KIT, rules: RouteRules = NO_RULES
) -> tuple[ParsedBasic, dict]:
    """Question text → (parse, navigation result). Raises ParseError / MapError."""
    parsed = parse_basic(text, building)
    return parsed, run_parsed(parsed, building, include_steps, model, rules)


__all__ = ["ParseError", "ParsedBasic", "answer_basic", "parse_basic", "run_parsed"]
