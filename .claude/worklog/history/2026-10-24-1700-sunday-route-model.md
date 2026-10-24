# Sunday route model (geodesic) and route rules, selectable per call (Q-014)

- **Author:** Claude (Q-014 session) · **Date:** 2026-10-24
- **Related:** Q-014, D-002 (kit model stays default), docs/kit/route-model.md

## Summary
Adds a second route model matching the organisers' Sunday route-scoring rule as we understand it (door to door
inside each space, 0.15 m off the walls; stairs 2 m per metre climbed; lift 15 m + 1 m per metre) and the route
rules (production bays destination-only, no outside shortcut, forklift), selectable per call next to the unchanged
kit model, wired into navigation, the warm-up/benchmark route path and the Guide tools; measures how the models
differ on train/dev warm-up routes.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Geodesic in-space distance: polygon shrunk 0.15 m (mitre), visibility graph over reflex vertices, door discs 0.3 m, fallbacks (raw polygon, straight line); cached; `space_distances` + `space_path` | `core/geodesic.py` | read; `uv run pytest tests/test_geodesic.py -q` → 6 passed (rectangle, L-room bend at (1.85, 1.85), U-room, 0.2 m corridor fallback, real building) |
| C2 | Route models `kit` (= `BuildingMap.graph`, unchanged, same node/edge order) and `geodesic` (door–door edges per space, stairs 2 m/m climbed per consecutive stop, lift 15 + 1 m/m per pair of stops) via `route_graph(view, step_free, model, rules)`; `expand` returns kit-style paths | `core/route_models.py` | read; `tests/test_route_models.py::test_kit_model_without_rules_is_the_kit_graph_and_adds_no_fields`, `test_geodesic_stairs_and_lift_cost_from_elevation` |
| C3 | `BuildingMap.graph()` / `core/building_map.py` not modified | `core/building_map.py` | `git diff --cached --stat` shows no building_map.py |
| C4 | Rules `RouteRules(bays_destination_only, no_outside, forklift)`: bays and `outside` only as leg start/end (`leg_graph` subgraph view), forklift = openings ≥ 3 m, no stairs, walkway-like spaces removed; `SUNDAY_RULES` = bays + no outside; detection by type/room_type/name words, not by building ids | `core/route_models.py` (`is_production_bay`, `is_walkway`, `endpoint_only`, `leg_graph`, `single_source`) | `uv run pytest tests/test_route_models.py -q` → 14 passed |
| C5 | "No route under these rules" = `reachable: false`, reason starting `no route under these rules (…)` | `core/navigation.py:leg` | `test_no_route_under_the_rules_is_a_structured_answer`, `test_forklift_needs_wide_openings_no_stairs_no_walkways` |
| C6 | `find_route`, `tour` (navigation) and `run_parsed` / `answer_basic` (warm-up/benchmark route path) take `model` + `rules`; defaults kit + no rules; result has `model`/`rules` only when non-default | `core/navigation.py`, `core/basic_parser.py` | read; warm-up unchanged: `uv run python scripts/validate_warmup.py \| tail -1` → `all 2130 answer 99.53%` |
| C7 | Guide tools: `find_route`, `tour`, `reachable_rooms`, `compare_routes` (via `space_distances`/`room_distances`) obey `BuildingSession.route_rules()` (bays + no outside always, forklift from profile); `route_model` attribute (default kit); `forklift` preset + `forklift` profile field + `set_profile(forklift=…)` schema; find_route description mentions the rules | `agent/tools.py` | `test_guide_routes_obey_rules_and_forklift_preset`, `test_guide_reachable_rooms_include_bays_as_destinations_only`; `uv run pytest -q` all pass |
| C8 | `sequence_length` re-measures an ordered space list (best door choice; None if a step has no real door/connector or breaks a rule) and equals the geodesic route's own length | `core/route_models.py:sequence_length` | `test_sequence_length_matches_the_route_and_rejects_invalid_lists`, `test_sequence_length_on_real_warmup_routes` |
| C9 | Measurement script on train+dev warm-up legs; numbers in route-model.md match its output | `scripts/compare_route_models.py`, `docs/kit/route-model.md#sunday-route-model-and-route-rules-q-014` | `uv run python scripts/compare_route_models.py` (~45 s) → 1578 legs, 1457 reachable, 115 different sequences, 202 pass outside, 127 no route under rules; kit 0.9301 / 88.8 %, kit+rules 0.9841 / 93.1 % min 0.361, geodesic+rules 1.0000 |
| C10 | `test_profiles.py` unknown-preset example changed from `forklift` (now a real preset) to `hovercraft` | `tests/test_profiles.py` | `git diff --cached tests/test_profiles.py` |
| C11 | Docs + memory bank: route-model.md new section + sources, solver-plan.md "Sunday route questions", routing-profiles.md forklift preset row, Q-014 progress, project-state Start here, log entry; links OK | docs/, memory-bank/ | `python3 scripts/check_links.py` → OK |
| C12 | No deployment files staged (backend/, supabase/, vercel.json, pyproject.toml, uv.lock, .env*, docs/guides/commands.md, tests/test_deploy.py, tests/test_persistence.py) | — | `git diff --cached --name-only` |

