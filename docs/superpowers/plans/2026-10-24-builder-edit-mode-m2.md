---
id: plan-builder-edit-mode-m2
summary: Task-by-task plan for milestone 2 of the Builder Edit mode — prompt edits by a Builder agent (tools, propose → Apply, ghost overlay on the plan), offline rules client, backend stream + apply, Edit-mode chat.
sources: [../specs/2026-10-24-builder-edit-mode-design.md, 2026-10-24-builder-edit-mode-m1.md, agent/guide.py, agent/offline_llm.py, agent/places.py, backend/app.py, backend/drafts.py, core/edits.py]
related: [../specs/2026-10-24-builder-edit-mode-design.md, 2026-10-24-builder-edit-mode-m1.md, ../../architecture/ai-agents.md]
---

# Builder Edit Mode — Milestone 2 (Prompt Edits) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In Edit mode the user types what they want ("make Lab 0.21 two metres wider to the east", "move the 3D
printer to Office 0.14", "add a door between 0.02 and 0.03"); a Builder agent proposes a list of edit ops, the plan
shows it as a ghost overlay with the problems it would add, and the user clicks **Apply** (or says "yes").

**Architecture:** `agent/builder.py` is a Claude tool-use loop shaped like `agent/guide.py` over the M1 draft
(`backend/drafts.py`). Read-only tools describe the draft; `propose_edit(ops, summary)` dry-runs the ops with
`core/edits.py` + `core/validate.py` and parks a proposal — the agent has no apply tool. The backend streams a
Builder turn as NDJSON and applies a proposal on request. The frontend shows a Builder chat in Edit mode and draws
the proposal as a ghost on the plan.

**Tech Stack:** Python ≥ 3.12 (uv), anthropic SDK (beta messages, same call shape as the Guide), shapely, FastAPI,
pytest; Vite + React 19 + TypeScript.

**Spec:** [docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md](../specs/2026-10-24-builder-edit-mode-design.md)
— §4 (Builder agent), §5 (proposals, ghost overlay, Apply / Cancel), milestone 2 of "Delivery order". Builds on
[M1](2026-10-24-builder-edit-mode-m1.md) (ops, validator, drafts, Edit mode UI).

## Global Constraints

- The agent never changes the draft itself: no apply tool; a proposal enters the draft only via
  `POST /drafts/{id}/proposals/{pid}/apply` (the UI's Apply button, or the user's "yes" mapped by the backend).
- Model: env `BUILDER_MODEL`, default `claude-opus-5-5`; effort env `BUILDER_EFFORT`, default `medium`. Offline
  (`GUIDE_LLM=offline` or no key) uses `agent/builder_offline.py`, never the network.
- Numbers and ids in the agent's reply must come from tool results, the user or the overview: reuse
  `agent.guide.ungrounded` with one repair round, like the Guide.
- Tool results stay compact (cached system prompt + overview, as the Guide).
- Ops are exactly `core/edits.py` ops; the one new op this milestone adds is `move_edge` (Task 1).
- Never write into `data/train|dev|test/`; benchmark path untouched; `uv run pytest` stays green.
- Commits only via `/ship` (D-008); `.claude/worklog/PENDING.md` kept current; `python3 scripts/check_links.py`
  after doc / memory-bank edits.

## Review Focus

1. A proposal made, then the user drags something before clicking Apply → the stale proposal is refused (409,
   "the draft changed since; ask again"), never applied on top of a different draft (test in Task 4).
2. "yes" with no pending proposal, or with two → treated as a normal message to the agent, nothing applied
   (test in Task 3).
3. The agent proposes ops that raise `EditError` → the tool returns the error, the agent may retry; after
   `MAX_REPAIRS` failures the reply says it couldn't, nothing is parked (test in Task 3).
4. An ambiguous room name ("the lab" with three labs) → the agent asks which one instead of guessing; `find`
   returns the candidates with what tells them apart (test in Task 2 for the tool; prompt rule in Task 3).
5. A proposal that adds validator errors → the reply and the proposal card name the new problems before Apply
   (test in Task 3).

---

### Task 1: `move_edge` op (move a wall by a distance)

Moving a wall is the core of "make X wider / narrower"; composing it from two `move_vertex` ops lets the first op
cut a neighbour diagonally before the second runs. One op, one `settle`.

