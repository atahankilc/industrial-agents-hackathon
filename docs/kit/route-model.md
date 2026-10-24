---
id: kit-route-model
summary: The exact graph and cost model used to compute every expected route length. Reproduce it bit-for-bit.
sources:
  - archive/initial-repo/README.md §3 "The route model behind the expected answers"
  - archive/initial-repo/starter_agent/building_map.py:175-246
  - organisers' Discord note on route scoring (2026-10-24), quoted in § Sunday scoring model
related: [data-format.md, questions.md, starter-agent.md, ../architecture/solver-plan.md]
---

# Route model (must match to the centimetre)

[Docs index](../README.md) · Data it is built from: [data-format.md](data-format.md)

Expected route lengths in all answers come from this graph. `starter_agent/building_map.py` implements it
exactly (`BuildingMap.graph`, lines 179–212) — **reuse it rather than re-deriving**
([D-002](../../memory-bank/decisions.md#d-002)). The README tip: validate against warm-up answers on dev;
lengths should match to the cm.

## Graph

| Element | Becomes | Position |
|---|---|---|
| each space | node (id = space id) | **anchor** = `shapely.Polygon(space.polygon).representative_point()` — NOT the centroid |
| each opening | node `"door:<opening_id>"` | `opening.position` |
| `"outside"` | single node shared by all entrances | — |

| Edge | Weight |
|---|---|
| space ↔ each of its openings | straight-line distance anchor → opening position (`math.dist`) |
| entrance ↔ `outside` | **0** (all entrances meet at one outside node) |
| stairs, between consecutive stops (by level) | **12 m × floor span** |
| lift, between consecutive stops | **15 m wait + 6 m × floor span** |

- Graph type is **`nx.MultiGraph`**: a stair and a lift may join the same two spaces — keep both edges.
- A route through a door costs `dist(anchor_A, door) + dist(door, anchor_B)`.
- Outside shortcut: a route may exit one entrance and re-enter another at zero cost. Benchmark questions only
  use cases where this makes no difference.

## Constraints

- **Step-free:** drop every opening and connector with `step_free: false`.
- **Closures:** a closed opening/connector is dropped; a closed **space** removes its node
  (`building_map.py:182-196`).
- **Min door width** (needed for `wide_delivery_count`): *not* in the starter code — filter openings with
  `width_m < min_width`. Whether lifts have a width constraint is open → [Q-004](../../memory-bank/open-questions.md#q-004).

## Path representations in answers

Warm-up route answers carry `space_path` (space ids, plus `"outside"` when the route leaves the building) and
`element_path` (the `via` of every graph edge walked: each opening appears **twice** — space → door node, door
node → space; a connector appears **once per floor segment**, e.g. `V08` five times from Floor 4 to Basement 1).
On parallel edges the cheaper one is used. Tours have `legs`, each with its own paths. Example in
[questions.md](questions.md#warm-up-questions).

`BuildingMap.route()` returns the same per leg (`RouteResult.legs`, `RouteResult.element_path`); verified exact
(length, `space_path`, `element_path`, unreachable cases) on all 1,338 train+dev warm-up route / step-free /
closure / tour questions: `uv run pytest tests/test_routes.py -q -s` (2026-10-24). The errand solver returns its
two legs in this format; `run_benchmark` puts them under `route` (Sunday format: [Q-001](../../memory-bank/open-questions.md#q-001)).

## Sunday scoring model (organisers' note, 2026-10-24)

Source: organisers' Discord message on how route answers are scored in the automatic check (pasted into the
session 2026-10-24; not in the kit). It describes a **different distance model** from the warm-up graph above.
The warm-up model stays the reference for train/dev/test answers; this one is how Sunday routes are measured.

**Building model**

- Spaces (rooms, corridors, aisles, stairwells, lifts) joined by doors, openings, stairs and lifts.
- Walking distance is measured **inside each space, door to door, ~15 cm off the walls**; paths go around
  corners, never through walls.
- Stairs = **2 m of walking per metre climbed**. Lift = **15 m** (waiting and doors) **+ 1 m per metre of height**.
- Furniture, equipment and machines are **not obstacles**; only room/aisle outlines count.
- A route to a machine or other item **ends in the room or bay that holds it**, not at its exact position.

**Rules for some questions**

- Without stairs: lifts, ramps and doors only.
- Forklift: forklift aisles and openings **≥ 3 m wide** only; pedestrian walkways don't count.
- Closed or blocked areas must be avoided.
- Factory production bays are destinations: you may drive into one to deliver, not through one as a shortcut.
- If no route exists under the rules, the correct answer is to say so.

**Scoring**

- Answer = the ordered list of spaces passed through. Each step must cross a real door, opening, stair or lift and
  respect the rules above; otherwise the route is invalid and scores 0.
- They re-measure the route with their distance rule; **our own length numbers don't affect the score**.
- Score = best possible length ÷ our length; within 1% of the best = full marks.

**Differences from the warm-up graph**

| | Warm-up graph ([above](#graph)) | Sunday scoring model |
|---|---|---|
| In-space distance | straight line anchor (`representative_point`) → door | door → door geodesic, ~0.15 m off walls |
| Stairs | 12 m × floor span | 2 m × metres climbed |
| Lift | 15 m + 6 m × floor span | 15 m + 1 m × metres of height |
| Start/end in a space | the anchor | UNVERIFIED (destination: anywhere in the holding room/bay) |

Consequence: the space sequence that is shortest under the warm-up graph is not guaranteed to be within 1% of the
best under the Sunday model. Plan and open details: [Q-014](../../memory-bank/open-questions.md#q-014); factory
schema (aisles, walkways, bays): [Q-015](../../memory-bank/open-questions.md#q-015); output format:
[Q-001](../../memory-bank/open-questions.md#q-001).

## Distances that are NOT the route model

- `straight_line_3d` uses the polygon **centroid** (not representative point) + floor `elevation_m`.
- "Nearest" in `errand` = route-model distance (UNVERIFIED — confirm against train answers, see
  [solver-plan.md](../architecture/solver-plan.md#errand)).

## Related

- [questions.md](questions.md) — which kinds use routing
- [starter-agent.md](starter-agent.md) — code walkthrough
- [solver-plan.md](../architecture/solver-plan.md)
