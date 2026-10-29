---
id: organizations
summary: Organisations and their own maps — an org (TUM) owns buildings, lists them on the main map or keeps them to its own map, shares that map by link or membership, and shows its sites as islands pulled close together instead of the whole world. Phase 1 (ownership, roles, listings), phase 2 (maps, share links, ?map= scope, organisations sheet, Edit mode and imports for org editors) and phase 3's island board with dragging, naming and drawn (rectangular) areas and location on the board are built; merging / splitting sites, areas of any shape and phase 4 are the plan.
sources:
  - backend/api/access.py
  - backend/api/routes/orgs.py
  - backend/api/routes/accounts.py
  - backend/api/maps.py
  - backend/api/routes/maps.py
  - supabase/migrations/20261029120000_maps.sql
  - frontend/src/org/OrgScreen.tsx, frontend/src/Root.tsx, frontend/src/map/MapLanding.tsx
  - frontend/src/map/board.ts, frontend/src/map/boardTiles.ts, frontend/src/map/style.ts, frontend/scripts/board.check.ts
  - tests/test_maps.py (layout)
  - tests/test_maps.py
  - tests/test_org_editing.py
  - backend/api/deps.py
  - supabase/migrations/20261028120000_orgs.sql
  - tests/test_orgs.py
related: [visualization.md, living-building.md, ../architecture/overview.md, ../../memory-bank/decisions.md]
---

# Organisations and their maps

