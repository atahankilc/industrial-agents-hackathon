---
id: arch-solver-plan
summary: PROPOSED deterministic algorithm per benchmark question kind, with the definition it implements, open questions, and validation method.
status: proposed — algorithms must be validated against train/dev answers before being marked VERIFIED
sources: [../kit/questions.md, ../kit/route-model.md, ../challenge/scoring.md]
related: [overview.md, ../kit/questions.md, ../../memory-bank/open-questions.md]
---

# Solver plan per question kind — PROPOSED

[Docs index](../README.md) · Definitions: [questions.md](../kit/questions.md#precise-definitions) ·
Tolerances: [scoring.md](../challenge/scoring.md#tolerances-per-kind)

Status legend: `TODO` not built · `BUILT` implemented · `VERIFIED` matches train+dev answers (record score).
Keep the status column current; mirror it in [project-state.md](../../memory-bank/project-state.md).

Validation method for every kind: run the solver on train+dev `inputs` (no LLM), compare to `answer` with
`benchmark.score` logic. Only then hook up text parsing.

| Kind | Test share | Status | Dev score |
|---|---|---|---|
| floor_area_total | 23% | TODO | – |
| shared_walls_count | 18% | TODO | – |
| largest_room | 14% | TODO | – |
| errand | 14% | TODO | – |
| wide_delivery_count | 12% | TODO | – |
| straight_line_3d | 10% | TODO | – |
| room_stacked | 6% | TODO | – |
| what_if_door | 2% | TODO | – |
| step_free_reachable_count | 0% (Sunday?) | TODO | – |

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
Same argmax either way for intersection area. Restrict candidates to some `type`? → [Q-003](../../memory-bank/open-questions.md#q-003).

## shared_walls_count
For each other space on the same floor, excluding corridors, stairwells and lifts: length of this room's
boundary within 0.35 m of the other polygon ≥ 1 m. Candidate implementation:
`ring_a.intersection(Polygon(b).buffer(0.35)).length >= 1.0` — direction (A's outline vs B's) and exclusion rule
(`type` vs `room_type`) unverified → [Q-003](../../memory-bank/open-questions.md#q-003).

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

## Answer formatting (all kinds)
Solver returns a structured result; a formatter writes 1–3 explanation lines + `Answer: …` in exactly the
template the question asks for ([D-003](../../memory-bank/decisions.md#d-003)).

## Related
- [overview.md](overview.md) · [questions.md](../kit/questions.md) · [route-model.md](../kit/route-model.md)
