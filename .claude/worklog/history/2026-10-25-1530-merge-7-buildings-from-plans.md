# Merge 7-buildings-from-plans into dev (buildings from plans: reference + trace, map position, floors per file, add / straighten floors, delete)

- **Author:** Claude session industrial-agents-hackathon (merge, for Atahan); branch work by a Claude session with Utku
  (f2e3e73) · **Date:** 2026-10-25
- **Related:** D-023; docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md; the branch's own
  worklog `.claude/worklog/history/2026-10-25-1700-buildings-from-plans-UNVERIFIED.md` (4 verifier rounds, /ship
  skipped for time — "Atahan runs /ship": this is that run)

## Summary
Merge commit of `origin/7-buildings-from-plans` (one commit, f2e3e73, branched from 401dfa1) into dev (4466286, 8
commits ahead of the merge base). B1–B16 are the branch's claims, re-checked on the merged tree; M1–M6 are the
merge itself (25 conflict blocks in 12 files resolved keeping both sides).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| B1 | `reference_for` stores a ≤1600 px JPEG data URL with the px → metres transform, crops empty paper (grey ≥ 235, 6 px edge kept) and moves the transform with the crop; `strip_references` removes them | `core/plan_import/reference.py` | `uv run pytest tests/test_plan_references.py -q` → 11 passed |
| B2 | `GET /drafts/{id}/references` returns the references by level; every other draft payload has them stripped | `backend/drafts.py` `state`, `references`; `backend/app.py` | `tests/test_plan_references.py` |
| B3 | `scale_building` scales the building about (0, 0) and also each floor's `reference.transform` and `m_per_px`; `set_location` sets / removes `building.location` | `core/edits.py` | `tests/test_plan_references.py::test_scale_building_scales_the_reference_with_it`, `tests/test_placement.py` |
| B4 | `core/geoplace.py`: lat/lon ↔ metres with bearing, footprint, IoU fit (principal axes + coordinate descent, scale clamped 0.75–1.25, low_confidence below IoU 0.5 or at a bound), `location_for`, `placement_ops`, `distance_m` | `core/geoplace.py` | `uv run pytest tests/test_geoplace.py -q` |
| B5 | `PUT /drafts/{id}/location` (scale out of 0.75–1.25 → 422, fit `by_hand`) and `POST /drafts/{id}/fit`; `/imports/stream` takes `place` / `device`, places the import and returns `location`, `located_by`, `suggestion`; save sets `supersedes` and the older catalogue entry is hidden from the map | `backend/app.py`, `backend/drafts.py` | `uv run pytest tests/test_placement.py tests/test_import_location.py -q` |
| B6 | EXIF GPS read (`photo_gps`, S/W negative) and median over photos (`median_gps`); Overpass lookup `building_at` (inside first, then nearest; any failure → None) | `core/plan_import/ingest.py`, `core/osm_lookup.py` | `tests/test_import_location.py` |
| B7 | Frontend: reference panel right of the editor sized to the image + Trace overlay; right-click card at the cursor with the outline of the building under it (left click / Esc closes); Placement screen (drag / turn / size, suggestion, tile fallback); "Edit position" map-pin button in the Edit bar for placed buildings (one undo step via `useDraft.adopt`); map applies `location.bearing` | `frontend/app/src/edit/*`, `src/map/*`, `src/import/*`, `src/building/BuildingScreen.tsx`, `src/Root.tsx`, `src/api.ts` | `cd frontend/app && npx tsc -b` (clean); `node --experimental-strip-types scripts/geo.check.ts` / `scripts/trace.check.ts` → ok |
| B8 | `test_buildings_carry_a_location_only_where_one_is_known` scoped to kit buildings (user buildings can now be placed) | `tests/test_backend.py` | read the test |
| B10 | Each uploaded file has a user-given floor (`levels` form field: one int per file, all different, else 422); sources carry it, the Creator is told, `register_plan` keeps it | `core/plan_import/ingest.py` `load_sources`, `core/plan_import/model.py` `Source.level`, `agent/creator.py` `opening`, `agent/creator_tools.py` `tool_register_plan`, `backend/app.py` `levels_or_422` | `uv run pytest tests/test_floor_levels.py -q` |
| B11 | Edit mode "Add a floor": `draft` form field imports into the open draft as one undo step (edit op `add_floors`, `core/plan_import/merge.py`): floors laid onto the building with walls parallel (quarter turns only, `fit_shape(bearings=…)`), stairs / lifts joined, plans kept; a level the draft has → 422 before the Creator runs | `core/plan_import/merge.py`, `core/geoplace.py` `fit_shape`, `core/edits.py` `add_floors`, `backend/app.py` | `uv run pytest tests/test_add_floor.py tests/test_floor_levels.py -q` |
| B12 | Edit ops `straighten_floor` (turn a floor in place parallel to the lowest floor, its plan too) and `set_reference` (move / turn / resize a floor's kept plan) | `core/edits.py` | `tests/test_add_floor.py::test_straighten_floor_turns_it_parallel_to_the_lowest_floor`, `tests/test_plan_references.py::test_set_reference_moves_a_floors_plan` |
| B13 | `DELETE /buildings/user/{slug}` (admin only in access mode): file store moves it to `.deleted/`, memory / Postgres delete it; the version it superseded returns to the map; dataset / unknown → 404 | `backend/app.py`, `backend/drafts.py` `delete`, `delete_building` (3 backends) | `tests/test_add_floor.py` delete tests |
| B14 | Frontend: per-file Floor inputs (validated) on the import; ＋ Add a floor and ruler Straighten in the Edit bar; map card Open / Delete only ("Which version?" picks first, "Version n" labels); trace Adjust (drag + handles + Turn / Size buttons); reference window draggable / resizable (localStorage); problems list and toast over the reference (z-index 5); floor picker follows the draft; Edit position draws the current floor; Save position closes first | `frontend/app/src/import/*`, `src/edit/*`, `src/map/MapLanding.tsx`, `src/map/Placement.tsx`, `src/building/BuildingScreen.tsx`, `src/Root.tsx`, `src/api.ts` | `npx tsc -b`; `node --experimental-strip-types scripts/trace.check.ts` → ok |
| B15 | `agent/campus.py` `lnglat` uses `core.geoplace.to_lnglat` with the building's `location.bearing`, so the Guide's campus entrance positions follow a placed building's bearing; kit buildings (bearing 0) are unchanged | `agent/campus.py` `lnglat`, `Campus.entrances` | read the diff; the campus tests in the full suite pass |
| B16 | Save keeps the draft's own `source_ref.import` (adjusted trace, plans scaled with the building, floors added with their plans), falling back to the base's import only when the draft has none — also on a second save of a saved building | `backend/drafts.py` `save`, `references` docstring | `uv run pytest tests/test_plan_references.py -k survive -q` (RED before the fix: transform reverted to the base's) |
| B9 | Docs: visualization.md new section, commands.md 3 endpoints + import fields, spec status implemented; memory bank: project-state, log, D-023 | docs/, memory-bank/ | `python3 scripts/check_links.py` → OK |
| M1 | Every change of f2e3e73 is in the merged tree except where a conflict was resolved as listed in M2–M5 (no branch file dropped; the branch's new files all present) | whole tree | `git diff f2e3e73 --stat` vs the merge (only the M2–M5 spots and dev's own changes differ); `git diff --name-only 401dfa1 f2e3e73 --diff-filter=A` all exist |
| M2 | backend/app.py `/buildings` items carry both dev's `kind` and the branch's `location: None if superseded` | `backend/app.py` `buildings` | read; `tests/test_backend.py` |
| M3 | Frontend conflicts kept both sides: Root.tsx (branch's `ImportPlace` + `onImport(where)` + `onDeleted`, dev's removal of `onList` / `Showing`); MapLanding.tsx (dev's kind chips / search / list + branch's create / delete card, `versionOf`, helpers; no `onList`); EditBar.tsx (dev's `accessTool` + branch's `onPlace` / `onAddFloor` / `onStraighten`); EditLayer.tsx (branch's `trace` under, dev's Access hatching over it); useDraft.ts (both `adopt` / `references` and `failed`) | those files | `npx tsc -b` exit 0; read the hunks |
| M4 | BuildingScreen.tsx: imports of both; dev's `useDraft(…, admin)` / Building settings / `useAccessRules` + branch's Edit position / Add a floor state, the branch's `placing` renamed `placingOnMap` (dev's living-building `placing` is the live pallet drop); the branch's reference-column insets fitted onto dev's current insets (no `devOpen` / `PANEL_PX` / `DEV_PX` / `ThemeIcon`, which dev removed); `shownPlan` defined once, before `current`; dev's `liveBottom`; `restricted` + `trace` both passed to EditLayer; EditBar gets `accessTool={admin}` and the branch's callbacks | `frontend/app/src/building/BuildingScreen.tsx` | `grep -n "placingOnMap\|devOpen\|PANEL_PX" …`; `npx tsc -b` exit 0 |
| M5 | CSS / docs: map.css + import.css take the branch's new rules (import.css keeps dev's removal of its reduced-motion line); visualization.md has the branch's new section followed by dev's renamed "## Answers on the plan"; log.md keeps both histories (branch entry on top), the d6b07c9 fixes heading now names 4466286; project-state's last-updated line names the merge and both chunks | those files | read; `python3 scripts/check_links.py` |
| M6 | The merged app runs: no page errors on the map, a building and Edit mode; the right-click create card appears; the live panel still works and hides in Edit mode | browser | see "Checks I ran" |

