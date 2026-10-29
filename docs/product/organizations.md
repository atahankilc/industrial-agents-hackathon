---
id: organizations
summary: Organisations and their own maps — an org (TUM) owns buildings, lists them on the main map or keeps them to its own map, shares that map by link or membership, and shows its sites as islands pulled close together instead of the whole world. Phase 1 (ownership, roles, listings) is built; phases 2–4 are the plan.
sources:
  - backend/api/access.py
  - backend/api/routes/orgs.py
  - backend/api/routes/accounts.py
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
| **Site** (phase 3) | One island on a map: buildings close together and the area the org draws around them | Stammgelände, Garching, Weihenstephan |
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

## Phase 2 — maps and sharing (planned)

- `maps` (org, slug, name, visibility, share-token hash, layout) and `map_buildings` (map, building, site): one
  building may sit on several maps (a joint TUM–LMU map).
- `GET /maps/{slug}` returns the map, its buildings (including unlisted ones) and its layout; `?map=tum` opens it,
  `?map=tum&k=<token>` a link-shared one (only the token's hash is stored; revoking makes a new one).
- `MapLanding` gets a scope (`world` | `map`): the search pill and the Guide's neighbours search only the map's
  buildings, across all its sites (the Guide states the real distance to another site and draws no route between
  sites). The org's name and logo replace the wordmark, with a small "on Steward".
- Org settings screen: people and roles, buildings and their listing, maps, the share link. Building settings
  (`src/access/`) open for org editors, not only the admin.
- Edit mode and imports for org editors, saving into their org.
- Main map: listed buildings carry their org's badge; tapping it opens the org's public map.
- An unlisted building opened by `?building=` without its map has no position on the landing (the list omits it);
  `GET /maps/{slug}` fixes that for the map, a single-building lookup for a bare link.

## Phase 3 — the compact island board (planned)

The org's map does not show the world. Each site is an island cut to the area drawn for it (default: the buildings'
hull plus a margin) with its streets, green, water and OSM blocks; the islands sit next to each other instead of
15 km apart, and the org may drag them closer.

- **Honest compression:** inside an island everything is at true scale and true north. Between islands a seam marks
  the cut and says the real distance ("↔ 15 km"), like an axis break on a chart. Islands are only moved, never
  turned or scaled.
- **How:** one MapLibre map on "board" coordinates. When a map is published, each site's OSM content inside its
  area is taken once from the vector tiles (OpenMapTiles schema, ODbL attribution kept, snapshot date stored),
  shifted to the island's place on the board and stored as GeoJSON; the board style is generated from `style.ts`'s
  palette, so it looks like the main map. The model, the camera bridge (`bridge.ts`) and the x-ray blocks
  (`neighbours.ts`) work as now with the shifted origin.
  Rejected: real geography with a mask (keeps the 15 km gaps), one map instance per island (WebGL context limit,
  no continuous pan), rewriting tile URLs (only shifts by whole z14 tiles, ~1.6 km).
- **Layout:** islands packed by size, in a column on a phone and a row on a wide screen; editors may rearrange.
  Sites come from clustering the buildings by distance (the campus already uses `NEARBY_M` = 600 m), then are named,
  merged or split by the org.
- **Location:** the blue dot appears shifted onto the board when the user stands inside an island; otherwise "nearest
  site: Garching, 3 km".

## Phase 4 — polish (planned)

Verification by email domain (`@tum.de` joins as viewer), an iframe embed for the org's site, Creator quota per org,
paging or bounding-box listing once there are many orgs.

## Open questions

- [Q-022](../../memory-bank/open-questions.md#q-022): who may start an org (anyone, as built, or approved first).
- [Q-023](../../memory-bank/open-questions.md#q-023): do islands show the surrounding streets and OSM blocks or only
  the org's buildings and drawn area.
- [Q-024](../../memory-bank/open-questions.md#q-024): what the app calls a map ("workspace", "map", …) and who owns
  today's unowned `user/*` buildings (now: the platform).
