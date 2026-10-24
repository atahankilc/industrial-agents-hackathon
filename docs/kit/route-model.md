---
id: kit-route-model
summary: The exact graph and cost model used to compute every expected route length. Reproduce it bit-for-bit.
sources:
  - archive/initial-repo/README.md §3 "The route model behind the expected answers"
  - archive/initial-repo/starter_agent/building_map.py:175-246
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

Warm-up route answers carry `space_path` (space ids only) and `element_path` (openings/connectors traversed;
each opening appears **twice** — once entering the door node, once leaving it; connectors appear once). Tours
have `legs`, each with its own paths. Example in [questions.md](questions.md#warm-up-questions).

## Distances that are NOT the route model

- `straight_line_3d` uses the polygon **centroid** (not representative point) + floor `elevation_m`.
- "Nearest" in `errand` = route-model distance (UNVERIFIED — confirm against train answers, see
  [solver-plan.md](../architecture/solver-plan.md#errand)).

## Related

- [questions.md](questions.md) — which kinds use routing
- [starter-agent.md](starter-agent.md) — code walkthrough
- [solver-plan.md](../architecture/solver-plan.md)
