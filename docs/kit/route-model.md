---
id: kit-route-model
summary: The exact graph and cost model used to compute every expected route length. Reproduce it bit-for-bit.
sources:
  - archive/initial-repo/README.md §3 "The route model behind the expected answers"
  - archive/initial-repo/starter_agent/building_map.py:175-246
  - core/route_models.py, core/geodesic.py, scripts/compare_route_models.py (Sunday model, Q-014)
related: [data-format.md, questions.md, starter-agent.md, ../architecture/solver-plan.md]
---

# Route model (must match to the centimetre)

> ⚠ **Sunday route scoring uses a different distance rule** (door-to-door inside each space, 15 cm off walls; stairs
> 2 m per metre climbed; lift 15 m + 1 m per metre; production bays destination-only; forklift ≥ 3 m) — see
> [Q-014](../../memory-bank/open-questions.md#q-014). This page stays correct for the kit's own answers (warm-up
> routes, `errand`) until the organisers say otherwise. Our implementation of the new rule, selectable per call:
> [below](#sunday-route-model-and-route-rules-q-014).

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

Warm-up route answers carry `space_path` (space ids only) and `element_path` (openings/connectors traversed;
each opening appears **twice** — once entering the door node, once leaving it; connectors appear once). Tours
have `legs`, each with its own paths. Example in [questions.md](questions.md#warm-up-questions).

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
