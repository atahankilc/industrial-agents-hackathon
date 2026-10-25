---
id: plan-reference-and-location-plan
summary: Implementation plan for the import's straightened plan beside the Edit mode editor (reference + trace) and for buildings at a place on the map (OSM fit, photo GPS, hand placement, supersede on re-save).
sources:
  - docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md
  - core/plan_import/model.py, backend/drafts.py, backend/app.py, core/edits.py, frontend/app/src/building/BuildingScreen.tsx, frontend/app/src/map/MapLanding.tsx
related: [../specs/2026-10-25-plan-reference-and-location-design.md, 2026-10-25-plan-import.md]
---

# Plan reference in Edit mode + buildings at a place on the map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the import's straightened plan beside (and, on a switch, under) the editor, and let a building be
created at a tapped place on the map, fitted onto its OSM footprint, corrected by hand, saved with a real position.

**Architecture:** The import keeps, per floor, a downscaled straightened plan image + its px → metres transform
inside the building data (`source_ref.import.floors[level].reference`), served to Edit mode by a draft endpoint
and stripped from every other payload. A building's real position is `building.location` (the kit
`locations.json` fields + `bearing`); a pure geo module (Python and TS twins) converts building metres ↔ lat/lon
with that bearing; a fit module places a generated building onto an OSM footprint; two new edit ops
(`scale_building`, `set_location`) make placement an ordinary, undoable draft step.

**Tech Stack:** Python 3.12 (FastAPI, shapely, numpy, Pillow, OpenCV already present), React 19 + TypeScript +
MapLibre (frontend/app), pytest; TS math checked with `node --experimental-strip-types`.

**Spec:** `docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md`

## Global Constraints

- Order and cut lines: Milestone 1 (Part 1) → Milestone 2 (Part 2 core) → Milestone 3 (GPS) only if time remains; each milestone ships on its own (`/ship`, commit-verifier at effort medium, Utku's preference).
- Edit mode keeps the plan's own orientation; only the map applies `bearing` (degrees, angle from east to the building's x axis, counter-clockwise; 0 for every kit building).
- Fit scale limited to within ±25 % (0.75–1.25), applied to the building's coordinates, shown to the user.
- Trace opacity default 0.4; reference panel open/closed remembered per browser (`localStorage`, wrapped in try/catch).
- Split view only for buildings with references (imports and their saved copies); kit buildings keep today's Edit mode.
- Same access rule as Edit mode: references are served only under `/drafts/...` (admin-only in `ACCESS_MODE=on`).
- Never touch the Sunday benchmark path (`agent/run_benchmark_v1.py`, `agent/answer.py`, `SUBMISSION/`); a kit building's model is never replaced or hidden by a new version.
- Positioned user/imported building re-saved → it supersedes the one it came from on the map; second versions side by side only from "Create a building here" on a kit building.
- GPS mismatch: the photos' median GPS inside another OSM building, or > 50 m from the tapped one (Milestone 3).

## Review Focus

- A floor with no reference (an import from before this change, or a floor the Creator registered without an image) → the panel says "No plan image for this floor" instead of breaking; test in Task 1 and Task 2.
- A very large PDF page → the stored reference is capped (long side ≤ 1600 px, JPEG quality 80); test in Task 1.
- An OSM building cut at vector-tile edges → the footprint pieces under the tap are merged before fitting; test in Task 5 (two halves of a rectangle merge into one ring).
- A fit that hits the scale limit or a poor overlap (IoU < 0.5) → still placed, flagged `low_confidence`, the user corrects by hand; test in Task 4.
- Re-saving a positioned building in the Supabase store, not only files → supersede works through the `DraftBackend` protocol; test in Task 6 with the fake DB used by `tests/test_draft_backends.py`.

---

## Milestone 1 — The plan beside the editor

### Task 1: Keep a reference image per floor and serve it to Edit mode

**Files:**
- Create: `core/plan_import/reference.py`
- Modify: `backend/app.py` (`import_stream`: attach references before `drafts.create_import`; new `GET /drafts/{draft_id}/references`)
- Modify: `backend/drafts.py` (`DraftStore.state`, `DraftStore.references`)
- Test: `tests/test_plan_references.py`

