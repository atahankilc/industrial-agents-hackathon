---
id: kit-route-model
summary: The exact graph and cost model used to compute every expected route length. Reproduce it bit-for-bit.
sources:
  - archive/initial-repo/README.md §3 "The route model behind the expected answers"
  - archive/initial-repo/starter_agent/building_map.py:175-246
  - organisers' Discord note on route scoring (2026-10-24), quoted in § Sunday scoring model
  - core/route_models.py, core/geodesic.py, scripts/compare_route_models.py (Sunday model, Q-014)
related: [data-format.md, questions.md, starter-agent.md, ../architecture/solver-plan.md]
---

# Route model (must match to the centimetre)

> ⛔ **OUTDATED since kit 1.1.0 (2026-10-24).** The organisers recomputed every train/dev/test route answer with
> the new rule (door to door 15 cm off the walls, 30 cm door landings, stairs 2 m per metre climbed, lift 15 m once
> per ride + 1 m per metre, no outdoor link). The kit model below no longer reproduces the expected answers.
> Authoritative now: `archive/initial-repo/README.md` §3 "The route model behind the expected answers",
> `archive/initial-repo/CHANGELOG.md`, `archive/initial-repo/starter_agent/building_map.py` (1.1.0); line numbers
> cited on this page refer to the 1.0.0 starter. Status: [Q-014](../../memory-bank/open-questions.md#q-014). This
> page is rewritten when our core is ported.

> ⚠ **Sunday route scoring uses a different distance rule** (door-to-door inside each space, 15 cm off walls; stairs
> 2 m per metre climbed; lift 15 m + 1 m per metre; production bays destination-only; forklift ≥ 3 m) — see
> [Q-014](../../memory-bank/open-questions.md#q-014). Kit 1.1.0 adopted this rule for all expected answers (banner
> above), except the production-bay and forklift rules, which its README does not state. Our pre-1.1.0 approximation
> of it: [below](#sunday-route-model-and-route-rules-q-014).

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
- **Min door width** (needed for `wide_delivery_count`): *not* in the starter code — keep only openings (every
  kind: door, opening, entrance) with `width_m >= min_width`; connectors have no width field, so lifts are not
  width-limited. VERIFIED 80/80 → [solver-plan.md](../architecture/solver-plan.md#wide_delivery_count).

## Equal-length ties

10 warm-up legs have a second path of exactly equal length; we still match gold `space_path`/`element_path`
because networkx Dijkstra breaks ties the same way — this depends on `BuildingMap.graph()` adding nodes and
edges in its current order. **Don't refactor it.** (`scripts/validate_warmup.py` reports `tie`/`equal_alt`.)

## Path representations in answers

Warm-up route answers carry `space_path` (space ids, plus `"outside"` when the route leaves the building) and
`element_path` (the `via` of every graph edge walked: each opening appears **twice** — space → door node, door
node → space; a connector appears **once per floor segment**, e.g. `V08` five times from Floor 4 to Basement 1).
On parallel edges the cheaper one is used. Tours have `legs`, each with its own paths. Example in
[questions.md](questions.md#warm-up-questions).

`BuildingMap.route()` returns the same per leg (`RouteResult.legs`, `RouteResult.element_path`); verified exact
(length, `space_path`, `element_path`, unreachable cases) on all 1,338 train+dev warm-up route / step-free /
closure / tour questions: `uv run pytest tests/test_routes.py -q -s` (2026-10-24). The errand solver returns its
two legs in this format; the v1 runner `agent.run_benchmark_v1` (.json output) puts them under `route`, the
canonical `agent.run_benchmark` has them in `evidence.legs` (`nodes`, `spaces`, `elements`) (Sunday format: [Q-001](../../memory-bank/open-questions.md#q-001)).

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
- "Nearest" in `errand` = route-model distance on the full graph, any floor — VERIFIED 93/93 against gold `via`
  ([solver-plan.md](../architecture/solver-plan.md#errand)).

<a id="sunday-route-model-and-route-rules-q-014"></a>
## Sunday route model and route rules (Q-014)

`core/route_models.py`; every `core/navigation.py` route call (`find_route`, `tour`, warm-up `run_parsed`) takes
`model="kit" | "geodesic"` and `rules=RouteRules(...)`. **Default: `kit` without rules** — exactly
`BuildingMap.graph` (node/edge order unchanged, so the tie-breaking above holds; `tests/test_route_models.py`).
The geodesic model and the rules are our reading of the organiser note — **UNVERIFIED** until Q-014 is answered.

| | kit | geodesic |
|---|---|---|
| inside a space | anchor → door straight lines | door → door shortest path in the polygon shrunk by 0.15 m (`core/geodesic.py`: mitre offset, visibility graph over its reflex vertices; within 0.3 m of a door the path may be closer to walls) |
| first / last space | from / to the anchor | from / to the anchor — UNVERIFIED, Q-014 (2) |
| stairs | 12 m × floor span, per consecutive stop | 2 m × metres climbed (`elevation_m` difference), per consecutive stop |
| lift | 15 m + 6 m × span, per consecutive stop | 15 m + 1 m × metres of height, one edge per pair of stops (one wait per ride) |
| graph | kit nodes | kit node ids + door–door edges inside each space (`space` attribute); paths are expanded back to the kit representation, so `space_path` / `element_path` / steps look the same |

Rules (`RouteRules`, both models): `bays_destination_only` (production / assembly / logistics / warehouse /
additive zones and halls named "bay": start or end of a leg only; `lobby` halls excluded), `no_outside` (`outside`
only as start or end), `forklift` (openings ≥ 3 m of every kind, no stairs, walkway-like spaces by type/room_type/
name removed; lifts allowed — UNVERIFIED). `SUNDAY_RULES` = bays + no outside. No route under the rules →
`reachable: false`, reason `"no route under these rules (…): …"`.

`sequence_length(view, space_path, …)` re-measures an ordered space list the way the organisers score it (best
door choice per step; `None` = invalid step or rule broken → score 0).

**Measured on train+dev warm-up legs** (`uv run python scripts/compare_route_models.py`, 1,578 legs, 1,457
reachable under the kit model, 2026-10-24): the kit and geodesic models choose a **different space sequence in 115
legs (7.9 %)**. Scored as best ÷ ours against the geodesic + Sunday-rules best:

| our answer | mean score | full marks (≥ 0.99) | score 0 | min |
|---|---|---|---|---|
| kit model, no rules | 0.930 | 88.8 % | 75 (pass `outside`) | 0 |
| kit model + rules | 0.984 | 93.1 % | 0 | 0.361 |
| geodesic + rules | 1.000 | 100 % | 0 | 1.000 |

The worst kit legs are multi-floor ones where the kit model takes a lift and the new costs prefer the stairs (e.g.
proc-campus-dev-001 F0-S016 → F1-S003: kit 75.84 m re-measured vs 27.41 m best). 202 kit legs pass through
`outside`; **127 legs have no route at all once `outside` is banned** (106 Swiss Dwellings, 21 OSM: parts joined
only via the street) — whether that is right is organiser question (3). With outside allowed (bay rule only) the
kit model scores 0.983 mean, 92.9 % full marks. No warm-up route passes a production bay.

## Related

- [questions.md](questions.md) — which kinds use routing
- [starter-agent.md](starter-agent.md) — code walkthrough
- [solver-plan.md](../architecture/solver-plan.md)