**Files:**
- Modify: `core/edits.py`
- Test: `tests/test_edits.py`

**Interfaces:**
- Produces op `{"op": "move_edge", "space_id": str, "edge": [[x1, y1], [x2, y2]], "offset_m": float}` — both
  endpoints move along the edge's outward normal (away from the space's centroid side) by `offset_m` (negative =
  inward), in every space on the floor that has them (within `VERTEX_MATCH_M`); then `settle` once.
  `edge` must be an edge of the space (both endpoints are consecutive vertices, either order) → else `EditError`.
- Produces `edge_sides(polygon: list[list[float]]) -> list[dict]` — each edge as
  `{"side": "north"|"east"|"south"|"west"|"other", "from": [x, y], "to": [x, y], "length_m": float}`; side = the
  outward normal's compass direction when within 10° of an axis (x east, y north), else `"other"`. Used by the
  Builder's `space_info` (Task 2).

- [ ] **Step 1: Write the failing tests**

```python
def test_move_edge_widens_room_and_shrinks_neighbour(base)   # A's edge shared with B, offset 1.0 →
                                                             # A.area += 1*len, B.area -= 1*len (±0.05), no overlap
def test_move_edge_negative_offset_narrows(base)             # offset -0.5 → A.area -= 0.5*len (±0.05)
def test_move_edge_moves_corners_in_neighbours_on_both_ends(base)  # rooms sharing either endpoint get it moved
def test_move_edge_rejects_non_edge(base)                    # two non-consecutive vertices → EditError
def test_edge_sides_of_rectangle()                           # [[0,0],[4,0],[4,3],[0,3]] → sides {south, east,
                                                             # north, west}, lengths 4, 3, 4, 3
```

- [ ] **Step 2: Run** `uv run pytest tests/test_edits.py -q -k "move_edge or edge_sides"` — Expected: FAIL (unknown op / missing function).
- [ ] **Step 3: Implement** `move_edge` (registered with `@op`) and `edge_sides` in `core/edits.py`.
- [ ] **Step 4: Run** `uv run pytest tests/test_edits.py -q` — Expected: PASS (all).
- [ ] **Step 5: Ship** via `/ship`.

### Task 2: Builder tools (`agent/builder_tools.py`)

**Files:**
- Create: `agent/builder_tools.py`
- Test: `tests/test_builder_tools.py`

**Interfaces:**
- Consumes: `DraftStore`, `Draft` (backend/drafts.py), `apply_op`, `EditError`, `edge_sides` (core/edits.py),
  `validate` (core/validate.py), `agent.places.candidates` / `describe` / `nearest_names`,
  `core.solvers.walls.shared_wall_neighbours`.
- Produces:
  - `@dataclass Proposal: id: str; summary: str; ops: list[dict]; draft_version: int; new_problems: list[dict];
    effect: dict`
  - `class BuilderTools(store: DraftStore, draft: Draft)` with `call(name: str, arguments: dict) -> dict` (unknown
    tool / bad arguments → `{"error": ...}`, never raises) and `pending: dict[str, Proposal]`.
  - `BUILDER_TOOLS: list[dict]` — Anthropic tool definitions for the five tools below.
  - Tools (all read the *current* draft building `store.building(draft)`):
    - `overview()` → `{"name", "floors": [{"id", "level", "name", "spaces"}], "spaces", "openings", "assets",
      "problems": <error count>}`
    - `find(query: str, floor_level?: int)` → `{"matches": [describe(...) …≤8], "assets": [{"id", "name", "in"} …≤8]}`;
      nothing → `{"matches": [], "did_you_mean": nearest_names(...)}`
    - `space_info(space: str)` (id or phrase; ambiguous → `{"error": "'…' is ambiguous …"}` via
      `agent.places.problem`) → `{"id", "name", "type", "room_type", "floor_id", "area_m2", "bbox",
      "edges": edge_sides(...), "neighbours": [{"id", "name", "shared_m", "side"}], "openings": [{"id", "kind",
      "to", "position", "width_m"}], "assets": [{"id", "name", "position"}]}` — coordinates rounded to 2 decimals.
    - `floor_plan(floor_id: str)` → `{"floor_id", "spaces": [{"id", "name", "type", "bbox"}]}` (bbox only — keeps
      it compact).
    - `propose_edit(ops: list[dict], summary: str)` → dry-run `apply_op` over the ops on the current building;
      `EditError` → `{"error": str}`; else new problems = `validate(after, base=current)` errors whose
      `(code, ids)` are not among the current errors; effect = `{"changed_spaces": [{"id", "name", "area_before",
      "area_after"}], "added": {kind: n}, "removed": {kind: n}}`; parks a `Proposal` (id `P<n>`, draft_version =
      `draft.version`) and returns `{"proposal_id", "summary", "effect", "new_problems": [messages],
      "needs_confirmation": true}`. Only the newest proposal stays pending (a new one replaces older ones).