**Interfaces:**
- Produces: `reference_for(floor: FloorPlan, max_side: int = 1600) -> dict` → `{"image": "data:image/jpeg;base64,…", "transform": [[a, b, c], [d, e, f]]}` (2×3, image px of the *stored* (downscaled) image → building metres, y up); `strip_references(building: dict) -> dict` (deep copy without any `reference` key); `DraftStore.references(draft: Draft) -> list[dict]` → `[{"floor_id", "level", "image", "transform"}]` sorted by level, `[]` when none; endpoint `GET /drafts/{id}/references` → `{"floors": [...]}` (404 unknown draft).

- [ ] **Step 1: Write the failing tests** — `test_reference_is_a_capped_jpeg_with_a_scaled_transform` (a 3000×1000 px `FloorPlan.image`, `transform` = [[0.01,0,0],[0,-0.01,10]] → stored image long side 1600, transform entries a, d scaled by 3000/1600, data URL prefix `data:image/jpeg;base64,`); `test_state_never_carries_reference_images` (a building with a reference in `source_ref.import.floors["0"]` → `DraftStore.state(draft)["building"]` has no `reference` anywhere); `test_references_survive_save_and_reopen` (`create_import` → `references` has floor `<id>-F0` → `save` → a new draft on `user/<slug>` → same references); `test_floor_without_reference_is_left_out` (two floors, one with reference → one entry); `test_references_endpoint` (404 for an unknown draft id; 200 `{"floors": [...]}`).
- [ ] **Step 2: Run** `uv run pytest tests/test_plan_references.py -q` → FAIL (`ModuleNotFoundError: core.plan_import.reference`).
- [ ] **Step 3: Implement** `reference_for` (OpenCV resize INTER_AREA, `cv2.imencode('.jpg', …, [IMWRITE_JPEG_QUALITY, 80])`, compose the downscale into the transform); in `import_stream` after `result.status == "done"`, for each `session.floors[level]` with an image set `building["building"]["source_ref"]["import"]["floors"][str(level)]["reference"] = reference_for(floor)` (keep a reference to the `ImportSession` you create); `DraftStore.state` returns `strip_references(self.building(draft))`; `DraftStore.references` reads `source_ref.import.floors` of the draft's *built* building (survives `save`, which already copies `source_ref.import`) and maps level → floor id `<building id>-F<level>` via the building's `floors`.
- [ ] **Step 4: Run** the new tests and `uv run pytest tests/test_drafts.py tests/test_draft_backends.py tests/test_plan_import*.py -q` → PASS.
- [ ] **Step 5: Commit** (worklog + `/ship` at the end of Milestone 1, or per task if preferred).

### Task 2: Split view with the reference panel

**Files:**
- Create: `frontend/app/src/edit/ReferencePanel.tsx`, styles in `frontend/app/src/edit/edit.css`
- Modify: `frontend/app/src/api.ts` (`FloorReference`, `api.draftReferences`), `frontend/app/src/edit/useDraft.ts` (load references with the draft), `frontend/app/src/building/BuildingScreen.tsx` (layout when editing)

**Interfaces:**
- Consumes: `GET /drafts/{id}/references` (Task 1).
- Produces: `export type FloorReference = { floor_id: string; level: number; image: string; transform: [[number, number, number], [number, number, number]] }`; `api.draftReferences(draftId: string): Promise<FloorReference[]>`; `useDraft(...)` returns `references: FloorReference[]`; `ReferencePanel({ reference, floorName, onClose }: { reference: FloorReference | null; floorName: string; onClose: () => void })`.

- [ ] **Step 1:** Add the type + API call; `useDraft` fetches references once per draft id.
- [ ] **Step 2:** `ReferencePanel`: the image with wheel-zoom and drag-pan (CSS transform, no library), header "Reference · <floor name>" + close button; `reference === null` → "No plan image for this floor".
- [ ] **Step 3:** `BuildingScreen`: when `editing && draft.references.length > 0 && referenceOpen`, wrap the plan area in a two-column layout (reference left 50 %, editor right); the panel's reference = the entry whose `floor_id === editFloorId`; `referenceOpen` from `localStorage['edit.referenceOpen']` (default true, try/catch); a toolbar button reopens a closed panel.
- [ ] **Step 4: Verify** `cd frontend/app && npx tsc -b` → exit 0; headless Chrome (claude-in-chrome or the dev server + screenshot) on a draft that has references: switching floor tabs switches the image; close → full width; reload keeps it closed.
- [ ] **Step 5: Commit.**

