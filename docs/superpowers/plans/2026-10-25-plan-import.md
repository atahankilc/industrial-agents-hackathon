---
id: plan-import-plan
summary: Implementation plan for Builder project 2 — the Creator agent that turns floor-plan PDFs / photos into a building.json draft and opens it in Edit mode.
sources:
  - docs/superpowers/specs/2026-10-25-plan-import-design.md
  - backend/drafts.py, backend/app.py, agent/builder.py, core/validate.py, frontend/app/src/edit/EditMode.tsx, frontend/app/src/Root.tsx
related: [../specs/2026-10-25-plan-import-design.md, 2026-10-24-builder-edit-mode-m3.md]
---

# Plan import (Creator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload PDFs / images of floor plans → the Creator agent builds a `building.json` draft with all floors → the app opens it in the existing Edit mode, where the Builder chat corrects it.

**Architecture:** Deterministic image/geometry code in `core/plan_import/` (ingest, rectify, wall mask, cells, labels, scale, stacking, assembly). A Claude tool loop `agent/creator.py` drives those stages through tools in `agent/creator_tools.py`; it reads images (tool results carry PNGs) and returns structured labels, never coordinates (except the coarse-box fallback). The result is stored as a private draft base `import/<id>` in `backend/drafts.py`; `POST /imports/stream` streams progress; the frontend opens `EditMode` on that base.

**Tech Stack:** Python 3.12 (uv), numpy, opencv-python-headless, pypdfium2, pypdf, Pillow, shapely, anthropic SDK, FastAPI (+ python-multipart); React/TS (Vite) frontend.

**Spec:** [docs/superpowers/specs/2026-10-25-plan-import-design.md](../specs/2026-10-25-plan-import-design.md)

## Global Constraints

