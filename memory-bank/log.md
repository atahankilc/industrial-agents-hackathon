---
id: log
summary: Append-only dated session log, newest on top. The hackathon weekend's log is archived.
related: [project-state.md, ../archive/hackathon/log-2026-10-24-to-25.md]
---

# Log

[Memory bank](README.md) · Hackathon weekend (2026-10-24 – 2026-10-25):
[archive/hackathon/log-2026-10-24-to-25.md](../archive/hackathon/log-2026-10-24-to-25.md)

## 2026-10-29 — Organisations: the Guide's neighbours on a map

- You-are-here shipped as `4ec7c94`. The migrations are still not applied: they wait for Atahan's explicit go
  (shared database).
- The app sends `X-Steward-Map` / `X-Steward-Map-Key` on `?map=` (`frontend/src/api.ts` `headers`); `backend/api/app.py`
  registers `deps.read_map_scope` as an app-wide async dependency (a ContextVar reaches the sync routes in the
  threadpool); `deps.shown_by_map(viewer)` = the map's buildings the viewer may open through it;
  `conversation_or_404` hides `hidden_buildings(viewer) - shown_by_map(viewer)` from the campus.
- `tests/test_maps.py::test_the_guide_gets_the_maps_unlisted_buildings_as_neighbours_on_the_map` (no header, right key,
  wrong key, unknown map, org member without key). Headless: requests on `?map=tum-sites` carry `x-steward-map`, the
  main map's do not.

## 2026-10-29 — Organisations phase 3: you are here on the board

- Drawn areas shipped as `c656a9a`.
- `board.ts` `whereOnBoard(board, real point)`: on an island → the point moved with it; else the nearest island and
  metres to its area's edge. MapLanding: a `BoardLocate` control (MapLibre's look) instead of `GeolocateControl` on a
  board; the main map's location card and remembered answer now apply on a board too (`locate` → `locateOnBoard`);
  `watchPosition`; dot layers `board-me(-halo)`; fly to the dot, or after a tap to the nearest island; `.ml-near` note
  (nearest site, or a refused / failed position), closable.
- Headless (Playwright geolocation, map `tum-sites`): standing at StudiTUM → the dot on the Garching island, map flown
  there (zoom 16), no note; in Pasing → no dot, "You are not on this map. Nearest site: Hauptgebäude, 7.5 km away.",
  the button then flies to that island; the phone shows the note under the title; a point 200 m south of StudiTUM is
  rightly "40 m away" (outside the island). No console errors.

## 2026-10-29 — Organisations phase 3: drawn areas

- Arranging and naming shipped as `a636f91`.
- Areas are rectangles (decided here, said to Atahan): polygons would need general clipping in `boardTiles.ts` and
  irregular islands cannot meet edge to edge.
- Backend: `Site.area` `{x0,y0,x1,y1}` in world grid steps (0..2^26, 0 < side ≤ 20 000). `board.ts`: `Island.core`
  (buildings + 10 m), `auto`, `drawn`; `reshapeAt` (pull, grid, never inside `core`, ≤ 3 km a side, refuse overlap),
  `changed({area} | {fit})`, `overlaps`; stored areas grown back round grown sites; the board key includes the areas.
  MapLanding: edges / corners taken within 10 px (22 px touch), the island under the pointer winning on a shared edge,
  resize cursors, outlines and corner handles while arranging, "Fit the area to its buildings".
- Found headless: (1) the key held only places, so a shrunk area kept its old tiles; (2) `bridge.ts` kept stale
  put-back block pieces (`rest`) in the gap because its key was ids + count: now also where the pieces lie. Both fixed;
  `refreshTiles` turned out unnecessary once the key changes.
- Headless (fake owner): a corner drag grew Weihenstephan right and down, pulled to the main campus's lower edge, saved
  `area`; dragging Garching's left edge inward stopped at its building; the gap then showed only the table; a reload
  kept both; the fit button shows for a drawn area; opening a building on the board and on the main map still works
  (bridge state ok); no console errors.

## 2026-10-29 — Organisations phase 3: editors arrange and name the islands

- The first cut shipped as `cbd043b`.
- Backend: `PUT /maps/{slug}` takes `layout` (`Site`: buildings, name ≤ 60, dx / dy in grid steps within ±2^26, both or
  neither; ≤ 200 sites; empty sites dropped, buildings de-duplicated). `tests/test_maps.py::test_editors_arrange_and_name_the_islands`.