## Checks I ran

- `uv run pytest -q` → `182 passed, 1 skipped in 18.82s`
- `uv run python scripts/validate_warmup.py | tail -1` → `all 2130  answer 99.53%` (unchanged, = 2120/2130)
- `uv run python scripts/validate_solvers.py | tail -1` → `all 655 / 655`
- `uv run python scripts/check_routes.py | tail -1` → `core routes exact to 1cm: 120 / 120`
- `uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer` → `all 138 / 138 (100%)`
- `uv run python scripts/compare_route_models.py` → table above (C9)
- `uvx ruff check core/route_models.py core/geodesic.py tests/test_route_models.py` → clean
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`
- Extra (not in a script): with outside allowed (bay rule only) kit scores 0.9829 mean / 92.9 % full marks (in route-model.md).

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (Start here)
- [x] `memory-bank/log.md` entry added (and the old handoff entry's anchor link fixed after the heading rename)
- [x] decisions / open questions touched: Q-014 progress (no new decision; kit stays default per user)
- [x] docs touched: route-model.md, solver-plan.md, routing-profiles.md

## Known gaps / not done
- Geodesic model and rules are our reading of the organiser note — UNVERIFIED until Q-014 (1)–(5) are answered;
  start/end of a route = the space anchor (Q-014 (2)); lifts are allowed for forklifts (unknown).
- Kit stays default everywhere incl. benchmark; switching Sunday route questions to geodesic + rules waits for the
  organisers (and the Sunday output format, Q-001). No benchmark question kind for routes exists yet.
- `errand` / `what_if_door` solvers still use the kit model only.
- `BuildingSession.route_model` is not persisted by backend/persistence.py (default kit on restore) — deploy file,
  not touched.
- numpy is used by core/geodesic.py; it is a transitive dependency (shapely), not declared in pyproject.toml
  (Atahan's file, not touched).
- `core/geodesic.py` + `tests/test_geodesic.py` written by a subagent, reviewed by me.

## Verification rounds
- Round 1: VERDICT: PASS (TREE 3ffc491c227eddf250ddde977f6b07e2f3e2adef)

## Verification report (round 1)

VERDICT: PASS
All claims C1–C12 MET. pytest 182 passed, 1 skipped; check_links OK; no secrets; benchmark/score.py unchanged; no
hard-coding to test buildings; every "Checks I ran" item re-run and matching (validate_warmup 99.53 %, solvers
655/655, check_routes 120/120, dev 138/138, ruff clean, compare_route_models numbers match route-model.md, bay-only
extra 0.9829 / 92.9 %). Undeclared: tool_reachable_rooms now uses space_distances (min width via profile_closures,
only behaviour change = the rules, covered by C7); unused imports removed — not significant.
