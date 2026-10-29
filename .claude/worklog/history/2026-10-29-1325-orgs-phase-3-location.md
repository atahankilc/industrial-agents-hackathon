# Organisations phase 3: you are here on the island board

- **Author:** Claude (Opus 5.5 session) · **Date:** 2026-10-29
- **Related:** D-029, docs/product/organizations.md § Phase 3

## Summary
On an org map's island board, the user's position is shown where it is on the board: standing inside an island's
real area, the blue dot is moved with that island; elsewhere a note names the nearest site and how far it is. The
board has its own location button and uses the main map's location consent.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `whereOnBoard(board, [lng, lat])`: inside an island's `real` rect → `{at}` (moved with `toBoard`); else `{nearest, metres}` with metres to the nearest island's edge; null for an empty board | `frontend/src/map/board.ts` | `node --experimental-strip-types frontend/scripts/board.check.ts` → ok (Garching point on its island; Pasing → main campus, 6–9 km) |
| C2 | On a board, `BoardLocate` (an `IControl` with MapLibre's geolocate look) replaces `GeolocateControl`; the location consent effect no longer skips boards; `locate()` on a board calls `locateOnBoard('auto')`; the button calls it with `'tap'` | `frontend/src/map/MapLanding.tsx` | read |
| C3 | `locateOnBoard` starts one `watchPosition` (cleared on unmount and on error); an error sets "Location is off for this site." / "Your position could not be found." | `MapLanding.tsx` | read |
| C4 | Dot layers `board-me-halo`, `board-me` from source `board-me` (re-added after a theme swap); on a fix the map flies to the dot if on an island; after a tap, if on no island, fits the nearest island; each fix flies at most once | `MapLanding.tsx` | read; headless |
| C5 | `.ml-near` note (not while a building is open or while arranging, closable): the error or "You are not on this map. Nearest site: <name or first building>, <distance> away."; bottom centre on wide screens, under the title on phones | `MapLanding.tsx`, `frontend/src/map/map.css` | read; headless |
| C6 | Docs: organizations.md (you-are-here paragraph, "On the board" bullet, summary, still-to-do), project-state, log | docs, memory-bank | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q` → `980 passed, 2 skipped in 130.79s (0:02:10)` (no backend change)
- `node --experimental-strip-types frontend/scripts/board.check.ts` → `board.check: ok`
- `cd frontend && npx tsc -b` → clean; `npx oxlint src/map` → no output; `npx vite build` → `✓ built`
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`
- Headless Playwright (scratchpad, geolocation granted, map `tum-sites`): at 48.2668, 11.6702 (StudiTUM) → `board-me` at [11.5729, 48.1483] (the Garching island on the board), map centred there at zoom 16, no note; at Pasing → no dot, note "You are not on this map. Nearest site: Hauptgebäude, 7.5 km away.", the button then moved the map to that island; phone 390×844 → note under the title; a point 200 m south of StudiTUM → "StudiTUM, 40 m away" (outside its island, correct). No console errors.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none new
- [x] docs touched: docs/product/organizations.md

## Known gaps / not done
- No accuracy circle and no heading; the dot does not follow the camera (it flies once per fix request).
- The island's name falls back to its first building's name when unnamed.
- Merging / splitting sites and polygon areas are still to do.
- Browser checks are scratchpad Playwright scripts, not in the repo.

## Verification rounds
- Round 1: PASS (tree fb062faeec6bf28812781b0cb6e825abcb8df043)

## Verification report (round 1)

VERDICT: PASS
TREE: fb062faeec6bf28812781b0cb6e825abcb8df043

C1–C6 MET (C4, C5 by reading). pytest 980 passed, 2 skipped; links OK (25 files); no secrets; score.py unchanged; no
hard-coding; board.check ok, tsc clean, oxlint clean, vite build ok. Headless checks not re-run (scratchpad). No
significant undeclared changes.
