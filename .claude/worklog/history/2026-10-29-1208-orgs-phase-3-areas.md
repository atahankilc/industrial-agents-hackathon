# Organisations phase 3: editors draw the islands' areas

- **Author:** Claude (Opus 5.5 session) · **Date:** 2026-10-29
- **Related:** D-029, docs/product/organizations.md § Phase 3

## Summary
While arranging an org map's board, an island taken by an edge or corner has its area drawn (a rectangle that always
holds the site's buildings, at most 3 km a side, pulled to neighbours' edges, never over another island). The area is
stored with the site in the map's layout. Two bugs found on the way are fixed: the board key ignored areas (stale
tiles), and `bridge.ts` kept stale put-back block pieces when only their places changed.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `Site.area` `{x0,y0,x1,y1}` ints in 0..2^26 with 0 < side ≤ 20 000 (`AREA_STEPS`), else 422; stored as given (or null) | `backend/api/routes/maps.py` `Area`, `layout_site` | `uv run pytest -q tests/test_maps.py` → 8 passed (`test_a_drawn_area_is_a_rectangle_on_the_grid`) |
| C2 | `islandsOf` gives each island `core` (buildings + `CORE_M` 10 m) and `auto` (the app's area); `boardOf` applies a stored `area` as `real`, grown to contain `core`, and marks it `drawn`; `layoutOf` stores `area` for drawn islands only | `frontend/src/map/board.ts` | `node --experimental-strip-types frontend/scripts/board.check.ts` → ok |
| C3 | `reshapeAt(board, index, rect, edges, pull)`: moving edges pulled to other islands' edges within `pull`, on the grid, never inside `core`, ≤ `MAX_AREA_M` (3000 m) a side unless the buildings need more, null on overlap; `changed({area})` keeps the island's place, `changed({fit: true})` gives back `auto`; `overlaps` shared with `dropAt` | `board.ts` | board.check.ts (400 m wider, stops at buildings, 9 km capped, refused into the main campus, stored and found again, fit) |
| C4 | The board key includes every island's area (a new area → new tile URL) | `board.ts` `boardFrom` | board.check.ts `drawn.key !== arranged.key` |
| C5 | MapLanding arranging: an edge or corner within 10 px (22 px touch) is taken to draw the area, the island under the pointer winning where two meet; resize cursors; ghost shows the reshaped area (red when refused); drop saves `changed({area})`; outlines and corner handles drawn while arranging (`board-handles`); naming card offers "Fit the area to its buildings" for drawn areas (disabled if it would overlap); "Line them up" keeps areas; bar text mentions edges | `frontend/src/map/MapLanding.tsx` | read; headless below |
| C6 | `applyBlocks` rebuild key also holds where the put-back pieces lie, so pieces moved (same ids and count) are rebuilt | `frontend/src/map/bridge.ts` | read; headless: the gap after shrinking shows no `buildings-3d-rest` features |
| C7 | Docs: organizations.md drawn-areas paragraph, still-to-do (any shape), header summary; commands.md layout row; project-state; log | docs, memory-bank | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q tests/test_maps.py` → `8 passed`
- `uv run pytest -q` → `980 passed, 2 skipped in 117.09s (0:01:57)`
- `node --experimental-strip-types frontend/scripts/board.check.ts` → `board.check: ok`; `geo.check.ts` → `geo.check (merged tiles): ok`
- `cd frontend && npx tsc -b` → clean; `npx oxlint src/map src/Root.tsx src/api.ts` → no output; `npx vite build` → `✓ built`
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`
- Headless Playwright (scratchpad, fake owner, :8391/:5391, map `tum-sites`): Weihenstephan's lower-right corner showed `nwse-resize`; dragging it +120/+60 px grew the island right and down, the lower edge pulled to the main campus's (607 → 607); PUT with `area`; Garching's left edge dragged 300 px inward stopped at its building (843 → 931); gap rendered features: only a pin name (before the bridge fix: `buildings-3d-rest`; before the key fix: roads too); the fit button visible for the drawn area; reload kept both areas; `?map=tum-sites&building=…` and `?building=osm-way10053349` open with bridge state (own 76 / 80 blocks) and no console errors.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none new (rectangle-only areas recorded in organizations.md and the log)
- [x] docs touched: docs/product/organizations.md, docs/guides/commands.md

## Known gaps / not done
- Areas are rectangles only (no polygons).
- No merging / splitting of sites; no blue dot on the board.
- Shrinking an island leaves a gap to its neighbour (by the editor's choice); no automatic close-up.
- Keyboard cannot move or reshape islands.
- Browser checks are scratchpad Playwright scripts, not in the repo.

## Verification rounds
- Round 1: PASS (tree 638d11f06cc7b916290cc5e7ccd0d739be9ca508)

## Verification report (round 1)

VERDICT: PASS
TREE: 638d11f06cc7b916290cc5e7ccd0d739be9ca508

C1–C7 MET (C5, C6 by reading). test_maps 8 passed; full pytest 980 passed, 2 skipped; board.check ok; geo.check ok;
tsc clean; oxlint clean; links OK (25 files); no secrets; score.py unchanged; no hard-coding; working tree = index.
vite build and headless Playwright not re-run (scratchpad). No significant undeclared changes.
