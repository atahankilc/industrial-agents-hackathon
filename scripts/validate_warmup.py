"""End-to-end check of the navigation layer on every train/dev warm-up question (questions_basic.jsonl):
question text → tests/kit_oracles/basic_parser.py → backend/core/navigation.py → compare with the gold answer.

  uv run python scripts/validate_warmup.py            # per-kind table
  uv run python scripts/validate_warmup.py -v         # also list every failure and tie

Metrics per kind: parse (kind + resolved ids == gold), answer (locate: top asset; count: number; routes:
reachable flag and length within 1 cm, or equal to the organisers' 1.1.0 starter where the gold differs from it), reachable flag,
length, exact space_path and element_path. A path that
differs from gold but has the same length and whose gold path is a valid walk of that same cost is a *tie* — not
counted wrong for the answer, reported separately. `oracle` = navigation fed the gold ids reproduces the gold
route exactly (or by a verified tie) — isolates navigation from name ambiguity; `ambiguous` = the text names a
space whose name several spaces on that floor share (OSM duplicates such as "Büro"); `gold_in_alternatives` =
parse misses that are exactly such cases (gold id is one of the same-name spaces); `equal_alt` = questions where
some leg has a second exactly-equal shortest path (exact-path match then depends on Dijkstra tie-break order)."""

import argparse
import importlib.util
import itertools
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import networkx as nx

from tests.kit_oracles.basic_parser import ParseError, parse_basic
from backend.core.building_map import BuildingMap, MapError
from backend.core.navigation import (
    RouteAnswer,
    count_assets,
    find_route,
    locate,
    path_length,
    routing_view,
    tour,
)

DATA = ROOT / "data"
STARTER = ROOT / "archive/initial-repo/starter_agent/building_map.py"
LENGTH_TOLERANCE_M = 0.01
ROUTE_KINDS = ("route", "route_step_free", "route_with_closure")
METRICS = ("parse", "answer", "reachable", "length", "space_path", "element_path")


@cache
def building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


def warmup_questions() -> list[tuple[Path, dict]]:
    questions = []
    for path in sorted((DATA / "buildings").glob("*/questions_basic.jsonl")):  # train and dev only
        questions += [(path.parent, json.loads(line)) for line in path.open(encoding="utf-8") if line.strip()]
    return questions


@dataclass
class Outcome:
    kind: str
    checks: dict[str, bool] = field(default_factory=dict)
    tie: bool = False
    ambiguous: bool = False
    gold_in_alternatives: bool = False
    oracle: bool | None = None  # route kinds: navigation output == gold when fed the gold ids
    reference: bool = False  # length = organisers' starter, ≠ gold (see starter_length)
    equal_alternative: bool = False  # some leg has >1 exactly-shortest path (gold matched by tie-break order)
    error: str = ""


def gold_params(question: dict) -> dict:
    answer = question["answer"]
    if question["kind"] == "tour":
        return {"stops": answer["stops"]}
    if question["kind"] in ROUTE_KINDS:
        params = {"start": answer["from_space_id"], "destination": answer["to_space_id"]}
        if "closed_element_id" in answer:
            params["closed"] = answer["closed_element_id"]
        return params
    return {}


def compare_route(
    outcome: Outcome, ours: RouteAnswer, gold: dict, bmap: BuildingMap, step_free: bool, closed: tuple[str, ...]
) -> None:
    gold_reachable = gold.get("reachable", True)
    outcome.checks["reachable"] = ours.reachable == gold_reachable
    if not gold_reachable or not ours.reachable:
        same = ours.reachable == gold_reachable
        for metric in ("length", "space_path", "element_path"):
            outcome.checks[metric] = same
        return
    outcome.checks["length"] = abs(ours.length_m - gold["optimal_length_m"]) <= LENGTH_TOLERANCE_M  # type: ignore[operator]
    if not outcome.checks["length"] and outcome.checks.get("parse", True):
        # Same as the organisers' own 1.1.0 starter but not the gold (resplan-12462, 10 cm): counted as right.
        reference = starter_length(bmap, ours.from_space_id, ours.to_space_id, step_free, closed)
        outcome.reference = abs(reference - ours.length_m) <= LENGTH_TOLERANCE_M  # type: ignore[operator]
        outcome.checks["length"] = outcome.reference
    outcome.checks["space_path"] = ours.space_path == gold["space_path"]
    outcome.checks["element_path"] = ours.element_path == gold["element_path"]
    if outcome.checks["length"] and not (outcome.checks["space_path"] and outcome.checks["element_path"]):
        gold_cost = path_length(bmap, gold["space_path"], gold["element_path"], step_free=step_free, closed=closed)
        outcome.tie = gold_cost is not None and abs(gold_cost - ours.length_m) <= LENGTH_TOLERANCE_M  # type: ignore[operator]


