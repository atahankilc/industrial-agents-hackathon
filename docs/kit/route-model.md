---
id: kit-route-model
summary: The exact graph and cost model (kit 1.1.0) used to compute every expected route length and to grade routes. Reproduce it bit-for-bit.
sources:
  - archive/initial-repo/README.md §3 "The route model behind the expected answers" (kit 1.1.0)
  - archive/initial-repo/CHANGELOG.md (1.1.0)
  - archive/initial-repo/starter_agent/building_map.py:25-115, 271-327 (1.1.0)
  - organisers' Discord note on route scoring (2026-10-24), quoted in § Sunday scoring model
  - core/building_map.py, core/route_models.py, tests/test_routes.py, tests/test_route_models.py
related: [data-format.md, questions.md, ../../archive/hackathon/docs/kit/starter-agent.md, ../architecture/solver-plan.md]
---

# Route model (must match to the centimetre)

[Docs index](../README.md) · Data it is built from: [data-format.md](data-format.md)

Since **kit 1.1.0 (2026-10-24)** the expected answers (train/dev, and the hidden test answers) and the judges'
grading use one route model: README §3 of the kit, implemented exactly by the 1.1.0
`starter_agent/building_map.py`. Our `core/building_map.py` carries that code unchanged (geometry helpers +
`BuildingMap.graph`) — **reuse it, don't re-derive** ([D-002](../../memory-bank/decisions.md#d-002),
[D-014](../../memory-bank/decisions.md#d-014)). Kit 1.0.0 used a different model (anchor → door straight lines,
stairs 12 m per floor, lift 15 m + 6 m per floor, all entrances joined outside); it is gone.

## Graph

| Node | Position |
|---|---|
| each open space | **anchor** = `representative_point()` of its polygon (repaired with `buffer(0)` if invalid) — NOT the centroid |
| each open opening | `"door:<opening_id>"` at `opening.position` |

| Edge | Weight (rounded to 3 decimals) |
|---|---|
| inside a space: every pair of its nodes (anchor and each opening) | shortest walk that stays **15 cm off the walls** and goes round corners: visibility graph over the two points and the corners of `polygon.buffer(-0.15)`, a segment is clear if `buffer(0.02)` of that outline covers it; all-pairs shortest paths; blocked → straight line × 1.5 |
| an opening's own step | an opening "lands" **30 cm inside** each space (nearest point of `polygon.buffer(-0.30)`, else `-0.05`, else the anchor); the opening → landing distance is added to every walk that uses it |
| stairs, consecutive stops (by level) | **2 m × metres climbed** (`elevation_m` difference) |
| lift, **every pair** of stops | **15 m once per ride + 1 m × metres climbed** |

- A corridor you only pass through is walked **door to door**, not via its centre.
- **No outdoor link:** an entrance leads out, not into another part of the building. Parts that meet only outside
  have no route → `reachable: false`. Our `route_graph` adds an `outside` node (0 m to each open entrance) only so
  a route may *start or end* outside; it is never passed through (`endpoint_only`).
- Graph type is **`nx.MultiGraph`**: a stair and a lift (or two doors) may join the same two nodes — keep both.
- Furniture and machines are not obstacles; a route to an item ends in the space that holds it.
- Walk edges carry `space=<space id>`; stair/lift edges `via=<connector id>`.

## Constraints

