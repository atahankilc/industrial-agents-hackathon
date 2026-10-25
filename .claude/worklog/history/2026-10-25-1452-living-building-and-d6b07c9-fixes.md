# The living building (live obstacles, reroutes, simulated IoT fleet) + post-commit verifier fixes for d6b07c9

- **Author:** Claude sessions industrial-agents-hackathon (living building, worktree `5-living-building`, merged into
  the main checkout) and industrial-agents-hackathon-20 (verifier fixes, C1–C6) · **Date:** 2026-10-25
- **Related:** docs/product/living-building.md; exhaustive commit-verifier run on d6b07c9 (FAIL, 10 required fixes); D-015

## Summary
One commit at the user's request ("Everything together"): (1) the living building — connected things that report
positions, cut the walks they block, and move the route on the map round them; (2) session -20's fixes for every
item of the d6b07c9 verifier report (C1–C6).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `checking` starts true and is cleared once GET /config answers (access off, catch) or, in access mode, once the restore / GET /me is done; `mayChange` is false while checking, so `?edit=1` shows no Edit bar and `useDraft` sends no /drafts request before then (fix 1) | `frontend/app/src/access/auth.ts` initial state, `startAccess`; `building/BuildingScreen.tsx` `mayChange`, `useDraft(…, editing, …)` | read; `npx tsc -b --noEmit` |
| C2 | `set_my_location("outside")` returns resolve's "No place matches 'outside'…" again, not `{'error': 'outside'}` (fix 3); route starts still accept OUTSIDE | `agent/tools.py` `start_of(reference, outside=True)`, `tool_set_my_location`; `tests/test_voice_location.py::test_outside_is_no_position` | `uv run pytest -q tests/test_voice_location.py` |
| C3 | log.md: the three "(not committed)" headings now say "(d6b07c9)"; a new entry on top, including session 70's part of d6b07c9 (fixes 2, 5) | `memory-bank/log.md` | `grep -n "(not committed)" memory-bank/log.md` → only the new entry's heading |
| C4 | ai-agents.md: `suggest_my_location(rooms?)` table row with `maybe_here`; `set_my_location` row notes the ambiguous start; "Place names" row describes the shortlist (more than 8 → 12 nearest) + highlight (fixes 4, 7) | `docs/architecture/ai-agents.md` | read |
| C5 | project-state: last-updated line names d6b07c9 and these fixes; new session-50 bullet; Building settings tabs Access / People / Objects (fixes 4, 5, 8) | `memory-bank/project-state.md` | read; check_links |
| C6 | Stale "next-move card" comments fixed in core/directions.py `guidance`, backend/sessions.py `safe_steps`, building/Elsewhere.tsx (fix 9) | those files | `grep -rn "next-move card" core backend frontend/app/src` → only CameraWalk.tsx (still true there) and CSS class names |
| C7 | This worklog covers both chunks; session -20's earlier summary/gap lines are replaced; checks below are for this tree | `.claude/worklog/PENDING.md` | read |
| L1 | Standing obstacles cut a walk only when the free area (outline − clearance/2, minus footprints + clearance/2) no longer joins its two ends; each door landing belongs to its nearest free piece only; the start/end space counts as reached from any free door; narrow spaces fall back to the walk line; moving ones cost WAIT_M, wet floor WET_M, squeeze is noted only | `core/live.py` `LiveEffects` (`free_parts`, `reach`, `edge`, `across`, `apply`) | `uv run pytest -q tests/test_live.py` (blockage, near side, squeeze vs wheelchair, wait, door on the only door, narrow corridor, door-beside-blockage) |
| L2 | Routing takes `live=` without changing any route when it is None or empty; lengths stay true metres; live notes `avoided` / `passing` / `detour_m` / `without_live_m` / `blocked_by`; touched-only doors collapsed so paths stay well-formed | `core/navigation.py` `leg`, `live_notes`, `merged_live`, `find_route`, `tour`; `core/live.py` `collapse_hops`, `path_graph`; `core/preferences.py` `path_only(live_extra=)` | `tests/test_live.py::test_no_live_state_changes_nothing`, `::test_preferences_and_the_live_state_together_report_true_metres`, `::test_live_routes_have_well_formed_paths_everywhere_in_a_busy_building`; benchmark paths untouched: full `uv run pytest -q` |
| L3 | A simulated live world per building (forklifts/AGV in factories, delivery + cleaning robots, BLE-tagged pallets/carts left behind), report intervals per kind, BLE fixes averaged, trails = last 50 m, wet zones dry after WET_S, idle worlds stop after IDLE_S | `backend/live.py` `LiveWorld`, `KINDS`, `report`, `trimmed`, `wet_zones`, `LiveHub.tick` | `tests/test_live.py::test_a_world_fills_with_things_that_report`, `::test_the_trail_is_the_last_50_metres_and_splits_by_floor`, `::test_a_ble_tag_reports_a_steady_position`, `::test_wet_zones_follow_the_cleaning_robot_and_dry_up`, `::test_an_idle_world_stops_and_its_things_vanish`, `::test_every_simulated_kind_moves_and_stays_inside_the_building` |
| L4 | Robot mission planning runs on a planner thread on a copy of the device (never holds the world lock while routing); worlds are built outside the hub lock; at most one new mission per tick | `backend/live.py` `new_mission`, `plan_off_clock`, `LiveHub.world`, `plan`, `plan_forever` | `tests/test_live.py::test_the_hub_plans_off_the_clock_and_things_move` |
| L5 | `GET /live?building&session_id` returns the snapshot (+ `clearance_m`) and re-asks the route on the map by its event's own `request`: `reroute` (new route event appended, Guide `live_note` set), `alert` (no way round / no request; once per blocker set) or `suggestion` (≤ every 4 s); `POST /live/shorter` takes it | `backend/live.py` `router`, `live_check`, `take_shorter`, `route_blocked`, `route_walks` | `tests/test_live.py::test_the_route_on_the_map_is_moved_round_pallets`, `::test_the_reroute_follows_the_route_on_the_map_not_an_older_question`, `::test_a_route_without_a_request_gets_an_alert_not_a_new_route` |
| L6 | Route events carry `request` from find_route, route_to_building (to the exit) and the arrival from a nearby building; `BuildingSession.reroute(request)` routes it again under the live state | `agent/tools.py` `tool_find_route`, `reroute`; `agent/campus.py` route events | `tests/test_guide.py` (exact route event incl. `request`); read |
| L7 | `/live/control` (speed clamped 0.25–8, pause, resume, drop pallet/forklift at a point, clear, block_route, reset) and real-device ingest (`POST /live/devices`, `/live/devices/{id}/report` with `X-Device-Token`) reject bad input with 4xx | `backend/live.py` `control`, `register`, `device_report`, `drop`, `blocking_spot` | `tests/test_live.py::test_control_rejects_what_it_cannot_do`, `::test_a_tapped_pallet_and_a_real_device`, `::test_a_real_device_on_an_unknown_floor_is_refused` |
| L8 | Access mode: a non-admin never sees things (or wet patches) in spaces hidden from them, neither in `GET /live` nor in `live_status` | `backend/app.py` `live_hidden`; `backend/live.py` `hidden_hazard`, `visible`, `SessionLive.devices(spaces)` | `tests/test_live.py::test_viewers_never_see_things_in_spaces_hidden_from_them` |
| L9 | Guide: sessions get `session.live` while a world runs (`with_live`), Guide routes use it, new tool `live_status` only then, prompt paragraph on `live` results, `[live note]` sent with the next turn | `backend/app.py` `with_live`; `agent/tools.py` `live_effects`, `live_clearance`, `tool_live_status`, `LIVE_STATUS`, `tool_definitions`; `agent/guide.py` prompt, `live_note` | `tests/test_live.py::test_the_guide_can_ask_what_is_live`; read |
| L10 | Sessions with live routes still save (JSON) | `backend/persistence.py` unchanged | `tests/test_live.py::test_sessions_with_live_routes_still_save` |
| L11 | Frontend: live layer (footprints by tone, no-pass zone for blockers, fading 50 m trails, dashed ahead line, wet patches), markers with a ping per report, Live button + panel (devices, demo controls, tap to drop), route notices (reroute auto-hides 9 s, alert/suggestion stay until dismissed/taken or the route ends); hidden in Edit mode; never another building's snapshot | `frontend/app/src/live/` (`LiveLayer.tsx`, `LivePanel.tsx`, `kinds.ts`, `useLive.ts`, `live.css`); `building/BuildingScreen.tsx`; `plan/PlanView.tsx`; `plan/palette.ts` (`liveBlock`, `liveIdle`, `liveWet`); `api.ts` types + calls | `npx tsc -b --noEmit`; `npx vite build`; read |
| L12 | Docs: new `docs/product/living-building.md` (front matter, linked from docs/README.md, backlink from routing-profiles.md); log entry + project-state bullet | those files | `python3 scripts/check_links.py` |
| L13 | Access mode: `POST /live/control` and `POST /live/devices` need the building admin (`admin_or_403(authorization)`, only when access is enabled); with access mode off they stay open (demo). `block_route` still looks the session up via `conversation_or_404`; the device report endpoint keeps its own `X-Device-Token` | `backend/live.py` `router(..., enabled, admin_or_403)`, `admin_in_access_mode`, `control`, `register`; `backend/app.py` `live_router(..., lambda: access.enabled, admin_or_403)`; `docs/product/living-building.md` Access mode paragraph | `uv run pytest -q tests/test_live.py::test_in_access_mode_only_the_admin_uses_the_controls_and_registers_devices` (anonymous + member → 403, admin → 200; monkeypatched access, `hub.worlds` cleared by the fixture) |
| L14 | `live_check` reroute: the new route event is enriched first; if the map can't draw it (no `line`) the alert is returned without appending the event, setting `live_note` or saving; only a drawable reroute is appended, noted and saved (otherwise unchanged) | `backend/live.py` `live_check` | read; `uv run pytest -q tests/test_live.py` |