@cache
def starter_module():
    spec = importlib.util.spec_from_file_location("starter_building_map", STARTER)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def starter_length(bmap: BuildingMap, start: str, end: str, step_free: bool, closed: tuple[str, ...]) -> float:
    """The route length by the organisers' kit 1.1.0 starter agent (archive copy), our reference implementation."""
    reference = starter_module().BuildingMap(bmap.data)
    reference.closed = {bmap.find_element(item) for item in closed}
    try:
        return reference.route(start, end, step_free=step_free).length_m
    except ValueError:
        return float("nan")


def gold_among_alternatives(params: dict, alternatives: dict[str, list[str]], expected: dict) -> bool:
    """Every gold id equals the parsed id or is one of the same-name alternatives for that slot."""
    slots = {"stops": ["s0", "s1", "s2"]}
    for key, value in expected.items():
        if key == "stops":
            pairs = [(slot, ours, want) for slot, ours, want in zip(slots["stops"], params.get("stops", []), value)]
        else:
            pairs = [(key, params.get(key), value)]
        for slot, ours, want in pairs:
            if ours != want and want not in alternatives.get(slot, []):
                return False
    return True


def oracle_matches(bmap: BuildingMap, kind: str, expected: dict, gold: dict) -> bool:
    """Navigation alone: fed the gold ids, does it reproduce the gold answer exactly (or by a verified tie)?"""
    closed = (expected["closed"],) if "closed" in expected else ()
    if kind == "tour":
        result = tour(bmap, expected["stops"])
        if gold.get("reachable") is False:  # kit 1.1.0: a tour with an unreachable stop has no legs
            return not result.reachable
        legs = list(zip(result.legs, gold["legs"], strict=True))
    else:
        result = find_route(
            bmap, expected["start"], expected["destination"], step_free=kind == "route_step_free", closed=closed,
            include_steps=False,
        )
        legs = [(result, gold)]
    for ours, gold_leg in legs:
        check = Outcome(kind)
        compare_route(check, ours, gold_leg, bmap, kind == "route_step_free", closed)
        if not (all(check.checks.values()) or check.tie):
            return False
    return True


def has_equal_alternative(bmap: BuildingMap, kind: str, expected: dict) -> bool:
    """Does any leg have a second, equally short path? Then exact-path match relies on Dijkstra's tie-break."""
    view = routing_view(bmap, (expected["closed"],) if "closed" in expected else ())
    graph = view.graph(kind == "route_step_free")
    stops = expected["stops"] if kind == "tour" else [expected["start"], expected["destination"]]
    for first, second in itertools.pairwise(stops):
        try:
            if len(list(itertools.islice(nx.all_shortest_paths(graph, first, second, weight="weight"), 2))) > 1:
                return True
        except nx.NetworkXNoPath:
            continue
    return False