### Task 3: Trace underneath

**Files:**
- Modify: `frontend/app/src/edit/EditLayer.tsx` (draw the trace), `frontend/app/src/edit/EditBar.tsx` (switch + opacity), `frontend/app/src/edit/geometry.ts` (matrix helper)
- Create: `frontend/app/scripts/trace.check.ts`

**Interfaces:**
- Consumes: `FloorReference` (Task 2).
- Produces: `traceMatrix(transform: FloorReference['transform']): string` in `edit/geometry.ts` → an SVG `matrix(a b c d e f)` string placing image px in the EditLayer's metre space (EditLayer draws building metres inside the floor-aligned group; apply the same y convention it uses for polygons); `EditLayer` prop `trace?: { image: string; transform: FloorReference['transform']; opacity: number }`.

- [ ] **Step 1: Write the check** `frontend/app/scripts/trace.check.ts`: for transform [[0.02,0,1],[0,-0.02,8]], image px (0,0) → metres (1, 8) and (100, 50) → (3, 7) after applying the matrix the way the EditLayer's group maps metres (assert with `node:assert`).
- [ ] **Step 2: Run** `node --experimental-strip-types frontend/app/scripts/trace.check.ts` → FAIL (`traceMatrix` not exported).
- [ ] **Step 3: Implement** `traceMatrix`; EditLayer renders `<image href={trace.image} transform={traceMatrix(...)} opacity={trace.opacity} pointerEvents="none" preserveAspectRatio="none">` as its first child (under rooms); EditBar: "Trace" toggle + range 0.1–0.8 (default 0.4), shown only when the current floor has a reference.
- [ ] **Step 4: Verify** the check passes, `npx tsc -b` exit 0; live: run one real import of `building_plans/residenz-münchen-building-plan.pdf` (calls Claude, ≈ $1 — say so before running), open Edit mode, switch the trace on: the drawn walls lie on the generated room outlines (screenshot).
- [ ] **Step 5: Ship Milestone 1** — `.claude/worklog/PENDING.md` (claims per task), docs: `docs/product/visualization.md` (Edit mode section: reference + trace), `docs/guides/commands.md` (`GET /drafts/{id}/references` row), memory bank (state + log); `/ship`.

---

## Milestone 2 — A building at a place on the map

### Task 4: Geo placement core (metres ↔ lat/lon with bearing, fit onto a footprint)

**Files:**
- Create: `core/geoplace.py`
- Test: `tests/test_geoplace.py`

