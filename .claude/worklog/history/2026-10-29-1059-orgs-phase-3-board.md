# Organisations phase 3, first cut: an org map is an island board

- **Author:** Claude (Opus 5.5 session) · **Date:** 2026-10-29
- **Related:** D-029 (update), Q-023, docs/product/organizations.md § Phase 3

## Summary
An organisation's map (`?map=`) no longer shows the world: its buildings are grouped into sites, each site is an
island (the rectangle round its buildings + 150 m) cut from the real map, and the islands sit edge to edge with a
seam that says how far apart they really are. The base map's tiles are cut and moved in the browser through a
`board://` MapLibre protocol; the buildings, pins and the open model move with their island.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Sites: single linkage at `NEARBY_M` = 600 m on building centres; island = bbox of outlines + `MARGIN_M` = 150 m, snapped outward to the z14 grid (`STEP` = 2^-26 world units) | `frontend/src/map/board.ts` `islandsOf` | read; `node --experimental-strip-types frontend/scripts/board.check.ts` → `board.check: ok` |
| C2 | Layout: row (west→east) or column (north→south), edge to edge, centred on the first island which is not moved; every move a whole multiple of `STEP`; seams between neighbours labelled `"<distance> apart"` with the real distance between island centres, label point past the seam end (`anchor` top / right) | `board.ts` `arrange`, `distanceLabel` | board.check.ts asserts these |
| C3 | `onBoard` moves a building's lat/lon, origin and outline with its island (first island untouched); `toReal` inverts `toBoard`; `islandAt` finds the island under a board point | `board.ts` | board.check.ts |
| C4 | Board tiles: `registerBoard` adds a `board` protocol once; each board tile collects, for every island it overlaps, the real tiles at the same zoom under it, clips every feature to the island and to the real tile's own square (points filtered, lines Liang–Barsky, polygon rings Sutherland–Hodgman), moves it by the island offset in grid units, keeps type / id / properties, and encodes with `fromVectorTileJs`; real tiles cached (256, LRU), the TileJSON fetched once | `frontend/src/map/boardTiles.ts` | read; headless check below |
| C5 | `boardStyle(dark, tiles, shapes)`: the main style with `openmaptiles` replaced by the board tiles (maxzoom 14, same attribution), background = table colour, island ground fill right above it, island edge, dashed seam line, seam labels; `mapStyle` unchanged except the attribution string moved into a constant | `frontend/src/map/style.ts` | read; main map's source still `https://tiles.openfreemap.org/planet` (headless) |
| C6 | `MapLanding`: new props `scoped`, `board`; scoped maps use `boardStyle` (an empty board until buildings arrive), swap style when the theme or `board.key` changes, keep the camera inside `boardBounds(board, 1)`, frame the board; no GeolocateControl and no location prompt when scoped; "Create a building here" only on an island and sent at the real place (`realPlace`) | `frontend/src/map/MapLanding.tsx` | read |
| C7 | `Root` builds the board for `?map=` (row ≥ 900 px wide, column below), passes moved buildings to the map and for origins; `BuildingScreen` gets `realOrigin` (memoised) and uses it for `outdoorWalk` | `frontend/src/Root.tsx`, `frontend/src/building/BuildingScreen.tsx` | read |
| C8 | `@mapbox/vector-tile`, `pbf`, `@maplibre/vt-pbf` added as direct dependencies at the versions maplibre already installs (no new packages) | `frontend/package.json`, `package-lock.json` | `git diff` shows only these three entries |
| C9 | Docs: organizations.md § Phase 3 rewritten as built + still to do; front matter sources; D-029 update; Q-023 notes the default built; commands.md lists the two `.check.ts` scripts; project-state and log updated | docs / memory-bank | read; `python3 scripts/check_links.py` |

## Checks I ran
- `node --experimental-strip-types frontend/scripts/board.check.ts` → `board.check: ok`
- `node --experimental-strip-types frontend/scripts/geo.check.ts` → `geo.check (merged tiles): ok`
- `cd frontend && npx tsc -b` → no output (clean)
- `npx oxlint src/Root.tsx src/map/MapLanding.tsx src/map/board.ts src/map/boardTiles.ts src/map/style.ts src/building/BuildingScreen.tsx` → no warnings
- `cd frontend && npx vite build` → `✓ built` (the >500 kB chunk warning as before)
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`
- `uv run pytest -q` → `978 passed, 2 skipped in 135.60s` (no backend change in this commit)
- Headless Playwright (in-memory backend :8391 with a public map `tum-sites`: Hauptgebäude, Mensa, StudiTUM, TUM 4107 Weihenstephan; Vite :5391): wide → three islands in a row with streets and 3D blocks inside, "15 km apart" under both seams; phone → a column; zoomed into Garching → Lichtenbergstraße and blocks on the island; `?building=osm-way476929995` → the model sits on its island; theme switch to light → style rebuilt on `board://…` tiles; main map `/` → `openmaptiles` source still the OpenFreeMap URL; no console errors.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: D-029 update, Q-023 status note
- [x] docs touched: docs/product/organizations.md, docs/guides/commands.md

## Known gaps / not done
- Editors cannot yet drag, name, merge or split islands (`layout` column unused); no drawn areas.
- No blue dot on a board (location is off there).
- A polygon cut at a real tile edge shows that edge faintly on the flat `footprint` layer (z13–14.6).
- Board layout is decided when the buildings arrive; resizing between phone and wide does not re-arrange.
- Mercator scale drifts ~0.3 % per 15 km of north–south move (documented).
- No automated browser test in the repo for the board (headless check was from the scratchpad).

## Verification rounds
- Round 1: PASS (tree 308ec0d3d92b031eedceb46b77edfd9c0b4f0832)

## Verification report (round 1)

VERDICT: PASS
TREE: 308ec0d3d92b031eedceb46b77edfd9c0b4f0832

C1–C9 MET. pytest 978 passed, 2 skipped; links OK (25 files); no secrets; score.py unchanged; no hard-coding.
Re-ran board.check (ok), geo.check (ok), tsc -b (clean), oxlint on the six files (clean), vite build (built).
Headless Playwright not reproducible (scratchpad scripts), declared in Known gaps.
Undeclared: fly-back also uses boardBounds on a board; a few exhaustive-deps disables; TABLE colours (part of C5). Trivial.
