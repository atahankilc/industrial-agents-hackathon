---
id: builder-edit-mode-design
summary: Design of the app's Edit mode — edit a copy of a building by prompt and by click-and-drag on a 2D plan with a live 3D preview; first step of Level 4 (Build).
status: proposed
sources:
  - conversation with Utku, 2026-10-24
  - docs/challenge/brief.md (Level 4)
  - archive/initial-repo/README.md §1, §3, judging table
  - docs/kit/data-format.md
  - agent/tools.py, backend/app.py, backend/sessions.py, backend/persistence.py, frontend/app/src/App.tsx
related: [../plans/2026-10-24-builder-edit-mode-m1.md, ../plans/2026-10-24-builder-edit-mode-m2.md, ../plans/2026-10-24-builder-edit-mode-m3.md, ../../architecture/ai-agents.md, ../../kit/data-format.md, ../../challenge/brief.md, 2026-10-24-guide-agent-design.md]
---

# Builder · Edit mode — design

Implementation plans: [milestone 1](../plans/2026-10-24-builder-edit-mode-m1.md) (drag edit, done) · [milestone 2](../plans/2026-10-24-builder-edit-mode-m2.md) (prompt edits, done) · [milestone 3](../plans/2026-10-24-builder-edit-mode-m3.md) (deployed store — owner Atahan).

## Intent

Level 4 of the brief: *create or update a building from floor plans, by conversation; a new building should take
minutes, not days.* Today the app can only **view** buildings and apply Guide-level changes (close / reopen /
add a door). This design adds an **Edit mode** in which the user changes a building — its rooms, doors and the
things inside — by **typing what they want** or by **clicking and dragging** on a plan, on a **copy** of the
building, then saves the copy as a new building that the Viewer and the Guide use like any other.

Edit mode is the first of three Builder projects, agreed order (Utku, 2026-10-24):

1. **Edit mode** (this document) — the edit core every later project writes into.
2. Build from scratch — from PDF / image / conversation with a spatial-understanding model (separate design).
3. Scan ingest — point cloud / 3D scan → `building.json` + 2D images added to the dataset (separate design;
   candidate L5 "Capture on site").

Why the core matters beyond the demo: the judging table counts "buildings built correctly from plans" inside the
55-point automatic score. Projects 2 and 3 will produce draft buildings; the operations, validator and draft
store defined here are what turn a model's guess into a valid `building.json`.

Blueprint-Bench 2 (andonlabs.com/evals/blueprint-bench-2, read 2026-10-24) is the reason for the
validator-first stance: models get room counts right ~90% of the time but mostly fail on which rooms connect.
Model output is never trusted as-is; code checks it and the user confirms it.

## Decided by Utku

- The UI has two modes: **Viewer** and **Edit**. Turning on Edit makes the plan editable.
- Edits come from **a prompt** (describe the building as you picture it) **and** from **click-and-drag**.
- The building **and** the positions of the things inside it can be edited.
- Edits happen on a **copy**, never on the original dataset.
- Layout **C**: edit on a **2D plan** of one floor, with a **small live 3D preview** in a corner; chat on the right;
  a **View / Edit** switch at the top; a "copy (draft) · N changes · Undo · Save" strip.
- Work happens on a **separate branch**.
- Confirmed playback (all correct): first switch to Edit makes a draft copy; one floor at a time with the existing
  floor picker; click a room → vertex handles; doors slide along walls; assets drag and rotate; drags go straight
  into the draft; prompt edits are shown as a preview first and enter the draft on **Apply** (same
  propose → confirm idea as the Guide); the validator runs after every change and marks problems in red without
  blocking; Save warns about open problems; Save adds the copy to the building list as a new building usable
  by Viewer and Guide; Undo exists.

## Delivery order (Utku, 2026-10-24)

Each milestone is usable on its own; there is time for all three, but this is the order:

1. **Drag-edit → Save → the Guide routes in the saved building**, end to end, **local store only**
   (core ops + validator, drafts API on `data/user/`, PlanEditor + 3D preview).
