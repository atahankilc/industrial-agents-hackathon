"""Kit route model vs the Sunday geodesic scoring rule (Q-014) on every train/dev warm-up route leg.

  uv run python scripts/compare_route_models.py          # summary table
  uv run python scripts/compare_route_models.py -v       # also the worst legs

Every leg of the warm-up `route`, `route_step_free`, `route_with_closure` and `tour` questions (gold start/end ids,
closures from the question text) is routed four ways: kit model and geodesic model, each without rules and with
the Sunday rules (production bays destination-only, no shortcut outside). Each answer's space sequence is then
re-measured the way the organisers score it (core/route_models.sequence_length, geodesic rule): score =
best ÷ ours, full marks within 1 %, 0 for a sequence that breaks a rule. `best` = the geodesic model with rules."""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.basic_parser import ParseError, parse_basic  # noqa: E402
from core.building_map import BuildingMap, MapError  # noqa: E402
from core.navigation import find_route, routing_view  # noqa: E402
from core.route_models import (  # noqa: E402
    GEODESIC,
    KIT,
    NO_RULES,
    SUNDAY_RULES,
    is_production_bay,
    sequence_length,
)

FULL_MARKS = 0.99  # within 1 % of the best length
VARIANTS = {"kit": (KIT, NO_RULES), "kit+rules": (KIT, SUNDAY_RULES), "geodesic": (GEODESIC, NO_RULES),
            "geodesic+rules": (GEODESIC, SUNDAY_RULES)}


def warmup_legs() -> list[tuple[BuildingMap, str, str, str, bool, tuple[str, ...]]]:
    legs = []
    for split in ("train", "dev"):
        for path in sorted((ROOT / "data" / split).glob("*/questions_basic.jsonl")):
            building = BuildingMap.load(path.parent)
            for line in path.read_text(encoding="utf-8").splitlines():
                question = json.loads(line) if line.strip() else {}
                kind = question.get("kind")
                if kind not in ("route", "route_step_free", "route_with_closure", "tour"):
                    continue
                closed: tuple[str, ...] = ()
                if kind == "route_with_closure":
                    try:
                        closed = (str(parse_basic(question["question"], building).params["closed"]),)
                    except (ParseError, MapError, KeyError):
                        continue
                answer = question["answer"]
                gold = answer["legs"] if kind == "tour" else [answer]
                for item in gold:
                    legs.append((building, question["id"], item["from_space_id"], item["to_space_id"],
                                 kind == "route_step_free", closed))
    return legs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    verbose = parser.parse_args().verbose
    counts: Counter[str] = Counter()
    scores: dict[str, list[float]] = {name: [] for name in VARIANTS}
    worst: list[tuple[float, str, str]] = []
    legs = warmup_legs()
    for building, question_id, start, end, step_free, closed in legs:
        view = routing_view(building, closed)
        routes = {
            name: find_route(view, start, end, step_free=step_free, model=model, rules=rules, include_steps=False)
            for name, (model, rules) in VARIANTS.items()
        }
        best = routes["geodesic+rules"]
        if not routes["kit"].reachable:
            counts["unreachable (kit, no rules)"] += 1
            continue
        counts["legs"] += 1
        kit_path, geo_path = routes["kit"].space_path, routes["geodesic"].space_path
        counts["kit ≠ geodesic sequence (no rules)"] += kit_path != geo_path
        counts["kit route passes outside"] += "outside" in kit_path[1:-1]
        counts["kit route passes a production bay"] += any(
            space in building.spaces and is_production_bay(building.spaces[space]) for space in kit_path[1:-1]
        )
        if not best.reachable:
            counts["no route under the Sunday rules"] += 1
            continue
        counts["scored legs (route exists under rules)"] += 1
        own = sequence_length(view, best.space_path, step_free=step_free, rules=SUNDAY_RULES)
        if own is None or abs(own - best.length_m) > 0.01:
            counts["sanity: geodesic re-measure ≠ its own length"] += 1
        for name, route in routes.items():
            measured = route.reachable and sequence_length(view, route.space_path, step_free=step_free,
                                                           rules=SUNDAY_RULES)
            score = min(1.0, best.length_m / measured) if measured else 0.0
            scores[name].append(score)
            if name == "kit+rules":
                worst.append((score, question_id, f"{start} → {end}"))
    print(f"warm-up legs: {len(legs)}")
    for key, value in counts.items():
        print(f"  {key:45} {value}")
    print(f"\n{'answer from':16} {'mean score':>10} {'full marks':>11} {'< 0.99':>7} {'score 0':>8} {'min':>6}")
    for name, values in scores.items():
        full = sum(value >= FULL_MARKS for value in values)
        zero = sum(value == 0 for value in values)
        print(f"{name:16} {statistics.mean(values):10.4f} {full / len(values):10.1%} {len(values) - full:7} "
              f"{zero:8} {min(values):6.3f}")
    if verbose:
        print("\nworst kit+rules legs:")
        for score, question_id, leg in sorted(worst)[:15]:
            print(f"  {score:.3f} {question_id} {leg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
