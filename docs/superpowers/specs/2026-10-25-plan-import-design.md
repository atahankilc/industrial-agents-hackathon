---
id: plan-import-design
summary: Design of Builder project 2 — create a building.json draft from PDFs / images of floor plans with an agentic pipeline (find plans, segment rooms in code, label with Claude vision, scale, stack floors, validate), then hand it to the existing Edit mode for prompt corrections.
status: proposed
sources:
  - conversation with Utku, 2026-10-25
  - docs/challenge/brief.md (Level 4 "Build")
  - docs/kit/data-format.md
  - backend/drafts.py, core/validate.py, agent/builder.py
  - building_plans/ (Residenz PDF, Rathaus JPEG, Urban Colab photos, Projektsteckbrief PDF — looked at 2026-10-25)
related: [../plans/2026-10-25-plan-import.md, 2026-10-24-builder-edit-mode-design.md, ../../architecture/ai-agents.md, ../../kit/data-format.md, ../../challenge/brief.md]
---

# Builder · Plan import — design

[Docs index](../../README.md) · Follows [Edit mode](2026-10-24-builder-edit-mode-design.md) (Builder project 1).

## Intent

Level 4 of the brief: *create a building from floor plans, by conversation — minutes, not days.* The user uploads
one or more files (PDF, photo, scan) of a building's floor plans. **Without asking anything**, an agent finds the
floor plans in them, builds a `building.json` in the dataset's schema ([data-format.md](../../kit/data-format.md))
and opens it as a draft in the existing Edit mode. There the user corrects it by text or voice with the existing
Builder chat (M2) and saves it; the building then opens in 3D and the Guide routes in it like any other.

Agreed with Utku (2026-10-25):

- **Input:** files only. The user's prompt is **not** used during drafting; it is used **after**, to correct the
  draft (existing Builder chat, unchanged).
- **Must work in the demo:** the Munich Urban Colab photos (all floors) **and** the Residenz PDF (both floors).
- **Must generalise:** an agentic workflow that works on unseen plans, not tuned to these files.
- External libraries for PDF parsing are allowed.
- Viewing / 3D / editing are out of scope (they exist).
- Time: ~12 h (hackathon, 2026-10-25).

### The test inputs (`building_plans/`, looked at 2026-10-25)

| File | What it is | What makes it hard |
|---|---|---|
| `urban_collab/*.jpeg` (11) | phone photos of "Flucht- und Rettungsplan" boards, one per floor (title e.g. "Erdgeschoss"), plus photos of black wayfinding signs with room names, one near-blank photo | perspective, glare, green escape-route fill, legend / symbols / text blocks around the plan, same floor photographed twice, signs are schematic |
| `residenz-münchen-building-plan.pdf` | 2-page tourist brochure: ground floor + upper floor, vector drawing, numbered rooms, colour legend, name list ("74-80 Nibelungen Halls") | no scale bar, hatched / coloured fills, huge complex with courtyards, text columns beside the plan |
| `rathaus_münchen.jpeg` | historic architectural drawing, ground floor, scale bar | thick walls, vaulting patterns drawn inside rooms, handwritten numbers |
| `Projektsteckbrief-…pdf` | 5 pages of project text + one landscape site plan | **contains no floor plan** — the right answer is "no floor plan found" |

## Goals

1. Any mix of PDF / JPEG / PNG files → one building draft with **all floors** that appear, or a clear "no floor
   plan found".
2. Draft contents: `floors` (level, name), `spaces` (polygon, `type`, `room_type`, `name`, `ref`), `openings`
   (doors between rooms, entrances to `outside`), `vertical_connectors` (stairs / lifts across floors). Enough
   that the Guide can route through it.
3. Passes `core/validate.py` without errors (warnings allowed), or the remaining issues are shown in the Edit mode.
4. Metres: a scale is always set, with its source and confidence recorded.
5. The user sees progress while it runs (what was found, which floor is being read) and lands in Edit mode.
6. A measurable score on our own data (eval below), so changes can be compared.

## Non-goals

- Assets (furniture, machines) — `assets: []`.
- Any change to Edit mode, the Builder chat, the 3D view, the Guide.
- Asking the user questions during drafting.
- Combining several buildings in one import (one import = one building).
- Exact cm geometry — route-able and recognisable is the bar.

## Anti-goals (fails even if it "works")

- Anything keyed to these files (file names, pixel coordinates, the word "Erdgeschoss" hard-coded as level 0
  without a general floor-name mapping, etc.).
- Silent junk: a draft that looks complete but invents rooms that are not on the plan, or quietly drops a floor.
  Uncertainty is recorded and shown, never hidden.