**Interfaces:**
- Produces: `to_lnglat(origin: dict, bearing_deg: float, x: float, y: float) -> tuple[float, float]` (local equirectangular, R = 6378137, same convention as `scripts/fit_locations.py`); `to_metres(origin, bearing_deg, lon, lat) -> tuple[float, float]`; `footprint(building: dict) -> Polygon` (union of the ground floor's space polygons, buffered 0.25 m); `@dataclass Placement(origin: dict, bearing_deg: float, scale: float, iou: float, low_confidence: bool)`; `fit(building: dict, ring: list[list[float]]) -> Placement` (ring = [lon, lat] OSM outer ring); `location_for(building: dict, placement: Placement, address: str | None = None) -> dict` → `{"lat", "lon", "address", "origin", "bearing", "outline", "height_m", "fit": {"scale", "iou", "low_confidence"}}` (`outline` = footprint rings in [lon, lat], placed with origin + bearing after scaling; `lat`/`lon` = outline centroid).

- [ ] **Step 1: Write the failing tests** — `test_bearing_zero_matches_the_kit_convention` (x = 10 → 10 m east of origin, same numbers as `scripts/fit_locations.py`'s helper); `test_round_trip` (to_metres(to_lnglat(p)) ≈ p within 1 mm, bearing 37°); `test_fit_recovers_an_l_shaped_building` (L-shaped 30×20 m building; OSM ring = the same shape rotated 30°, scaled 1.1, placed at 48.1497 N 11.5679 E → bearing within 2° of 30, scale 1.10 ± 0.02, IoU ≥ 0.95); `test_fit_scale_is_bounded` (OSM ring 1.6× bigger → scale 1.25, `low_confidence` True); `test_poor_overlap_is_flagged` (IoU < 0.5 → `low_confidence`).
- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `fit`: OSM ring → metres around its centroid; seed bearing from the principal axes of both shapes (try the 4 axis-aligned flips), seed scale from √(area ratio) clamped to [0.75, 1.25], seed shift by centroids; refine by maximising shapely IoU over (dx, dy, bearing, scale) with a coarse-to-fine grid (no new dependency); `low_confidence` = IoU < 0.5 or scale at a bound.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit.**

### Task 5: Placement as draft edits, and positions from the backend

**Files:**
- Modify: `core/edits.py` (ops `scale_building`, `set_location`), `backend/app.py` (`/imports/stream` accepts `place`; `PUT /drafts/{id}/location`), `backend/drafts.py` (`save`: supersede; catalogue location for `user/` buildings), `backend/sessions.py` (catalogue + `/buildings` read `building.location`, hide superseded), `agent/campus.py` and any other user of `origin` for metres ↔ lat/lon (use `core.geoplace` with `bearing`, 0 = unchanged)
- Test: `tests/test_placement.py`, `tests/test_edits.py` (new ops)

**Interfaces:**
- Consumes: Task 4.
- Produces: ops `{"op": "scale_building", "factor": float}` (scales every space polygon, opening position/width unchanged, asset position about (0, 0)) and `{"op": "set_location", "location": dict | null}`; form field `place` on `POST /imports/stream`: JSON `{"ring": [[lon, lat], …]}` (footprint pieces already merged by the frontend) or `{"point": [lon, lat]}`; the `done` line gains `"location"`; `PUT /drafts/{id}/location` body `{"origin": {"lat", "lon"}, "bearing_deg": float, "scale": float}` (scale relative to the current building, product with earlier fits kept within 0.75–1.25) → applies `[scale_building, set_location]` as one undo step, returns the draft state; `/buildings` items for `user/` buildings carry `location` (+ `bearing`), `null` when superseded.

- [ ] **Step 1: Write the failing tests** — ops: `test_scale_building_scales_polygons_and_positions`, `test_set_location_round_trips_through_undo`; placement: `test_import_with_a_place_is_fitted_and_located` (fake Creator as in the existing import-stream tests, `place.ring` = the fake building's footprint rotated 20° at a lat/lon → `done.location.bearing` ≈ 20, location stored on the draft's building); `test_point_place_centres_without_fit`; `test_put_location_is_one_undo_step`; `test_saved_positioned_building_is_on_the_map` (`/buildings` returns its `location` with `origin`, `bearing`, `outline`); `test_resave_supersedes_on_the_map` (save → reopen → save again → older slug's `location` is `null` in `/buildings`, newer has it) — also with the Supabase fake backend from `tests/test_draft_backends.py`; `test_kit_building_second_version_keeps_both` (place on a kit building's outline → both the kit building and the new one keep their locations); `test_merged_tile_pieces` (frontend sends merged ring — backend accepts a ring with ≥ 4 points, rejects < 3 with 422).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Supersede: `DraftStore.save` sets `location["supersedes"] = <old slug>` when the draft's base is `user/<old>` and the old building has a location; the catalogue computes the superseded set from all saved buildings and returns `location: null` for them. Campus / sessions: replace the local metres ↔ lat/lon math with `core.geoplace` (pass `location.get("bearing", 0)`).
- [ ] **Step 4: Run** the new tests + `uv run pytest -q` → all pass (kit buildings unchanged: bearing 0).
- [ ] **Step 5: Commit.**

### Task 6: Map: bearing-aware placement, "Create a building here", hand correction, version choice

**Files:**
- Create: `frontend/app/src/map/geo.ts` (pure math), `frontend/app/scripts/geo.check.ts`, `frontend/app/src/map/Placement.tsx`
- Modify: `frontend/app/src/map/bridge.ts` (use `geo.ts`; `Origin` gains `bearing?: number`; `follow` turns the map by the building's bearing), `frontend/app/src/map/MapLanding.tsx` (tap card, version chooser), `frontend/app/src/import/ImportScreen.tsx` (send `place`, then the placement step), `frontend/app/src/api.ts` (`Building.location.bearing`, `api.setDraftLocation`), `frontend/app/src/Root.tsx` (flow)

**Interfaces:**
- Consumes: Task 5 endpoints and `location` shape.
- Produces: `toLngLat(origin: Origin, x: number, y: number)` / `fromLngLat(origin, lng, lat)` honouring `origin.bearing ?? 0`; `api.setDraftLocation(draftId: string, body: { origin: { lat: number; lon: number }; bearing_deg: number; scale: number })`; `Placement({ draftId, location, onDone })` — map at the place, the building outline as a GeoJSON overlay: drag to move, a rotate handle, a scale handle (overall scale kept within 0.75–1.25), "Looks right" → `setDraftLocation` → Edit mode.

- [ ] **Step 1: Write the check** `geo.check.ts`: bearing 0 equals the current formula for (10, 0) and (0, 10); bearing 90 → x = 10 lands 10 m north; round trip within 1e-6 m.
- [ ] **Step 2: Run** `node --experimental-strip-types frontend/app/scripts/geo.check.ts` → FAIL.
- [ ] **Step 3: Implement** geo.ts and switch bridge.ts to it (map camera bearing = view bearing − building bearing).
- [ ] **Step 4: Implement the flow:** tapping a tile building on the landing map → card "Create a building here" (on one of our model blocks: "Open" and "Create a new version here"); the tapped footprint = the union of the rendered `building` features under the tap (merge tile pieces) as `place.ring`; ImportScreen posts `place`; on `done` with `location` → `Placement`; tapping a spot where two of our buildings overlap → "Which version?" list.
- [ ] **Step 5: Verify** checks pass, `npx tsc -b` exit 0; live (≈ $1, say so first): tap the Urban Colab building → import its photos → placement shows the fitted outline → nudge → Edit mode → Save → back on the map the new block stands there, tapping it opens it with the Guide.
- [ ] **Step 6: Ship Milestone 2** — worklog, docs (`docs/product/visualization.md` map + placement, `docs/guides/commands.md` endpoints, `docs/architecture/overview.md` if the data model section lists `location`), memory bank; `/ship`.

---

## Milestone 3 — GPS (only if time remains)

### Task 7: Photo GPS and the "did you mean" check

**Files:**
- Modify: `core/plan_import/ingest.py` (`photo_gps(data: bytes) -> tuple[float, float] | None` from EXIF GPSInfo, Pillow), `backend/app.py` (stream line `{"type": "gps", "lat", "lon", "photos": n}` = median of the photos with GPS), `frontend/app/src/import/ImportScreen.tsx` (compare with the chosen place; fallback: browser geolocation taken at upload; "These photos were taken at <name> — did you mean that one?"), `frontend/app/src/map/MapLanding.tsx` ("Import" without a place: GPS proposes the building under it)
- Test: `tests/test_plan_import_gps.py`

- [ ] **Step 1: Write the failing tests** — `test_photo_gps_reads_the_demo_photos` (each of `building_plans/urban_collab/*.jpeg` → lat ≈ 48.1, lon ≈ 11.5; skip if the folder is absent); `test_photo_without_gps_is_none`; `test_stream_reports_median_gps`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; mismatch rule (inside another OSM building or > 50 m) in the frontend, checked live.
- [ ] **Step 5: Ship Milestone 3.**

### Task 8: "Edit position" on a saved building

**Files:**
- Modify: `frontend/app/src/edit/EditBar.tsx` (menu item "Edit position", only when the building has a `location`), `frontend/app/src/map/Placement.tsx` (reused with the current location as start)

- [ ] **Step 1:** "Edit position" opens `Placement` for the current draft with its `location`; "Looks right" → `api.setDraftLocation` (Task 5) → back to Edit mode; Save supersedes as usual (Task 5 test covers it).
- [ ] **Step 2: Verify** `npx tsc -b` exit 0; live: move a saved building 10 m, save, the map shows only the new position.
- [ ] **Step 3: Ship** with Milestone 3.