## Checks I ran (merged tree)

- `uv run pytest -q` → `4 failed, 1084 passed, 2 skipped` with files still marked unmerged (the 4 = tests/test_commit_hook.py, `git write-tree` fails mid-merge); after `git add` of the resolutions: `uv run pytest -q tests/test_commit_hook.py` → `12 passed` (so 1088 passed, 2 skipped)
- `uv run pytest -q tests/test_plan_references.py tests/test_geoplace.py tests/test_placement.py tests/test_import_location.py tests/test_add_floor.py tests/test_floor_levels.py tests/test_live.py tests/test_backend.py` → `115 passed in 10.48s`
- `cd frontend/app && npx tsc -b` → exit 0; `npx oxlint src` → 40 warnings, 0 errors; `npx vite build` → `✓ built in 603ms`
- `node --experimental-strip-types scripts/geo.check.ts` → `geo.check (merged tiles): ok`; `scripts/trace.check.ts` → `trace.check: ok`
- `python3 scripts/check_links.py` → `OK: all links resolve in 42 files`
- Fix round 1, after the decisions.md next-id bump: `python3 scripts/check_links.py` → `OK: all links resolve in 42 files`
- No conflict markers: `git grep -n -E "^(<<<<<<<|>>>>>>>|\|\|\|\|\|\|\|) "` → nothing
- Headless Chrome (backend :8775 with `ACCESS_MODE=off`, vite :5185): map right-click → `.ml-create` card 1; factory Live panel 8 things; `?edit=1` → Edit bar 1, Live button 0; page errors / console errors: none. With access mode on and signed out the Edit button and create card are hidden (expected).

