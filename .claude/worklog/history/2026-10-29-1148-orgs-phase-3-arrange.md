# Organisations phase 3: editors arrange and name the islands

- **Author:** Claude (Opus 5.5 session) · **Date:** 2026-10-29
- **Related:** D-029, docs/product/organizations.md § Phase 3

## Summary
A map's editors drag the islands of its board (mouse or touch, pulled against neighbours' edges, never onto one) and
name its sites; each change is saved at once in the map's `layout` and the board follows it on every screen.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `PUT /maps/{slug}` accepts `layout: {sites: [{buildings, name, dx, dy}]}`: name ≤ 60 (trimmed, empty → null), dx / dy ints within ±2^26 and kept only when both are given, ≤ 200 sites, sites without buildings dropped, buildings de-duplicated; editors only; name / visibility changes keep the layout | `backend/api/routes/maps.py` `Site`, `Layout`, `layout_site`, `update_map` | `uv run pytest -q tests/test_maps.py` → 7 passed |
| C2 | `boardOf(buildings, arrangement, layout)`: stored sites matched to computed islands by most shared buildings (each once); if any matched site has dx and dy, islands are placed by the layout (unplaced ones to the right of the board, tops aligned, edge to edge) and the board is the same on every screen; otherwise automatic arrangement with stored names | `frontend/src/map/board.ts` `matchSites`, `placeByLayout`, `boardOf` | `node --experimental-strip-types frontend/scripts/board.check.ts` → ok (row and column give the same key and rects for a stored layout; a new far building goes right; names alone keep the automatic key) |
| C3 | `seamsOf`: a seam wherever two islands share an edge (vertical seam label below its lower end, horizontal one left of its left end); `arrange` now uses it (same seams as before for rows and columns) | `board.ts` | board.check.ts (first-cut assertions still pass) |
| C4 | `dropAt` pulls the dragged rect's edges onto another island's edges within `pull`, snaps to the grid, returns null on overlap; `changed` moves / renames one island; `layoutOf` stores moves in grid steps; `Board.byHand` | `board.ts` | board.check.ts |
| C5 | Names drawn over each named island's top-left corner (`island-name` layer in `boardStyle`) | `board.ts` `boardShapes`, `style.ts` | read |
| C6 | MapLanding: "Arrange" in the scope header when `onArrange` is given (Root passes it when `can_edit`); while arranging, clicks do not open buildings; mousedown / touchstart on an island prevents the pan and drags a ghost outline (red when refused); drop → `onArrange(layout)`; tap → name form ("Save name"); bar with "Line them up" (only when `byHand`) and Done; a refused save is put back by Root and said as "Not saved: …" | `frontend/src/map/MapLanding.tsx`, `frontend/src/Root.tsx` `arrange`, `frontend/src/map/map.css` | read; headless below |
| C7 | A changed board after the first one swaps tiles in place (`VectorTileSource.setTiles`) and updates the `board` shapes with `setData`; the first real board (after the empty one) and theme changes still `setStyle` | `MapLanding.tsx` style effect | read; headless reload check |
| C8 | `OrgMapView.layout`, `api.updateMap(..., {layout})` | `frontend/src/api.ts` | read |
| C9 | Docs: organizations.md (arranging paragraph, still-to-do), commands.md API row, project-state, log | docs, memory-bank | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q tests/test_maps.py` → `7 passed`
- `uv run pytest -q` → `979 passed, 2 skipped in 113.45s (0:01:53)`
- `node --experimental-strip-types frontend/scripts/board.check.ts` → `board.check: ok`
- `cd frontend && npx tsc -b` → clean; `npx oxlint src/Root.tsx src/api.ts src/map` → no output; `npx vite build` → `✓ built`
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`
- Headless Playwright (scratchpad, fake signed-in owner, in-memory backend :8391, map `tum-sites`): Arrange → dragging Weihenstephan under the main campus showed the ghost and dropped snapped to the campus's left and lower edges (screen x0 556 = 556, y0 607 = 607); PUT layout sent; seam "30 km apart"; tapping Garching and saving "Garching" drew the name; after a reload the arrangement came back. First reload showed blank islands (`setTiles` during the empty board's style load, 0 transportation features after 20 s); fixed (first board → setStyle), then 189 features at 5 s. Phone 390×844 with CDP touch events: the island moved, the map centre did not change, one PUT; bar moved under the title (it overlapped the zoom buttons). No console errors.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none new (within D-029)
- [x] docs touched: docs/product/organizations.md, docs/guides/commands.md

## Known gaps / not done
- No merging or splitting of sites by hand; no drawn areas; no blue dot on the board.
- Keyboard: islands cannot be moved without a pointer (naming works by keyboard once the form is open).
- Concurrent editors: the last save wins (whole layout replaced).
- An island may be dragged far from the others (no limit); the camera bounds follow the board.
- Browser checks are scratchpad Playwright scripts, not in the repo.

## Verification rounds
- Round 1: PASS (tree 84590fc2c5cb75fb069734ea917ee1a5e5c9369e)

## Verification report (round 1)

VERDICT: PASS
TREE: 84590fc2c5cb75fb069734ea917ee1a5e5c9369e

C1–C9 MET. test_maps 7 passed; full pytest 979 passed, 2 skipped; board.check ok; tsc clean; oxlint clean; links OK (25 files);
no secrets; score.py unchanged; no hard-coding. vite build and headless Playwright not re-run (scratchpad, Known gaps).
Undeclared (minor): Site.buildings capped at 500; board.ts exports `at` and types Piece/SiteLayout/Layout; a duplicate
tests/test_maps.py entry in organizations.md front matter.