def evaluate_question(directory: Path, question: dict) -> Outcome:
    kind, gold = question["kind"], question["answer"]
    outcome = Outcome(kind)
    bmap = building(directory)
    try:
        parsed = parse_basic(question["question"], bmap)
    except ParseError as error:
        outcome.error = f"ParseError: {error}"
        outcome.checks = {metric: False for metric in METRICS}
        return outcome
    params = parsed.params
    outcome.ambiguous = parsed.ambiguous
    if parsed.kind != kind:
        outcome.checks["parse"] = False
        outcome.error = f"parsed kind {parsed.kind}"
    if kind == "locate":
        result = locate(bmap, params["asset_type"] if "asset_type" in params else params["query"])  # type: ignore[arg-type]
        top = result.assets[0] if result.assets else None
        outcome.checks.setdefault("parse", any(hit.asset_id == gold["asset_id"] for hit in result.assets))
        outcome.checks["answer"] = (
            top is not None
            and top.asset_id == gold["asset_id"]
            and top.space_id == gold["space_id"]
            and top.floor_level == gold["floor_level"]
        )
        return outcome
    if kind == "count":
        floor_id = params.get("floor_id")
        level = bmap.floors[floor_id]["level"] if floor_id else None  # type: ignore[index]
        outcome.checks.setdefault("parse", params["asset_type"] == gold["asset_type"] and level == gold["floor_level"])
        result = count_assets(bmap, params["asset_type"], floor_id)  # type: ignore[arg-type]
        outcome.checks["answer"] = result.count == gold["count"]
        return outcome
    expected = gold_params(question)
    outcome.checks.setdefault("parse", all(params.get(key) == value for key, value in expected.items()))
    if not outcome.checks["parse"] and not outcome.error:
        outcome.error = f"params {params} != gold {expected}"
        outcome.gold_in_alternatives = parsed.ambiguous and gold_among_alternatives(params, parsed.alternatives, expected)
    outcome.oracle = oracle_matches(bmap, kind, expected, gold)
    outcome.equal_alternative = has_equal_alternative(bmap, kind, expected)
    closed = (params["closed"],) if "closed" in params else ()
    try:
        if kind == "tour":
            result = tour(bmap, params["stops"])  # type: ignore[arg-type]
            if gold.get("reachable") is False:  # kit 1.1.0: {"stops", "reachable": false}
                same = not result.reachable
                for metric in ("reachable", "length", "space_path", "element_path"):
                    outcome.checks[metric] = same
                outcome.checks["answer"] = outcome.checks["parse"] and same
                return outcome
            outcome.checks["reachable"] = result.reachable
            legs_ok = [Outcome(kind) for _ in gold["legs"]]
            for leg_outcome, ours, gold_leg in zip(legs_ok, result.legs, gold["legs"], strict=False):
                compare_route(leg_outcome, ours, gold_leg, bmap, False, ())
            if len(result.legs) != len(gold["legs"]):
                legs_ok = [Outcome(kind, {"length": False, "space_path": False, "element_path": False})]
            for metric in ("space_path", "element_path"):
                outcome.checks[metric] = all(item.checks.get(metric, False) for item in legs_ok)
            outcome.checks["length"] = (
                result.length_m is not None
                and (abs(result.length_m - gold["optimal_length_m"]) <= LENGTH_TOLERANCE_M
                     or any(item.reference for item in legs_ok))  # a leg equal to the starter, not the gold
            ) and all(item.checks.get("length", False) for item in legs_ok)
            outcome.tie = any(item.tie for item in legs_ok)
        else:
            step_free = kind == "route_step_free"
            result = find_route(
                bmap, params["start"], params["destination"], step_free=step_free, closed=closed, include_steps=True  # type: ignore[arg-type]
            )
            compare_route(outcome, result, gold, bmap, step_free, closed)
    except MapError as error:
        outcome.error = f"MapError: {error}"
        for metric in ("reachable", "length", "space_path", "element_path"):
            outcome.checks[metric] = False
    outcome.checks["answer"] = outcome.checks["parse"] and outcome.checks["reachable"] and outcome.checks["length"]
    return outcome


def evaluate() -> tuple[dict[str, Counter], dict[str, int], list[tuple[str, Outcome]]]:
    """Per-kind Counter of passed metrics, per-kind totals, and every (id, outcome) with an error/miss/tie."""
    passed: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    notable: list[tuple[str, Outcome]] = []
    for directory, question in warmup_questions():
        outcome = evaluate_question(directory, question)
        totals[outcome.kind] += 1
        for metric, ok in outcome.checks.items():
            passed[outcome.kind][metric] += ok
        passed[outcome.kind]["tie"] += outcome.tie
        passed[outcome.kind]["equal_alt"] += outcome.equal_alternative
        passed[outcome.kind]["ambiguous"] += outcome.ambiguous
        passed[outcome.kind]["gold_in_alternatives"] += outcome.gold_in_alternatives
        if outcome.oracle is not None:
            passed[outcome.kind]["oracle"] += outcome.oracle
        if outcome.error or outcome.tie or not all(outcome.checks.values()):
            notable.append((question["id"], outcome))
    return dict(passed), dict(totals), notable


def report(passed: dict[str, Counter], totals: dict[str, int]) -> None:
    columns = (*METRICS, "oracle", "tie", "equal_alt", "ambiguous", "gold_in_alternatives")
    print(f"{'kind':20s} {'n':>5s} " + " ".join(f"{column:>12s}" for column in columns))
    for kind in sorted(totals):
        cells = []
        for column in columns:
            if column in ("tie", "equal_alt", "ambiguous", "gold_in_alternatives"):
                cells.append(f"{passed[kind][column]:>12d}")
            elif kind in ("locate", "count") and column not in ("parse", "answer"):
                cells.append(f"{'-':>12s}")
            else:
                cells.append(f"{100 * passed[kind][column] / totals[kind]:>11.1f}%")
        print(f"{kind:20s} {totals[kind]:5d} " + " ".join(cells))
    total = sum(totals.values())
    answered = sum(passed[kind]["answer"] for kind in totals)
    print(f"{'all':20s} {total:5d}  answer {100 * answered / total:.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="list every failure and tie")
    arguments = parser.parse_args()
    passed, totals, notable = evaluate()
    report(passed, totals)
    if arguments.verbose:
        for question_id, outcome in notable:
            failed = [metric for metric, ok in outcome.checks.items() if not ok]
            print(f"{question_id:40s} {outcome.kind:20s} tie={outcome.tie} failed={failed} {outcome.error}")


if __name__ == "__main__":
    main()