2. **Prompt edits with Apply** (Builder agent, proposals, ghost overlay).
3. **Deployed path** (Supabase `buildings` table, catalogue read per request on serverless).

## Goals

- Edit a building's spaces, openings and assets by prompt and by drag, on a draft copy, with undo.
- Every change is checked by deterministic code; problems are visible immediately.
- Saved drafts are first-class buildings: listed in `GET /buildings`, loadable by `BuildingSession`, routable by
  the Guide, rendered by the point cloud.
- Works locally **and** on the deployed app (Vercel + Supabase).

## Non-goals (this project)

- Creating a building from nothing, PDF/image understanding, scan ingest (projects 2 and 3).
- Adding or removing **floors** or **vertical connectors** (stairs / lifts) — *builder's call to keep out; listed
  as the first follow-up*.
- Multi-user / concurrent editing of one draft.
- Editing equipment.csv (assets in `building.json` only).
- Changing the benchmark path: `core/building_map.py` behaviour, solvers and `agent.run_benchmark` stay as they are.

## Anti-goals (failure even if it "works")

- Any write into `data/train|dev|test/`.
- The agent changing the draft without the user's explicit Apply.
- A validator that flags the **unchanged** dataset buildings as broken (false alarms train the user to ignore red).
- Drag that feels imprecise: the route model is centimetre-exact, so geometry must snap and show numbers.
- A saved building that the Guide or the point cloud cannot load.

## Constraints

- Schema stays exactly `building.json` as in [data-format.md](../../kit/data-format.md): top-level keys
  `building, floors, spaces, openings, vertical_connectors, assets`; polygons not closed; metres; one XY frame.
- Python ≥ 3.12 via `uv`; frontend is the existing Vite + React + r3f app in `frontend/app/`.
- The deployed backend runs on Vercel serverless (no shared memory, read-only filesystem) — drafts and saved
  buildings must live in Supabase when `SUPABASE_DB_URL` is set, like conversations
  (`backend/persistence.py`).
- Commits only via `/ship` (D-008).

## Design

### 1. Edit operations — `core/edits.py` (new)

A draft is **base building + ordered list of operations**. An operation is a small JSON dict; applying the list
to the base gives the draft building. Undo = drop the last op and replay; this mirrors how
`backend/persistence.py` already replays applied changes deterministically.

Operation set (each validates its own arguments and raises a clear error on unknown ids):

