---
id: plan-builder-edit-mode-m1
summary: Task-by-task plan for milestone 1 of the Builder Edit mode — edit ops, validator, drafts store + API, 2D plan editor with 3D inset, save → Guide (local store).
sources: [../specs/2026-10-24-builder-edit-mode-design.md, core/solvers/walls.py, core/solvers/reachability.py, backend/app.py, backend/sessions.py, frontend/app/src/App.tsx]
related: [../specs/2026-10-24-builder-edit-mode-design.md, ../../architecture/ai-agents.md]
---

# Builder Edit Mode — Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drag-edit a copy of a building on a 2D plan (with a live 3D preview), undo, save it as `user/<slug>`, and
have the Guide route in the saved building — local store only.

**Architecture:** A draft is *base building + list of steps*, each step a list of JSON ops (`core/edits.py`,
pure functions on building dicts). `core/validate.py` returns issues for any building dict. `backend/drafts.py`
stores drafts and saved buildings under `data/user/` and the FastAPI app exposes `/drafts…`. The frontend gets a
View/Edit switch, an SVG `PlanEditor` and the existing `Scene` as a 3D inset.

**Tech Stack:** Python ≥ 3.12 (uv), shapely, FastAPI + TestClient, pytest; Vite + React 19 + r3f, TypeScript.

**Spec:** [docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md](../specs/2026-10-24-builder-edit-mode-design.md)
— milestone 1 of its "Delivery order". Milestones 2 (Builder agent) and 3 (Supabase) get their own plans.

## Global Constraints

- Never write into `data/train|dev|test/`. Saved/draft data lives only in `data/user/` (gitignored).
- Schema stays `building.json` (top-level `building, floors, spaces, openings, vertical_connectors, assets`;
  polygons not closed; metres).
- New ids: spaces `<floor_id>-S-new<n>`, openings `<floor_id>-O-new<n>`, assets `<building_id>-A-new<n>`
  (n = 1 + highest existing n for that prefix).
- Saved building: `building.source = "edited"`, `building.source_ref = {"base": <base catalogue id>}`, new
  `building.id` = slug, `building.name` = user's name; licence/attribution copied from the base.
- New elements `"synthetic": false`; new assets `"source": "edited"`.
- Coordinates written by ops are rounded to 3 decimals.
- `core/building_map.py`, solvers and the benchmark path are not modified; `uv run pytest` stays green.
- Commits only via the `/ship` skill (D-008); keep `.claude/worklog/PENDING.md` current.
- After any doc / memory-bank edit: `python3 scripts/check_links.py`.

## Review Focus

1. A drag that drops a vertex onto/through a neighbour so the neighbour would vanish → op refused with a clear
   error, draft unchanged (test in Task 2).
2. Dropping a door far from any wall its two spaces share → snapped onto the shared wall; if they share none →
   refused (test in Task 1).
3. Undo on a draft with no steps → 409-style error, not a crash (test in Task 4).
4. Saving twice with the same name → second gets `-2`, both load (test in Task 4).
5. Unknown base id / unknown draft id → 422 / 404, never a path join from user input (test in Task 4).

---

### Task 1: Edit operations (`core/edits.py`)

**Files:**
- Create: `core/edits.py`
- Test: `tests/test_edits.py`

**Interfaces:**
- Produces:
  - `class EditError(ValueError)`
  - `apply_op(building: dict, op: dict) -> dict` — returns a new dict (deep copy), input untouched.
  - `apply_steps(base: dict, steps: list[list[dict]]) -> dict` — applies every op of every step in order.
  - `space_at(building: dict, floor_id: str, xy: list[float]) -> str | None`
  - Op dicts are `{"op": <name>, ...args}` with the names/args of the spec table §1. Task 2 adds `move_vertex`
    and `set_polygon`'s neighbour fitting.

- [ ] **Step 1: Write the failing tests** (load `data/train/proc-campus-train-000/building.json` as the fixture)

```python
def test_apply_op_does_not_mutate_base(base): ...           # base == copy after apply_op
def test_add_space_gets_new_id(base):                       # id == f"{floor}-S-new1"; second add → -S-new2
def test_delete_space_removes_its_openings_and_assets(base)
def test_set_space_renames(base)
def test_add_opening_snaps_onto_shared_wall(base):          # position 2 m off the wall → result within 0.05 m of
                                                            # shapely shared outline of the two polygons
def test_add_opening_without_shared_wall_raises(base)       # two far-apart rooms → EditError
def test_move_opening_snaps(base)
def test_set_opening_width(base)
def test_add_asset_and_move_recomputes_space(base):         # move into another room → space_id == that room
def test_move_asset_rotation(base)
def test_unknown_id_raises(base)                            # EditError mentions the id
def test_apply_steps_is_deterministic(base)                 # same steps twice → identical dicts
```

