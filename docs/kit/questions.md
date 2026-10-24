---
id: kit-questions
summary: All warm-up and benchmark question kinds, their answer schemas, precise geometric definitions, inputs fields and counts per split.
sources:
  - archive/initial-repo/README.md §4
  - "scan of data/{train,dev}/*/questions*.jsonl and data/test/questions.csv, 2026-10-24"
related: [../challenge/scoring.md, route-model.md, data-format.md, ../architecture/solver-plan.md]
---

# Questions

[Docs index](../README.md) · Scoring rules: [scoring.md](../challenge/scoring.md) · How we solve them:
[solver-plan.md](../architecture/solver-plan.md)

Two files per building: `questions_basic.jsonl` (warm-up, **not scored**, train/dev only) and
`questions.jsonl` (benchmark, **scored**). Questions are generated — don't hard-code; new ones work the same way.

## Warm-up questions

`{"id", "building_id", "kind", "question", "answer"}` — one search or one route each. Ids end `-Q##`.
Dev counts: route 120 · locate 100 · count 40 · route_step_free 40 · tour 40 · route_with_closure 29.

| Kind | Example | Answer fields |
|---|---|---|
| `locate` | "Where is the single bed?" | `asset_id`, `space_id`, `space_name`, `floor_level`, `position` |
| `count` | "How many wardrobe items are on the ground floor?" | `count`, `asset_type`, `floor_level` |
| `route` | "How do I get from Living room 0.01 (Ground floor) to Bedroom 0.03 (Ground floor)?" | `from_space_id`, `to_space_id`, `optimal_length_m`, `space_path`, `element_path` |
| `route_step_free` | "Is there a step-free route from … to …?" | as route, or `reachable: false` |
| `route_with_closure` | "Office staircase is closed for maintenance. How do I get from … to …?" | route fields + `closed_element_id`, or `reachable: false` |
| `tour` | "Starting at …, visit … then … in this order." | `stops`, `optimal_length_m`, `legs[]` |

`count` matches `asset.type` exactly on the floor (see oracle in `starter_agent/evaluate.py:66-74`).
The starter tools reach 100% on these via `--oracle` ([starter-agent.md](starter-agent.md#evaluation)).

## Benchmark questions

Ids end `-H##`. Train/dev lines include `skill`, `inputs` (resolved ids behind the question) and `answer`
(scorer object, see [scoring.md](../challenge/scoring.md#how-a-reply-is-parsed)). Test lines: only `id`,
`building_id`, `kind`, `question`. **`inputs` is absent in test** — our agent must parse the question text.

Two groups: **plan facts** (room areas, door widths — fields the starter agent never exposes) and **spatial
reasoning** (3D stacking, shared walls, centroids, what-if edits).

### Kinds, counts and examples

| Kind | train | dev | test | `skill` | `inputs` keys |
|---|---|---|---|---|---|
| `floor_area_total` | 150 | 31 | 33 | room geometry: summed area | `floor_id, room_type` |
| `shared_walls_count` | 119 | 24 | 26 | wall adjacency from polygons | `start` |
| `largest_room` | 76 | 20 | 21 | room geometry: area | `floor_id, room_type` |
| `errand` | 74 | 19 | 20 | chain nearest-item, area and routing | `start, asset_type, floor_id, room_type` |
| `wide_delivery_count` | 61 | 19 | 18 | door widths + reachability | `start, floor_id, min_width` |
| `straight_line_3d` | 17 | 13 | 15 | 3D geometry: centroids and floor elevations | `first, second` |
| `room_stacked` | 17 | 9 | 9 | 3D stacking: polygon overlap between floors | `start, direction` |
| `what_if_door` | 2 | 2 | 3 | what-if edit with effects on another floor | `first, second, door_floor_id, floor_id` |
| `step_free_reachable_count` | 1 | 1 | 0 | reachability under constraints | `closed, start, floor_id` |

`what_if_door` and `step_free_reachable_count` have very few labelled examples (4 and 2) → high risk of
definition mismatch; see [Q-005](../../memory-bank/open-questions.md#q-005).

Representative questions (verbatim from train/dev):

- **largest_room** — "Which is the largest bedroom on the floor 1, and how big is it in m²? Finish with a line
  'Answer: <room name or number>, <area> m²'." → answer `space` with `accept` ["1.02", "Bedroom 1.02 (apartment 5)"],
  `reject` (runner-ups), `area` 25.5 ±5%.
- **floor_area_total** — "…total floor area of every kitchen on the floor 3 added together…" → number ±5%.
- **errand** — "I'm in Bedroom 2.10 (apartment 8) (Floor 2). I need to grab a desk from the room that has one
  closest to me, then carry it to the largest bedroom on the floor 1. I can carry it on the stairs. How far will
  I walk in total, in metres?" → number 40.19 ±1%/≥1 m; answer also stores `via` (item room) and `target`.
- **shared_walls_count** — "…How many other rooms on that floor share a wall with it? Count every room whose wall
  runs along it for at least 1 m, with or without a door between them; corridors, stairwells and lifts don't count."
- **wide_delivery_count** — "I'm moving a 1.0 m wide hospital bed. It can't go on stairs or steps (lifts are
  fine), and every door it passes through must be at least 1.0 m wide. It arrives through the entrance into
  Landing 0.27 (Ground floor). Into how many rooms on the floor 4 can it be delivered?"
- **straight_line_3d** — "…straight-line distance in metres between the centres of the two rooms (each room's
  floor-plan centroid, at its floor's elevation)?" → ±2%.
- **room_stacked** — "There's water dripping from the ceiling in Büro (Ground floor). Which room is directly
  above it?" (or "…which room directly below…").
- **step_free_reachable_count** — "Lift 2 is out of service. A wheelchair user comes in through the entrance
  into Corridor N0110 (Ground floor). How many rooms on the floor 2 can they still reach?"
- **what_if_door** — "What if we add a door between Corridor N0110A (Ground floor) and Corridor N0123A (Ground
  floor), in the middle of the wall they share? How many rooms on the floor 2 would then have a shorter walk out
  of the building, to their nearest entrance, by more than 1 m?"

Every question ends with an answer template, e.g. `Finish with a line 'Answer: <number>'`.

### Precise definitions

From README §4 — these are normative:

- **Directly above / below:** the space on the next floor up/down whose outline covers **most** of this room's
  outline. Only used on buildings with one shared XY frame (procedural, OSM).
- **Sharing a wall:** at least **1 m** of one room's outline runs within **0.35 m** of the other room's outline
  (walls have thickness).
- **Room centre:** polygon **centroid**, at the floor's `elevation_m`.
- **What-if door:** placed at the middle of the shared wall, walked like any other door, between any two rooms,
  halls or corridors. The question is about a **different floor** than the door's. "Walk out of the building" =
  route-model distance ([route-model.md](route-model.md)) to the nearest entrance.

Guarantees: answers are well defined — the right room beats the runner-up by a clear margin, every constraint
actually changes the answer, and the largest room is never simply the room with the most furniture.

### Ambiguities we must resolve empirically (against train/dev answers)

- What counts as a "room" in counts (`type == "room"`? include `hall`? exclude balconies/outdoor?) →
  [Q-003](../../memory-bank/open-questions.md#q-003)
- Lift width / door width rule in `wide_delivery_count` → [Q-004](../../memory-bank/open-questions.md#q-004)
- How names in question text map to spaces when OSM names repeat (e.g. "Büro") → [Q-006](../../memory-bank/open-questions.md#q-006)

## Related

- [scoring.md](../challenge/scoring.md) · [route-model.md](route-model.md) · [solver-plan.md](../architecture/solver-plan.md)
