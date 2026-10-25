# City view x-ray, real-width roads and walkways; multiple admin emails

- **Author:** Claude Code session (Atahan) · **Date:** 2026-10-25
- **Related:** docs/product/visualization.md (city view refinements, roads), docs/superpowers/specs/2026-10-25-access-profiles-design.md

## Summary
Map/city view: the open building's OSM blocks become a wireframe in the model's scene, coplanar OSM blocks under the
blue model blocks are removed (z-fighting), a MapLibre custom layer x-rays the blocks within 500 m in front of the
building, roads/walkways are drawn at estimated real widths, a ground line + basement veil, and Back flies the map
to the camera it had on opening. Access mode: ADMIN_EMAIL accepts several comma-separated emails.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `ADMIN_EMAIL` parsed as comma-separated, trimmed, lower-cased set; admin check uses it | `backend/access.py` `admin_emails`, `SupabaseAuth` | read; `uv run pytest tests/test_access.py -q` |
| C2 | New test for comma-separated admin emails (incl. empty) | `tests/test_access.py::test_admin_emails_comma_separated` | run it |
| C3 | `.env.example`, `docs/guides/commands.md`, access-profiles spec describe ADMIN_EMAIL as comma-separated | those files | read diff |
| C4 | New x-ray custom layer for blocks near the open building (dithered cut-away, footprints, MapLibre lighting) | `frontend/app/src/map/neighbours.ts` (new), used by `bridge.ts` | read |
| C5 | `bridge.ts`: per-polygon matching of merged tile features, `rest` source for un-hidden polygons, `onShell` wireframe feed, `hideBlocks(…, height)`, `setTheme`, re-gather only after new tiles | `frontend/app/src/map/bridge.ts` | read |
| C6 | Roads at estimated real widths per class (`ROAD_M`, UNVERIFIED in docs), walkway/cycle/steps layers replace dashed path; shell layer/colour removed | `frontend/app/src/map/style.ts` | read |
| C7 | Wireframe `City` + ground line / basement veil in the model scene; BuildingScreen passes `city` and height | `PlanView.tsx`, `BuildingScreen.tsx` | read |
| C8 | Back flies to the camera stored on opening; heights re-read only after new tiles; list panel `visibility:hidden` while open | `MapLanding.tsx`, `map.css` | read |
| C9 | Frontend type-checks and builds | `frontend/app` | `npx tsc -b --noEmit`; `npm run build` |
| C10 | Docs + memory bank updated (visualization.md, project-state, log) | those files | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q` → `771 passed, 2 skipped in 94.08s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- `cd frontend/app && npx tsc -b --noEmit` → no output (clean)
- `npm run build` → `✓ built in 533ms` (chunk-size warning only)
- Visual/perf behaviour (x-ray look, frame times, applyBlocks 183→16 ms) was measured in the browser in the session, not re-run here.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (city view line)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: visualization.md, commands.md, access-profiles spec

## Known gaps / not done
- No automated tests for the map/x-ray (visual, checked manually in browser).
- Road widths are UNVERIFIED estimates (tiles carry no width).
- X-ray size/softness still to be tuned with Atahan.
- `.claude/worktrees/` deliberately not committed (local git worktree).

## Verification rounds
- Round 1: PASS

## Verification report (round 1)

VERDICT: PASS — all claims C1–C10 MET. pytest 771 passed/2 skipped; links OK; tsc clean; build OK; no secrets; score.py unchanged; no hard-coding.
Undeclared (minor): DEV-only debug hooks window.__bridge / window.__xray; osmHeights per-polygon prefilter; model-blocks filter hides blue blocks within 500 m (x-ray redraws them).
Advisory: visualization.md 2026-10-24 bullet still describes the old shell / fly-out-to-every-pin (superseded below it); log.md "Learned" says osmHeights not changed, contradicted by the later perf-pass line.
