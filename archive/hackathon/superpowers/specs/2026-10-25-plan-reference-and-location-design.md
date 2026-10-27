---
id: plan-reference-and-location-design
summary: Design of two additions to plan import — (1) the straightened source plan beside the editor in Edit mode, with a "trace underneath" switch; (2) creating a building at a place on the map, fitting it onto the OSM building there, checking the photos' GPS, saving it with a real position so it shows on the map like the kit buildings.
status: implemented 2026-10-25 (branch `7-buildings-from-plans` (started as `6-plan-reference-location`); agreed with Utku in conversation)
sources:
  - conversation with Utku, 2026-10-25 (brainstorming; layout C picked in the visual companion)
  - core/plan_import/model.py (FloorPlan.image rectified + cropped, FloorPlan.transform px → frame metres)
  - core/plan_import/assemble.py (source_ref.import.floors: source, m_per_px, alignment; floor ids `<building>-F<level>`)
  - backend/app.py (/imports/stream), backend/drafts.py (create_import, insert_building, register)
  - backend/sessions.py + backend/locations.json (`location` = lat/lon/origin/outline/height_m, kit OSM buildings only)
  - frontend/app/src/map/MapLanding.tsx, map/bridge.ts (Origin = {lat, lon}, x east / y north, no rotation), map/style.ts (OpenFreeMap vector tiles)
  - scripts/fit_locations.py (kit footprints shifted onto their OSM ways, translation only)
  - building_plans/urban_collab/*.jpeg (all 11 photos carry GPS EXIF, checked 2026-10-25)
related: [2026-10-25-plan-import-design.md, 2026-10-24-builder-edit-mode-design.md, ../../product/visualization.md, ../../architecture/ai-agents.md, ../../guides/commands.md, ../plans/2026-10-25-plan-reference-and-location.md]
---

# Plan reference in Edit mode, and buildings created at a place on the map

[Docs index](../../../../docs/README.md) · Builds on: [plan-import-design](2026-10-25-plan-import-design.md),
[builder-edit-mode-design](2026-10-24-builder-edit-mode-design.md)

## Intent

Plan import (the Creator) makes a building from floor-plan photos or PDFs, but the result is not perfect, and the
person fixing it in Edit mode today sees only the generated building — not the plan it came from. They want to
**look at the original plan while they correct the building**, floor by floor.

They also want the building to **live where it really is**: stand in front of (or inside) a building, find it on the
app's map, say "create a building here", photograph its evacuation plans, correct the result, save — and from then on
find it on the map like the kit's buildings, tap it, get routes and open Edit mode.

## Part 1 — The plan beside the editor

### What the user sees (decided with Utku; layout C)

- In Edit mode on a building that came from a plan import, the screen splits: **left the reference**, **right the
  editor** as today (plan editor, floor tabs, 3D inset, Builder chat stay as they are, in the right half).
- The reference is the **straightened plan** (the import's rectified + cropped image), not the original photo.
- **The reference follows the floor tabs:** switching to another floor shows that floor's plan.
- **"Trace underneath" switch** in the editor: lays the same plan faintly under the rooms, at the right scale and
  position, so walls and doors can be dragged onto the drawn ones.

### My calls (not discussed; Utku accepted them in the play-back)

- The reference can be zoomed and panned on its own.
- The trace has an opacity control (default about 40 %).
- The reference panel can be closed; the editor then takes the full width. The choice is remembered per browser.
- Only buildings made by an import get the split; kit buildings and edited kit buildings keep today's Edit mode.
- After Save the references stay with the building: opening Edit mode on it again (or on a copy of it) shows them.

### What has to change (findings, 2026-10-25)

- Today the import keeps nothing of the images: `load_sources` holds them in memory, the building records per floor
  only `source`, `m_per_px`, `alignment` (`source_ref.import.floors`). The straightened image
  (`FloorPlan.image`) and its px → metres transform (`FloorPlan.transform`, 2×3, frame metres, y up) exist during
  the run and are thrown away.
- So the import must **store, per floor, the straightened image and its transform** with the draft, and the
  frontend must get them per floor (image + the matrix that places it in the plan's metres). The trace needs the
  transform to be in the same frame as the plan editor draws (check what `core/floorplan.py` / the draft plan does
  with the building frame — offsets or centring — and apply the same).
- Storage: local mode keeps drafts and saved buildings as files under `data/user/`; deployed mode keeps them in
  Supabase Postgres (`builder_drafts`, `saved_buildings`, `builder_imports`). Images are a few hundred kB each
  (long side ≤ 2400 px, JPEG/PNG). Where they go in deployed mode (a bytea column, Supabase Storage, or a
  downscaled copy inline) is **left to the builder**; the requirement is that they survive the draft → saved
  building step and a restart, and are only served to someone who may open that building's Edit mode (same access
  rule as `/drafts`).

## Part 2 — A building at a place on the map

### The flow (decided with Utku)

1. On the map, tap an OSM building → a **"Create a building here"** action. It is also offered on buildings that
   already have a model (the blue blocks); there the new one is saved **beside the existing model as a second
   version**, never replacing it.
2. Upload the photos / PDFs (today's import screen, with the chosen place shown).
3. The import reads the **GPS of the photos (EXIF)**. If it points clearly at another building than the one tapped,
   the app proposes it: "These photos were taken at <building> — did you mean that one?" — the user picks.
4. The generated building is **fitted onto the chosen OSM building's footprint** automatically: shift, rotation
   and scale.
5. If the fit is wrong, the user **corrects it by hand on the map**: drag to move, rotate (and, my call, scale with
   a handle) over the OSM footprint. This changes the position (origin, bearing) and, for the scale, the
   building's size — never its orientation in Edit mode.
6. Edit mode with the reference (Part 1) as usual; **Save**.
7. From then on the building is **on the map for everyone**, like the kit buildings: its block in the city, its pin;
   tapping it opens it with routes, the Guide and Edit mode, as for any other building.

### My calls (not discussed; Utku accepted them in the play-back)

- Started from the existing "Import" button instead of the map: if the photos carry GPS, the app proposes the
  building at that position (same "did you mean" step), else the building gets no position (as today).
- The hand correction comes right after the automatic fit, before Edit mode; a saved building's position can also
  be changed later from Edit mode ("Edit position").
- Tapped place without an OSM building (open ground): the building is placed with its centre on the tapped point,
  no automatic fit; the hand correction still works.
- Two versions on the same place: tapping asks which one to open.
- "Clearly another building": the photos' GPS (median of the photos that have it) lies inside another OSM building's
  footprint, or more than ~50 m from the tapped one. Phone GPS indoors is often 10–30 m off, so a photo position near
  the tapped building is not a mismatch. Exact rule left to the builder.

### How the position is represented (decided with Utku after the builder check)

- **Edit mode keeps the plan's own orientation.** The building's coordinates are never rotated: walls stay square
  on screen and line up with the reference plan and the trace, and the Builder's compass-side edits ("move the north
  wall", `core/edits.py` `edge_sides`) keep working. ("North" in the Builder then means the plan's up, not true
  north — acceptable.)
- **The rotation lives in the position, the map applies it.** `location` gains a **bearing** (degrees, the angle
  from east to the building's x axis, counter-clockwise; 0 for every kit building), next to `origin` (lat/lon of
  the building's (0, 0)) and `outline`. The map code that turns building metres into lat/lon (`map/bridge.ts`
  `toLngLat` and everything that places the model, blocks, pins and the camera hand-over) rotates by the bearing.
  Kit buildings have bearing 0, so nothing changes for them.
- **Scale** found by the fit is applied to the building's coordinates (it corrects the import's own estimate from
  door widths or a scale bar), limited (my call: within ±25 %) and shown to the user.
- Saved and imported buildings need a place for this position (today positions live only in the static
  `backend/locations.json` for kit buildings). Storing it with the building (`building.location`: the fields of a
  `locations.json` entry + `bearing` + the OSM footprint it was fitted to) keeps it through drafts and saves; the
  exact place is left to the builder, but `/buildings` returns it in the existing `location` shape (+ `bearing`).
- The OSM footprint comes from what the map already loads (OpenFreeMap vector tiles, building layer); a tiled
  footprint can be cut at tile edges, so the builder decides whether to merge pieces from the tiles or fetch the
  way from the OSM API (as `scripts/fit_locations.py` does, with its cache).

### Saving a building that has a position (decided with Utku)

- Today every Save writes a new saved building (`user/<slug>`, `-2`, `-3`, …). For a **positioned user/imported
  building**, a new save **supersedes** the one it was made from on the map: the newer one is shown, the older one
  stays in the list of buildings but gets no pin or block (a "supersedes" link from the new to the old).
- **Second versions side by side** happen only on purpose: "Create a building here" on a kit building that already
  has a model. The kit model and the new building both show; tapping asks which one.
- "Edit position" on a saved building is a save like any other (supersedes it).

### Order and cut lines (decided with Utku — today is the last day)

1. **Part 1** (reference beside the editor + trace) — shippable on its own.
2. **Part 2 core:** tap a building on the map → upload → automatic fit (shift, bearing, bounded scale) → hand
   correction on the map → Edit mode → Save → on the map for everyone, tappable like the kit buildings (with
   supersede on re-save and the version choice on kit buildings).
3. **If time remains:** the GPS "did you mean" check; GPS placement when starting from the Import button; "Edit
   position" on a saved building later.

### GPS when uploading from a phone (decided with Utku)

- Phone browsers (iOS Safari especially) often strip location from photos picked in a file input. So the GPS check
  uses the photos' EXIF GPS when present and **otherwise the browser's current position** (geolocation, asked with
  the app's existing location prompt), taken at upload time.

## Goals

- Correcting an imported building with the plan visible next to it and, with the trace, under it.
- Creating a building at a real place in a few taps, fitted onto its OSM footprint, corrected by hand if needed,
  and found again on the map by anyone.
- Works for the demo inputs: the Urban Colab photos (with GPS) and the Residenz PDF (no GPS: placed by the tap only).

## Non-goals

- Changing how the Creator segments or labels plans.
- Rotating the building's own coordinates (the map applies the bearing instead).
- Editing OSM data, or creating OSM footprints.
- Several buildings in one import.

## Anti-goals (fails even if it works)

- Any change to the Sunday benchmark path or its answers (`agent/run_benchmark_v1.py`, `SUBMISSION/`).
- Replacing or hiding an existing kit building's model when a second version is created.
- Showing someone the plan images of a building whose Edit mode they may not open.
- A fit that silently changes the building's size a lot (it must stay within the limit and be shown).

## Constraints

- Today is the hackathon's final day (code freeze in the afternoon, 2026-10-25): work in the order and cut lines
  above; each step must be shippable on its own.
- Repo rules: TDD, `/ship` with the commit verifier, docs + memory bank updated (CLAUDE.md).
- Same access rules as Edit mode and imports (`ACCESS_MODE`: admin-only for `/drafts` and `/imports`).
- Both local (files) and deployed (Supabase) stores must work.

## Left to the builder

- Where images are stored in deployed mode, image format and size, how they are served.
- The fitting method (e.g. outline IoU maximisation over shift / rotation / bounded scale, seeded by the principal
  axes), and how the OSM footprint is obtained.
- The exact GPS mismatch rule, the map interaction for the hand correction (handles, gestures), and copy.
- How "supersedes" is stored in both stores (files and Supabase `saved_buildings`) and filtered in `/buildings`.
- How the "which version?" choice looks.