- `board.ts`: `boardOf(…, layout)` matches stored sites by shared buildings; any hand-placed island → the stored board
  on every screen, unplaced sites to its right; `seamsOf` (wherever islands meet), `dropAt` (pull to edges, refuse
  overlap), `changed`, `layoutOf`, `byHand`. MapLanding: "Arrange" under the title for editors, drag with mouse or
  touch (no pan), ghost outline (red = refused), tap to name, "Line them up", "Not saved: …"; tiles swapped with
  `setTiles` once a board is shown (the first board still gets a style of its own: a `setTiles` while the empty
  board's style was loading left the islands blank after a reload, found headless and fixed).
- Headless (fake owner, :8391/:5391): dragging Weihenstephan under the main campus snapped to its left and lower
  edges, saved `dx/dy`, seam "30 km apart"; naming Garching showed its name; after a reload the arrangement and the
  tiles came back; on a phone a touch drag moved the island without panning the map; no console errors.

## 2026-10-29 — Organisations phase 3, first cut: the island board

- 2c shipped as `090b423`.
- `frontend/src/map/board.ts` (pure): sites by single linkage at 600 m, an island = rectangle round the outlines + 150 m,
  laid edge to edge in a row (wide) or column (phone), moved by whole z14 grid steps in Web Mercator; seams with the real
  distance ("15 km apart": the Noto glyphs have no arrows, the first try drew "↔" as dots). `boardTiles.ts`: a
  `board://` MapLibre protocol cuts each board tile from the real OpenFreeMap tiles (clip to island and to the real
  tile's square, move, re-encode with `@maplibre/vt-pbf`). `style.ts` `boardStyle`: the same layers on the board tiles,
  islands on a table colour. `Root.tsx` moves the map's buildings onto the board; `BuildingScreen` gets `realOrigin` for
  the outdoor walk. No geolocation on a board; "Create a building here" only on an island, at the real place.
- Checks: `node --experimental-strip-types frontend/scripts/board.check.ts` ok, `geo.check.ts` ok, `npx tsc -b` clean,
  `npx oxlint` on the changed files: no warnings. Headless (in-memory backend :8391, map `tum-sites`: Hauptgebäude +
  Mensa, StudiTUM Garching, Weihenstephan): three islands in a row (wide) and a column (phone), streets and blocks
  inside, "15 km apart" under each seam; StudiTUM opened from the board sits on its island with Lichtenbergstraße
  round it; the theme switch rebuilds the board style (light); the main map still uses the OpenFreeMap source; no
  console errors.

## 2026-10-29 — Organisations phase 2c: Edit mode and imports for org editors

- 2a/2b shipped as `b126fd7` (1 verifier round).
- Backend: `deps.draft_or_404(draft_id, authorization)` lets only whoever administers the draft's base reach it (404
  otherwise); `creator_org_or_403` (admin, or editor / owner of a **verified** org, because a Creator run is paid);
  `own_import` gives the `import/<id>` base an access row with that org; `adopt` hands a saved building to the base's
  org (an edit keeps the listing, a building from plans starts unlisted); `SaveDraft.map` puts it on the org map it was
  made from. `/drafts`, `/imports` gate in `app.py` lets org editors / owners through; deleting a saved building needs
  its admin. `tests/test_org_editing.py` (6).
- Frontend: the pencil and Edit mode follow `administers(access, org)`; "New building from floor plans" shows on a
  verified org's map for its editors, and the import sends that org; saves send `?map=`.
- Headless (fake signed-in owner, in-memory backend :8391): on `?map=tum-campus` the create button is offered; on
  Hauptgebäude both the settings and the pencil show; the pencil opens Edit mode (`POST /api/drafts` 200, plan and
  references 200); no console errors.
- `uv run pytest -q` → 978 passed, 2 skipped.

## 2026-10-29 — Organisations phase 2a/2b: maps, share links, the Organisations sheet

- Phase 1 shipped as `b614c91` (verifier round 1 found that any signed-in user could change the listing of a platform
  building through their own org with `owned: false`; fixed and tested before the commit).
- Backend: `backend/api/maps.py` (OrgMap, memory / Postgres stores), `backend/api/routes/maps.py`, migration
  `20261029120000_maps.sql` (not applied); `listing_item` shared by `/buildings` and `/maps/{slug}`; the Guide's
  campus keeps the session's own building (an unlisted one opened by link kept no neighbours). The share key is stored
  as is, not hashed as first planned, so editors can copy the link again (it only opens a map; renewing shuts out the
  old link). `tests/test_maps.py` (6).
- Frontend: `?map=` scope in `Root.tsx` / `MapLanding.tsx` (map name + org, "on Steward"; a map the viewer may not
  open says so there), `src/org/OrgScreen.tsx` + `org.css` (account menu → Organisations), `administers()` in
  `src/access/auth.ts` (org editors get the Building settings; the pencil stays the admin's), three listings in the
  Building settings, listing-aware saves in `useAccessRules.ts`.
- Checked headless (Playwright, Chrome extension not connected) against an in-memory test backend on :8391 with a fake
  signed-in owner (scratchpad script, nothing on Supabase): map scope wide and phone, a private map's note, the sheet
  signed out and in, making a map, link visibility, a building on and off it, a listing change, opening the map by its
  link; no console errors. Fixed on the way: the sheet lacked the HUD tokens outside `.access-layer`; the map title ran
  under the account button on phones; "1 buildings".
- `uv run pytest -q` → 972 passed, 2 skipped; `npx tsc -b` clean; `check_links.py` OK.

## 2026-10-28 — Organisations: plan and phase 1 ([D-029](decisions.md#d-029))

- Atahan: institutions (TUM) want their own map with only their buildings, shared by link or workspace, sites shown
  as pieces pulled together, some buildings also on the main map. Plan in
  [organizations.md](../docs/product/organizations.md) (4 phases); Atahan said "start" without answering the open
  points, so defaults were taken and recorded as [Q-022](open-questions.md#q-022)–[Q-024](open-questions.md#q-024).
- Phase 1 (backend): `backend/api/access.py` (listing, `Org`, `OrgMember`, `can_admin`, stores),
  `backend/api/routes/orgs.py`, per-building admin in `/access/*`, `/objects*`, `/live/control|register`, `deps`
  (`building_admin_or_403`, campus catalogue filtered by `hidden_buildings`), `org` in `GET /buildings`, `orgs` in
  `GET /me`, migration `20261028120000_orgs.sql` (not applied).
- Found while planning: `with_campus` gave the Guide the whole catalogue, so neighbours / nearby search could name a
  private building to a viewer who may not list it; now filtered (`test_the_guide_does_not_name_buildings_…`).
- Verifier round 1: an org's people could change a building their org does not own (e.g. hide a platform building
  with `owned: false`); `PUT /orgs/{slug}/buildings` now answers 403 to non-admins unless the org owns the building
  (`test_an_org_cannot_change_buildings_it_does_not_own`). The access-mode API table in
  [commands.md](../docs/guides/commands.md) now says who the building admin is, listing / `org`, and the `/orgs` endpoints.
- `uv run pytest -q` → 966 passed, 2 skipped; `npx tsc -b` clean; `check_links.py` OK.

## 2026-10-28 — D-028 deployed and the building-id migration applied

- Shipped `306fd5a` (data merge), `366dd05` (Atahan's README features), `e57a9b2` (CLAUDE.md data line, Atahan
  approved); PR #11 `dev` → `main` merged (`30ddf99`). A push to `dev` only made a preview: production follows `main`.
- Migration `20261027120000_building_ids.sql`: dry run in a rolled-back transaction first, then applied once
  production served the new ids: conversations 826 (+13 states), builder_drafts 54, saved_buildings 4 (+4 jsonb),
  access_buildings 2, access_members 1, fleet_objects 0; afterwards 0 old-style ids in any of these columns.
- Right after the deploy every `/api/*` call answered 500 `FUNCTION_INVOCATION_FAILED` for ~2–3 min, then it recovered
  by itself. The same code against the same (migrated) DB, and a copy of the exact function bundle, answered 200
  locally; cause unknown (no Vercel logs from here). Now: `/api/health` 200 (`tts`/`stt` true), `/api/buildings` 286
  with new ids, sessions on `proc-campus-train-000` and `user/arcisstra-e-21-edited` 200, old id 422.
- Size: the function's repo files 49.7 → 49.6 MB (renders were already excluded); the repo 217 → 71.5 MB.

## 2026-10-27 — Dataset in one `data/buildings/` folder, floor renders removed ([D-028](decisions.md#d-028))

- Atahan: merge train/dev/test and drop the PNG/SVG renders (only `building.json` builds a building). Before: the API
  function on Vercel bundles `data/` with the code (no separate storage; `excludeFiles` already dropped png/svg/jsonl/
  equipment.csv); Supabase holds only saved buildings, drafts, conversations, access and fleet rows.
- `git mv` of all 280 building folders into `data/buildings/`; 1,594 PNG + 797 SVG deleted (208 MB → 65 MB);
  `manifest.csv` `path` → `buildings/<id>`; test `questions.csv` / `submission_template.csv` →
  `archive/hackathon/test-set/`; `scripts/eval_import.py` deleted (Atahan's choice).
- Ids: kit buildings are now their directory name (Atahan chose a DB migration over aliases):
  `backend/api/sessions.py` catalogue, `DEMO_BUILDING`, default building; tests, scripts, docstrings and
  `tests/*_scenarios` JSON follow. Labelled-question tests filter on `answer` instead of the folder.
  `supabase/migrations/20261027120000_building_ids.sql` written (applied 2026-10-28, entry above). Local `data/user/.drafts` (8 files,
  gitignored) rewritten the same way.
- `uv run pytest -q` 955 passed / 2 skipped; `validate_solvers.py --kinds shared_walls_count` 143/143. Found, not
  fixed: `scripts/check_routes.py` already crashed at HEAD (MapError, no route in dev `osm-way360544293`, Lufthansa
  Lounge → Deutsches Museum); it now reads the dev buildings from the manifest.

## 2026-10-27 — Removed the `?view=list` page and the unused Geist-outline brand files

- Atahan: the list view is no longer used. Deleted `frontend/src/search/` (BuildingSearch.tsx, search.css); `Root.tsx`
  has landings `map | import` only, an old `?view=list` link lands on the map (headless: map canvas + search field,
  no `.bs`), an import's done / exit go to the map. Comments in AccessLayer.tsx, map.css, import.css updated.
- Deleted `scripts/brand/steward-outline.json` and `outline.py` (the earlier Geist wordmark; `marks.cjs` no longer
  reads them). Generator re-run into a scratch dir: all 10 SVGs byte-identical to `frontend/public/brand/`.
- `tsc -b` 0, `oxlint src` 0 (existing warnings only, none in touched files), links OK.

## 2026-10-27 — Wordmark: finer walls (Atahan's pick)

- Of the five refinements Atahan chose 3, "finer walls": walls 2 → 1.5, clay face 1.5 → 1.3. The letters now live in
  `frontend/src/brand/wordmark.json`, read by both `Wordmark.tsx` (the landing) and `scripts/brand/marks.cjs`, which
  now writes `frontend/public/brand/wordmark*.svg` from it (mark + name laid out as on the landing) instead of the
  outlined Geist name. Run into a scratch dir first: the other 8 brand SVGs came out byte-identical; only the two
  wordmark files changed. `steward-outline.json` / `outline.py` are no longer used by the generator (kept).
- Not taken: arrival animation, rooms, live heading, floor stack. `tsc -b`, `oxlint` clean; renders checked.
- The picked building's solid "Open" button (in the list row and under the closed search) looked bolted on: the row
  itself now opens it, with a quiet "Open ›" inside on the right (`.ml-go`). Clicking the closed card's row went to
  `?building=test%2Fosm-way50300147` (headless check).

## 2026-10-27 — Landing round 3: search as a pill, the card only once it opens

- Atahan approved wordmark A ("clay plan") and the logo. The search field no longer starts on a card: closed, it is a
  glass pill on the map (and the picked building a pill under it); a click brings the card in round it (background,
  border and blur fade in) while the height opens. The panel keeps its place and size, see-through and click-through
  when closed, so the field never moves. Opening no longer animates `height` (it laid the 286-row list out again every
  frame; the design hook flagged it): the panel is always full height, cut to its top by a `clip-path` on wide
  screens and slid down by a `transform` on narrow ones. Per frame on click (headless): wide, the clip interpolates
  over ~9 frames; phone, translateY 686 → 583 → 481 → 151 → 33 → 0 px.
- Five wordmark refinements shown to Atahan on a local page (port 5398, scratchpad, not in the repo): arrival
  (route to the d's door, once), rooms, finer walls, live heading cone, floor stack. Recommended: finer walls +
  arrival. He picked finer walls (entry above).

## 2026-10-27 — Landing round 2: logo apart from the search, new wordmark, opening animation

- Atahan: the icon was too small on desktop, the wordmark had no character, no animation when the list opened, and
  the logo could stand apart from the search. Now: mark (60 px desktop, 42 px phone) + a new wordmark
  (`frontend/src/brand/Wordmark.tsx`, option A of three shown: "clay plan") alone at the top left; the search card
  under it. The opening animation was missing because of a `prefers-reduced-motion` block the first round added
  (the app runs full motion always, `src/motion.ts`); removed. Rows and chips now rise in, staggered 22 ms.
- Height per frame on click (headless, 1440×900): 70 → 199 → 315 → 414 → 689 → 732 → 784. `tsc -b`, `oxlint` clean.
- Wordmark options B (flat plan) and C (Geist stacked like floors) are mockups only; awaiting Atahan's pick.

## 2026-10-27 — Landing: Steward card with a search field, the list opens on click

- `frontend/src/map/MapLanding.tsx` + `map.css`: the always-open 400 px list panel is now one card with the
  Steward wordmark (dark / light by theme) and the search field. Click in the field (or `/`) → the card grows to full
  height (height animated from the measured top, `--ml-top`) with the kind chips, the grouped list and "New building
  from floor plans"; Esc (clears the query first), ×, a map tap or picking a building closes it. A building picked from
  the list stays in the closed card with **Open**. Phone: bottom sheet growing upward, clear of Account; the map
  controls follow the sheet's height and hide while it is open.
- Checked in headless Chrome over CDP (1440×900 and 390×844, screenshots): closed, open, typed "arc" (3 on the map,
  4 with no location), picked (map flies in, row with Open). Real mouse/key events: click field → open (h 868),
  Esc → closed (h 120), `/` → open, map click → closed. `tsc -b` and `oxlint` clean.

## 2026-10-27 — Local folder moved to `~/Documents/steward`

- Repo folder `~/Documents/industrial-agents-hackathon` → `~/Documents/steward`; worktree `collab-edits` →
  `~/Documents/steward-collab-edits` (`git worktree list` shows both paths). Claude's project memory copied over.
- The moved `.venv` broke `npm run dev`: its scripts' shebangs still pointed at the old folder, so `uv run uvicorn`
  ran Anaconda's Python 3.9 uvicorn and the backend died with `No module named 'anthropic'`. Fixed by recreating it
  (`rm -rf .venv && uv sync`); `pnpm run dev` then served backend `/docs` 200 on 8390 and the app 200 on 5390.
- WebStorm (local, `.idea/` is git-ignored): module file renamed to `steward.iml`, `.idea/.name` = `steward`.
- A `[vite] http proxy error … ECONNREFUSED 127.0.0.1:8390` right after start is the frontend asking before the
  backend listens (backend start took ~18 s on the fresh `.venv`); it stops once uvicorn is up.

## 2026-10-27 — Steward outside the repo: GitHub, Vercel, Supabase

- GitHub repo renamed `atahankilc/industrial-agents-hackathon` → `atahankilc/steward` (`gh repo rename`); `origin`
  points at the new URL; `dev` pushed (`9251dd8..b33c47c`); repo homepage → https://steward-io.vercel.app.
- Vercel project renamed by Atahan; `steward.vercel.app` and `steward-app.vercel.app` were taken, the app is at
  **https://steward-io.vercel.app** (`/` 200 with title "Steward", `/api/health` 200). The old
  `industrial-agents-hackathon.vercel.app` first answered 404 `DEPLOYMENT_NOT_FOUND`; later
  it answers a 308 to https://steward-io.vercel.app/ (`/api/health` → `/api/health` on steward-io).
- Voice was off on the deployment (`ELEVENLABS_API_KEY` missing in Vercel, so `/api/health` said `tts`/`stt`
  false and the app fell back to the browser's voice). Atahan added the key and redeployed: `tts`/`stt` true,
  `POST /api/tts` returns a 20 KB MP3, `POST /api/stt/token` 200.
- Supabase: Atahan renamed the project and set Site URL / Redirect URLs to steward-io (his report). Local folder: still to move.

## 2026-10-27 — The app is called Steward

- [D-027](decisions.md#d-027): name chosen with Atahan over several rounds (job titles, architecture terms; Maze
  rejected). Mark = the clay cutaway (three floors, you in a doorway); a single bold floor at 32 px and below; icon
  ground `#060606`. Moving the app's own dark HUD to that black was tried and reverted at his request.
- Renamed in README, CLAUDE.md, PRODUCT.md, `pyproject.toml` / `uv.lock`, both `package.json` (+ lock), `index.html`
  title and home-screen title, the web manifest (now also 192/512 icons), the FastAPI title, backend docstrings and
  the two OSM User-Agent strings. History (archive, hackathon references, research notes) keeps the old name.
- `scripts/brand/marks.cjs` draws every icon; `outline.py` turned "Steward" in Geist 500 (kerned) into
  `steward-outline.json` so the wordmark needs no font.
- Not done yet: GitHub, local folder, Vercel, Supabase (see project-state Next 0).

## 2026-10-27 — One command to run the app; own local ports

- `npm run dev` at the repo root (`package.json` → `scripts/dev.sh`) starts the backend and the Vite app together;
  Ctrl-C, TERM or either side exiting stops both (only the script's own process trees). It refuses a busy port.
  Without `.env` the backend runs `GUIDE_LLM=offline`.
- Default ports moved off 8765 / 5181 (Vite's 5173 when started bare) to **8390** (backend) and **5390** (app), so
  this project no longer clashes with other local projects (north-star runs on 5288). `frontend/vite.config.ts`:
  `port: 5390`, `strictPort`, proxy default `127.0.0.1:8390`; `BACKEND_PORT` / `FRONTEND_PORT` override.
  README, `docs/guides/commands.md`, `backend/api/app.py` docstring and `scripts/sim_object.py` default updated;
  `vercel.json` leaves the root `package.json` out of the function bundle.
- Checked: `npm run dev` serves `/api/health` through the app on 5390; a second copy on 8391/5391 stops fully on TERM
  and when its backend is killed, and leaves the first copy running; a busy port exits 1 with a message;
  `uv run pytest tests/test_deploy.py -q` 8 passed.

## 2026-10-27 — Guide tools and living building split into packages

- [D-026](decisions.md#d-026): `backend/agents/tools.py` → `backend/agents/tools/` (session + 7 mixins + definitions +
  shared); `backend/api/live.py` → `backend/api/live/` (world, hub, reroute, endpoints). `__init__.py` re-exports
  keep every import working; code moved verbatim (checked with `inspect.getsource` against the old modules).
  References to the old paths in code comments, docs and the frontend now point at the packages.
- Checked: `uv run pytest -q` 955 passed / 2 skipped, `uvx ruff check --select F,E9` clean on both packages,
  `check_links.py` OK.

## 2026-10-27 — One solver implementation; API routers

- [D-025](decisions.md#d-025): `core/solvers_v1.py` removed; `compute`'s `solve()` runs `backend/core/solvers/`
  (`SolverResult.to_dict()`, shared with the `solve` tool). `tests/test_solvers.py` now checks the canonical solvers
  (655/655 on gold inputs and from text); the errand-walkability check moved from `tests/test_routes.py` to
  `tests/test_solvers_routing.py` (all 93 errands); `tests/test_compute.py` gained a `solve()` check.
- `backend/api/app.py` (1164 lines) split: `app.py` assembles (~120), `deps.py` shared stores + guards,
  `routes/{guide,voice,accounts,drafts,imports,openai_chat}.py`. Code moved verbatim except stores read as `deps.X`.
  Checked: identical OpenAPI (58 operations), `uv run pytest -q` 955 passed / 2 skipped, uvicorn boots and answers
  `/api/health`, `/sessions`, `/buildings`.

## 2026-10-27 — Repo restructure: frontend/ + backend/{api,agents,core}

- [D-024](decisions.md#d-024): `frontend/app/` → `frontend/`; `backend/` → `backend/api/`, `agent/` →
  `backend/agents/`, `core/` → `backend/core/` (one Python package `backend`); `benchmark/score.py` →
  `tests/kit_oracles/score.py` (unmodified). Imports, `vercel.json` (web root `frontend/`, entrypoint
  `backend.api.app:app`), `pyproject.toml` (`packages = ["backend"]`), `DATA_DIR` (`parents[2]`), CLAUDE.md, README,
  docs and memory-bank paths updated; archived-file paths and the worklog history left as they were.
- Checked: `uv run pytest -q` 955 passed / 2 skipped (same as before), `npm run build`, `check_links.py`.
  Not checked: a real Vercel deploy.

## 2026-10-26 — Location dot back after a reload inside a building

- `frontend/src/map/MapLanding.tsx`: the "show my location" step ran only on the map's first mount and skipped
  itself when a building was open, so a reload inside a building never showed the dot on the map. It now waits for
  the map to be shown (no open building) and runs once; a run undone before the browser answered (dev double mount)
  asks again. Checked with `npm run build`; not tried in a browser (extension not connected).

## 2026-10-26 — Living building noted as demo-grade

- Opened [Q-021](open-questions.md#q-021): `backend/api/live.py` keeps device positions in serverless-instance memory
  (no Supabase), so positions freeze without requests, differ between instances and vanish with the instance.
  Atahan: good enough for now; linked from [project-state.md](project-state.md) small gaps.

## 2026-10-26 — LLM parser, solver agent and decision cache archived

- Atahan: delete `llm_cache/` (done, it was untracked) and, on Claude's recommendation, archive what only the
  benchmark used. The app used just two small parts: the python sandbox of `agent/solver_agent.py` (now
  `backend/agents/compute.py`, the Guide's `compute` tool; its 5 tests in `tests/test_compute.py`) and `LlmUsage` /
  `building_vocabulary` of `agent/llm_parser.py` (now in `backend/agents/rewriter.py`). Archived to
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md): `agent/llm_parser.py`, `agent/solver_agent.py`, `agent/llm_cache.py`,
  `tests/test_llm_route_spec.py`, `tests/test_solver_agent.py`, `tests/fake_llm.py`, `tests/conftest.py`.
  `core/question_parser.py`, `core/basic_parser.py`, `core/formatter.py` (test oracles only) moved to
  `tests/kit_oracles/`. pytest 955 passed, 2 skipped (978 − 28 archived + 5 moved).

## 2026-10-26 — Benchmark code archived

- Atahan: move everything about the hackathon that the app does not use to the archive. Moved with `git mv` to
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md): `agent/answer.py`, `agent/benchmark_agent.py`, `agent/parsing.py`,
  `agent/run_benchmark.py`, `agent/run_benchmark_v1.py`, `agent/guide_v1/`, `benchmark/evaluate.py`,
  `scripts/eval_llm_parser.py`, `scripts/eval_sunday_probe.py`, `tests/sunday_probe/` and their 10 tests; the
  benchmark sections of commands.md went into that README. `docs/challenge/` and `docs/kit/starter-agent.md` moved to
  `archive/hackathon/docs/`. Kept (test oracles for app code): `tests/kit_oracles/score.py`, `core/formatter.py`,
  `core/basic_parser.py`. `tests/fake_llm.py` now holds the fake client `tests/test_llm_route_spec.py` needs;
  `pyproject.toml`: `testpaths = ["tests"]`, the `run_benchmark` script entry removed. pytest 978 passed, 2 skipped.
- Re-score by another session (scratchpad only, UNVERIFIED here): with the right answer format and the bay /
  forklift rules on, ~0.89 on the jury's 36 sample questions; our submitted answers scored 0.19–0.33.

## 2026-10-26 — Post-hackathon cleanup

- Git: `main` fast-forwarded into `dev` (same commit `25c79b5`); deleted the merged local branches
  `backup/dev-before-pull-1043` and `voice-improvements`; pruned the stale `.claude/worktrees/voice-improvements`
  worktree; saved the 4 stashes as branches `archive/stash-0` … `archive/stash-3` and cleared the stash list;
  `git gc` (131 MB → 102 MB). Not done (needs Atahan's permission): push `dev`, delete the merged remote branches
  `2-builder-edit`, `4-sunday-agent`, `7-buildings-from-plans`.
- Moved hackathon material to [archive/hackathon/](../archive/hackathon/README.md): `SUBMISSION/`, the organiser
  PDF, technical explanation, demo runbook, the superpowers specs and plans (from `docs/`), the weekend log and the last
  project state. Links rewritten; `check_links.py` OK.
- New short [project-state.md](project-state.md); CLAUDE.md, README.md and docs index rewritten for ongoing
  development; hackathon-only questions closed ([Q-001](open-questions.md#q-001),
  [Q-002](open-questions.md#q-002), [Q-014](open-questions.md#q-014), [Q-017](open-questions.md#q-017),
  [Q-018](open-questions.md#q-018), [Q-019](open-questions.md#q-019)).
- Removed the unused `frontend/src/ui/Chat.tsx`.
- Held: removing the benchmark-only code (another session was re-scoring with `agent/run_benchmark_v1.py`).