- Room shapes drawn freehand by the model from pixel guesses (Blueprint-Bench lesson in the
  [Edit mode design](2026-10-24-builder-edit-mode-design.md#intent): models count rooms well and place them badly).

Scope (Utku, 2026-10-25): everything in this document is built in the ~12 h — no cut list.

## How it works (decided)

Code does geometry; the model does reading and judgement. Every model output is checked by code.

### The Creator agent (my recommendation, 2026-10-25)

The work is done by one named agent, **Creator** (`agent/creator.py`), next to the existing **Guide** (answers,
routes) and **Builder** (edits a draft). Story: *Creator draws the building from plans, Builder fixes it with you,
Guide walks you through it.* There is no separate "PDF agent": a PDF is only an input format, turned into page
images by code in stage 0; after that every input is the same.

Creator is a Claude tool loop whose tools are the stages below (`list_sources`, `find_plans`, `prepare_plan`,
`segment` with method `walls` | `colours`, `label_cells`, `render_overlay`, `coarse_rooms`, `set_scale`,
`stack_floors`, `assemble`, `validate`). Code enforces the skeleton — `assemble` refuses a floor that was never
labelled, the job cannot finish without `validate` — while the agent decides the parts that differ per input:
which pages to use, when to switch to the colour path or coarse geometry, when to re-label after looking at the
overlay, which scale evidence to trust. Its reasoning lines are the progress messages the user sees. After the
hand-off, the draft's chat is the Builder's, unchanged.

### Stage 0 — Ingest (code)

- PDF → one image per page at ~200 dpi, plus each embedded raster image, plus the page's text with positions.
- Images → as-is (EXIF orientation applied).
- Each becomes a **source page** with an id, shown to later stages as a downscaled image.

### Stage 1 — Find the plans (model, one call over thumbnails)

Claude sees all source pages (thumbnails, labelled) and returns, per page: is there a floor plan; for each plan on
it: the floor name as written ("Erdgeschoss", "Upper floor", "1. OG"), the **level** it maps to (general rule in
the prompt: EG/ground/Parterre = 0, n. OG / Floor n = n, UG/basement = −1 …), a bounding box of the plan drawing
(excluding legend, text, title), whether it is a photo needing rectification, and which pages are duplicates of the
same floor (keep the sharpest). Pages with a legend / room-name list are noted as **label sources** for that floor
(Residenz's name column, Urban Colab signs). No plan anywhere → stop with that message.

### Stage 2 — Clean the plan image (code, model only as fallback)

- Photo: find the sheet's quadrilateral (OpenCV contour) and warp it flat; if that fails, ask the model for the four
  corners. Then crop to the plan box from stage 1.
- Make a **wall mask**: dark pixels (low value, low saturation) so coloured fills (green escape routes, Residenz
  colours) are not walls; close small gaps; remove text blobs and small symbols (connected components below a
  size).

### Stage 3 — Rooms as cells (code)

- The free (non-wall) area is split into **cells** = connected regions, after closing door gaps with a
  door-sized morphological close so each room becomes its own cell. Cells touching the image border / the big
  outside region are "outside".
- Each cell → simplified polygon (shapely, small tolerance), in pixel coordinates.
- Adjacency between cells and where they touch (for doors later).

**Fallback when the cells are bad** (Utku, 2026-10-25): (a) first a second code path — segment by **colour
regions** (fills like Residenz's room colours) instead of dark walls; (b) if that also fails, accept the model's
**coarse geometry** (boxes / corner points per room) for that floor, marked `low_confidence` in the draft's notes.
Which path a floor used is recorded and shown. "Bad" = the Creator's own check (stage 4 review sees cells that
cross obvious walls or a room-count far from the labels it can read).

### Stage 4 — Label the cells (model, agentic per floor)

The model sees the cleaned plan with **numbered cell overlays** (and the original crop, and the floor's label
sources) and returns, per cell: keep / outside / merge-with-cell / split-hint; `type` (room | corridor | stair |
lift | hall | outdoor); `room_type` from the dataset list ([data-format.md](../../kit/data-format.md#room-types));
`name` and `ref` read from the plan (or legend); and which **adjacent cell pairs have a door** and which cells have
an **entrance** to outside. Courtyards are `outdoor` spaces or outside (model's judgement, recorded).

Then the loop: code renders the result (coloured rooms, names, doors) back over the plan and the model reviews it
against the original — fixes allowed are the same structured actions (merge, relabel, add / remove door). Max 2
review rounds per floor. This is the "agentic" part: the model looks at its own output and corrects it, but never
draws coordinates.

### Stage 5 — Scale and stacking (code + model readings)

- **Scale (px → m)**, first that applies: (a) scale bar or written dimension read by the model and measured in code;
  (b) door widths — median door gap in px = 0.9 m; (c) typical room size prior. Recorded in `building.source_ref`
  with method + confidence, shown in Edit mode as a note.
- **Stacking:** one XY frame per building. Floors are aligned to the ground floor by matching outline (mask
  registration, translation + scale + small rotation) with stair / lift cells as anchors; if alignment fails,
  centre floors on each other and record that.
- **Connectors:** stair / lift spaces on consecutive levels whose aligned centroids are close become one
  `vertical_connector` (`stairs` step_free false, `lift` true).

### Stage 6 — Assemble and validate (code)

- Build `building.json` with the dataset's id scheme (`<building_id>-F<level>-S###`, …) and y up.
- Doors: `position` = midpoint of the shared boundary of the two cells, `width_m` from the gap or 0.9 default,
  `step_free: true`. Entrances: on the cell's outside edge.
- `validate()`; code fixes the mechanical ones (snap doors onto the shared wall, tiny overlaps trimmed); for
  `unreachable` rooms the model gets one more turn to add a missing door. What remains goes into the draft as
  issues.

### Stage 7 — Hand-off (backend + small frontend)

- The building is stored like a saved building (`insert_building` + `register` → `user/<slug>`, see
  `backend/drafts.py`) and a draft is created on it (`DraftStore.create(base=user/<slug>)`) → the app opens Edit
  mode on it. Corrections, undo, save then work as today.
- **Backend changes this needs (my call, 2026-10-25):** today a draft is validated against its base, so every
  issue already in the base shows as a warning "(already in the original building)" (`DraftStore.validate`,
  `builder_tools` rejects only new errors) — for an import that would hide its own errors. A draft made by an
  import is marked `imported`; it is validated without a base (its issues stay errors) and the Builder's
  `propose_edit` checks against the issues it had before the edit. Saving keeps the import notes (scale method and
  confidence, alignment fallback) in `source_ref` next to `base`.
- **Not shared before Save (my call):** the import's building is stored as a private base for that draft only
  (not listed in `/buildings`, no slug claimed); it enters the shared catalogue only when the user saves, like any
  edited building. Abandoned imports are just unused drafts.
- New endpoint: `POST /imports/stream` (multipart files) streams NDJSON progress (stage, floor, message) while the
  Creator works and ends with `{draft_id, base}` or an error — one request, no job store, the same pattern as the
  Builder's `/drafts/{id}/chat/stream` (changed from a job id + events endpoint while planning, 2026-10-25).
- Frontend: an "Import from plans" entry on the landing / search screen → file picker (drag & drop) → progress
  view → Edit mode.

### Tools / libraries (decided by me — say if you disagree)

- **PDF:** `pypdfium2` (render pages, Apache/BSD) + `pypdf` (embedded images, text). Not PyMuPDF: it is AGPL and
  this repo is MIT ([D-009](../../../memory-bank/decisions.md#d-009)).
- **Images / geometry:** `opencv-python-headless`, `numpy`, `shapely` (already used).
- **Model:** Claude Opus 5.5 vision (same `BUILDER_MODEL` setting as the Builder); calls cached where possible.
  Expected cost ~$0.2–0.5 per floor (UNVERIFIED until measured).

## Evaluation

- `scripts/eval_import.py`: run the import on a sample of dataset `floor_*_plain.png` renders (they are drawings of
  the matching `building.json`, see [Q-018](../../../memory-bank/open-questions.md#q-018)) and score: room count,
  matched-room IoU after alignment, door connectivity (same room pairs), reachability. A fixed sample of ~10
  buildings mixing procedural / OSM / Swiss / ResPlan.
- Demo inputs: Urban Colab (all floors) and Residenz (both floors) must produce a draft with no validate errors,
  all floors present, readable names; checked by eye and with the Guide routing between two named rooms.
- Rathaus and Projektsteckbrief as generalisation checks (a reasonable draft; "no floor plan found").

Stop-tuning bar (my call): on the eval sample, room count within ±20 % and ≥ 70 % of door-connected room pairs
found, median, with 0 validate errors after assembly — beyond that, time goes to the demo inputs.

Wayfinding signs (my call): used only as **name sources** for their floor (stage 1 label sources), never for
geometry or adjacency.

## Left to the builder

- Exact thresholds (dark-pixel cut-off, gap-closing size, polygon tolerance), tuned on the eval set — not on the
  demo files.
- Prompt wording, image sizes sent to the model, how cell numbers are drawn.
- Job store (in memory is fine for the demo; jobs need not survive a restart).
- Exact progress event shape and the look of the upload / progress screens (follow the app's existing style).
- Whether the per-floor stages run in parallel.