[Docs index](../README.md) · Decision: [D-029](../../memory-bank/decisions.md#d-029) (proposed) · Questions:
[Q-022](../../memory-bank/open-questions.md#q-022)–[Q-024](../../memory-bank/open-questions.md#q-024)

Today the landing map shows every building anyone saved, and access mode
([D-015](../../memory-bank/decisions.md#d-015)) has one admin over every building. An institution such as TUM wants
its own map: only its buildings, shared with its people or by a link, and some of them also on the main map.

## Concepts

| Term | What | Example |
|---|---|---|
| **Org** | Owns buildings; people in it have a role | TUM (`tum`) |
| **Role** | `viewer` opens the org's private buildings · `editor` also administers them (rules, members, objects, listing) · `owner` also manages the org's people | — |
| **Listing** (per building) | `listed` on the main map · `unlisted` anyone with the link or the org's map opens it, only the org finds it · `private` only the org and invited members | — |
| **Map** (phase 2) | An org's curated set of buildings with its own address and visibility (`private` / `link` / `public`); an org may have several | "TUM Campuses" |
| **Site** (phase 3) | One island on a map: buildings close together and the area round them (later: the area the org draws) | Stammgelände, Garching, Weihenstephan |
| **Admin** | `ADMIN_EMAIL`, as before: every building and org | — |

Buildings without an org belong to the platform (the admins): the kit dataset and today's saved `user/*` buildings.

## Rules (phase 1, built)

- Anyone signed in may start an org and is its first owner. An org always keeps an owner.
- Only the admin gives a building to an org or takes it back: an org named after a university must not be able to
  claim that university's buildings.
- Only an org the admin has **verified** may move a building to `listed`; any org may make its buildings `unlisted`
  or `private`. A building already listed stays listed when the admin hands it to an org.
- `hidden_buildings(viewer)` (not in `GET /buildings`) = unlisted and private buildings unless the viewer is in the
  owning org or an invited member of the building. The Guide's neighbours (`backend/agents/campus.py`) get the same
  filtered catalogue, so it never names or routes to a building the viewer cannot list. Before phase 1 the campus
  saw the whole catalogue, so a private building's name could leak through "what is nearby".
- `can_admin(viewer, building)`: the admin, or an editor / owner of the owning org. It guards the building's access
  rules and members (`/access/*`), moving objects (`/objects*`), the live controls (`/live/control`,
  `/live/register`), the Guide's `send_object`, and makes no space restricted for them.
- Still admin-only: Edit mode (`/drafts`), creating from plans (`/imports`), deleting a saved building. These move
  to org editors in phase 2, together with choosing the org a new building is saved into (Creator runs are paid:
  per-org quota first).
- Everything stays behind `ACCESS_MODE=on`; with it off the app is exactly as before.

### Storage

`supabase/migrations/20261028120000_orgs.sql`: `orgs` (slug, name, verified, created_by), `org_members`
(org, user_id, email, role), and on `access_buildings` the new `listing` and `org` columns. `public` is still
written: code from before the migration reads and writes only `public`, so when the two disagree `public` wins
(`building_row`). The migration has to be applied before this code is deployed against the shared database.

### API

| Call | Who | Does |
|---|---|---|
| `POST /orgs` `{slug, name}` | signed in | creates the org; caller is owner; slug 1–40 of `a-z0-9-` |
| `GET /orgs` | signed in | my orgs with my role (every org for the admin) |
| `GET /orgs/{slug}` | its people, admin | org, my role, its buildings with listing; members for owners |
| `PUT /orgs/{slug}` `{name?, verified?}` | owner (name), admin (verified) | |
| `POST /orgs/{slug}/invite` `{email, role}` | owner | sign-in link to pass on (no email sent), adds the role |
| `PUT /orgs/{slug}/members` `{user_id, email, role\|null}` | owner | change or remove a role |
| `PUT /orgs/{slug}/buildings` `{building, listing?, owned?}` | admin (ownership), editor (listing) | |
| `PUT /access/building` `{…, listing?}` | building admin | as before; `public` alone keeps an unlisted building unlisted |
| `GET /buildings` | anyone | each item now has `org` |
| `GET /me` | anyone | now also `orgs: {slug: role}` |

## Phase 2 — maps and sharing (built)

Built (2026-10-29):

- **Maps** (`backend/api/maps.py`, `backend/api/routes/maps.py`, `supabase/migrations/20261029120000_maps.sql`, not
  applied yet): `maps` (slug, org, name, visibility, token, buildings, layout). A map's address is global (`?map=<slug>`);
  `buildings` is an ordered list of ids, so one building may sit on several maps; `layout` waits for phase 3.
  Visibility: `private` (the org's people), `link` (anyone with `&k=<token>`), `public` (anyone). The token is stored
  as is (not hashed), so editors can copy the link again; it only opens the map, and `POST /maps/{slug}/link` makes a
  new one that shuts out the old link.
- A map lists only the buildings its viewer may open: unlisted ones for everyone who has the map, private ones only for
  the org's people. Editors put on a map the org's own buildings and anyone's listed ones; owners delete maps.
- **App:** `?map=<slug>[&k=]` turns the landing into the map (`Root.tsx` → `GET /maps/{slug}`): only its buildings,
  framed on them, its name and org in place of Steward's mark with "on Steward" back to the main map; a map the viewer
  may not open says so in the same place. The scope stays while buildings open and close.
- **Organisations sheet** (`src/org/OrgScreen.tsx`, account menu → Organisations, `?view=org[&org=]`): the viewer's
  organisations and a new one; per org its maps (open, copy link, who opens it, new link, which buildings, delete),
  its buildings' listing, and for owners its people (role, remove, invite link).
- **Building settings** open for the org's editors and owners (`administers` in `src/access/auth.ts`, from `GET /me`
  `orgs`), with the three listings; the Edit-mode pencil stays the admin's.
- The Guide's campus keeps the session's own building even when it is hidden for the viewer (an unlisted building
  opened by its link still has its neighbours).
- **The Guide's neighbours on a map** (2026-10-29): while on `?map=`, the app sends `X-Steward-Map` (and
  `X-Steward-Map-Key` for `&k=`) with every request (`api.ts` `headers`); an app-wide async dependency puts them in
  `deps.map_scope`, and `conversation_or_404` stops hiding the map's buildings from the campus for whoever may open
  that map (`shown_by_map`: the org's people, the admin, or the right key; private buildings still only for the org).
  So an outsider on a link-shared map gets its unlisted buildings as neighbours. Per request, not stored with the
  session: a session restored on another instance (Vercel) gets the same answer.

- **2c, Edit mode and imports for org editors** (2026-10-29): a draft is reachable by whoever administers its base
  (`deps.draft_or_404`; anyone else gets 404, and `/drafts`, `/imports` keep a first gate in `app.py` for the admin and
  orgs' editors / owners). A building from plans needs the admin, or an editor / owner of a **verified** org
  (`creator_org_or_403`: a Creator run is paid, and verifying is the admin's call); its private base `import/<id>`
  gets an access row with that org (`own_import`). A saved draft belongs to its base's org (`adopt`): an edit keeps
  the base's listing, a building from plans starts unlisted. Saved from an org map (`?map=`), it goes onto that map
  when the saver edits it. In the app the pencil and "New building from floor plans" show for those who may use
  them; an import started on a verified org's map sends that org. Deleting a saved building: whoever administers it.

Still to do:

- A per-org quota on Creator runs (now only verified orgs may run them).
- Main map: listed buildings carry their org's badge; tapping it opens the org's public map.
- An unlisted building opened by a bare `?building=` link (without its map) has no position on the landing.

## Phase 3 — the compact island board (first cut built)

The org's map does not show the world. Each site is an island cut to the area round its buildings, with its streets,
green, water and OSM blocks; the islands sit next to each other instead of 15 km apart.

Built (2026-10-29), all in the app (`frontend/src/map/board.ts`, `boardTiles.ts`; checked by
`node --experimental-strip-types frontend/scripts/board.check.ts`):

- **Sites:** the map's buildings with a position, grouped by single linkage at `NEARBY_M` = 600 m (the Guide's campus
  uses the same distance). An island is the rectangle round a site's outlines plus `MARGIN_M` = 150 m.
- **Layout:** islands edge to edge, in a row west to east on a wide screen and a column north to south on a phone
  (decided when the map's buildings arrive), each centred on the first, which stays where it really is. Nothing is
  stored: the board follows the map's buildings.
- **Honest compression:** an island is only moved, never turned or scaled. The move is a Web Mercator translation in
  whole steps of the z14 tiles' 4096 grid, so the base map can be cut and moved exactly. (Mercator's scale changes a
  little with a move north or south: about 0.3 % per 15 km at Munich's latitude.) A dashed seam marks each cut, and
  past its end the table says how far apart the two sites really are ("15 km apart"; the map's Noto glyphs have no
  arrows).
- **Tiles:** a `board://<key>/{z}/{x}/{y}` protocol (`maplibregl.addProtocol`) builds each board tile from the real
  OpenFreeMap tiles under the islands it shows: every feature clipped to the island and to its real tile's own square,
  moved, and written back as a vector tile (`@mapbox/vector-tile`, `pbf`, `@maplibre/vt-pbf`, already maplibre's
  dependencies, now listed directly). The style (`style.ts` `boardStyle`) is the main map's, on these tiles, with the
  table round the islands a shade off the ground. The OSM block heights, the blocks hidden under an open building and
  the x-ray blocks (`bridge.ts`, `neighbours.ts`) read the same `openmaptiles` source unchanged. The tiles are fetched
  live, so the board shows OSM as it is today (ODbL attribution as on the main map). Known limit: a polygon cut at a
  real tile's edge draws that edge faintly on the flat `footprint` layer (z13–14.6).
- **Buildings:** `Root.tsx` moves each building's position, origin and outline with its island, so pins, model
  blocks, framing and the open building's model and camera all agree. The building screen gets the real origin too
  (`realOrigin`) for the walk outside to the next building, which the Guide gives in real coordinates.
- **On the board:** "Create a building here" works only on an island and sends the real place under the tap; the
  camera is kept over the board.
- The decision against stored snapshots: cutting the tiles in the browser needs no publish step, no storage and no
  snapshot to refresh. Still rejected: real geography with a mask (keeps the 15 km gaps), one map instance per island
  (WebGL context limit, no continuous pan).

- **Arranging** (2026-10-29): the map's editors (`can_edit`) get "Arrange" under the map's title. An island is dragged
  with the mouse or a finger (the map does not pan meanwhile); its outline shows where it will land, pulled against
  another island's edge within 14 px so they meet without a gap, red where it would lie on another island (dropped
  there, it stays where it was). A tap without a move names the site (shown over its top left corner). Each change is
  saved at once: `PUT /maps/{slug}` `{"layout": {"sites": [{buildings, name, dx, dy}]}}` (moves in grid steps, null =
  placed by the app; names up to 60 characters, at most 200 sites) and put back with "Not saved: …" in the bar if the
  backend refuses. A stored site is found again by the buildings it shares most with a new site. Once any island is
  placed by hand the board is the stored one on every screen, and a new site goes to its right; "Line them up" drops
  the places and keeps the names. Seams are drawn wherever two islands meet. The board's tiles change in place
  (`setTiles`) so moving an island does not blink the map.
- **Drawn areas** (2026-10-29): while arranging, every island shows its outline and corners; taken by an edge or corner
  (within 10 px, 22 px with a finger; where two islands meet, the one under the pointer) its area follows the pointer
  instead of the island moving. The area is a rectangle, so islands still meet edge to edge and the tiles are cut
  exactly; it always holds the site's buildings (and 10 m round them: `core`), is at most 3 km a side (`MAX_AREA_M`;
  the backend allows 20 000 grid steps, ~8 km at Munich), is pulled to neighbouring edges like a move, and is refused
  (red) over another island. Stored as `area` (grid steps of the world) with the site; a site that has grown past its
  drawn area gets it grown back round its buildings. A tapped island whose area was drawn offers "Fit the area to its
  buildings" (the app's area again); "Line them up" keeps drawn areas. The board's key includes every island's area,
  so new tiles are fetched when one changes; `bridge.ts` rebuilds the put-back block pieces when their places change,
  not only their number (found when a shrunk area left blocks standing in the gap).

- **You are here** (2026-10-29): the board has its own location button (MapLibre's would put the dot where the user
  really is, off the board) and asks for location like the main map (the same card, the same remembered answer). The
  browser's position is watched; standing inside an island's real area, the blue dot is drawn moved with that island
  and the map flies to it (`whereOnBoard`); anywhere else there is no dot, and a note says "You are not on this map.
  Nearest site: Garching, 3.2 km away." (metres to the nearest island's edge; its name, else its first building's);
  after a tap on the button the map then flies to that island. A refused or failed position says so in the same note.

Still to do in phase 3:

- Merging or splitting sites by hand.
- Areas of any shape (now rectangles: a polygon needs general clipping in `boardTiles.ts`, and irregular islands
  cannot meet edge to edge).
- A building on an org map that has no position still has no island (it is listed under the map, as on the main map).

## Phase 4 — polish (planned)

Verification by email domain (`@tum.de` joins as viewer), an iframe embed for the org's site, Creator quota per org,
paging or bounding-box listing once there are many orgs.

## Open questions

- [Q-022](../../memory-bank/open-questions.md#q-022): who may start an org (anyone, as built, or approved first).
- [Q-023](../../memory-bank/open-questions.md#q-023): do islands show the surrounding streets and OSM blocks or only
  the org's buildings and drawn area (built: streets and blocks, the plan's default).
- [Q-024](../../memory-bank/open-questions.md#q-024): what the app calls a map ("workspace", "map", …) and who owns
  today's unowned `user/*` buildings (now: the platform).
