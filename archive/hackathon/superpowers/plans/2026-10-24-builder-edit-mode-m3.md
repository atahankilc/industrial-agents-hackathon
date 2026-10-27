---
id: plan-builder-edit-mode-m3
summary: Task-by-task plan for milestone 3 of the Builder Edit mode — drafts, saved buildings and Builder history in Supabase so the Edit mode works on the deployed (Vercel, serverless, read-only filesystem) app. Owner Atahan.
sources: [../specs/2026-10-24-builder-edit-mode-design.md, 2026-10-24-builder-edit-mode-m1.md, 2026-10-24-builder-edit-mode-m2.md, backend/drafts.py, backend/app.py, backend/sessions.py, backend/persistence.py, agent/builder.py, supabase/migrations/20261024120000_conversations.sql, vercel.json]
related: [../specs/2026-10-24-builder-edit-mode-design.md, 2026-10-24-builder-edit-mode-m2.md, ../../guides/commands.md]
---

# Builder Edit Mode — Milestone 3 (Deployed Store) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Owner:** was Atahan; Utku took it back on 2026-10-24 (not started) and Claude built Tasks 1–5 the same day — see
the spec's "Milestone 3 decisions". **Status:** Tasks 1–5 done (offline tests + live Supabase tests + a two-instance
end-to-end run against Supabase); Task 6 (deploy + public smoke test) pending.

**As built (differs from the text below):** `DraftStore(source, catalogue)` keeps its old argument order — `source`
is a directory (→ `FileDraftBackend`) or any backend, so existing tests are untouched; the backend also has
`draft_version`, `builder_version` and `building_path` (saved buildings keep a `path` in file mode); a change is
redone up to `SAVE_ATTEMPTS = 3` times before 409 (one retry lost under a two-instance stress test); the
SessionStore finds saved buildings through `SessionStore.user_buildings` (the DraftStore); `/buildings` refreshes
quietly (database down → dataset buildings still listed); app-wide handlers map `Conflict` → 409 and `psycopg.Error`
→ 503; the Edit mode reloads the draft after a 409. Migration: `supabase/migrations/20261025120000_builder_drafts.sql`
(applied to the Supabase project 2026-10-24). Tests: `tests/test_draft_backends.py`.

**Goal:** The Edit mode (drag edits, prompt edits, save) works on the deployed app: drafts, saved buildings
(`user/<slug>`) and the Builder's conversation live in Supabase Postgres, so any serverless instance can serve any
request; locally without `SUPABASE_DB_URL` everything keeps using `data/user/` as today.