| op | arguments | notes |
|---|---|---|
| `add_space` | floor_id, polygon, type, room_type, name, ref | new id `<floor_id>-S-new<n>` |
| `delete_space` | space_id | also deletes its openings, and its assets (*builder's call: delete, not orphan*) |
| `set_space` | space_id, name?, ref?, type?, room_type? | rename / retype |
| `set_polygon` | space_id, polygon | replaces the outline |
| `move_vertex` | floor_id, from_xy, to_xy | moves that point in **every** space on the floor that has it (shared walls stay shared — *builder's call*); openings on a moved wall are re-projected onto the new wall |
| `move_edge` | space_id, edge [[x1,y1],[x2,y2]], offset_m | *(added in milestone 2)* moves a wall along its outward normal in every room that has its corners, then fits neighbours once — the Builder's "make X wider" |
| `add_opening` | space_ids (2, or 1 + "outside"), position, kind, width_m, step_free | id `<floor_id>-O-new<n>` |
| `move_opening` | opening_id, position | position is snapped onto the shared wall |
| `set_opening` | opening_id, width_m?, step_free?, kind? | |
| `delete_opening` | opening_id | |
| `add_asset` | space_id, name, category, type, position, footprint | id `<building>-A-new<n>`, `source: "edited"` |
| `move_asset` | asset_id, position, rotation_deg?, space_id? | space_id recomputed from position if omitted |
| `set_asset` | asset_id, name?, type?, category?, footprint? | |
| `delete_asset` | asset_id | |

Composite prompt edits ("make lab 0.21 two metres wider to the east", "split the hall into two rooms") are
expressed by the Builder agent as a **list** of these ops, applied as one undo step.

New elements get `"synthetic": false` and the building gets `building.source = "edited"`,
`building.source_ref = {"base": <base id>}`, a new `id` and the user's `name`; licence/attribution are copied from
the base (data licences still apply, D-009).

### 2. Validator — `core/validate.py` (new)

`validate(building_dict) -> list[Issue]`, `Issue = {severity: "error"|"warning", code, message, ids: [...]}`.
Checks:

- polygon: ≥ 3 points, valid, non-zero area (shapely, already a dependency via `core/geodesic.py`);
- overlapping spaces on the same floor (area above a small tolerance);
- opening lies on a wall shared by its two spaces (or on the outer wall for entrances), within a tolerance;
- every room reachable from an entrance (reuse the existing graph / reachability code, not a new one);
- vertical connectors reference existing spaces;
- asset position inside its space polygon;
- duplicate ids / dangling references.

**Calibration rule:** before any check counts as an `error`, run it over all 280 dataset buildings. Anything the
unchanged dataset violates is either a tolerance bug or becomes a `warning` (e.g. real OSM quirks). The test
suite pins this: validating every dataset building yields **zero errors**.

### 3. Drafts and saved buildings — `backend/drafts.py` (new)

- `Draft {id, base, name, ops, version}` → materialised `BuildingMap` (cached per version) + issues.
- Store: Supabase table `buildings` (new migration under `supabase/migrations/`) when `SUPABASE_DB_URL` is set;
  otherwise a local directory `data/user/<slug>/building.json` (+ `draft.json` with base + ops), **gitignored**.
  Same optimistic-version pattern as conversations.
- Saved buildings join the catalogue as `user/<slug>` (`load_catalogue` + the Supabase rows), so
  `GET /buildings`, `PUT /sessions/{id}/building`, the Guide and `GET /sessions/{id}/points` work unchanged.
- Editing a saved building creates a new draft whose base is that saved building.

API (prefix as the rest of the backend):

| method | path | does |
|---|---|---|
| POST | `/drafts` `{base}` | new draft from a catalogue building |
| GET | `/drafts/{id}` | building JSON + issues + op count |
| GET | `/drafts/{id}/points` | point-cloud export of the draft (3D preview) |
| POST | `/drafts/{id}/ops` `{ops}` | apply ops now (drag path); returns building + issues |
| POST | `/drafts/{id}/undo` | drop last step |
| POST | `/drafts/{id}/save` `{name}` | write as `user/<slug>`; response includes open issues |
| POST | `/drafts/{id}/chat/stream` | Builder agent turn (streamed like `/chat/stream`) |
| POST | `/drafts/{id}/proposals/{pid}/apply` | apply a pending proposal |

### 4. Builder agent — `agent/builder.py` (new)

Claude tool-use loop in the same shape as `agent/guide.py` (cached system prompt with a compact overview of the
draft, append-only history, offline client for tests). Model: env `BUILDER_MODEL`, default `claude-opus-5-5`
(*builder's call*).

Tools:

- read-only: `overview`, `find` (place resolution via `agent/places.py`), `space_info` (polygon, area, neighbours,
  openings, assets), `floor_plan` (compact geometry of one floor);
- `propose_edit(ops, summary)` → validates by dry-running the ops on a copy; returns the issues the ops would
  introduce and a `proposal_id`. Never applies. If the dry run raises errors the agent gets them back and may
  retry (bounded, like the Guide's repair).
- No apply tool: applying is the user's **Apply** button (or the user saying yes, which the backend maps to the
  pending proposal) — same rule as D-010's "same-turn apply refused".

The agent asks only what it needs (e.g. "which wall?" when ambiguous) and states numbers from tool results only
(reuse the Guide's grounding check).

### 5. Frontend — Edit mode (`frontend/app/`)

- Header: **View / Edit** switch. Entering Edit with no draft calls `POST /drafts`; the strip shows
  "Copy of <name> (draft) · N changes · ↶ Undo · Save".
- **`PlanEditor`** (new, SVG, one floor, uses the existing floor picker): spaces as polygons with labels,
  openings as wall marks, assets as footprint rectangles. Select → handles. Drag vertex / slide door along wall /
  drag + rotate asset. Snap to 0.05 m grid and to existing vertices; live dimension readout (m, m²). On drop →
  one op via `/ops`.
- **3D preview** inset: the existing `Scene` fed by `/drafts/{id}/points`, refreshed after each step.
- **Issues**: red outline on offending elements + a small list; click focuses the element.
- **Proposals**: the chat panel talks to the Builder in Edit mode; a proposal renders as a ghost overlay on the
  plan with **Apply / Cancel** in the chat card.
- **Save**: name prompt; if issues exist, show them and let the user save anyway (warning, not block).
- Back to **View** shows the saved building (or the base if the draft wasn't saved; the draft stays resumable).

### 6. Tests and checks

- `tests/test_edits.py`: each op; replay determinism; undo; ids; shared-vertex move keeps neighbours and doors.
- `tests/test_validate.py`: every dataset building → 0 errors; crafted broken buildings → the expected issue codes.
- `tests/test_drafts.py`: API round trip with the local store; saved building appears in `/buildings`, loads in a
  `BuildingSession`, Guide `find_route` works on it.
- `tests/test_builder.py`: offline scripted conversation ("widen lab 0.21 by 2 m to the east" → proposal → Apply).
- Benchmark unchanged: `uv run pytest` stays green; dev score 138/138 unaffected.
- UI verified in the browser with the `run` skill (drag, undo, save, switch to View, ask the Guide a route).

## Left to the builder

- Exact tolerances (wall-on-opening, overlap area) — set by the calibration rule above.
- How the Builder phrases proposals and how big `floor_plan` output may get (keep tool results compact).
- PlanEditor internals (pan/zoom, hit testing), visual styling within the existing monochrome theme (D-011).
- Whether `/drafts` reuses `Conversation` or has its own session object.

## Calls made by Claude (check these)

1. Branch `2-builder-edit` from `1-agentic-yarag` HEAD, in a separate git worktree so the uncommitted Guide work
   on `1-agentic-yarag` stays where it is.
2. No adding floors or stairs/lifts in this project (first follow-up).
3. Deleting a space deletes its doors and assets.
4. Moving a shared vertex moves it in every room that has it.
5. Drafts/saved buildings in Supabase on deploy, `data/user/` (gitignored) locally.
6. Builder model `claude-opus-5-5`, overridable by `BUILDER_MODEL`.
7. Problems never block Save — they warn.
8. A draft starts from the **clean catalogue building** (`POST /drafts {base: <catalogue id>}`), not from the
   Guide session's state: closures are temporary session state and Guide-added doors are not carried over.
9. Save / back to View switches the session to the saved building with the existing
   `PUT /sessions/{id}/building` — the Guide conversation **restarts** (a short system line in the chat says so).
   No "swap building, keep history" path in this project.
10. Public deploy has no accounts: every saved building is visible to everyone; a name clash gets a numeric
    suffix (`user/<slug>-2`); saving a draft of `user/x` always creates a new building; no delete endpoint.
11. The open draft id is kept in the browser (`localStorage`, keyed by base building); `GET /drafts/{id}` resumes
    it. No server-side lookup by session or base.
12. **Walls stay shared, also mid-edge.** `move_vertex` / a wall move also updates neighbours whose edge the
    moved point lies on (inserting a matching point so the wall stays shared and the neighbour shrinks or grows).
    If a neighbour would lose all its area the op is refused with an error. *Implemented (after the M1 review)* as:
    the area the changed rooms give up goes to the neighbour it borders most, and the area they take is cut from
    the neighbours they overlap — same outlines as inserting matching points, without the long-edge artefacts. So "widen lab 0.21 two metres to the
    east" shrinks the room next door instead of producing an overlap.
