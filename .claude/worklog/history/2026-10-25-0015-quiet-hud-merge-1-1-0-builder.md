# Building screen "Quiet HUD", map landing, dev panel; merged with kit 1.1.0 route model + Builder Edit mode

- **Author:** Claude (Opus 5.5) sessions for Atahan, 2026-10-24 → 2026-10-25 · **Date:** 2026-10-25
- **Related:** D-011, D-014 (kit 1.1.0 route model), memory-bank/log.md entries 2026-10-24 "Plan view: solid walls"
  … 2026-10-25 "Pulled `origin/dev` twice"; docs/product/visualization.md

## Summary
The uncommitted app work on `dev` since 92f063a: point cloud removed, plan-view walls/doors/furniture/overlaps, map
landing + list view, the dev panel merged into the app, and the building screen's voice-first "Quiet HUD" (Guide
captions + Core, work trail, next-move card, camera walk, dead-reckoning tracking). `origin/dev` was pulled twice on
top of it (26b908f kit 1.1.0 route model, b352e83 Builder Edit mode); this change also contains the conflict
resolution and the fixes for what broke without a text conflict.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Point cloud removed: `core/pointcloud.py`, `tests/test_pointcloud.py`, `GET /sessions/{id}/points`, route `vertices`, `frontend/app/src/App.tsx`, `src/scene/` deleted; no code imports `core.pointcloud` / `export_points` | `backend/app.py`, `backend/sessions.py`, `core/floorplan.py` (now holds `door_gaps`, `sorted_floors`, `floor_indices`, `SKIPPED_TYPES`) | `git diff --cached --stat`; `grep -rn -E 'core\.pointcloud\|export_points' backend core agent tests frontend/app/src scripts` → nothing |
| C2 | `export_plan(building_map, center=None)` computes `center` from the space bounds when not given (same formula as `backend/drafts.py` `DraftStore.plan`) | `core/floorplan.py:export_plan` | read both; `uv run pytest -q tests/test_floorplan.py tests/test_drafts.py` |
| C3 | Plan walls/doors/overlaps: `wall_solids` (gaps, 10 cm partitions incl. rooms < 3 cm apart, 25 cm exterior), `open_zones` (no wall where an open space runs through a bigger one), `overlaps` stripes, `outlines`, doors = threshold strips (no swing) | `core/floorplan.py`, `frontend/app/src/plan/geometry.ts`, `furniture.ts`, `palette.ts`, `PlanView.tsx` | `uv run pytest -q tests/test_floorplan.py` |
| C4 | Route events carry a plan `line` (`core/routeline.route_line`) and the Guide's `steps` (`core/directions.guidance`) | `core/routeline.py`, `core/directions.py:guidance`, `backend/sessions.py` | `uv run pytest -q tests/test_routeline.py tests/test_directions.py tests/test_backend.py` |
| C5 | Merge fix: `core/routeline.py` no longer uses the deleted `core/geodesic.py`; its in-space walk uses `core/building_map.py`'s `outline` / `door_landing` / `visibility_matrix` with `WALL_CLEARANCE_M` and `COVER_TOLERANCE_M` (cached per outline); `core/building_map.py` itself unchanged | `core/routeline.py:_walkable`, `walk_corners` | read; `git diff --cached core/building_map.py` → empty; `uv run pytest -q tests/test_routeline.py` |
| C6 | Merge fix: Builder's `GET /drafts/{id}/points`, `api.draftPoints` and `test_points_endpoint` removed (needed the deleted `core/pointcloud.py`; unused by the UI); all other `/drafts` endpoints kept | `backend/app.py`, `frontend/app/src/api.ts`, `tests/test_drafts.py`, `docs/guides/commands.md` | `grep -n "/points" backend/app.py` → nothing; `uv run pytest -q tests/test_drafts.py` |
| C7 | Merge: `/buildings` keeps both `drafts.refresh(quiet=True)` (Builder) and `location` (map landing) | `backend/app.py:buildings` | read; `uv run pytest -q tests/test_backend.py` |
| C8 | Merge: Edit mode reachable from the HUD: "Edit this building" item in `BuildingScreen`'s "…" menu → `EditMode`; `Root` passes `onOpen={(id) => go(id, view.landing)}` so a saved building opens; Edit-mode `PlanView` gets `story={EMPTY_STORY}` | `frontend/app/src/building/BuildingScreen.tsx`, `Root.tsx`, `edit/EditMode.tsx` | read; `cd frontend/app && npm run build` passes |
| C9 | Map landing (MapLibre, OpenFreeMap) for the 17 OSM buildings with a position (`backend/locations.json`), list view `?view=list`; `/buildings` items have `location` | `frontend/app/src/map/`, `Root.tsx`, `src/search/`, `backend/locations.json`, `NOTICE.md` (ODbL) | `uv run pytest -q tests/test_backend.py`; read NOTICE.md |
| C10 | Dev panel in the app (`frontend/app/src/dev/`, shown in Vite dev or `?dev`) with backend `/dev/*` | `frontend/app/src/dev/`, `backend/devtools.py`, `backend/app.py` | `uv run pytest -q tests/test_devtools.py` |
| C11 | Quiet HUD: `Core.tsx`, `Guide.tsx` (captions, work trail), `NextMove.tsx`, `CameraWalk.tsx` + `frame.ts`, `tracking.ts` + `useTracking.ts`, `hud.css`; `Conversation.tsx` removed | `frontend/app/src/building/` | `npm run build` passes; screenshots only in earlier sessions (see Known gaps) |
| C12 | Core voice ticks animate with `transform: scaleY` instead of `height` (no layout per audio frame), same 4 + 13 px / 3 + 8 px sizes | `frontend/app/src/building/hud.css` `.core-ticks i::before` | read |
| C13 | Whole suite and frontend build pass; doc links resolve | — | `uv run pytest -q` → 753 passed, 2 skipped; `npm run build`; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q` → `753 passed, 2 skipped in 92.89s`
- `uv run pytest -q tests/test_routeline.py tests/test_drafts.py tests/test_backend.py tests/test_devtools.py tests/test_floorplan.py tests/test_directions.py` → `66 passed`
- `cd frontend/app && npm run build` → `✓ built in 494ms` (tsc -b included; only the chunk-size warning)
- `python3 scripts/check_links.py` → `OK: all links resolve in 32 files`
- `grep -rn -E 'core\.pointcloud|from core import geodesic|export_points|draftPoints' backend core agent tests frontend/app/src scripts` → nothing
- Merge check: every line either side added in the 9 files changed on both sides is present, except the lines
  deliberately rewritten (merged import lines, Edit button moved into the menu, `Root` `onBack`/`onOpen`) and the
  removed `/drafts/{id}/points` (C6).

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (Quiet HUD bullet, Edit mode in "…" menu, date)
- [x] `memory-bank/log.md` entries added (HUD steps 1–5, plan/dev panel/map entries, the two pulls)
- [x] decisions / open questions touched: none (no new decision; C6 recorded in the log)
- [x] docs touched: `docs/guides/commands.md`, `docs/product/visualization.md`, `docs/README.md`, `CLAUDE.md`, `NOTICE.md`

## Known gaps / not done
- The HUD, camera walk and tracking were checked with screenshots in earlier sessions, not on a real phone; the
  0.7 m stride is UNVERIFIED; camera "Where am I?" needs the real Claude Guide.
- Edit mode after the merge (menu entry, preview with the empty story) was not opened in a browser — build only.
- The `routeline` walk after the 1.1.0 port is covered by `tests/test_routeline.py` only; not looked at on the plan.
- `docs/product/visualization.md` "App and data path" section still describes the old point-cloud app (stale
  before this change).
- `oxlint` warns `react(set-state-in-effect)` at `frontend/app/src/edit/EditMode.tsx:68` (Builder code, pre-existing).
- Not committed on purpose: `.vite/` (Vite cache), `.impeccable/questions/` (design-tool log).

## Verification rounds
- Round 1: VERDICT: PASS (tree 4718c2daea53ced87c22d7a371e19bdbc3dfdf38)

---

# Verification report (round 1)

VERDICT: PASS
TREE: 4718c2daea53ced87c22d7a371e19bdbc3dfdf38

## Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | pointcloud.py, test_pointcloud.py, App.tsx, scene/* deleted; /sessions/{id}/points gone; enrich no longer adds vertices; floorplan.py holds sorted_floors/floor_indices/door_gaps/SKIPPED_TYPES; grep for core.pointcloud/export_points/core.geodesic/draftPoints empty |
| C2 | MET | export_plan default center = same formula as backend/drafts.py:378-380; tests pass |
| C3 | MET | wall_solids/open_zones/overlaps/outline/clip_segments; PARTITION_M 0.1, TOUCH_M 0.03, EXTERIOR_M 0.25; door_geometry no side; test_floorplan (8) pass |
| C4 | MET | enrich adds legs, steps (guidance), line (route_line); tests pass |
| C5 | MET | routeline imports building_map primitives; _walkable lru_cache; geodesic.py absent; building_map.py unchanged; test_routeline passes |
| C6 | MET | no /points in app.py; draft_points, api.draftPoints, test_points_endpoint, commands.md row removed; other /drafts intact; test_drafts passes |
| C7 | MET | buildings() keeps drafts.refresh(quiet=True) and location; test passes |
| C8 | MET | "Edit this building" menuitem → EditMode; Root onOpen; EditMode story={EMPTY_STORY}; npm run build OK |
| C9 | MET | map/ MapLanding.tsx, style.ts, map.css; ?view=list; locations.json 17 entries; NOTICE.md ODbL row; test_backend passes |
| C10 | MET | backend/devtools.py /dev/* included via include_router; panel gated by DEV or ?dev; test_devtools (4) passes |
| C11 | MET | HUD files staged; Conversation.tsx deleted; build passes; no-device check declared in Known gaps |
| C12 | MET | hud.css .core-ticks uses height 17px + scaleY((4+h*13)/17), small 11px + scaleY((3+h*8)/11) |
| C13 | MET | pytest 753 passed, 2 skipped; build OK; check_links OK |

## Standard checks
- pytest 753 passed, 2 skipped; targeted 66 passed; links OK; no secrets; score.py unchanged.
- hard-coding: none; locations.json has 4 test-split OSM ids as map positions only (declared C9).
- No unstaged tracked changes; .vite/ and .impeccable/questions/ deliberately untracked.

## Undeclared changes (trivial)
- enrich no longer takes first_index; directions.py docstring; test_plan_export asserts bounds center; commands.md /events row lacks `line`; CLAUDE.md doc-map label.

## Knowledge base
- project-state, log, visualization.md, README, commands.md, NOTICE.md updated.
- Remaining staleness (non-blocking): visualization.md "App and data path" section; project-state.md:101 opens with "monochrome point cloud".

## Required fixes
None.