- [ ] **Step 2: Run** `uv run pytest tests/test_edits.py -q` — Expected: FAIL (module missing).

- [ ] **Step 3: Implement `core/edits.py`.** One `_op_<name>(building, **args)` per op, dispatched by
  `apply_op`. Opening snapping: target segment = `poly_a.exterior.intersection(poly_b.buffer(WALL_TOLERANCE_M))`
  (import `WALL_TOLERANCE_M` from `core.solvers.walls`); for an entrance (`"outside"` in `space_ids`) the
  target is the space's exterior; position = `nearest_points(target, Point(xy))[0]`; empty target → `EditError`.
  `space_at` = first space on the floor whose polygon contains the point.

- [ ] **Step 4: Run** `uv run pytest tests/test_edits.py -q` — Expected: PASS.

- [ ] **Step 5: Ship** — PENDING.md claims for Task 1, then `/ship`.

### Task 2: Wall moves keep shared walls (`move_vertex`, `set_polygon`)

**Files:**
- Modify: `core/edits.py`
- Test: `tests/test_edits.py`

**Interfaces:**
- Produces ops `{"op": "move_vertex", "floor_id", "from_xy", "to_xy"}` and
  `{"op": "set_polygon", "space_id", "polygon"}`, both with neighbour fitting.

Algorithm (both ops):
1. `move_vertex`: in every space on `floor_id`, replace every vertex within `VERTEX_MATCH_M = 0.01` of `from_xy`
   by `to_xy`. `set_polygon`: replace that one outline.
2. Fit neighbours: for each other space on the floor whose polygon overlaps a changed polygon by more than
   `0.01` m², set it to `neighbour.difference(changed)`; if the result is empty, a MultiPolygon, or < 0.5 m² →
   `EditError("… would remove <name>")`.
3. Re-project openings of every changed space onto their shared wall (same snapping as Task 1); if no shared
   wall remains, leave the opening (the validator reports it).
4. Changed polygon invalid (`not is_valid`) → `EditError`.

- [ ] **Step 1: Write the failing tests**

```python
def test_move_vertex_moves_shared_corner_in_both_rooms(base)   # two rooms sharing a corner: both updated
def test_widen_room_shrinks_neighbour(base)                     # move the two east corners of room A 1 m east
                                                                # into B → B.area == old_B - 1*wall_len (±0.05),
                                                                # no overlap between A and B (< 0.01 m²)
def test_move_vertex_that_would_erase_neighbour_raises(base)    # EditError, input unchanged
def test_doors_follow_moved_wall(base)                          # door between A and B lies on new shared wall
def test_self_intersecting_polygon_raises(base)
```

  Pick rooms in the fixture by walking `shared_wall_neighbours` at test time — never hard-code ids beyond the
  fixture building.

- [ ] **Step 2: Run** `uv run pytest tests/test_edits.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** the algorithm above in `core/edits.py`.
- [ ] **Step 4: Run** `uv run pytest tests/test_edits.py -q` — Expected: PASS.
- [ ] **Step 5: Ship** via `/ship`.

### Task 3: Validator (`core/validate.py`) calibrated on the dataset

**Files:**
- Create: `core/validate.py`, `scripts/validate_dataset.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Produces: `validate(building: dict) -> list[dict]`, each issue
  `{"severity": "error" | "warning", "code": str, "message": str, "ids": list[str]}`, sorted errors first.
  Codes: `polygon_invalid`, `overlap`, `opening_off_wall`, `unreachable`, `no_entrance`, `dangling_ref`,
  `duplicate_id`, `asset_outside`.

- [ ] **Step 1: Write the calibration script** `scripts/validate_dataset.py`: runs `validate` over every
  `data/{train,dev,test}/*/building.json`, prints a count per (code, severity) and the worst examples.
- [ ] **Step 2: Write the failing tests**

```python
def test_dataset_has_no_errors():          # parametrize over all 280 building.json files; no issue with
                                           # severity "error"
def test_overlap_detected(base)            # apply set_polygon w/o fitting (mutate dict directly) → "overlap"
def test_opening_off_wall_detected(base)   # move an opening 3 m into a room by direct mutation
def test_unreachable_detected(base)        # delete every opening of one room by direct mutation
def test_dangling_ref_detected(base)       # opening points at a missing space id
def test_asset_outside_detected(base)
```