- [ ] **Step 1: Write the failing tests** (fixture: `DraftStore(tmp_path, catalogue)` + draft of
  `train/proc-campus-train-000`)

```python
def test_overview_counts(tools)
def test_find_exact_ref_and_did_you_mean(tools)       # "0.21"-style ref of a fixture room → one match;
                                                      # "Ofice" → did_you_mean non-empty
def test_find_ambiguous_lists_candidates(tools)        # a word matching ≥2 rooms → len(matches) >= 2
def test_space_info_edges_and_neighbours(tools)       # 4 edges with sides for a rectangular office; a neighbour
                                                      # has side in {north,east,south,west}
def test_space_info_ambiguous_is_error(tools)
def test_propose_edit_parks_and_reports_effect(tools)  # move_edge 1 m into neighbour → proposal_id, changed
                                                      # areas for both rooms, draft.steps unchanged
def test_propose_edit_bad_op_returns_error(tools)      # unknown id → {"error"}, nothing pending
def test_propose_edit_reports_new_problems(tools)      # delete every opening of a room → new_problems mentions
                                                      # "can't be reached"
def test_new_proposal_replaces_old(tools)
def test_unknown_tool_is_error(tools)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_builder_tools.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `agent/builder_tools.py`.
- [ ] **Step 4: Run** `uv run pytest tests/test_builder_tools.py -q` — Expected: PASS.
- [ ] **Step 5: Ship** via `/ship`.

### Task 3: Builder agent loop + offline client (`agent/builder.py`, `agent/builder_offline.py`)

**Files:**
- Create: `agent/builder.py`, `agent/builder_offline.py`
- Test: `tests/test_builder.py`

**Interfaces:**
- Consumes: `BuilderTools`, `BUILDER_TOOLS`, `Proposal` (Task 2); `agent.guide.ungrounded`, `agent.guide.llm_mode`;
  `agent.offline_llm.text_block / tool_use / message` (response helpers, also for scripted fakes in tests);
  `DraftStore.apply` (M1).
- Produces:
  - `@dataclass BuilderTurn: text: str; tool_calls: list[dict]; proposal: Proposal | None; applied: str | None;
    ungrounded: list[str]; stop_reason: str | None`
  - `class Builder(store: DraftStore, draft: Draft, client: object | None = None, model: str | None = None,
    effort: str | None = None)` with `reply(text: str) -> BuilderTurn`, `apply(proposal_id: str) -> str`
    (summary; raises `EditError("the draft changed since this proposal; ask again")` when
    `draft.version != proposal.draft_version`, or for an unknown id), `on_step` callback (same step dicts as the
    Guide: `{"kind": "tool"|"tool_done"|"check", ...}`), `usage`.
  - `make_builder_client() -> object` — `anthropic.Anthropic()` when `llm_mode() == "anthropic"`, else
    `BuilderOfflineClient()`.
  - Constants: `DEFAULT_MODEL = "claude-opus-5-5"`, `DEFAULT_EFFORT = "medium"`, `MAX_TOOL_ROUNDS = 10`,
    `MAX_REPAIRS = 2` (failed `propose_edit` calls per turn before the loop stops proposing).
- `reply` rules:
  1. If the text matches the Guide's confirm pattern (`agent.offline_llm.CONFIRM`) and exactly one proposal is
     pending → `apply` it, append a short exchange to the history (user text + assistant
     "Applied: <summary>") without an API call, return `applied=summary`.
  2. Else run the tool loop (request shape copied from `Guide.request`, tools = `BUILDER_TOOLS`, system =
     instructions + cached overview of the draft); after `MAX_REPAIRS` tool errors from `propose_edit`, the next
     tool call gets `{"error": "stop proposing; tell the user what failed"}`.
  3. Grounding: `ungrounded(text, corpus)`; if anything is missing, one repair message like the Guide's.
  4. `proposal` = the newest pending proposal created in this turn, if any.
- System instructions (`INSTRUCTIONS` in `agent/builder.py`) must say: you edit a *draft copy*; metres, x east,
  y north; find places with `find` / `space_info`, never invent ids; ask one short question when a place or wall
  is ambiguous; widen/narrow = `move_edge` with an edge from `space_info.edges`; move a thing = `move_asset`;
  doors = `add_opening` / `move_opening` / `set_opening`; always end with `propose_edit` and then tell the user
  the summary, the effect (areas) and any new problems, and ask them to Apply — never say it is done; the op
  list with arguments (copied from the spec §1 table + `move_edge`).
- Offline client rules (`BuilderOfflineClient`, request-in / message-out like `OfflineClient`): "rename X to Y",
  "make X N m wider|narrower to the north|east|south|west" (→ `space_info`, then `move_edge` on that side's edge),
  "add a door between X and Y" (→ `add_opening` at the shared-wall midpoint from `space_info` neighbours), else a
  help text naming those phrasings; replies are composed only from tool results.

- [ ] **Step 1: Write the failing tests** (scripted fake client built from `message(tool_use(...))` sequences,
  and the offline client)

```python
def test_turn_with_proposal_does_not_change_draft(store_draft)   # fake: space_info → propose_edit → text;
                                                                 # turn.proposal set, draft.steps == 0