- Never key anything to the demo files (names, pixel positions, floor words); tune thresholds on the dataset eval set (Task 13), never on `building_plans/`.
- No PyMuPDF (AGPL); PDF = `pypdfium2` + `pypdf` ([D-009](../../../memory-bank/decisions.md#d-009)).
- Output schema = [data-format.md](../../kit/data-format.md): ids `<building_id>-F<level>`, `…-F<level>-S###`, `…-F<level>-O####`, `…-V##`; metres, y up; `assets: []`; polygons not closed.
- Door default `width_m: 0.9`, `step_free: true`; stairs connector `step_free: false`, lift `true`.
- The model never draws room geometry except via `coarse_rooms` (recorded `low_confidence`).
- Scale is always set; `building.source_ref["import"]` records per floor: `scale_method`, `m_per_px`, `segmentation` (`walls`|`colours`|`coarse`), `low_confidence`, and stacking `alignment` (`registered`|`centred`).
- Model: `CREATOR_MODEL` (default `claude-opus-5-5`), `CREATOR_EFFORT` (default `medium`); request shape as `Builder.request` in `agent/builder.py`.
- Images sent to the model: long side ≤ 1568 px. Processing images: long side ≤ 2400 px.
- Commits only via `/ship` (worklog `.claude/worklog/PENDING.md`); work on a branch `3-plan-import` off `dev` (check `git status` first — parallel sessions share the checkout).
- After editing docs / memory-bank: `python3 scripts/check_links.py`.

## Review Focus

1. **A file set with no floor plan** (Projektsteckbrief) → the stream ends with `{"type":"no_plan","reason":…}`, no draft is created. Test in Task 10.
2. **Huge phone photos / scans** (4000 px JPEGs, 6.5 MB Rathaus) → downscaled on ingest, EXIF orientation applied; nothing times out. Test in Task 1.
3. **The same floor photographed twice** → `register_plan` refuses a second plan for a level unless `replace: true`. Test in Task 9.
4. **An unsupported or broken file next to good ones** (HEIC, encrypted PDF, zero-byte) → that file is reported in a `warning` event by name, the others are processed. Test in Task 1 + Task 11.
5. **Several floors but no stairs / lift labelled** → `finish` reports the upper floors `unreachable` to the agent (it gets one more turn) and the draft keeps those as errors, not warnings. Test in Task 7 + Task 8.

---

## File Structure

| File | Responsibility |
|---|---|
| `core/plan_import/__init__.py` | package docstring (pointer to the spec) |
| `core/plan_import/model.py` | dataclasses shared by all stages |
| `core/plan_import/ingest.py` | files → `Source`s; contact sheet; grid view |
| `core/plan_import/prepare.py` | photo rectification, crop, wall mask |
| `core/plan_import/cells.py` | segmentation (walls / colours / boxes), adjacency, door candidates, cell render |
| `core/plan_import/labels.py` | apply the model's labels / merges / doors; label render |
| `core/plan_import/scale.py` | m-per-px from bar, doors, prior |
| `core/plan_import/stack.py` | floor alignment, vertical connectors |
| `core/plan_import/assemble.py` | `building.json` assembly, auto-fixes |
| `agent/creator_tools.py` | `ImportSession`, `CREATOR_TOOLS` schemas, `CreatorTools.call` |
| `agent/creator.py` | the Creator tool loop |
| `backend/drafts.py` | import bases (`import/<id>`), validate without base, save keeps import notes |
| `supabase/migrations/20261025180000_builder_imports.sql` | `builder_imports` table |
| `backend/app.py` | `POST /imports/stream` |
| `frontend/app/src/import/ImportScreen.tsx`, `import.css` | upload + progress → `EditMode` |
| `frontend/app/src/api.ts`, `Root.tsx`, `search/BuildingSearch.tsx` | client call, route, entry button |
| `scripts/eval_import.py` | dataset eval (segment-only and full) |
| `scripts/live_creator.py` | run the Creator on a folder from the terminal |
| `tests/plan_fixtures.py` | synthetic plan images for tests |
| `tests/test_plan_import_*.py`, `tests/test_creator*.py`, `tests/test_imports_api.py` | tests |

### Shared types (`core/plan_import/model.py`, Task 1)

```python
Point = tuple[float, float]

@dataclass
class Source:
    id: str            # "s1", "s2", … in upload order
    origin: str        # "plan.pdf p2", "IMG_1.jpeg", "plan.pdf img3"
    image: np.ndarray  # BGR uint8, long side ≤ 2400
    text: str = ""     # PDF page text, "" for images

@dataclass
class Cell:
    id: int                   # 1.. in reading order (top-left first)
    polygon: list[Point]      # px, image coords (y down), not closed
    area_px: float
    outside: bool             # touches the border / is the exterior region

@dataclass
class DoorCandidate:
    cells: tuple[int, int] | tuple[int, str]   # (a, b) or (a, "outside")
    position: Point                            # px
    width_px: float

@dataclass
class Segmentation:
    method: str                                 # "walls" | "colours" | "coarse"
    cells: dict[int, Cell]
    adjacency: dict[tuple[int, int], list[Point]]   # sorted pair → shared boundary points (px)
    doors: list[DoorCandidate]

@dataclass
class CellLabel:
    type: str          # room | corridor | stair | lift | hall | outdoor
    room_type: str     # dataset list
    name: str
    ref: str = ""

@dataclass
class FloorPlan:
    level: int
    name: str
    source_id: str
    image: np.ndarray                 # rectified + cropped, BGR
    seg: Segmentation
    labels: dict[int, CellLabel] = field(default_factory=dict)        # after merges, by surviving cell id
    doors: list[DoorCandidate] = field(default_factory=list)          # accepted doors / entrances
    m_per_px: float | None = None
    scale_method: str | None = None
    transform: np.ndarray | None = None   # 2x3 px → frame metres (set by stack.align)
    alignment: str | None = None
    low_confidence: bool = False
```

---

### Task 1: Dependencies, shared types, ingest

**Files:**
- Modify: `pyproject.toml` (add `numpy`, `opencv-python-headless`, `pypdfium2`, `pypdf`, `pillow`, `python-multipart`), `uv.lock` via `uv add`
- Create: `core/plan_import/__init__.py`, `core/plan_import/model.py` (types above), `core/plan_import/ingest.py`, `tests/plan_fixtures.py`
- Test: `tests/test_plan_import_ingest.py`

**Interfaces:**
- Produces:
  - `load_sources(files: list[tuple[str, bytes]]) -> tuple[list[Source], list[str]]` — sources + warnings (`"<filename>: <why>"`).
  - `contact_sheet(sources: list[Source], per_sheet: int = 9) -> list[bytes]` — PNGs, each tile captioned with `source.id` + `origin`, long side ≤ 1568.
  - `grid_view(image: np.ndarray) -> bytes` — PNG ≤ 1568 with a 10×10 grid labelled 0.0…1.0 on both axes (for normalised bboxes / points).
  - `png(image: np.ndarray, max_side: int = 1568) -> bytes`.
  - `tests/plan_fixtures.py`: `draw_plan(rooms: list[tuple[float,float,float,float]], doors: list[tuple[float,float,str]], px_per_m: float = 20, wall_px: int = 4, margin_m: float = 2) -> np.ndarray` — white image, black walls around each room box (metres), a white gap of 0.9 m at each door `(x, y, "h"|"v")`; and `TWO_ROOMS_AND_CORRIDOR` = rooms `(0,4,5,8)`, `(5,4,10,8)`, corridor `(0,0,10,4)`, doors at `(2.5,4,"h")`, `(7.5,4,"h")`, entrance `(0,2,"v")`.

- [ ] **Step 1: Add deps** — `uv add numpy opencv-python-headless pypdfium2 pypdf pillow python-multipart`; `uv run python -c "import cv2, pypdfium2, pypdf, PIL"` exits 0.
- [ ] **Step 2: Write failing tests**

```python
def test_pdf_pages_become_sources(tmp_path):          # build a 2-page PDF with pypdfium2 or reportlab-free: render two fixture PNGs into a PDF via Pillow (Image.save(..., save_all=True))
    sources, warnings = load_sources([("plan.pdf", pdf_bytes)])
    assert [s.origin for s in sources][:2] == ["plan.pdf p1", "plan.pdf p2"] and warnings == []

def test_big_photo_is_downscaled_and_exif_rotated():   # 4000x3000 JPEG with EXIF orientation 6
    (s,), _ = load_sources([("IMG.jpeg", jpeg)])
    assert max(s.image.shape[:2]) == 2400 and s.image.shape[0] > s.image.shape[1]

def test_bad_files_are_warnings_not_errors():
    sources, warnings = load_sources([("a.heic", b"xx"), ("empty.pdf", b""), ("ok.png", png_bytes)])
    assert len(sources) == 1 and any(w.startswith("a.heic:") for w in warnings) and any(w.startswith("empty.pdf:") for w in warnings)

def test_contact_sheet_and_grid_are_small_pngs():
    assert all(max(Image.open(BytesIO(p)).size) <= 1568 for p in contact_sheet(sources))
    assert Image.open(BytesIO(grid_view(np.zeros((3000, 1000, 3), np.uint8)))).size[1] <= 1568
```

- [ ] **Step 3: Run** `uv run pytest tests/test_plan_import_ingest.py -q` → FAIL (import error).
- [ ] **Step 4: Implement** `ingest.py`: PDF pages via `pypdfium2.PdfDocument(...).render(scale=200/72)` + `page.get_textpage().get_text_range()`; embedded images via `pypdf.PdfReader(...).pages[i].images`, kept only if long side ≥ 800 px; images via Pillow + `ImageOps.exif_transpose`; any exception per file → warning, continue.
- [ ] **Step 5: Run** → PASS. **Step 6:** worklog + `/ship`.

### Task 2: Prepare — rectify, crop, wall mask

**Files:** Create `core/plan_import/prepare.py`; Test `tests/test_plan_import_prepare.py`

**Interfaces:**
- Consumes: `Source.image`, `draw_plan`.
- Produces:
  - `rectify(image: np.ndarray, corners: list[Point] | None = None) -> tuple[np.ndarray, np.ndarray | None]` — warped sheet + 3×3 homography (None = not warped). `corners` normalised (0–1) TL, TR, BR, BL from the model; else the largest 4-point contour covering ≥ 30 % of the image.
  - `crop(image: np.ndarray, bbox: tuple[float,float,float,float], homography: np.ndarray | None) -> np.ndarray` — bbox normalised in the *source* image; mapped through the homography; 2 % margin.
  - `wall_mask(image: np.ndarray, dark: int = 110, max_saturation: int = 80, min_blob_px: int = 30) -> np.ndarray` — uint8 0/255, walls = dark AND low saturation (HSV), small blobs (text, symbols) removed.

- [ ] **Step 1: Failing tests**

```python
def test_rectify_flattens_a_skewed_sheet():
    flat = draw_plan(*TWO_ROOMS_AND_CORRIDOR); skewed = warp_with_known_quad(flat)   # helper in the test
    out, H = rectify(skewed)
    assert H is not None and abs(out.shape[1] / out.shape[0] - flat.shape[1] / flat.shape[0]) < 0.05

def test_rectify_leaves_a_scan_alone():
    out, H = rectify(draw_plan(*TWO_ROOMS_AND_CORRIDOR)); assert H is None

def test_wall_mask_ignores_green_fill_and_text():
    img = draw_plan(*TWO_ROOMS_AND_CORRIDOR); paint_corridor_green(img); put_text(img, "WC", in_room=0)
    mask = wall_mask(img)
    assert mask[corridor_centre] == 0 and mask[text_pixel] == 0 and mask[wall_pixel] == 255
```

- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** run → PASS. **Step 5:** `/ship`.

### Task 3: Cells from walls, adjacency, door candidates, render

**Files:** Create `core/plan_import/cells.py`; Test `tests/test_plan_import_cells.py`

**Interfaces:**
- Consumes: `wall_mask`, `model.Segmentation`, `Cell`, `DoorCandidate`.
- Produces:
  - `segment_walls(image: np.ndarray, gap_px: int | None = None, mask: np.ndarray | None = None) -> Segmentation` — `gap_px` default = 3 % of the image's short side.
  - `render_cells(image: np.ndarray, seg: Segmentation) -> bytes` — PNG: each non-outside cell tinted with its number at its representative point; door candidates as small red dots labelled `d1…`.
  - `simplify(polygon, tolerance_px: float) -> list[Point]` (shapely, tolerance 1.5 px default).

Algorithm (the part the signature does not determine):
```
closed = morph_close(mask, square(gap_px))          # door gaps become wall
free   = ~closed; label connected components (8-conn)
cells  = components with area ≥ (gap_px*2)^2; component touching the border → outside=True (merged into one outside cell)
polygon = largest outer contour → simplify
adjacency: dilate each cell by gap_px; pairs whose dilations overlap → shared boundary = overlap pixels' skeleton points
door candidates = connected components of (closed & ~mask) (pixels only the close added) whose dilation touches exactly two cells (or one cell + outside); position = centroid, width_px = longest side of its min-area rect
```

- [ ] **Step 1: Failing tests**

```python
def test_two_rooms_and_corridor():
    seg = segment_walls(draw_plan(*TWO_ROOMS_AND_CORRIDOR))
    inner = [c for c in seg.cells.values() if not c.outside]
    assert len(inner) == 3
    assert sorted(round(c.area_px / 400) for c in inner) == [20, 20, 40]     # m² at 20 px/m, ±1 tolerated via round
    assert len([d for d in seg.doors if "outside" not in d.cells]) == 2
    assert len([d for d in seg.doors if "outside" in d.cells]) == 1
    assert all(18 * 0.9 * 0.8 < d.width_px < 18 * 1.25 for d in seg.doors)  # ≈ 0.9 m at 20 px/m

def test_render_cells_is_png(): assert render_cells(img, seg)[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5:** `/ship`.

### Task 4: Fallback segmentations — colours and coarse boxes

**Files:** Modify `core/plan_import/cells.py`; Test `tests/test_plan_import_cells.py`

**Interfaces:**
- Produces:
  - `segment_colours(image: np.ndarray, k: int = 8, min_area_frac: float = 0.002) -> Segmentation` — k-means on Lab colour (white / near-white background cluster = free space excluded), each connected region of a non-background cluster = cell; hatching tolerated by a median blur (5 px) before clustering; adjacency + door candidates as in Task 3 (door candidates may be empty).
  - `cells_from_boxes(shape: tuple[int, int], boxes: list[tuple[float,float,float,float]]) -> Segmentation` — normalised boxes → rectangular cells (method `"coarse"`), clipped where they overlap (later box loses), adjacency where boxes touch after growing 3 % of the long side (changed from 1 % after the first live run).

- [ ] **Step 1: Failing tests**

```python
def test_colour_regions_become_cells():
    img = filled_rooms_no_walls()          # three touching rectangles in three pastel colours + diagonal hatching on one
    seg = segment_colours(img)
    assert len([c for c in seg.cells.values() if not c.outside]) == 3 and seg.method == "colours"
    assert len(seg.adjacency) >= 2

def test_boxes_become_cells():
    seg = cells_from_boxes((400, 800), [(0, 0, .5, 1), (.5, 0, 1, 1)])
    assert seg.method == "coarse" and len(seg.cells) == 2 and (1, 2) in seg.adjacency
```

- [ ] **Step 2–5:** FAIL → implement → PASS → `/ship`.

### Task 5: Labels — apply and render

**Files:** Create `core/plan_import/labels.py`; Test `tests/test_plan_import_labels.py`

**Interfaces:**
- Consumes: `FloorPlan`, `Segmentation`.
- Produces:
  - `apply_labels(floor: FloorPlan, cells: list[dict], doors: list[list] | None, entrances: list[int] | None) -> list[str]` — mutates `floor`, returns problems (strings). Each cell item: `{"cell": int, "action": "room"|"outside"|"merge", "into": int?, "type", "room_type", "name", "ref"?}`. Merge = shapely union of polygons (cell `into` survives; adjacency/doors re-keyed). `doors=None` → accept all candidate doors between kept cells; a list → exactly those pairs `[a, b]` (position = candidate on that pair if any, else midpoint of the shared boundary; pair not adjacent → problem). `entrances`: cells with a door to outside (candidate if any, else the midpoint of the cell's longest outside-facing boundary).
  - Problems include: `"cell 7 has no label"`, `"cells 3 and 9 are not adjacent"`, `"unknown room_type 'foyer'"` (closed list from data-format.md), `"no entrance on this floor"` (level 0 only).
  - `render_labels(floor: FloorPlan) -> bytes` — PNG: rooms tinted by `type`, `name` written inside, doors as green bars, entrances as arrows.
  - Test helpers added to `tests/plan_fixtures.py`: `floor_from(fixture, level: int = 0) -> FloorPlan` (segmented, unlabelled) and `labelled_floor(level: int = 0, stair: bool = False) -> FloorPlan` (labelled with `FIXTURE_LABELS`, entrance on the corridor on level 0; `stair=True` adds a 3×3 m stair room at the corridor's east end, `type` `stair`).

- [ ] **Step 1: Failing tests**

```python
def test_merge_and_label():
    floor = floor_from(TWO_ROOMS_AND_CORRIDOR)
    problems = apply_labels(floor, [{"cell": 1, "action": "room", "type": "room", "room_type": "office", "name": "Office 1"},
                                    {"cell": 2, "action": "merge", "into": 1},
                                    {"cell": 3, "action": "room", "type": "corridor", "room_type": "corridor", "name": "Corridor"}],
                            doors=None, entrances=[3])
    assert problems == [] and len(floor.labels) == 2 and floor.seg.cells[1].area_px > 30 * 400

def test_unknown_room_type_and_missing_label_are_problems():
    problems = apply_labels(floor, [{"cell": 1, "action": "room", "type": "room", "room_type": "foyer", "name": "X"}], None, None)
    assert "unknown room_type 'foyer'" in " ".join(problems) and any("has no label" in p for p in problems)
```

- [ ] **Step 2–5:** FAIL → implement → PASS → `/ship`.

### Task 6: Scale, stacking, connectors

**Files:** Create `core/plan_import/scale.py`, `core/plan_import/stack.py`; Test `tests/test_plan_import_stack.py`

**Interfaces:**
- Produces:
  - `scale_from_bar(floor: FloorPlan, p0: Point, p1: Point, length_m: float) -> float` (points normalised in the floor image) → m/px.
  - `scale_from_doors(floor: FloorPlan) -> float | None` — `0.9 / median(width_px)` of accepted doors, None if < 2 doors.
  - `scale_prior(floor: FloorPlan) -> float` — median kept-room area ≈ 20 m².
  - `ensure_scales(floors: list[FloorPlan]) -> None` — fills `m_per_px` / `scale_method` where unset: doors, else the scale of an already-scaled floor whose image size is within 10 % (same sheet format), else prior.
  - `align(floors: list[FloorPlan]) -> None` — sets `transform` + `alignment`. Lowest level is the frame (origin at its footprint's bottom-left, y up). Others: filled footprint masks at common 0.1 m/px, `cv2.findTransformECC` (`MOTION_EUCLIDEAN`, 200 iters), accepted if correlation ≥ 0.6 → `"registered"`, else centroids matched → `"centred"`.
  - `connectors(floors: list[FloorPlan], max_dist_m: float = 3.0) -> list[tuple[str, list[tuple[int, int]]]]` — `("stairs"|"lift", [(level, cell_id), …])` chaining consecutive levels by nearest centroid of same `type` within `max_dist_m` after `transform`.

- [ ] **Step 1: Failing tests**

```python
def test_scale_from_doors_on_fixture():               # fixture at 20 px/m → 0.05 m/px
    assert abs(scale_from_doors(labelled_floor()) - 0.05) < 0.008

def test_two_shifted_floors_register_and_connect():
    f0, f1 = floor_with_stair(offset_px=(0, 0), level=0), floor_with_stair(offset_px=(40, -25), level=1)
    ensure_scales([f0, f1]); align([f0, f1])
    assert f1.alignment == "registered"
    assert connectors([f0, f1]) == [("stairs", [(0, f0_stair_id), (1, f1_stair_id)])]

def test_unalignable_floor_is_centred():
    align([f0, blank_noise_floor(level=1)]); assert floors[1].alignment == "centred"
```

- [ ] **Step 2–5:** FAIL → implement → PASS → `/ship`.

### Task 7: Assemble + auto-fix + validate

**Files:** Create `core/plan_import/assemble.py`; Test `tests/test_plan_import_assemble.py`

**Interfaces:**
- Consumes: `FloorPlan`s after Task 6, `core.validate.validate`, `core.edits.wall_target` (door snapping).
- Produces:
  - `assemble(building_id: str, name: str, floors: list[FloorPlan], origins: list[str]) -> dict` — full `building.json`: `building` = `{"id", "name", "source": "imported", "source_ref": {"import": {"files": origins, "floors": {level: {"scale_method", "m_per_px", "segmentation", "low_confidence", "alignment"}}}}, "license": "user-provided", "attribution": "", "split": "user", "units": "m"}`; floor names as read, `elevation_m = 3.0 * level`, `height_m = 3.0`; calls `ensure_scales` / `align` first if any floor lacks `m_per_px` / `transform`; `floors` keys in `source_ref` are `str(level)`; spaces from kept labelled cells (polygon through `transform`, rounded 2 dp, counter-clockwise); openings `kind` `door` / `entrance`; connectors from `stack.connectors`; `assets: []`.
  - `autofix(building: dict) -> dict` — doors snapped onto the wall the two spaces share (`wall_target`); overlaps ≤ 0.5 m² trimmed from the smaller space; spaces < 0.5 m² dropped with their doors.
  - `check(building: dict) -> list[dict]` = `validate(building)` (no base).

- [ ] **Step 1: Failing tests**

```python
def test_fixture_assembles_without_errors():
    b = autofix(assemble("imp-test", "Test", [labelled_floor()], ["fixture.png"]))
    assert [i for i in check(b) if i["severity"] == "error"] == []
    assert {s["type"] for s in b["spaces"]} == {"room", "corridor"} and len(b["openings"]) == 3
    assert b["spaces"][0]["id"].startswith("imp-test-F0-S") and b["assets"] == []
    assert b["building"]["source_ref"]["import"]["floors"]["0"]["scale_method"] == "doors"

def test_two_floors_without_stairs_report_unreachable():          # Review Focus 5
    b = autofix(assemble("imp-test", "T", [labelled_floor(0), labelled_floor(1)], []))
    assert any(i["code"] == "unreachable" and i["severity"] == "error" for i in check(b))
```

- [ ] **Step 2–5:** FAIL → implement → PASS → `/ship`.

### Task 8: Draft store — private import bases

**Files:**
- Modify: `backend/drafts.py` (protocol + three backends + `DraftStore.known/base_building/issues/save` + new `create_import`)
- Create: `supabase/migrations/20261025180000_builder_imports.sql` — `create table if not exists public.builder_imports (id text primary key, building jsonb not null, created_at timestamptz not null default now()); alter table public.builder_imports enable row level security;`
- Test: `tests/test_drafts.py` (add), `tests/test_drafts_postgres.py` if the live-DB tests live there (follow the existing skip-if-no-DB pattern)

**Interfaces:**
- Produces:
  - `IMPORT_PREFIX = "import/"`.
  - `DraftBackend.insert_import(import_id: str, building: dict) -> None`, `DraftBackend.load_import(import_id: str) -> dict | None` — File: `.imports/<id>.json`; Memory: dict; Postgres: `builder_imports`.
  - `DraftStore.create_import(building: dict) -> Draft` — new uuid4 hex `import_id`, stores the building, creates a draft with `base = "import/<import_id>"`, `name = building["building"]["name"]`.
  - `DraftStore.known(base)` true for a stored import; `base_building` loads it (cached); **not** added to `catalogue` (so `/buildings` does not list it).
  - `DraftStore.issues(draft)`: for an import base → `validate(building)` without base (errors stay errors).
  - `agent/builder_tools.py` needs no change: `propose_edit` already compares against the draft as it is (`validate(after, base=current)`), so an import's existing errors don't block a proposal and new ones are still caught.
  - `DraftStore.save`: for an import base, `source_ref = {"base": draft.base, "import": <base's source_ref["import"]>}` and `source = "imported"`.

- [ ] **Step 1: Failing tests**

```python
def test_import_draft_is_private_and_keeps_its_errors(store):
    draft = store.create_import(broken_two_floor_building())        # one unreachable floor
    assert draft.base.startswith("import/") and draft.base not in store.catalogue
    assert any(i["severity"] == "error" and i["code"] == "unreachable" for i in store.issues(draft))

def test_saving_an_import_keeps_its_notes(store):
    draft = store.create_import(fixture_building()); building_id = store.save(draft, "Urban Lab")
    saved = store.base_building(building_id)["building"]
    assert saved["source"] == "imported" and saved["source_ref"]["import"]["floors"]["0"]["scale_method"] == "doors"

def test_memory_backend_shares_imports_across_stores():           # serverless contract
    a, b = two_stores_on_one_memory_backend(); d = a.create_import(fixture_building())
    assert b.get(d.id) is not None and b.issues(b.get(d.id)) == a.issues(d)
```

- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `uv run pytest tests/test_drafts.py -q` PASS and the whole suite `uv run pytest -q` still green. **Step 5:** apply the migration to Supabase only when Utku says so (note in worklog). **Step 6:** `/ship`.

### Task 9: Creator tools

**Files:** Create `agent/creator_tools.py`; Test `tests/test_creator_tools.py`

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces:
  - `@dataclass ImportSession`: `sources: list[Source]`, `warnings: list[str]`, `floors: dict[int, FloorPlan]`, `label_sources: dict[int, list[str]]`, `finished: dict | None` (`{"building": dict, "issues": list}`), `no_plan: str | None`, `finish_attempts: int = 0`.
  - `CREATOR_TOOLS: list[dict]` (Anthropic tool schemas) and `CreatorTools(session).call(name: str, args: dict) -> list[dict]` returning tool_result **content blocks** (`{"type":"text","text": json}` and optionally `{"type":"image","source":{"type":"base64","media_type":"image/png","data":…}}`); errors → a single text block `{"error": …}` and the loop marks `is_error`.

| tool | args | does | returns |
|---|---|---|---|
| `list_sources` | — | | contact sheets (images) + per source `{id, origin, size, text[:600]}` + warnings |
| `view_source` | `source_id` | | `grid_view` image + full text[:4000] |
| `register_plan` | `source_id, level, floor_name, bbox[4], photo: bool, corners?[4][2], label_sources?[ids], replace?` | rectify (if photo) → crop → `segment_walls`; refuses an existing level unless `replace` | `render_cells` image + `{cells: n, outside, door_candidates: n}` |
| `segment` | `level, method: walls\|colours, gap_px?, dark?` | re-segment (labels cleared) | `render_cells` image + counts |
| `coarse_rooms` | `level, boxes: [{box[4]}]` | `cells_from_boxes`, `low_confidence = True` | `render_cells` image |
| `label_cells` | `level, cells[], doors?, entrances?` | `apply_labels` | `render_labels` image + problems |
| `set_scale` | `level, method: bar\|doors\|prior, p0?, p1?, length_m?` | scale fns | `{m_per_px, method}` |
| `stack_floors` | — | `ensure_scales`, `align` | per level `{alignment, m_per_px}` + one image: all floors' outlines overlaid in the frame |
| `finish` | `name` | requires ≥ 1 floor, every floor labelled (no unlabelled kept cell); `assemble` + `autofix` + `check`; on errors and `finish_attempts == 0` → returns them and sets attempts = 1 (agent may fix and call again); else stores `finished` | `{issues, spaces, openings, connectors}` |
| `no_plan` | `reason` | only if no floor registered | sets `no_plan` |

- [ ] **Step 1: Failing tests** (fixture PNG uploaded as a source)

```python
def test_register_label_finish_happy_path():
    tools = CreatorTools(session_from([("plan.png", fixture_png)]))
    out = tools.call("register_plan", {"source_id": "s1", "level": 0, "floor_name": "Ground floor", "bbox": [0, 0, 1, 1], "photo": False})
    assert any(b["type"] == "image" for b in out)
    tools.call("label_cells", {"level": 0, "cells": FIXTURE_LABELS, "entrances": [3]})
    result = json.loads(tools.call("finish", {"name": "Test"})[0]["text"])
    assert result["issues"] == [] and tools.session.finished is not None

def test_second_plan_for_same_level_is_refused():                 # Review Focus 3
    tools.call("register_plan", {... "level": 0 ...})
    assert "error" in json.loads(tools.call("register_plan", {... "level": 0 ...})[0]["text"])

def test_finish_refuses_unlabelled_floor(): ...
def test_no_plan_refused_after_a_floor_is_registered(): ...
def test_finish_gives_one_repair_chance_then_accepts():           # two floors, no stairs
    first = finish(); assert first["issues"] and tools.session.finished is None
    second = finish(); assert tools.session.finished is not None
```

- [ ] **Step 2–5:** FAIL → implement → PASS → `/ship`.

### Task 10: Creator agent loop

**Files:** Create `agent/creator.py`; Test `tests/test_creator.py`

**Interfaces:**
- Consumes: `CreatorTools`, `ImportSession`; `agent.guide.FALLBACK_BETA`, `MAX_TOKENS`, `Usage`, `llm_mode`.
- Produces:
  - `class Creator(session: ImportSession, client: object | None = None, model: str | None = None, effort: str | None = None)` with `on_step: Callable[[dict], None] | None` and `run() -> CreatorResult`.
  - `@dataclass CreatorResult`: `status: "done" | "no_plan" | "failed"`, `building: dict | None`, `issues: list[dict]`, `reason: str`, `usage: Usage`.
  - Steps emitted: `{"kind": "say", "text"}` for each model text block (the progress lines the user reads), `{"kind": "tool", "name", "level"?}`, `{"kind": "tool_done", "name", "ok"}`.
  - Constants: `DEFAULT_MODEL = "claude-opus-5-5"` (`CREATOR_MODEL`), `DEFAULT_EFFORT = "medium"` (`CREATOR_EFFORT`), `MAX_TOOL_ROUNDS = 60`, `MAX_IMAGES = 40`, `KEEP_IMAGES = 8` (changed 2026-10-25 after measuring cost: images stay so the cached prefix keeps growing; only past 40 images are all but the newest 8 replaced by a text note, in one go — dropping one per turn rewrote the whole cache every turn).
  - `INSTRUCTIONS` system prompt covers: the stage order; floor-name → level rule (EG / Erdgeschoss / ground / Parterre / rez-de-chaussée = 0; "n. OG" / "n. Obergeschoss" / "Floor n" / "Upper floor" (single) = n or 1; UG / Untergeschoss / basement = −1); one plan per level, keep the sharpest duplicate; legends and room lists are name sources; check `render_cells` — if cells cross obvious walls or the room count is far from the labels you can read, try `segment` `colours`, then `coarse_rooms`; label every kept cell; look at `render_labels` and fix (≤ 2 review rounds per floor); set scale from a scale bar or written dimension when one is visible; label stairs/lifts on every floor; one short sentence before each tool call saying what you are doing (shown to the user); never ask the user; finish or `no_plan`.
  - Without an API key (`llm_mode() != "anthropic"`) `run()` returns `status="failed", reason="the Creator needs Claude (set ANTHROPIC_API_KEY)"`.

- [ ] **Step 1: Failing tests** with a scripted fake client (list of canned responses, like the Builder tests)

```python
def test_scripted_import_finishes():            # fake: say → register_plan → label_cells → finish → end_turn
    result = Creator(session, client=FakeClient(SCRIPT)).run()
    assert result.status == "done" and result.building["spaces"] and steps[0] == {"kind": "say", "text": "Looking at the files."}

def test_no_plan_ends_without_building():       # Review Focus 1
    result = Creator(text_only_session, client=FakeClient([tool("list_sources"), tool("no_plan", reason="only text")])).run()
    assert result.status == "no_plan" and result.building is None

def test_old_images_are_dropped():              # 8 image tool results → only last 6 still images in the 9th request
def test_stops_after_max_rounds():              # endless tool calls → status "failed"
```

- [ ] **Step 2–5:** FAIL → implement → PASS → `/ship`.
- [ ] **Step 6: Live smoke** — `scripts/live_creator.py <folder|files…> [--out building.json]` prints steps and usage; run on one dataset `floor_0_plain.png`; record time + cost in the worklog.

### Task 11: Backend `POST /imports/stream`

**Files:** Modify `backend/app.py`; Test `tests/test_imports_api.py`

**Interfaces:**
- Consumes: `load_sources`, `ImportSession`, `Creator`, `DraftStore.create_import`.
- Produces: `POST /imports/stream` (multipart `files: list[UploadFile]`, ≤ 20 files, ≤ 25 MB each → 413) → NDJSON lines: `{"type":"warning","detail"}` (per bad file), `{"type":"step", …Creator step}`, then exactly one of `{"type":"done","draft_id","base","issues","notes"}` / `{"type":"no_plan","reason"}` / `{"type":"error","detail"}`. Thread + queue exactly like `draft_chat_stream`. A `Creator` factory `make_creator(session) -> Creator` at module level so tests can patch it.

- [ ] **Step 1: Failing tests** (TestClient, patched `make_creator` returning a fake that yields a fixture building)

```python
def test_import_stream_creates_private_draft(client):
    lines = post_files(client, [("plan.png", fixture_png)])
    done = lines[-1]; assert done["type"] == "done" and done["base"].startswith("import/")
    assert client.get(f"/drafts/{done['draft_id']}").status_code == 200
    assert done["base"] not in [b["id"] for b in client.get("/buildings").json()]

def test_bad_file_is_a_warning(client):          # Review Focus 4
    lines = post_files(client, [("x.heic", b"zz"), ("plan.png", fixture_png)])
    assert lines[0] == {"type": "warning", "detail": lines[0]["detail"]} and lines[0]["detail"].startswith("x.heic:")

def test_no_plan_line(client): ...
def test_too_many_files_is_413(client): ...
```

- [ ] **Step 2–5:** FAIL → implement → PASS (`uv run pytest -q` all green) → `/ship`.

### Task 12: Frontend — import screen

**Files:**
- Create: `frontend/app/src/import/ImportScreen.tsx`, `frontend/app/src/import/import.css`
- Modify: `frontend/app/src/api.ts` (`importPlans(files: File[], onLine: (line: ImportLine) => void): Promise<void>` — NDJSON reader like the Builder stream), `frontend/app/src/Root.tsx` (route `'import'`), `frontend/app/src/search/BuildingSearch.tsx` (prop `onImport: () => void`, button "Create from floor plans")

**Interfaces:**
- `ImportScreen({ palette, onSaved, onExit })`: states `pick` (drop zone + file list, accepts `.pdf,image/*`) → `working` (file thumbnails, the Creator's `say` lines as a growing list, current tool as a subtle status, warnings in amber) → on `done`: `localStorage.setItem('draft:' + base, draft_id)` then render `<EditMode base={base} palette onSaved onExit />` (EditMode resumes that draft via its existing `openDraft`; no EditMode change) · on `no_plan`: message + "Try other files" · on `error`: message + retry.
- Style: follow the existing clay palette / cards of the building screen and Edit mode (`edit/edit.css`, `building/hud.css`).

- [ ] **Step 1:** implement; `cd frontend/app && npx tsc --noEmit` → 0 errors.
- [ ] **Step 2:** run backend (real key) + Vite (ports per [commands.md](../../guides/commands.md#frontend-app)); in headless Chrome upload one dataset `floor_0_plain.png`: progress lines appear, Edit mode opens with rooms, Save → building opens. Screenshot into the worklog.
- [ ] **Step 3:** `/ship`.

### Task 13: Eval on the dataset + threshold tuning

**Files:** Create `scripts/eval_import.py`; doc row in `docs/guides/commands.md`

**Interfaces:**
- `uv run python scripts/eval_import.py --segment-only [--n 30]` — no model: for a fixed, seeded sample of `floor_*_plain.png` across sources (procedural / OSM / Swiss / ResPlan), `segment_walls` vs the floor's `building.json` spaces: room-count ratio, per-room best IoU after scaling with the known px/m of the render and aligning bboxes. Prints a table + medians.
- `uv run --env-file .env python scripts/eval_import.py --full --n 10` — runs the Creator; scores room count, matched IoU, door-connected pairs found / true pairs (pairs matched through IoU ≥ 0.5), reachability, `check` errors; prints cost.
- Stop-tuning bar (spec): median room count within ±20 %, ≥ 70 % connected pairs found, 0 validate errors after assembly.

- [ ] **Step 1:** implement `--segment-only`; tune `gap_px`, `dark`, `min_blob_px` defaults in code until the segment-only medians stop improving; record before/after in the worklog.
- [ ] **Step 2:** `--full --n 10`; fix prompt/tool issues that are general (never file-specific); record the numbers.
- [ ] **Step 3:** `/ship`.

### Task 14: Demo inputs, generalisation checks, docs

**Files:** Modify `docs/architecture/ai-agents.md` (Creator row + section), `docs/guides/commands.md` (live_creator, eval_import, import endpoint), `memory-bank/project-state.md`, `memory-bank/log.md`, `memory-bank/open-questions.md` (Q-018 note), spec status → `built`.

- [ ] **Step 1:** `scripts/live_creator.py building_plans/urban_collab` → every floor on the boards present, names readable, 0 `check` errors (or remaining issues listed); Guide route between two named rooms on different floors works (`uv run python -c` with `core.navigation.find_route` on the saved building).
- [ ] **Step 2:** same for `building_plans/residenz-münchen-building-plan.pdf` (both floors).
- [ ] **Step 3:** `building_plans/rathaus_münchen.jpeg` → a reasonable draft; `building_plans/Projektsteckbrief-…pdf` → `no_plan`.
- [ ] **Step 4:** any fix found here must be general (a rule, a threshold, a prompt line that would help an unseen plan) — write in the worklog why it generalises.
- [ ] **Step 5:** end-to-end once in the app (upload Urban Colab photos → Edit mode → one Builder chat correction → Save → 3D + Guide route).
- [ ] **Step 6:** docs + memory bank; `python3 scripts/check_links.py`; `/ship`.