## Checks I ran

- `uv run pytest -q` (main checkout, after the merge) → `1035 passed, 2 skipped in 123.15s`
- `uv run pytest -q tests/test_live.py tests/test_voice_location.py tests/test_guide.py` → `54 passed in 8.72s`
- `npx tsc -b --noEmit` (frontend/app) → exit 0; `npx vite build` → `✓ built in 589ms`
- `python3 scripts/check_links.py` → `OK: all links resolve in 40 files`
- `grep -rn "next-move card" core backend frontend/app/src` → only `CameraWalk.tsx` (C6)
- Living building, in the worktree before the merge: stress script over all 280 buildings (world, 150 s simulated,
  snapshot, 5 live routes, blocked-route reroute, route_line on each) → `rows 280 errors 0`, no malformed paths;
  headless Chrome (Playwright) with the live Opus Guide: reroute while guiding (trip 50 m → 80 m, guide goes on),
  alert + dismiss, "clear again" + Take it (back to 50 m), tap to drop (outside refused), Edit mode hides the layer.
- Session -20 (before the merge): `uv run pytest -q tests/test_voice_location.py` → `10 passed`;
  `set_my_location {"place": "outside"}` → `{'error': "No place matches 'outside'. Try search with fewer words."}`

- Fix round 1 (after verifier round 1), main checkout:
  - `uv run pytest -q` → `1036 passed, 2 skipped in 119.38s (0:01:59)`
  - `uv run pytest -q tests/test_live.py` → `37 passed in 7.26s` (includes the new
    `test_in_access_mode_only_the_admin_uses_the_controls_and_registers_devices`)
  - `python3 scripts/check_links.py` → `OK: all links resolve in 40 files`

