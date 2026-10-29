# Organisations phase 2a/2b: maps with share links, ?map= scope, the Organisations sheet

- **Author:** Claude (Opus 5.5 session) · **Date:** 2026-10-29
- **Related:** D-029 (proposed), docs/product/organizations.md (Phase 2), Q-022–Q-024

## Summary
Organisations get maps: a named list of their buildings with its own address, opened by members, by a share link or
by anyone. The app opens such a map with `?map=` and shows only its buildings under the map's name. A new
Organisations sheet lets people start an org, manage its maps, its buildings' listing and its people. Org editors
also get the Building settings, which now offer three listings.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `OrgMap` (slug, org, name, visibility private/link/public, token, buildings, layout) with `opens_with(token)`; `MemoryMaps` and `PostgresMaps` (get, of_org, insert → False when taken, put, delete); `deps.maps` from env | `backend/api/maps.py`, `backend/api/deps.py` | read; `uv run pytest tests/test_maps.py -k opens_with` |
| C2 | Migration creates `maps` (FK to orgs on delete cascade, visibility check, index on org, RLS on); not applied | `supabase/migrations/20261029120000_maps.sql` | read |
| C3 | `/orgs/{org}/maps` POST (editors; slug validated; 409 when taken; link visibility gets a token) and GET (its people); `GET /maps/{slug}?k=` opens for the org's people, anyone when public, anyone with the right key when link, else 404; it lists only the buildings the viewer may open; `token` only for editors; PUT name/visibility, PUT buildings (the org's own or listed ones, else 403), POST link renews the key, DELETE (owners) | `backend/api/routes/maps.py`, registered in `backend/api/app.py` | `uv run pytest tests/test_maps.py` → 6 passed |
| C4 | `/buildings` items and map items share one shape (`listing_item`) | `backend/api/routes/guide.py` | read |
| C5 | The Guide's campus keeps the session's own building even if it is hidden for the viewer | `backend/api/deps.py` `with_campus` | `test_the_guide_keeps_neighbours_of_an_unlisted_building_opened_by_link` |
| C6 | API client: `Listing`, `OrgRole`, `Org`, `OrgDetail`, `OrgMember`, `OrgMapView`, `OrgMapSummary`, `MapVisibility`; org and map calls; `Me.orgs`; `AccessRules.listing/org` | `frontend/src/api.ts` | read; `npx tsc -b` |
| C7 | `?map=<slug>[&k=]` loads `GET /maps/{slug}` instead of `/buildings`; the landing shows the map name and org with "on Steward" back to the main map; a map the viewer may not open shows a note there; the map param stays while buildings open; `MapLanding` remounts per map | `frontend/src/Root.tsx`, `frontend/src/map/MapLanding.tsx`, `frontend/src/map/map.css` | read; headless check below |
| C8 | Organisations sheet at `?view=org[&org=]` (account menu → Organisations): list + new org; per org its maps (open, copy link, visibility, new link, buildings on/off, delete for owners), its buildings' listing (editors), its people (owners: role, remove, invite link); wrapped in `.access-layer` for the HUD tokens | `frontend/src/org/OrgScreen.tsx`, `frontend/src/org/org.css`, `frontend/src/access/AccessLayer.tsx`, `Root.tsx` | read; headless check below |
| C9 | `access.orgs` from `GET /me`; `administers(access, org)`; `refreshOrgs()`; the building screen shows the Building settings to org editors/owners (the pencil stays admin-only) and passes `admin` to the settings sheet | `frontend/src/access/auth.ts`, `frontend/src/building/BuildingScreen.tsx` | read |
| C10 | The Building settings' access tab offers listed / unlisted / private; saves send `listing` only when it matches `public` (the Access tool's switch still sends only `public`) | `frontend/src/access/BuildingSettings.tsx`, `frontend/src/access/useAccessRules.ts` | read |
| C11 | Docs and memory bank: organizations.md phase 2 section rewritten (built vs to do, token stored as is), commands.md map rows, docs/README entry, project-state, log | those files | `python3 scripts/check_links.py` |

## Checks I ran

- `uv run pytest -q` → `972 passed, 2 skipped in 113.87s`
- `uv run pytest -q tests/test_maps.py tests/test_orgs.py` → `17 passed`
- `cd frontend && npx tsc -b` → clean; `npx oxlint` → only warnings in files this change does not touch (PlanView.tsx and others)
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`
- Headless (Playwright, scratchpad; the Chrome extension was not connected) against an in-memory test backend on :8391
  (fake viewers, seeded org `tum` and maps; nothing written to Supabase) and Vite on :5391:
  - `?map=tum-campus` wide and phone: the title "TUM Stammgelände", "TU München · on Steward", "Search 2 buildings",
    framed on the two buildings
  - `?map=tum-private` anonymous: "This map is not open to you. Sign in, or ask for its new link." and "Back to the main map"
  - `?view=org` signed out: "Sign in to see your organisations."
  - as a fake signed-in owner: list → TU München → make a map → Link → Hauptgebäude on → a listing change → Open →
    URL `?map=tum-garching-x91485&k=…`
  - no console errors

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none new (D-029 still proposed; the token-not-hashed choice is in the doc and log)
- [x] docs touched: docs/product/organizations.md, docs/guides/commands.md, docs/README.md

## Known gaps / not done
- Neither migration (`20261028120000_orgs.sql`, `20261029120000_maps.sql`) is applied; deploying before applying them
  breaks access mode.
- 2c is not done: Edit mode, imports and deleting saved buildings stay admin-only.
- The Guide's neighbours on a link-shared map leave out the map's unlisted buildings for outsiders.
- No org badges on the main map; an unlisted building opened by a bare `?building=` link has no map position.
- Not checked against real Supabase sign-in (fake session only); `PRODUCT.md` has an unrelated unstaged change that
  is not part of this commit.