- [ ] **Step 3: Implement `validate`.** Overlaps via `shapely.STRtree` per floor, error above 0.05 m².
  `opening_off_wall`: distance from position to the shared outline > `WALL_TOLERANCE_M` (+ calibration margin).
  `unreachable`: `core.solvers.reachability.reachable_spaces` from `OUTSIDE`'s neighbours with
  `step_free=False`; buildings without an entrance → one `no_entrance` warning and skip the check.
- [ ] **Step 4: Calibrate.** Run `uv run python scripts/validate_dataset.py`. Every (code) the unchanged dataset
  triggers is either a tolerance bug (fix the tolerance) or downgraded to `warning`. Record the final counts in
  the module docstring.
- [ ] **Step 5: Run** `uv run pytest tests/test_validate.py -q` — Expected: PASS (280 dataset cases + crafted).
- [ ] **Step 6: Ship** via `/ship`.

### Task 4: Drafts store + API (`backend/drafts.py`, `backend/app.py`, `backend/sessions.py`)

**Files:**
- Create: `backend/drafts.py`
- Modify: `backend/app.py` (draft endpoints), `backend/sessions.py` (`SPLITS` gains `"user"`), `.gitignore`
  (`data/user/`, `.superpowers/`)
- Test: `tests/test_drafts.py`

**Interfaces:**
- Consumes: `apply_steps`, `EditError` (Task 1–2), `validate` (Task 3), `load_catalogue`, `SessionStore`.
- Produces:
  - `@dataclass Draft: id: str; base: str; name: str; steps: list[list[dict]]`
  - `class DraftStore(root: Path, catalogue: dict[str, dict])` with `create(base) -> Draft`,
    `get(draft_id) -> Draft | None`, `building(draft) -> dict` (cached by `(id, len(steps))`),
    `apply(draft, ops) -> Draft` (raises `EditError`, nothing stored on error), `undo(draft) -> Draft`
    (raises `EditError` when no steps), `save(draft, name) -> str` (returns the catalogue id `user/<slug>`, writes
    `root/<slug>/building.json` and `draft.json`, adds the entry to `catalogue`).
  - Drafts persist as `root/.drafts/<id>.json`; draft ids are `uuid4().hex`, validated by regex before any path
    use. Slug = lowercase ascii, `[a-z0-9-]`, clash → `-2`, `-3`, …
  - Endpoints (response for all but save/points: `{"draft": {id, base, name, steps: len}, "building": dict,
    "issues": list}`):
    `POST /drafts {base}` (422 unknown base) · `GET /drafts/{id}` (404) · `GET /drafts/{id}/points`
    (`export_points(BuildingMap(...))`) · `POST /drafts/{id}/ops {ops}` (422 with the EditError message) ·
    `POST /drafts/{id}/undo` (409 when nothing to undo) · `POST /drafts/{id}/save {name}` →
    `{"building": "user/<slug>", "issues": [...]}`.
  - `app.py` builds `drafts = DraftStore(DATA_DIR / "user", store.catalogue)`; env `GUIDE_USER_DIR` overrides.

- [ ] **Step 1: Write the failing tests** (TestClient; `DraftStore` on `tmp_path`, monkeypatch `app.drafts`)

```python
def test_create_get_ops_undo_roundtrip(client)
def test_ops_error_is_422_and_draft_unchanged(client)
def test_undo_empty_is_409(client)
def test_unknown_base_422_unknown_draft_404(client)
def test_bad_draft_id_never_touches_fs(client)        # "../x" → 404
def test_save_lists_building_and_guide_routes(client): # save → GET /buildings contains "user/<slug>";
    # POST /sessions {building} works; BuildingSession.tool_find_route between two rooms returns a route
def test_save_same_name_twice_suffixes(client)         # "user/foo", "user/foo-2"
def test_points_endpoint(client)                       # 200, "points" in payload
def test_dataset_untouched(client)                     # mtime/hash of the base building.json unchanged
```