- Fix round 2 (after verifier round 2), main checkout:
  - `uv run pytest -q` → `1036 passed, 2 skipped in 155.40s (0:02:35)`
  - `uv run pytest -q tests/test_live.py` → `37 passed in 7.23s`
  - `python3 scripts/check_links.py` → `OK: all links resolve in 40 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (both chunks)
- [x] `memory-bank/log.md` entries added (both chunks)
- [ ] decisions / open questions: none needed
- [x] docs touched: docs/architecture/ai-agents.md (C4), docs/product/living-building.md (new), docs/README.md, docs/product/routing-profiles.md

## Known gaps / not done
- C1 not tried in a browser: with access mode off the Edit mode of `?edit=1` now appears only after GET /config answers (a short delay, no flash for the wrong viewer).
- If `startAccess()` were never called, `checking` would stay true and the Edit mode would never open; Root.tsx calls it on start.
- Living building: the devices are simulated (labelled "simulated" in the app and in `live_status`); no real hardware
  device tried. Worlds live in process memory: several backend instances would each run their own. Not tried with a
  live mic. The two giant OSM corridors (>100 corners) use straight lines for the squeeze / wet / narrow checks.
- `frontend/app/shot.mjs` and `.claude/worktrees/` are untracked and not part of this commit.

## Verification rounds
- Round 1: FAIL — live controls/devices open in access mode; log entry at bottom; misplaced comment; PENDING checks.

## Fix round 1
- Live controls / device registration open in access mode: implemented — `backend/live.py` `router` takes `enabled`
  and `admin_or_403`; `control` and `register` call `admin_in_access_mode(authorization)`; `backend/app.py` passes
  `lambda: access.enabled, admin_or_403`; test in `tests/test_live.py`; one sentence in the Access mode paragraph of
  `docs/product/living-building.md` (and its "Tested" count 36 → 37). Claim L13.
- log.md entry order: implemented — "The living building" entry moved unchanged from the bottom of
  `memory-bank/log.md` to just below the "(not committed)" verifier-fix entry at the top.
- Misplaced comment: implemented — `backend/live.py` the "offered back … this much shorter" comment is back on
  `REROUTE_GAIN_M`; `SUGGEST_EVERY_S` keeps only its own comment.
- PENDING.md: implemented — L13 row, fresh check outputs above, "Verification rounds" kept.
- Round 2: FAIL — project-state still says 36 tests / no admin-only note; log missing fix round 1. (Noted bug: reroute saved before its line check.)

## Fix round 2
- project-state "Living building" bullet: implemented — test count 36 → 37 and the access-mode clause (admin-only
  `/live/control`, `/live/devices`; open with access mode off), matching living-building.md. `memory-bank/project-state.md`.
- log.md fix-round line: implemented — one line added to the "The living building" entry. `memory-bank/log.md`.
- Reroute saved before its line check (verifier note): implemented — `backend/live.py` `live_check` enriches the event
  first and only appends / sets `live_note` / saves when it has a line. Claim L14.
- Round 3: PASS (tree 9b86d71).


---

# Verification report (final round)

VERDICT: PASS
TREE: 9b86d71dedd43999a7afe2a75048e79c98707030

All claims C1–C7 and L1–L14 MET. pytest 1036 passed, 2 skipped (run twice); test_live 37 passed; tsc exit 0; vite build OK; check_links OK (40 files); no secrets; score.py unchanged; no hard-coded test/building ids in non-test code.
Undeclared changes: none significant; every staged file maps to a claim.
Non-blocking notes: (a) the no-line alert path in live_check skips the once-per-blocker-set gate (may repeat per poll; the app's dismissed set hides repeats); (b) PENDING Known gaps says "two" giant OSM corridors, code/docs say 3.
Required fixes: none.
