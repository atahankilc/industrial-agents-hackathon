---
id: arch-solver-plan
summary: Deterministic algorithm per benchmark question kind, with the definition it implements, open questions, and validation method.
status: verified — every kind implemented in core/solvers.py and matches all train+dev answers (2026-10-24)
sources: [../kit/questions.md, ../kit/route-model.md, ../challenge/scoring.md]
related: [overview.md, ../kit/questions.md, ../../memory-bank/open-questions.md]
---

# Solver plan per question kind

[Docs index](../README.md) · Definitions: [questions.md](../kit/questions.md#precise-definitions) ·
Tolerances: [scoring.md](../challenge/scoring.md#tolerances-per-kind)

Status legend: `TODO` not built · `BUILT` implemented · `VERIFIED` matches train+dev answers (record score).
Keep the status column current; mirror it in [project-state.md](../../memory-bank/project-state.md).

Validation method for every kind: run the solver on train+dev `inputs` (no LLM), compare to `answer` with
`benchmark.score` logic. Only then hook up text parsing.

| Kind | Test share | Status | Score (train+dev) |
|---|---|---|---|
| floor_area_total | 23% | VERIFIED | 181/181 train+dev |
| shared_walls_count | 18% | VERIFIED | 143/143 train+dev |
| largest_room | 14% | VERIFIED | 96/96 train+dev |
| errand | 14% | VERIFIED | 93/93 train+dev |
| wide_delivery_count | 12% | VERIFIED | 80/80 train+dev |
| straight_line_3d | 10% | VERIFIED | 30/30 train+dev |
| room_stacked | 6% | VERIFIED | 26/26 train+dev |
| what_if_door | 2% | VERIFIED | 4/4 (few labels) train+dev |
| step_free_reachable_count | 0% (Sunday?) | VERIFIED | 2/2 (few labels) train+dev |

Code: `core/solvers.py` (`solve(bmap, kind, params)` takes the parser's params). Tests:
`uv run pytest tests/test_solvers.py -q -s` checks the solver on gold `inputs` and the full pipeline
question text → `core.question_parser` → solver; both 655/655 on train+dev (7 texts are ambiguous OSM names
and are counted by the parser test instead). All 145 test questions parse and solve without error.

### Rules settled empirically (2026-10-24)

| Kind | Rule that matches every train+dev answer | Variants rejected |
|---|---|---|
| shared_walls_count | Count spaces with `type` ∈ {room, hall}; ≥ 1 m of outline within 0.35 m (either direction, same result) | `type == room` only: 124/143; + outdoor: 90/143 |
| wide_delivery_count / step_free_reachable_count | Step-free graph (lifts ok); drop every opening (door, opening, entrance) with `width_m < min_width`; count `type == room` spaces on the floor reachable from the start | not tested |
| errand | "Nearest" = shortest route-model distance from start (stairs allowed) to a space holding the asset type; then on to the largest room of the type | – |
| room_stacked | Next level up/down; space with the largest polygon intersection area | – |
| what_if_door | New 0.9 m step-free door at the midpoint of the shared boundary (longest piece); rooms (`type == room`) whose distance to `outside` drops by > 1 m | only 4 labels |

## floor_area_total
Sum `Polygon(s.polygon).area` over spaces with `floor_id == F` and `room_type == T`. Answer: one number, ±5%.

## largest_room
Max area among spaces with `floor_id == F`, `room_type == T`. Answer line: `<ref or name>, <area> m²` — winner
first, no runner-ups before it.

## straight_line_3d
`c1 = Polygon(p1).centroid`, `c2 = …`; `z = floor.elevation_m`; Euclidean 3D distance. **Centroid, not
anchor.** Watch Swiss per-floor centring (probably not used for this kind — check).

## room_stacked
Next floor up/down by `level`; pick the space whose polygon intersection area with this room is largest
("covers most of this room's outline"). Answer: ref/name. Open: normalise by this room's area or the other's?
Same argmax either way for intersection area. Verified with every space as a candidate (26/26).

## shared_walls_count
Other spaces on the same floor with `type` ∈ {room, hall}: ≥ 1 m of one outline within 0.35 m of the other
(`ring.intersection(other_ring.buffer(0.35)).length`; both directions give 143/143). Resolved
[Q-003](../../memory-bank/open-questions.md#q-003).

## wide_delivery_count
Graph with step-free only (stairs excluded, lifts allowed) **and** openings with `width_m >= min_width`;
start = the stated entrance space; count reachable "rooms" on target floor. Lift width handling →
[Q-004](../../memory-bank/open-questions.md#q-004); room definition → [Q-003](../../memory-bank/open-questions.md#q-003).

## step_free_reachable_count
Close the named connector, step-free graph, BFS from start, count rooms on target floor.

## errand
1. From start, route-model distance to every space containing an asset of `asset_type` (any floor?) → nearest
   = `via`. 2. Target = largest `room_type` room on `floor_id`. 3. Total = d(start, via) + d(via, target).
   "I can carry it on the stairs" → non-step-free allowed; variants may require step-free. Validate with
   `answer.via` / `answer.target` stored in train answers.

## what_if_door
1. For each room on target floor, route-model distance to `outside` (nearest entrance) — baseline.
2. Add a door between first/second at the **middle of their shared wall** (midpoint of the shared boundary
   segment — not starter `add_door` nearest points). Width/step_free of new door: assume 0.9 m, step-free.
3. Recompute; count rooms with improvement > 1 m. Only 4 labelled examples → [Q-005](../../memory-bank/open-questions.md#q-005).

## Warm-up kinds (questions_basic.jsonl)
In case Sunday asks one-search / one-route questions ([Q-001](../../memory-bank/open-questions.md#q-001)), the
parser has a template per warm-up kind and `solve()` answers them (VERIFIED 2026-10-24, from the question text,
`uv run pytest tests/test_warm_up.py -q -s`):

| Kind | Solver | train+dev |
|---|---|---|
| `locate` | the asset of that type (label → type: exact, plural, start of asset name, end of type) | 553/553 |
| `count` | assets of that type with that `floor_id` | 239/239 |
| `route` / `route_step_free` / `route_with_closure` | `BuildingMap.route()` (closure added to `closed`); `reachable: False` when cut off | 715/720, 239/240, 136/138 |
| `tour` | `route()` with the middle stops as `via`, one leg per stop pair | 238/240 |

All 10 misses are texts naming a room that several rooms share (OSM duplicates such as "Büro"); the parser picks
the first candidate. The LLM parser knows these kinds too: 12/12 on reworded dev questions (live, 2026-10-24).

## Answer formatting (all kinds)
Solver returns a structured result; a formatter writes 1–3 explanation lines + `Answer: …` in exactly the
template the question asks for ([D-003](../../memory-bank/decisions.md#d-003)).

## Related
- [overview.md](overview.md) · [questions.md](../kit/questions.md) · [route-model.md](../kit/route-model.md)
