# Map: show the location dot after a reload inside a building

- **Author:** Claude session (for Atahan) · **Date:** 2026-10-26 22:50
- **Related:** user report "reload inside a building, go to the map: the location dot is gone"

## Summary
The map's "show my location" step ran only when the map first mounted and returned early if a building was open,
so after a reload inside a building the GeolocateControl was never triggered and the map had no dot. The step now
re-checks when the open building changes and runs once, the first time the map is shown.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | The location effect depends on `focusId` (was `[]`) and returns early while a building is open (`focusId`), so it runs when the map is first shown, also after a reload inside a building | `frontend/app/src/map/MapLanding.tsx` location `useEffect` | read the diff |
| C2 | It runs at most once per page (`locateAsked` ref), so opening and closing a building again does not call `geolocate.trigger()` a second time (a second trigger would toggle tracking off) | same | read: `locateAsked.current` set before the permission query |
| C3 | A run cleaned up before the browser answered (React dev double mount, building opened at once) resets `locateAsked` so the next run asks again; a run that already answered does not | same, `answered` flag in the cleanup | read |
| C4 | The behaviour for a normal map load (no building open) is unchanged: same granted / prompt+allowed → locate, prompt+not dismissed → our card, denied → quiet | same | read the `.then` / `.catch` / no-permissions branches |
| C5 | `memory-bank/log.md` has a 2026-10-26 entry for this fix; only that entry is staged (another session's unstaged Q-021 entry is not part of this commit) | `memory-bank/log.md` | `git diff --cached memory-bank/log.md` |

## Checks I ran
- `cd frontend/app && npx tsc --noEmit -p .` → no output (OK)
- `cd frontend/app && npm run build` → `✓ built in 669ms` (chunk-size warning only, pre-existing)
- `cd frontend/app && npx oxlint src/map/MapLanding.tsx` → no findings

## Knowledge base updates
- [x] `memory-bank/project-state.md` not updated: a small bug fix, no change to what exists or what is next
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: none (no doc describes the location-on-open step in this detail)

## Known gaps / not done
- Not tried in a browser: the Chrome extension was not connected. Atahan to check: open a building, reload, go back
  to the map → the dot shows.
- When the map is first shown after such a reload, the geolocate control moves the camera to the viewer's position
  (as on a normal first load), which can cut the fly-back from the building short.
- Many other files have unstaged changes from other sessions; none are staged here.

## Verification rounds
- Round 1: PASS

## Verification report (round 1)
VERDICT: PASS
TREE: d773388766876729f528b6c29f2fc163e7a53f08
- C1–C5: MET. C1 checked at MapLanding.tsx:531 and :569. C2: `locateAsked` is set before the permission query. C3: the `answered` flag is checked in the cleanup. C4: the `.then`/`.catch` logic is equivalent. C5: only this log entry is staged; the Q-021 entry stays unstaged.
- Standard checks: pytest 1088 passed, 2 skipped. Links OK in 27 files. No secrets. score.py unchanged. No hard-coding.
- Re-ran the checks listed in PENDING: tsc gave no output, oxlint gave no output, build passed with the chunk-size warning only.
- Undeclared: only an eslint-disable comment above the deps array, which does not change behaviour.
