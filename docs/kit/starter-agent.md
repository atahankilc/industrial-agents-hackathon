---
id: kit-starter-agent
summary: How the provided starter agent works (Claude tool runner + deterministic BuildingMap), its 6 tools, evaluators, and exactly what it lacks for the benchmark.
sources:
  - archive/initial-repo/starter_agent/README.md
  - archive/initial-repo/starter_agent/{agent,tools,building_map,viewer,evaluate}.py
  - benchmark/evaluate.py
related: [route-model.md, questions.md, ../architecture/overview.md, ../guides/commands.md]
---

# Starter agent

[Docs index](../README.md) · Route model it implements: [route-model.md](route-model.md)

Scores **< 5% on benchmark questions by design** (its tools don't expose areas, door widths or reachability),
but its core is the reference route implementation.

```
you ──► agent.py (Claude, tool runner) ──► tools.py ──► building_map.py ──► building.json
                                                          │ search, Dijkstra, closures, add door
                                              viewer.py ◄─┘ route PNGs → agent_output/
```

## `agent.py` — conversation layer

- `MODEL = "claude-opus-5-5"`, `EFFORT = "medium"`, `MAX_TOKENS = 16000`, `MAX_TOOL_ITERATIONS = 20`.
- Uses `client.beta.messages.tool_runner(...)` with `betas=["server-side-fallback-2026-07-01"]`,
  `fallbacks="default"`, `output_config={"effort": EFFORT}`.
- System prompt = guide instructions + `json.dumps(building_map.overview())`, marked
  `cache_control: ephemeral` (prompt caching of the building context).
- `BuildingAgent.ask()` mirrors the runner history into `self.messages` so follow-ups keep context; tracks token usage.
- CLI chat loop: `python -m starter_agent <building_dir> [--output agent_output]`.

## `building_map.py` — deterministic core (`BuildingMap`)

| Method | Does | Lines |
|---|---|---|
| `load(path)` | dir or file → dicts keyed by id: `floors, spaces, assets, connectors, openings` | 54–57 |
| `overview()` | floors, connectors, entrances, asset count, closures | 68–98 |
| `search(query, floor_level)` | all query words must be substrings of name/ref/type/id | 107–144 |
| `resolve_space(ref)` | space id / asset id / exact ref or name / exact asset name → space id; else `MapError` listing candidates | 146–171 |
| `anchor(space_id)` | `representative_point()` | 175–177 |
| `graph(step_free)` | the MultiGraph of [route-model.md](route-model.md) | 179–212 |
| `route(start, dest, step_free, via)` | Dijkstra per leg, concatenated; stores `last_route` | 214–246 |
| `directions(...)` | human steps ("Walk about 12 m through the door into …") | 248–275 |
| `set_closed(ref, closed)` | adds/removes id in `self.closed` | 291–297 |
| `add_door(a, b, step_free)` | same floor, polygons within 0.6 m; door at midpoint of `nearest_points`; width 0.9 m | 299–320 |
| `save(path)` | writes JSON | 322–323 |

Note: `add_door` places the door at the **nearest points** between polygons, not at the **middle of the shared
wall** that `what_if_door` requires ([questions.md](questions.md#precise-definitions)).

## `tools.py` — 6 tools (`@beta_tool`)

`building_overview`, `search_building(query, floor_level?)`, `find_route(start, destination, step_free?, via?)`,
`set_closed(element, closed)`, `add_door(first_space, second_space, step_free?)` (saves
`building_edited.json`), `show_route()` (PNG per floor via `viewer.py`). Errors → `ToolError`.

## Evaluation

- `starter_agent/evaluate.py` — warm-up set (`questions_basic.jsonl`). `--oracle` answers with tools directly
  (free, ~100%); live mode checks computed state (`last_route`, `located_asset_ids`), not prose.
- `benchmark/evaluate.py` — benchmark set (`questions.jsonl`), scores with `score.py`. Options: `--per-kind N`
  (seed 7), `--kinds …`, `--agent module:function`, `--name`, `--submission-csv`. Writes
  `agent_output/benchmark/<name>.jsonl`. Opus prices hard-coded for a cost estimate.
- Custom agent contract: `answer(building_directory: Path, question_text: str) -> str` (full reply).

## Gaps vs benchmark (what we must add)

| Missing capability | Needed by |
|---|---|
| room area from polygon; filter by `room_type` + floor | `largest_room`, `floor_area_total`, `errand` |
| min-door-width filter in graph + reachability count | `wide_delivery_count` |
| reachability count under closure + step-free | `step_free_reachable_count` |
| polygon proximity (0.35 m buffer, ≥1 m overlap length) | `shared_walls_count` |
| inter-floor polygon overlap | `room_stacked` |
| centroid + elevation 3D distance | `straight_line_3d` |
| door at middle of shared wall + all-rooms-to-nearest-entrance distances, before/after | `what_if_door` |
| nearest room containing asset type (by route) + chain | `errand` |
| deterministic `Answer:` line formatting | all ([scoring.md](../challenge/scoring.md#formatting-pitfalls-cost-real-points)) |
| multi-building, build-from-plan, UI, voice | Levels 3–5, Interaction |

Plan for each: [solver-plan.md](../architecture/solver-plan.md).

## Ideas from the starter README

Tune `SYSTEM_PROMPT` with tricky users (vague "the printer", wrong "room 9.99", changing mind); Level 3 = multiple
`BuildingMap`s linked by outdoor walkways + `building` tool arg; Level 4 = send plan PNG to Claude, have it emit
`spaces`/`openings` JSON, load and check reachability; Level 5 = `update_asset_position`, forklift closures, voice,
three.js stacked by `elevation_m`; cost = lower effort or Sonnet/Haiku and compare with evaluator.

## Related

- [route-model.md](route-model.md) · [architecture/overview.md](../architecture/overview.md) · [commands.md](../guides/commands.md)