- **Step-free:** drop every stair and every opening with `step_free: false`.
- **Closures:** a closed stair, lift, opening or space can't be used at all (a closed space loses its node and walks).
- **Min door width** (needed for `wide_delivery_count`): *not* in the kit model — keep only openings (every kind)
  with `width_m >= min_width`; connectors have no width field, so lifts are not width-limited. VERIFIED 80/80 →
  [solver-plan.md](../architecture/solver-plan.md#wide_delivery_count).

## Equal-length ties

Exact `space_path` / `element_path` matches depend on networkx Dijkstra breaking ties the same way as the kit:
`BuildingMap.graph()` adds nodes and edges in the starter's order. **Don't refactor it.**
(`scripts/validate_warmup.py` reports `tie` / `equal_alt`.)

## Path representations in answers

Warm-up route answers (1.1.0) carry `space_path` = **every space the route passes, in order, incl. corridors
crossed door to door** (and `"outside"` only as a start/end in our tools), and `element_path` = **each opening
once** and **each stair flight / lift ride once** (stairs F2 → F4 = the stair id twice, a lift ride once). Tours
have `legs`, each with its own paths; a tour with an unreachable stop is `{"stops": [...], "reachable": false}`.
Example in [questions.md](questions.md#warm-up-questions).

`core/building_map.py` `path_parts` / `expand` produce these from a Dijkstra node path (`expand` also gives the
space/door/space walk the step text uses). `BuildingMap.route()` and `core/navigation.py` (`find_route`, `tour`)
return them per leg. **Verified exact** (length ≤ 1 cm, `space_path`, `element_path`, unreachable cases) on all
**1,338** train+dev warm-up route / step-free / closure / tour questions: `uv run pytest tests/test_routes.py -q -s`
(2026-10-24). One gold value disagrees with the organisers' own 1.1.0 starter (resplan-12462 Q08 and the tour leg in
Q09: gold 7.57 m, starter and ours 7.67 m); the validators count a length equal to the starter as right.

## Performance

Walks are cached per space by (space id, outline, its openings) in `core/building_map._WALKS`, shared by copies,
sessions and edits; an added door is a new key. First build (dev, 2026-10-24): all but two buildings < 1 s; osm-way27917482 ~7 s and
**osm-way360544293 ~25 s** (two corridor polygons with ~1,000 corners each; ⅔ visibility checks, ⅓ Floyd-Warshall). A faster exact
variant (Dijkstra from the few door points) gave identical lengths on all 108k dev walk pairs but was only 1.5×
faster; an STRtree visibility test was 7× slower. Neither is used.

<a id="sunday-scoring-model-organisers-note-2026-10-24"></a>
## Sunday scoring model (organisers' note, 2026-10-24)

Source: organisers' Discord message on how route answers are scored in the automatic check (pasted into the
session 2026-10-24). Kit 1.1.0 made its distance rule the model above. Still from the note only (not in README §3):

- Without stairs: lifts, ramps and doors only.
- **Forklift:** forklift aisles and openings **≥ 3 m wide** only; pedestrian walkways don't count.
- Factory **production bays are destinations**: you may drive into one to deliver, not through one as a shortcut.
- If no route exists under the rules, the correct answer is to say so.
- **Scoring:** the answer is the ordered list of spaces; each step must cross a real door, opening, stair or lift
  and respect the rules (else 0); they re-measure it with their rule; score = best ÷ ours, within 1 % = full marks.

Factory schema (aisles, walkways, bays): [Q-015](../../memory-bank/open-questions.md#q-015); output format:
[Q-001](../../memory-bank/open-questions.md#q-001).

## Distances that are NOT the route model

- `straight_line_3d` uses the polygon **centroid** (not representative point) + floor `elevation_m`.
- "Nearest" in `errand` = route-model distance on the full graph, any floor — VERIFIED 93/93 against gold `via`
  (kit 1.1.0 answers, [solver-plan.md](../architecture/solver-plan.md#errand)).
- Step metres are NOT a separate estimate: `core/directions.py` `route_legs`, which drives the Guide's written and spoken steps and
  the camera legs, takes each step's metres from the route model's walks (as the kit's step text does), so step
  metres + stair/lift costs = the route length (`tests/test_directions.py`).

<a id="sunday-route-model-and-route-rules-q-014"></a>
## Route rules (Q-014)

`core/route_models.py`; every `core/navigation.py` route call takes `rules=RouteRules(...)` (and `model`, kept for
callers: `"kit"`, with `"geodesic"` an alias since 1.1.0). **Default: no rules** — the kit graph plus the `outside`
endpoint node (`tests/test_route_models.py`). The rules are our reading of the organiser note — **UNVERIFIED**:

- `bays_destination_only`: production / assembly / logistics / warehouse / additive zones and halls named "bay"
  are the start or end of a leg only (`lobby` halls excluded); door-to-door walks across a bay are removed too.
- `no_outside`: kept for callers; outside is always endpoint-only now.
- `forklift`: openings ≥ 3 m of every kind, no stairs, walkway-like spaces (type / room_type / name) and the
  walks across them removed; lifts allowed — UNVERIFIED.

`SUNDAY_RULES` = bays + no outside; the Guide always routes with them. No route under the rules →
`reachable: false`, reason `"no route under these rules (…): …"`. The kit 1.1.0 answers use **no** rules.

`sequence_length(view, space_path, …)` re-measures an ordered space list the way the organisers score it (best door
choice per step; `None` = invalid step, a pass through `outside`, or a rule broken → score 0). On the dev warm-up
answers it reproduces the gold length from the gold `space_path` (`tests/test_route_models.py`).

## Related

- [questions.md](questions.md) — which kinds use routing
- [starter-agent.md](../../archive/hackathon/docs/kit/starter-agent.md) — code walkthrough
- [solver-plan.md](../architecture/solver-plan.md)
