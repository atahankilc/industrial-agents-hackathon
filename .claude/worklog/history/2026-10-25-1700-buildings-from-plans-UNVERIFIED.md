> **Not verified:** /ship was skipped at Utku's request (time); 4 verifier rounds ran — the last one found only a stale test count, since fixed. Atahan runs /ship.

# Buildings from plans: reference + trace, real map position, floors per file, add / straighten floors, delete

- **Author:** Claude (session with Utku) · **Date:** 2026-10-25 15:00
- **Related:** D-023, docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md, docs/superpowers/plans/2026-10-25-plan-reference-and-location.md

## Summary
An imported building keeps each floor's straightened plan (shown beside the editor, optionally traced under it) and
gets a real map position: right-click card on the map → import → fit onto the OSM footprint (or EXIF GPS / browser
position) → placed by hand → saved with `building.location` (origin, bearing, outline) and shown on the map; re-save
supersedes the older version; "Edit position" in the Edit bar re-opens the placement.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `reference_for` stores a ≤1600 px JPEG data URL with the px → metres transform, crops empty paper (grey ≥ 235, 6 px edge kept) and moves the transform with the crop; `strip_references` removes them | `core/plan_import/reference.py` | `uv run pytest tests/test_plan_references.py -q` → 11 passed |
| C2 | `GET /drafts/{id}/references` returns the references by level; every other draft payload has them stripped | `backend/drafts.py` `state`, `references`; `backend/app.py` | `tests/test_plan_references.py` |
| C3 | `scale_building` scales the building about (0, 0) and also each floor's `reference.transform` and `m_per_px`; `set_location` sets / removes `building.location` | `core/edits.py` | `tests/test_plan_references.py::test_scale_building_scales_the_reference_with_it`, `tests/test_placement.py` |
| C4 | `core/geoplace.py`: lat/lon ↔ metres with bearing, footprint, IoU fit (principal axes + coordinate descent, scale clamped 0.75–1.25, low_confidence below IoU 0.5 or at a bound), `location_for`, `placement_ops`, `distance_m` | `core/geoplace.py` | `uv run pytest tests/test_geoplace.py -q` |
| C5 | `PUT /drafts/{id}/location` (scale out of 0.75–1.25 → 422, fit `by_hand`) and `POST /drafts/{id}/fit`; `/imports/stream` takes `place` / `device`, places the import and returns `location`, `located_by`, `suggestion`; save sets `supersedes` and the older catalogue entry is hidden from the map | `backend/app.py`, `backend/drafts.py` | `uv run pytest tests/test_placement.py tests/test_import_location.py -q` |
| C6 | EXIF GPS read (`photo_gps`, S/W negative) and median over photos (`median_gps`); Overpass lookup `building_at` (inside first, then nearest; any failure → None) | `core/plan_import/ingest.py`, `core/osm_lookup.py` | `tests/test_import_location.py` |
| C7 | Frontend: reference panel right of the editor sized to the image + Trace overlay; right-click card at the cursor with the outline of the building under it (left click / Esc closes); Placement screen (drag / turn / size, suggestion, tile fallback); "Edit position" map-pin button in the Edit bar for placed buildings (one undo step via `useDraft.adopt`); map applies `location.bearing` | `frontend/app/src/edit/*`, `src/map/*`, `src/import/*`, `src/building/BuildingScreen.tsx`, `src/Root.tsx`, `src/api.ts` | `cd frontend/app && npx tsc -b` (clean); `node --experimental-strip-types scripts/geo.check.ts` / `scripts/trace.check.ts` → ok |
| C8 | `test_buildings_carry_a_location_only_where_one_is_known` scoped to kit buildings (user buildings can now be placed) | `tests/test_backend.py` | read the test |
| C10 | Each uploaded file has a user-given floor (`levels` form field: one int per file, all different, else 422); sources carry it, the Creator is told, `register_plan` keeps it | `core/plan_import/ingest.py` `load_sources`, `core/plan_import/model.py` `Source.level`, `agent/creator.py` `opening`, `agent/creator_tools.py` `tool_register_plan`, `backend/app.py` `levels_or_422` | `uv run pytest tests/test_floor_levels.py -q` |
| C11 | Edit mode "Add a floor": `draft` form field imports into the open draft as one undo step (edit op `add_floors`, `core/plan_import/merge.py`): floors laid onto the building with walls parallel (quarter turns only, `fit_shape(bearings=…)`), stairs / lifts joined, plans kept; a level the draft has → 422 before the Creator runs | `core/plan_import/merge.py`, `core/geoplace.py` `fit_shape`, `core/edits.py` `add_floors`, `backend/app.py` | `uv run pytest tests/test_add_floor.py tests/test_floor_levels.py -q` |
| C12 | Edit ops `straighten_floor` (turn a floor in place parallel to the lowest floor, its plan too) and `set_reference` (move / turn / resize a floor's kept plan) | `core/edits.py` | `tests/test_add_floor.py::test_straighten_floor_turns_it_parallel_to_the_lowest_floor`, `tests/test_plan_references.py::test_set_reference_moves_a_floors_plan` |
| C13 | `DELETE /buildings/user/{slug}` (admin only in access mode): file store moves it to `.deleted/`, memory / Postgres delete it; the version it superseded returns to the map; dataset / unknown → 404 | `backend/app.py`, `backend/drafts.py` `delete`, `delete_building` (3 backends) | `tests/test_add_floor.py` delete tests |
| C14 | Frontend: per-file Floor inputs (validated) on the import; ＋ Add a floor and ruler Straighten in the Edit bar; map card Open / Delete only ("Which version?" picks first, "Version n" labels); trace Adjust (drag + handles + Turn / Size buttons); reference window draggable / resizable (localStorage); problems list and toast over the reference (z-index 5); floor picker follows the draft; Edit position draws the current floor; Save position closes first | `frontend/app/src/import/*`, `src/edit/*`, `src/map/MapLanding.tsx`, `src/map/Placement.tsx`, `src/building/BuildingScreen.tsx`, `src/Root.tsx`, `src/api.ts` | `npx tsc -b`; `node --experimental-strip-types scripts/trace.check.ts` → ok |
| C15 | `agent/campus.py` `lnglat` uses `core.geoplace.to_lnglat` with the building's `location.bearing`, so the Guide's campus entrance positions follow a placed building's bearing; kit buildings (bearing 0) are unchanged | `agent/campus.py` `lnglat`, `Campus.entrances` | read the diff; the campus tests in the full suite pass |
| C16 | Save keeps the draft's own `source_ref.import` (adjusted trace, plans scaled with the building, floors added with their plans), falling back to the base's import only when the draft has none — also on a second save of a saved building | `backend/drafts.py` `save`, `references` docstring | `uv run pytest tests/test_plan_references.py -k survive -q` (RED before the fix: transform reverted to the base's) |
| C9 | Docs: visualization.md new section, commands.md 3 endpoints + import fields, spec status implemented; memory bank: project-state, log, D-023 | docs/, memory-bank/ | `python3 scripts/check_links.py` → OK |

## Checks I ran
- `uv run pytest -q` → `1028 passed, 2 skipped, 18 warnings in 324.33s` (final run after the save fix, branch `7-buildings-from-plans`)
- `uv run pytest -q tests/test_plan_references.py tests/test_geoplace.py tests/test_placement.py tests/test_import_location.py` → `34 passed` (before the floor / delete work); `tests/test_add_floor.py tests/test_geoplace.py tests/test_placement.py tests/test_floor_levels.py tests/test_plan_references.py` → `42 passed` (re-run after the C16 test)
- `cd frontend/app && npx tsc -b` → no output (clean); `npx oxlint src` → warnings only (pre-existing kinds), 0 errors
- `node --experimental-strip-types scripts/geo.check.ts` → `geo.check (merged tiles): ok`; `scripts/trace.check.ts` → `trace.check: ok`
- `python3 scripts/check_links.py` → `OK: all links resolve in 39 files`
- Live in Chrome (localhost:5181): right-click card at the cursor + building outline; Edit position on a kit-building draft fitted via `/fit` (IoU 0.86), turned 2° and saved (bearing 0.08 → 2.08, steps 1 → 2); Utku's live import: placement OK, trace aligned after the scale fix.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions: D-023 (proposed)
- [x] docs touched: docs/product/visualization.md, docs/guides/commands.md, the design's front matter

## Known gaps / not done
- Postgres `delete_building` is untested (file + memory stores are). "Add a floor" with the real Creator was run by Utku live, not by me; the API path is tested with a fake Creator.
- Final whole-branch code review (skipped for time, user's call); Supabase store supersede path untested (file store only).
- OSM buildings cut at tile edges are not merged (outline may be a part).
- Overpass (overpass-api.de) is often busy; the app's tile fallback covers the photos/device case only.
- Existing imports made before the scale fix keep unscaled references (Utku's two local files were repaired by hand, data/user is gitignored).

## Verification rounds
- Round 4: FAIL — the focused-set count in Checks I ran was stale (41 → 42 with the C16 test). Fixed after re-running it; Utku approved one more round.
- Round 3: FAIL — the new plan doc had no front matter; C1's test count was stale (11 with the C16 test). Fixed: front matter + spec backlink, count 11.
- Round 2: FAIL — save dropped the draft's `source_ref.import` (trace edits, scaled / added plans lost; empty after a second save); branch name in memory bank. Fixed: C16 + test, branch names, log note.
- Round 1: FAIL — docs/README.md index said PROPOSED for the implemented spec; `agent/campus.py` change undeclared. Fixed by the implementer: README line → IMPLEMENTED 2026-10-25, claim C15 added.