## Knowledge base updates
- [x] `memory-bank/project-state.md` (last-updated line for the merge; the branch's own bullets came with it)
- [x] `memory-bank/log.md` (both histories; branch entry on top)
- [x] decisions: D-023 (proposed) came with the branch
- [x] decisions.md: "Next free id" bumped from D-023 to D-024 (D-023 exists; no D-024 yet) — fix round 1
- [x] docs: docs/product/visualization.md (merged), docs/guides/commands.md (branch)

## Known gaps / not done
- From the branch's worklog: - Postgres `delete_building` is untested (file + memory stores are). "Add a floor" with the real Creator was run by Utku live, not by me; the API path is tested with a fake Creator.
  - Final whole-branch code review (skipped for time, user's call); Supabase store supersede path untested (file store only).
  - OSM buildings cut at tile edges are not merged (outline may be a part).
  - Overpass (overpass-api.de) is often busy; the app's tile fallback covers the photos/device case only.
  - Existing imports made before the scale fix keep unscaled references (Utku's two local files were repaired by hand, data/user is gitignored).
- Not from this merge, seen while checking: the "New building from floor plans / Create →" row at the bottom of the
  map list has no CSS on dev (commit 3113a99 removed `.ml-more`), so its two texts run together.
- The create / delete card, Placement, Add a floor and Straighten were not exercised end to end in the browser after
  the merge (only that the card opens and Edit mode loads); their backend paths are covered by the tests above.

## Verification rounds
- Round 1: FAIL — decisions.md "Next free id" still D-023 (D-023 exists). All claims MET.
- Round 2: PASS (tree cce20ff).


---

# Verification report (final round)

VERDICT: PASS
TREE: cce20ff9dff3ffb45608cc4a92cadb008fea9fd7
All claims B1–B16 and M1–M6 MET. pytest 1088 passed, 2 skipped; targeted 115 passed; tsc exit 0; oxlint warnings only; vite build OK; geo/trace checks ok; check_links OK (42 files); no secrets; score.py unchanged; no hard-coding; no conflict markers; headless smoke test re-run (create card, Live panel, Edit mode hides Live, no errors).
Undeclared changes: none significant (worklog files; decisions.md next id D-024 declared).
Known gaps stated honestly.
