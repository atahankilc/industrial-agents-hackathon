# Organisations: the Guide's neighbours on an org map

- **Author:** Claude (Opus 5.5 session) · **Date:** 2026-10-29
- **Related:** D-029, docs/product/organizations.md § Phase 2 (open item "The Guide's neighbours on a map")

## Summary
On `?map=` the app tells the backend which org map it is on; for whoever may open that map, its buildings stop being
hidden from the Guide's neighbours, so an outsider on a link-shared map gets the map's unlisted buildings nearby.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `deps.map_scope` ContextVar, set per request by the async `read_map_scope` from `X-Steward-Map` / `X-Steward-Map-Key`; registered app-wide in `app.py` (`FastAPI(dependencies=[Depends(deps.read_map_scope)])`) | `backend/api/deps.py`, `backend/api/app.py` | read |
| C2 | `shown_by_map(viewer)`: empty without a map, with access mode off, for an unknown map, or when the viewer may not open it (not admin, no org role, key does not open it); else the map's buildings `access.visible` for the viewer (private ones only for the org) | `deps.py` | `uv run pytest -q tests/test_maps.py` → 9 passed |
| C3 | `conversation_or_404` hides `hidden_buildings(viewer) - shown_by_map(viewer)` from the campus | `deps.py` | test `test_the_guide_gets_the_maps_unlisted_buildings_as_neighbours_on_the_map` (no header / right key / wrong key / unknown map / org member without key) |
| C4 | The app adds the map headers to every request through `headers()` while the URL has `?map=` (and `&k=`) | `frontend/src/api.ts` `mapHeaders` | read; headless: requests on `?map=tum-sites` carry `x-steward-map`, on the main map they do not |
| C5 | Docs: organizations.md (paragraph, open item removed), project-state, log | docs, memory-bank | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q tests/test_maps.py` → `9 passed`
- `uv run pytest -q` → `981 passed, 2 skipped in 265.46s (0:04:25)`
- `cd frontend && npx tsc -b` → clean; `npx oxlint src/api.ts` → no output
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`
- Headless (scratchpad): on `?map=tum-sites&building=osm-way476929995`: `POST /api/sessions`, `GET /api/maps/tum-sites`, `GET /api/sessions/…/plan` with `map=tum-sites`; on `?building=osm-way10053349`: `map=-`. No page errors.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none new
- [x] docs touched: docs/product/organizations.md

## Known gaps / not done
- `GET /config` is sent without the headers (it uses its own fetch; it needs none).
- The map key travels as a header to our own backend (it is in the page URL already).
- The two Supabase migrations are still not applied (waiting for Atahan's go).

## Verification rounds
- Round 1: PASS (tree ef4db4d6f9446876014d0c0fd620d8c6db23c98d)

## Verification report (round 1)

VERDICT: PASS
TREE: ef4db4d6f9446876014d0c0fd620d8c6db23c98d

C1–C5 MET (C4 by reading). test_maps 9 passed; pytest 981 passed, 2 skipped; links OK; no secrets; score.py unchanged;
no hard-coding. Cosmetic note: in frontend/src/api.ts the old "JSON headers plus the bearer token" JSDoc now sits above
mapHeaders instead of headers() (to move back in a later touch).
