"""Live check of the Guide on scripted conversations (calls the Claude API, costs money).

  uv run --env-file .env python scripts/eval_guide.py                      # every tests/guide_conversations/*.json
  uv run --env-file .env python scripts/eval_guide.py tests/guide_conversations/lift_closure.json

Each turn's `expect` is checked against the TurnResult and the Guide's session. Keys: `asked` (reply ends with a
question), `tools` ([] = no tool call, otherwise each name was called), `route_to` (the turn's last route ends there and
its length equals a fresh core route from the session state), `no_route` (no route computed), `step_free` (session
flag), `space_ids_include`, `grounded`, `asset_total` (asset type id whose building-wide
count a `locate` result and the reply must state). Prints PASS/FAIL per turn and the total cost; exit 1 on any failure."""

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.guide.__main__ import cost  # noqa: E402
from agent.guide.guide import Guide, TurnResult  # noqa: E402
from core.solvers import route as core_route  # noqa: E402

EXPECT_KEYS = {"asked", "tools", "route_to", "no_route", "step_free", "space_ids_include", "grounded", "asset_total"}
CONVERSATIONS = Path(__file__).resolve().parent.parent / "tests" / "guide_conversations"


def load_conversation(path: Path) -> dict:
    conversation = json.loads(Path(path).read_text())
    for turn in conversation["turns"]:
        unknown = set(turn["expect"]) - EXPECT_KEYS
        if unknown:
            raise ValueError(f"{path}: unknown expect keys {sorted(unknown)}")
    return conversation


def fresh_routes(guide: Guide, start: str, destination: str) -> list[dict]:
    """Core routes from the Guide's session state, one per reading of the closures (one candidate id per stated
    closure, like tools.route): a closure like "the lift" may name several elements."""
    saved = set(guide.bmap.closed)
    routes = []
    try:
        for choice in itertools.product(*guide.session.closures):
            guide.bmap.closed = saved | set(choice)
            routes.append(core_route(guide.bmap, start, destination, step_free=guide.session.step_free))
    finally:
        guide.bmap.closed = saved
    return routes


def check_route(guide: Guide, result: TurnResult, destination: str) -> list[str]:
    if not result.routes:
        return [f"route_to {destination}: no route was computed"]
    last = result.routes[-1]
    if last["to_space_id"] != destination:
        return [f"route_to {destination}: route ends at {last['to_space_id']}"]
    if last.get("reachable") is not True:
        return [f"route_to {destination}: the Guide's route is not reachable"]
    references = fresh_routes(guide, last["from_space_id"], destination)
    if not all(ref.get("reachable") is True for ref in references):
        return [f"route_to {destination}: core finds no route for some reading of the closures"]
    lengths = {ref["optimal_length_m"] for ref in references}
    if len(lengths) > 1:
        return [f"route_to {destination}: closure readings give different lengths {sorted(lengths)}; the Guide "
                "should have asked"]
    if last["optimal_length_m"] not in lengths:
        return [f"route_to {destination}: optimal_length_m {last['optimal_length_m']} != core {lengths.pop()}"]
    return []


def check_asset_total(guide: Guide, result: TurnResult, asset_type: str) -> list[str]:
    """The count a `locate` call returned this turn equals the building's asset count, and the reply states it."""
    expected = sum(a["type"] == asset_type for a in guide.bmap.assets.values())
    results = guide.tool_results[len(guide.tool_results) - len(result.tool_calls):]
    totals = [r["total"] for call, r in zip(result.tool_calls, results, strict=True)
              if call["name"] == "locate" and r["status"] == "ok"]
    if expected not in totals:
        return [f"asset_total {asset_type}: core counts {expected}, locate totals {totals}"]
    if not re.search(rf"\b{expected}\b", result.text):
        return [f"asset_total {asset_type}: reply does not state {expected}"]
    return []


def check_turn(guide: Guide, result: TurnResult, expect: dict) -> list[str]:
    failures = []
    if "asked" in expect and result.asked != expect["asked"]:
        failures.append(f"asked is {result.asked}, expected {expect['asked']}")
    called = [call["name"] for call in result.tool_calls]
    if "tools" in expect:
        if not expect["tools"] and called:
            failures.append(f"expected no tool call, got {called}")
        missing = [name for name in expect["tools"] if name not in called]
        if missing:
            failures.append(f"tools not called: {missing} (called {called})")
    if "route_to" in expect:
        failures += check_route(guide, result, expect["route_to"])
    if expect.get("no_route") and result.routes:
        failures.append("a route was computed, expected none")
    if "step_free" in expect and guide.session.step_free != expect["step_free"]:
        failures.append(f"session step_free is {guide.session.step_free}, expected {expect['step_free']}")
    if "asset_total" in expect:
        failures += check_asset_total(guide, result, expect["asset_total"])
    missing_ids = [i for i in expect.get("space_ids_include", []) if i not in result.space_ids]
    if missing_ids:
        failures.append(f"space_ids missing {missing_ids} (got {result.space_ids})")
    if "grounded" in expect and result.grounded != expect["grounded"]:
        failures.append(f"grounded is {result.grounded}, expected {expect['grounded']}")
    return failures


def run_conversation(path: Path) -> tuple[int, int, float]:
    conversation = load_conversation(path)
    guide = Guide(Path(conversation["building"]))
    passed = 0
    for number, turn in enumerate(conversation["turns"], 1):
        try:
            result = guide.turn(turn["user"])
        except Exception as error:
            failures, reply = [f"error: {type(error).__name__}: {error}"], ""
        else:
            failures, reply = check_turn(guide, result, turn["expect"]), result.text
        passed += not failures
        print(f"  {'PASS' if not failures else 'FAIL'} turn {number}: {turn['user']}")
        for failure in failures:
            print(f"       - {failure}")
        if failures:
            print(f"       reply: {reply}")
    return passed, len(conversation["turns"]), cost(guide.usage)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scripted Guide conversations against the live API.")
    parser.add_argument("files", nargs="*", type=Path)
    files = parser.parse_args().files or sorted(CONVERSATIONS.glob("*.json"))
    passed = total = 0
    spent = 0.0
    for path in files:
        print(path.name)
        ok, count, price = run_conversation(path)
        passed, total, spent = passed + ok, total + count, spent + price
    print(f"\n{passed}/{total} turns PASS, total cost ~${spent:.4f}")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
