# Map → building transition, city / alone views, model buildings on the map, light map palette

- **Author:** Claude (session on branch `map-transition`) · **Date:** 2026-10-25
- **Related:** docs/product/visualization.md (Landing, Map → building); user request: smooth map → model transition,
  keep other buildings visible, two views (general viewers: whole map; building managers: one building), faster
  building loading, mark buildings that have a model, nicer light map.

## Summary
The landing map stays mounted under the building screen: tapping a pin flies in, the model takes over from the map's
camera and rises out of the ground, and the map then follows the model's camera so the city stays aligned around it.
A menu toggle shows the building in its city (neighbour pins tappable) or alone. The session + plan load starts on the
tap. Buildings with a model are drawn as blue blocks on the map; light mode has a new palette.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `backend/locations.json`: each of the 17 buildings has `origin` {lat, lon}, `outline` ([lon, lat] rings), `height_m`; `about` describes them | `backend/locations.json` | `python3 -c "import json;d=json.load(open('backend/locations.json'))['buildings'];print(len(d), all({'origin','outline','height_m'}<=set(v) for v in d.values()))"` → `17 True` |
| C2 | Backend test checks every located building's `origin` lies within 20 m of its outline centre (full distance: north and east offsets in metres, hypot < 20; data is 0.0–11.4 m) | `tests/test_backend.py::test_buildings_carry_a_location_only_where_one_is_known` | `uv run pytest -q tests/test_backend.py` → 22 passed |
| C3 | Map ↔ model bridge: kit metres ↔ lon/lat, zoom from px/m, `follow`, `mapView`, `settled` (waits for `!isMoving()`, not the first moveend), `pinAt`, `hideBlocks`/`showBlocks`/`applyBlocks`, `osmHeights` | `frontend/app/src/map/bridge.ts` | read the file |
| C4 | Session + plan fetched once per visit and shared (prefetch on tap; React dev double mount reuses it; dropped 1 s after the screen goes) | `frontend/app/src/building/opening.ts`, `Root.tsx` `go`, `BuildingScreen.tsx` load effect | read |
| C5 | Root keeps the map mounted under a located building, fades the old screen (350 ms `leaving`) before swapping, remembers the view choice in localStorage `ttyb-building-showing` (default `city`) | `frontend/app/src/Root.tsx` | read |
| C6 | MapLanding takes `buildings`/`error`/`focus` props; flies in (1.5 s, FOV eased to 4°) / jumps if just mounted, flies back out to all pins on close; hides the open building's pin and blue block; panel/controls step aside (`ml-open`, `inert`) | `frontend/app/src/map/MapLanding.tsx`, `map.css` | read |
| C6b | MapLanding also: `maxPitch: 75` (the model tilts to 69°); the location prompt and geolocation trigger are suppressed while a building is open (`focus`); dev builds only expose the map as `window.__map` (`import.meta.env.DEV`) for headless checks | `frontend/app/src/map/MapLanding.tsx` | read (`maxPitch`, `focusRef.current` in the geolocation effect, `askLocation && !focus`, `__map`) |
| C7 | Buildings with a model drawn as accent blocks: `models` GeoJSON source, `model-footprints` fill + `model-blocks` fill-extrusion, height = max(kit `height_m`, OSM block `render_height`) + 0.4, updated on map idle | `MapLanding.tsx` `addPins` / `updateHeights`, `style.ts` `modelColours` | read |
| C8 | Light map palette changed (land, greens, water, casings, labels, block side light 0.25 → 0.42; woods fade in by zoom); dark palette gains `ours`/`oursRoof`, and the wood opacity ramp's full-opacity stop moves from zoom 11 to 12 in both themes (dark keeps its 0.5 start, light starts at 0.25); `BUILDINGS_3D_FILTER` exported and used | `frontend/app/src/map/style.ts` | read the diff |
| C9 | PlanView: optional `ground`, `camera` ({intro, follow}), `onMiss` props; `Reveal` (model rises, 0.9 s), `Follow` (hands the camera to the map per frame, only when changed), Rig intro from the map's camera (1.1 s); defaults keep the old behaviour for callers that pass nothing | `frontend/app/src/plan/PlanView.tsx` | read |
| C10 | BuildingScreen: new props `origin`, `showing`, `onShowing`, `leaving` (dev's `onOpen` kept and reused for pin taps); classes `on-map`/`alone`/`ready`/`leaving`; `screen-stage` layer; menu item toggles "Show the building alone" / "Show it in the city" only for located buildings; Edit mode untouched | `frontend/app/src/building/BuildingScreen.tsx`, `screen.css` | read the diff vs dev |
| C10b | screen.css: `.plan-labels` fade in after a 0.6 s delay (after the model rises), `.screen-status` after 0.9 s (2.4 s over the map, so a quick open never shows it); both off under `prefers-reduced-motion` | `frontend/app/src/building/screen.css` | read |
| C15 | `load_catalogue` docstring names the optional `origin`, `outline`, `height_m` location fields | `backend/sessions.py` `load_catalogue` | read |
| C11 | Theme choice synced across all mounted `useTheme` instances (map and building screen) | `frontend/app/src/theme.ts` | read |
| C12 | `Building.location` type has optional `origin`, `outline`, `height_m` | `frontend/app/src/api.ts` | read |
| C13 | Docs + memory bank updated; links resolve | `docs/product/visualization.md`, `memory-bank/log.md`, `memory-bank/project-state.md` | `python3 scripts/check_links.py` → OK |
| C14 | Frontend typechecks; oxlint shows no new warnings vs dev | `frontend/app` | `cd frontend/app && npx tsc -b` (no output); `npx oxlint src \| grep -c warning` → 13 (same as dev) |

## Checks I ran

- `npx tsc -b` (frontend/app) → no output, exit 0
- `npx oxlint src | grep -c warning` → 13 on this branch, 13 on dev
- `uv run pytest -q` → `753 passed, 2 skipped in 92.26s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Fix round 1: `uv run pytest -q tests/test_backend.py` → `22 passed in 2.00s`; `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Headless Chrome (playwright-core + system Chrome, real GPU) against the branch servers: open from map in city and
  alone views, back, tap a neighbour pin (switched to Landwirtschaftsbau), menu toggle, direct `?building=` URL,
  building with no position (`train/proc-campus-train-000`, ready after ~470 ms, rises in), light + dark map with
  blue model blocks, Edit mode opened over the map. Screenshots looked right; not checked on a real phone.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (App visuals: map → building bullet)
- [x] `memory-bank/log.md` entry added (2026-10-25 map → building)
- [x] decisions / open questions touched: none
- [x] docs touched: `docs/product/visualization.md` (Map → building, Buildings with a model, Two ways to show)

## Known gaps / not done
- Outlines are derived from the kit's spaces (union, outset 0.6 m), not the OSM way: the archived georef outlines
  were deleted with `.viz-archive`. `origin` values came from that archived georef.json before it was deleted.
- The map's perspective is narrowed to 4° to match the orthographic model; alignment is exact at the screen centre
  and within a few percent at the edges, not pixel-exact.
- The model's own OSM blocks are hidden by centre-in-outline; where the tiles draw a whole campus block as one
  polygon (TUM main building), the grey block stays under the model.
- View toggle lives in the ••• menu (no visible control yet). Not verified on a real phone / real Chrome window.
- Edit mode header buttons (`.round`, `.where`) have no CSS in dev's `edit.css`; unchanged here, not fixed.

## Verification rounds
- Round 1: FAIL (C2 partial: test checked latitude only; docstring; undeclared items)

## Fix round 1
- C2 test checked latitude only: implemented — `tests/test_backend.py` now converts the lat/lon offsets of `origin`
  from (`lat`, `lon`) to metres (dlat × 111320, dlon × 111320 × cos(lat)) and asserts hypot < 20 m per building
  (`import math` added). Checked a 50 m longitude shift of every origin would fail it (17/17 exceed 20 m).
- `load_catalogue` docstring: implemented — `backend/sessions.py` mentions optional `origin`, `outline`, `height_m`
  and points at the `about` field of `backend/locations.json` (new claim C15).
- Undeclared items: claim corrected — added C6b (maxPitch 75, location prompt suppressed while a building is open,
  dev-only `window.__map`) and C10b (`.plan-labels` / `.screen-status` fade-in delays); C8 wording now says the
  wood ramp change applies to both themes; C2 text matches the fixed test.
- Checks re-run: `uv run pytest -q tests/test_backend.py` → `22 passed in 2.00s`;
  `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Round 2: PASS (tree aeec4cef)

---

# Verification report (round 2)

VERDICT: PASS
TREE: aeec4cef067d8b1361b61655fa4df81414ec7eba

C1–C15 (incl. C6b, C10b) MET. pytest 753 passed / 2 skipped; links OK (33 files); no secrets; benchmark/score.py unchanged; no hard-coding; tsc clean; oxlint 13 = dev 13. Headless Chrome checks not reproduced (visual, outside read-only verification). Notes: C9 Reveal runs for every caller (declared in docs); undeclared trivia only (map.css reduced-motion/narrow-screen panel offset, stage background moved to .screen-stage, pinBounds/fitPadding refactor, theme cycle from instance mode).

Round 1 (FAIL) required fixes, all done in fix round 1: full-distance origin test; sessions.py docstring; PENDING.md undeclared items and C8 wording.