- [ ] **Step 2: Run** `uv run pytest tests/test_drafts.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** `backend/drafts.py` and the endpoints.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all PASS (whole suite, benchmark tests included).
- [ ] **Step 5: Docs** — add the endpoints to `docs/guides/commands.md` (backend section) and the module
  docstring of `backend/app.py`.
- [ ] **Step 6: Ship** via `/ship`.

### Task 5: Frontend — Edit mode shell, read-only plan, 3D inset

**Files:**
- Modify: `frontend/app/src/api.ts`, `frontend/app/src/App.tsx`, `frontend/app/src/styles.css`,
  `frontend/app/src/scene/Scene.tsx` (optional `inset?: boolean`: no chat-panel principal-point shift, smaller
  canvas class)
- Create: `frontend/app/src/edit/EditMode.tsx`, `frontend/app/src/edit/PlanEditor.tsx`,
  `frontend/app/src/edit/geometry.ts`, `frontend/app/src/edit/edit.css`

**Interfaces:**
- Consumes: Task 4 endpoints.
- Produces (api.ts): types `BuildingJson`, `Issue`, `DraftState = { draft: {id, base, name, steps}, building:
  BuildingJson, issues: Issue[] }`, `Op = { op: string; [k: string]: unknown }`; `api.createDraft(base)`,
  `api.draft(id)`, `api.draftPoints(id)`, `api.applyOps(id, ops)`, `api.undo(id)`,
  `api.saveDraft(id, name) -> { building: string; issues: Issue[] }`.
- `PlanEditor` props: `{ building: BuildingJson; floorId: string; issues: Issue[]; onOps: (ops: Op[]) => void }`.

- [ ] **Step 1:** Header gets a View / Edit segmented switch. Edit → look up `localStorage["draft:" + buildingId]`,
  `api.draft(id)` if present (fall back to create on 404), else `api.createDraft(buildingId)` and store the id.
- [ ] **Step 2:** `EditMode` renders: the strip "Copy of <name> (draft) · N changes · ↶ Undo · Save",
  `PlanEditor` for the selected floor (existing floor picker drives it), the `Scene` inset fed by
  `api.draftPoints` (refetched after each change), an issues list. Chat panel hidden in Edit mode for M1.
- [ ] **Step 3:** `PlanEditor` draws spaces (polygons + name label), openings (short wall marks, width =
  `width_m`), assets (rotated footprint rects) in an SVG with y flipped (building y up), fit-to-floor viewBox,
  wheel zoom + drag pan. Elements in an error issue get the red outline.
- [ ] **Step 4: Verify** `cd frontend/app && npm run build` — Expected: no TypeScript errors. Run backend +
  Vite ([commands.md](../../../../docs/guides/commands.md#frontend-app)) and check in the browser that Edit shows the plan
  and the inset for `train/proc-campus-train-000`.
- [ ] **Step 5: Ship** via `/ship`.

### Task 6: Frontend — drag interactions, undo, issues

**Files:**
- Modify: `frontend/app/src/edit/PlanEditor.tsx`, `frontend/app/src/edit/geometry.ts`,
  `frontend/app/src/edit/EditMode.tsx`

**Interfaces:**
- Consumes: `onOps`, `api.applyOps`, `api.undo`.
- `geometry.ts` produces `snap(xy, vertices, grid = 0.05, radius = 0.25): [number, number]` (nearest existing
  vertex within radius, else grid) and `projectOnSegment`.

- [ ] **Step 1:** Click a space → selected; its vertices show handles. Drag a handle → live preview +
  dimension readout (edge lengths m, area m²); on drop → `[{op: "move_vertex", floor_id, from_xy, to_xy}]`.
- [ ] **Step 2:** Drag a door mark → slides along the wall (projected while dragging); drop →
  `move_opening`. Drag an asset → `move_asset`; `R` key or a rotate handle → `rotation_deg` ±15° snap.
- [ ] **Step 3:** Each op round-trips through `api.applyOps`; a 422 shows the message in the strip and reverts the
  preview. Undo button + Ctrl/Cmd-Z → `api.undo`. Clicking an issue selects/centres its element.
- [ ] **Step 4: Verify** `npm run build` clean; in the browser: move a shared corner (both rooms change), widen a
  room into its neighbour (neighbour shrinks, 3D inset updates), slide a door, move a machine into another room,
  undo three times (back to base).
- [ ] **Step 5: Ship** via `/ship`.

### Task 7: Save → Viewer → Guide, docs and memory bank

**Files:**
- Modify: `frontend/app/src/edit/EditMode.tsx`, `frontend/app/src/App.tsx`, `docs/architecture/ai-agents.md`
  (Builder section: implemented status), `docs/guides/commands.md`, `memory-bank/project-state.md`,
  `memory-bank/log.md`

- [ ] **Step 1:** Save → inline name field (default "<base name> (edited)") → `api.saveDraft`; if issues, show
  them with "Save anyway". On success: clear `localStorage["draft:" + base]`, reload `api.buildings()`,
  `api.switchBuilding(sessionId, newId)`, set mode View; the chat shows one system line
  "Switched to <name> — conversation restarted."
- [ ] **Step 2: Verify end to end in the browser** (offline Guide is fine): edit → save → View shows the
  edited building's point cloud → ask the Guide a route between two rooms → route drawn through the edited
  geometry. Also `uv run pytest -q` all PASS.
- [ ] **Step 3: Docs + memory bank** — status lines, commands, log entry; `python3 scripts/check_links.py` OK.
- [ ] **Step 4: Ship** via `/ship`.