def test_yes_applies_single_pending_proposal(store_draft)        # next reply("yes") → applied == summary,
                                                                 # draft.steps == 1, no client call made
def test_yes_without_pending_goes_to_model(store_draft)          # fake records a request; applied is None
def test_apply_stale_proposal_raises(store_draft)                # store.apply(other op) then builder.apply(pid)
                                                                 # → EditError "changed since"
def test_repeated_bad_proposals_stop(store_draft)                # fake proposes bad ops 3× → third gets the
                                                                 # "stop proposing" error; no proposal
def test_new_problems_reach_the_reply(store_draft)               # fake proposes deleting a room's doors; tool
                                                                 # result contains the problem text
def test_ungrounded_number_triggers_one_repair(store_draft)      # fake says "37 m²" not in any result → a
                                                                 # "[grounding check" message is sent once
def test_offline_widen_proposes_move_edge(store_draft)           # BuilderOfflineClient: "make <room ref> 1 m
                                                                 # wider to the <side>" → proposal ops[0]["op"]
                                                                 # == "move_edge"
def test_offline_rename_and_help(store_draft)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_builder.py -q` — Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** `agent/builder.py` and `agent/builder_offline.py`.
- [ ] **Step 4: Run** `uv run pytest tests/test_builder.py -q` — Expected: PASS.
- [ ] **Step 5: Ship** via `/ship`.

### Task 4: Backend — Builder stream and proposal apply

**Files:**
- Modify: `backend/app.py`
- Test: `tests/test_drafts.py` (extend)

**Interfaces:**
- Consumes: `Builder`, `make_builder_client` (Task 3), `drafts` store (M1).
- Produces:
  - In-memory `builders: dict[str, Builder]` keyed by draft id, created on first use, plus one
    `threading.Lock` per draft id (`draft_locks`); `/drafts/{id}/ops`, `/undo` and the Builder routes all hold
    that lock (this also closes the M1 race the verifier noted).
  - `POST /drafts/{id}/chat/stream {message}` → NDJSON: `{"type": "step", ...}` lines, then
    `{"type": "reply", "reply", "tool_calls": [{name, input}], "proposal": {"id", "summary", "ops",
    "new_problems", "effect", "building"} | null, "applied": str | null, "state": DraftState}` (`building` = the
    draft with the proposal's ops applied, for the ghost; `state` = current draft state), or
    `{"type": "error", "detail"}`.
  - `POST /drafts/{id}/proposals/{pid}/apply` → `DraftState`; stale or unknown proposal → 409 with the reason.
  - Builder history is in memory only (lost on restart) — milestone 3 persists it.

- [ ] **Step 1: Write the failing tests** (offline client; `GUIDE_LLM=offline`)

```python
def test_builder_stream_offline_proposal(client)      # "make <ref> 1 m wider to the <side>" → reply line with a
                                                      # proposal (ops[0].op == "move_edge"), state.draft.steps == 0