**Architecture:** `DraftStore` (backend/drafts.py) keeps its public methods and gets a storage backend:
`FileDraftBackend` (today's `data/user/` code, moved) or `PostgresDraftBackend` (two new tables), chosen like
conversations (`persistence.from_env()`: `SUPABASE_DB_URL` set and `GUIDE_PERSIST` not `off`). Every change is
*load latest → apply → save if the version is still the one loaded* (optimistic, like
`PostgresConversations.save`), so two instances never silently overwrite each other. Saved buildings join the
catalogue per request from the backend, and sessions load building **data** through the catalogue instead of a file
path. The Builder's history is dumped into the draft row after each turn and restored on whichever instance gets
the next one.

**Tech Stack:** Python ≥ 3.12 (uv), psycopg 3 (already used by backend/persistence.py), Supabase Postgres, FastAPI,
pytest.

**Spec:** [docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md](../specs/2026-10-24-builder-edit-mode-design.md)
— §3 (drafts store), "Constraints" (Vercel: no shared memory, read-only filesystem), milestone 3 of "Delivery
order", calls 5, 10, 11.

## What exists (read first)

- `backend/drafts.py` — `Draft {id, base, name, steps, version}`, `DraftStore`: `create`, `get`, `building`
  (cached per `(id, version)`), `issues`, `plan`, `apply(draft, ops, expected_version=None)`, `undo`, `save`,
  `state`, `register`; per-draft `threading.Lock` (one process only); files under `root/.drafts/<id>.json` and
  `root/<slug>/{building.json,draft.json}`.
- `backend/app.py` — `/drafts…` routes; one in-memory `Builder` per draft (`builders`, `builder_locks`),
  `tell_builder` notes for hand edits; `drafts = DraftStore(GUIDE_USER_DIR or data/user, store.catalogue)`.
- `backend/sessions.py` — `load_catalogue()` (dataset + whatever `DraftStore` registers),
  `SessionStore.build/get` → `BuildingSession.load(catalogue[id]["path"])` (a path!).
- `backend/persistence.py` — the pattern to copy: `MemoryConversations` (tests) / `PostgresConversations`
  (`execute` with `prepare_threshold=None` for the transaction pooler, optimistic `save … where version = %s`,
  `Conflict`), `from_env()`, `plain_messages()` for Anthropic content blocks.
- `agent/builder.py` — `Builder.messages`, `notes`, `tools.pending: dict[str, Proposal]`, `usage`; no dump/restore yet.
- `supabase/migrations/` — idempotent SQL, RLS on, no policies (backend connects directly).

## Global Constraints

- No behaviour change locally without `SUPABASE_DB_URL`: `uv run pytest` stays green with the file backend.
- With the Postgres backend, nothing writes to the filesystem (Vercel's is read-only).
- Optimistic concurrency everywhere: a write carries the version it loaded; a lost race → `Conflict` → HTTP 409
  "updated elsewhere meanwhile; try again" (same wording style as conversations).
- Never write `data/train|dev|test/`; dataset buildings stay files (they are deployed: `vercel.json` excludes only
  png/svg/jsonl/equipment.csv).
- Ids/slugs never become paths or SQL text: parameters only (`%s`), draft ids still checked by `DRAFT_ID`.
- Commits via `/ship` (D-008).

## Review Focus

1. Two browser tabs (two instances) apply ops to one draft at the same moment → one wins, the other gets 409 and
   reloads; no step is lost or duplicated (test in Task 4).
2. A Builder proposal made on instance A, Apply clicked on instance B → B restores the Builder from the row and
   applies (or 409s if stale) (test in Task 5).
3. Two saves with the same name from two instances → `user/foo` and `user/foo-2`, never one overwriting the other
   (unique slug in SQL, retry on conflict) (test in Task 2).
4. A saved building opened right after save on another instance → listed in `/buildings` and loadable (catalogue per
   request, not cached forever) (test in Task 3).
5. Database down / `SUPABASE_DB_URL` wrong → `/drafts` answers 503 with a clear message, the Guide keeps working on
   dataset buildings (test in Task 2).

---

### ✅ Task 1: Storage backend interface; move today's file code behind it

**Files:** Modify `backend/drafts.py` · Test: `tests/test_drafts.py` (unchanged, must stay green), new
`tests/test_draft_backends.py`

**Interfaces — Produces:**
```python
class DraftBackend(Protocol):
    def load_draft(self, draft_id: str) -> Draft | None: ...
    def insert_draft(self, draft: Draft) -> None: ...
    def save_draft(self, draft: Draft, loaded_version: int) -> None: ...   # raises Conflict
    def save_builder(self, draft_id: str, state: dict, loaded_version: int) -> int: ...  # Task 5
    def load_builder(self, draft_id: str) -> tuple[dict | None, int]: ...               # Task 5
    def insert_building(self, slug: str, name: str, base: str, building: dict, steps: list) -> bool: ...  # False = slug taken
    def saved_buildings(self) -> list[dict]: ...          # [{"slug", "name"}]
    def load_building(self, slug: str) -> dict | None: ...
```
`FileDraftBackend(root: Path)` implements it with today's layout (`.drafts/<id>.json`, `<slug>/building.json`,
`draft.json`; builder state in `.drafts/<id>.builder.json`). `DraftStore(catalogue, backend)`; `Conflict` is
`backend.persistence.Conflict`.

- [ ] Step 1: tests for `FileDraftBackend` round trips + `save_draft` with a stale `loaded_version` → `Conflict`.
- [ ] Step 2: run → fail. Step 3: implement, `DraftStore` delegates all I/O. Step 4: `uv run pytest -q` all green
  (behaviour unchanged). Step 5: ship.

### ✅ Task 2: Postgres backend + migration

**Files:** Create `supabase/migrations/20261025120000_builder_drafts.sql`; modify `backend/drafts.py`
(`PostgresDraftBackend`, `MemoryDraftBackend` for tests), `backend/app.py` (choose backend; 503 on DB errors) ·
Test: `tests/test_draft_backends.py`

Schema (idempotent; RLS on, no policies, like `conversations`):
```sql
create table if not exists public.builder_drafts (
    id text primary key, base text not null, name text not null,
    steps jsonb not null default '[]', version integer not null default 0,
    builder jsonb, builder_version integer not null default 0,
    created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table if not exists public.saved_buildings (
    slug text primary key, name text not null, base text not null,
    building jsonb not null, steps jsonb not null, created_at timestamptz not null default now());
```
`insert_building` = `insert … on conflict (slug) do nothing returning slug` → `False` when taken (the store then
tries `-2`, `-3`, …). `save_draft` = `update … set steps, version = %s+1 where id = %s and version = %s returning
version` → no row → `Conflict`.

- [ ] Step 1: tests run against `MemoryDraftBackend` (same semantics) and, when `SUPABASE_DB_URL` is set, the real
  one (`pytest.mark.skipif`), incl. Review Focus 3 and 5 (`psycopg.OperationalError` → `/drafts` 503).
- [ ] Step 2–4: implement; apply the migration with the command in
  [commands.md](../../../../docs/guides/commands.md#conversation-persistence-supabase-postgres); green. Step 5: ship.

### ✅ Task 3: Catalogue and sessions read saved buildings from the backend

**Files:** Modify `backend/sessions.py`, `backend/drafts.py`, `backend/app.py` · Test: `tests/test_drafts.py`,
`tests/test_backend.py`

- Catalogue entries for saved buildings carry no path: `{"id": "user/<slug>", "split": "user", "name", "source":
  "saved"}`; add `building_data(catalogue_entry) -> dict` (file → json, saved → `backend.load_building`) and use it
  in `SessionStore.build/get` (`BuildingSession(BuildingMap(data))` instead of `BuildingSession.load(path)`) and in
  `DraftStore.base_building`.
- `/buildings` and `UnknownBuilding` checks refresh saved buildings from the backend per request (a few ms; cache
  for ≤ 5 s per instance if needed) — Review Focus 4.

- [ ] Steps: test "save on store A, list + open session on a fresh store B sharing the backend" → fail → implement →
  green → ship.

### ✅ Task 4: Cross-instance correctness for drafts

**Files:** Modify `backend/drafts.py`, `backend/app.py` · Test: `tests/test_draft_backends.py`

- `get` always reloads the row when the backend is shared (or compares versions like `SessionStore.get`);
  `apply` / `undo` = reload → apply → `save_draft(loaded_version)`; on `Conflict` reload and retry once, then 409.
  `expected_version` (Builder proposals) is checked against the reloaded draft.
- The in-process per-draft lock stays (serialises one instance); the version check covers the rest.

- [ ] Steps: test two `DraftStore`s on one `MemoryDraftBackend` interleaving applies (Review Focus 1) → fail →
  implement → green → ship.

### ✅ Task 5: Persist the Builder's conversation

**Files:** Modify `agent/builder.py` (`dump() -> dict`, `Builder.restore(store, draft, state, client) -> Builder`),
`backend/app.py` (`builder_for` restores from `load_builder`; after each turn / apply → `save_builder`;
`tell_builder` writes its note through the same path) · Test: `tests/test_builder.py`, `tests/test_drafts.py`

- State: `{"format": 1, "messages": plain_messages(builder.messages), "notes", "pending": [asdict(p) …],
  "next_id", "usage": asdict(usage), "system": builder.system}` (keep the system blocks, like conversations, so the
  prompt cache prefix survives).
- Concurrency: `builder_version` optimistic; a lost race → 409 "send the message again".

- [ ] Steps: test "turn on Builder A (store A) → apply on store B with a restored Builder" (Review Focus 2) and a
  dump/restore round trip → fail → implement → green → ship.

### Task 6: Deploy and smoke test

- [ ] Apply the migration to the Supabase project; set nothing new (reuses `SUPABASE_DB_URL`, `ANTHROPIC_API_KEY`).
- [ ] Deploy; on the public URL: open a building → Edit → drag a corner → reload the page (draft resumes) → prompt
  "make <room> 1 m wider to the <side>" → Apply → Save → the saved building opens and the Guide routes in it.
- [ ] Docs: commands.md (deploy section: tables, that `/drafts` needs the DB on Vercel), ai-agents.md Builder status,
  project-state + log. Ship.

## Left to the implementer

- Whether `DraftStore` caches materialised buildings per instance (by `(id, version)` it is safe).
- Retry counts / backoff on `Conflict`; the 5 s catalogue cache.
- Whether old drafts are ever cleaned up (not needed for the hackathon).