def test_apply_proposal_endpoint(client)              # → 200, draft.steps == 1
def test_apply_stale_proposal_409(client)             # propose, then /ops rename, then apply → 409
def test_yes_in_stream_applies(client)                # propose, then stream "yes" → applied set, steps == 1
def test_builder_stream_unknown_draft_404(client)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_drafts.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** the routes and per-draft locks in `backend/app.py`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all PASS.
- [ ] **Step 5: Docs** — endpoint rows in `docs/guides/commands.md`; app docstring.
- [ ] **Step 6: Ship** via `/ship`.

### Task 5: Frontend — Builder chat, ghost overlay, Apply / Cancel

**Files:**
- Create: `frontend/app/src/edit/BuilderChat.tsx`
- Modify: `frontend/app/src/api.ts`, `frontend/app/src/edit/EditMode.tsx`, `frontend/app/src/edit/PlanEditor.tsx`,
  `frontend/app/src/edit/edit.css`

**Interfaces:**
- Consumes: Task 4 routes.
- Produces (api.ts): `type Proposal = { id: string; summary: string; ops: Op[]; new_problems: string[]; effect:
  unknown; building: BuildingJson }`, `type BuilderReply = { reply: string; tool_calls: {name: string; input:
  unknown}[]; proposal: Proposal | null; applied: string | null; state: DraftState }`,
  `api.builderStream(draftId, message, onStep) -> Promise<BuilderReply>` (NDJSON, same parsing as `chatStream`;
  steps shown with `ui/guideSteps.stepLabel` like the building screen),
  `api.applyProposal(draftId, proposalId) -> Promise<DraftState>`.
- `PlanEditor` gains `ghost?: BuildingJson | null`: spaces / openings / assets whose JSON differs from `building`
  (or are new) are drawn dashed on top (`.ghost`); removed ones are drawn crossed out.
- `BuilderChat` props: `{ draftId: string; onState: (state: DraftState) => void; onProposal: (proposal:
  Proposal | null) => void; proposal: Proposal | null }` — message list, live step lines ("Looking at …",
  from `step.name`), input; the proposal card shows summary, area changes, new problems (red), **Apply** →
  `api.applyProposal` → `onState`, **Cancel** → `onProposal(null)`.

- [ ] **Step 1:** Layout (Edit mode now lives in Atahan's `BuildingScreen`, merged from `dev`; the 3D inset is
  `PlanView` fed by `GET /drafts/{id}/plan`): right column = `PlanView` inset (top) + `BuilderChat` (fills the
  rest); the issues list moves to a compact panel at the bottom-left of the plan (`max-height: 28vh`). Style the chat
  with the screen's tokens (`--surface`, `--ground`, …) like `building/Conversation.tsx`; don't reuse dev's global
  class names (`.plan`, `.primary`) — they collide.
- [ ] **Step 2:** Proposal flow: on a reply with `proposal`, EditMode sets `ghost = proposal.building` and switches
  the floor to the first changed element's floor; Apply clears the ghost and takes the new state; any drag or
  undo also clears the ghost (the backend would refuse the stale proposal anyway).
- [ ] **Step 3: Verify** `cd frontend/app && npm run build` — Expected: clean. Browser (backend :8775 offline,
  Vite :5191), headless Chrome: type "make <ref> 1 m wider to the <side>" → ghost drawn + card → Apply → change
  count 1, neighbour shrunk in the plan; type it again → drag a door → Apply → error "changed since" shown.
- [ ] **Step 4: Live check (costs ~$0.1–0.3, uses the key from the main checkout's `.env`):** backend with
  `uv run --env-file <main>/.env uvicorn …` and three prompts — widen a lab, move a machine to another room,
  add a door between two offices; each must end with a proposal and no ungrounded numbers. Record model, seconds
  per turn and cost in the log.
- [ ] **Step 5: Docs + memory bank** — ai-agents.md Builder status (M2), commands.md Edit-mode paragraph
  (prompt edits), project-state + log; `python3 scripts/check_links.py` OK.
- [ ] **Step 6: Ship** via `/ship`.
