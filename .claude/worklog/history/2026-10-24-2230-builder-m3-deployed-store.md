# Builder M3: drafts, saved buildings and Builder history in Supabase (deployed store)

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-24 22:30
- **Related:** docs/superpowers/plans/2026-10-24-builder-edit-mode-m3.md (Tasks 1–5), spec "Milestone 3 decisions"

## Summary
The Edit mode's drafts, saved buildings and the Builder's conversation get a storage backend: files locally (as
before), Postgres (Supabase) when SUPABASE_DB_URL is set, so any serverless instance can serve any request. Writes are
version-checked (409 on a lost race), database errors are 503, saved buildings are shared via the catalogue.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `DraftBackend` protocol with `FileDraftBackend` (today's `data/user/` layout + `.drafts/<id>.builder.json`), `MemoryDraftBackend`, `PostgresDraftBackend`; `backend_from_env` picks Postgres iff `db_url()` | `backend/drafts.py` | read; `uv run pytest -q tests/test_draft_backends.py -k "round_trip or claimed"` |
| C2 | `DraftStore(source, catalogue)` keeps its signature (a Path → file backend); every change = sync → edit → `save_draft(loaded_version)`, redone up to `SAVE_ATTEMPTS = 3`, then `Conflict`; no op lost or duplicated across two instances | `backend/drafts.py:DraftStore.change/apply/undo` | `uv run pytest -q tests/test_draft_backends.py -k "interleaved or retried or proposal_version"` |
| C3 | Same name saved on two instances → `user/foo` and `user/foo-2` (atomic slug claim) | `DraftStore.save`, `insert_building` | `-k same_name` |
| C4 | Saved buildings join other instances' catalogues (`refresh`, ≤5 s, forced for unknown ids); in Postgres mode no `path`, data from the DB; sessions use `SessionStore.known` / `load_session` | `backend/drafts.py`, `backend/sessions.py` | `-k opens_on_another`; read sessions.py |
| C5 | `persistence.PostgresConnection` (shared execute) + `db_url()`; `PostgresConversations` behaviour unchanged | `backend/persistence.py` | `uv run pytest -q tests/test_persistence.py` |
| C6 | `Builder.dump` / `Builder.restore` (format 1; system, messages, corpus, notes, closed, pending without preview, next_id, usage); `BuilderTools.next_id` replaces the itertools counter | `agent/builder.py`, `agent/builder_tools.py` | `-k dump_restore` |
| C7 | App: Builder loaded per request (restored if the stored version is newer), stored after turn / apply / cancel / hand-edit note; lost race in the stream → error line "send the message again"; `Conflict` → 409, `psycopg.Error` → 503 app-wide; `/buildings` refreshes quietly | `backend/app.py` | `-k "another_instance or lost_a_race or keeps_losing or database_down"` |
| C8 | Migration creates `builder_drafts` + `saved_buildings` (idempotent, RLS on, no policies); applied to the Supabase project | `supabase/migrations/20261025120000_builder_drafts.sql` | read; live test below |
| C9 | Edit mode reloads the draft after a 409 | `frontend/app/src/edit/EditMode.tsx:run` | read; `cd frontend/app && npm run build` |
| C10 | Docs + memory bank updated (plan status/as-built, spec M3 decisions, ai-agents, commands, README, project-state, log) | docs, memory-bank | read; `python3 scripts/check_links.py` |

## Checks I ran

- `env -u SUPABASE_DB_URL uv run pytest -q` → `746 passed, 2 skipped` (baseline before: 729 passed, 1 skipped)
- `uv run pytest -q tests/test_draft_backends.py` ×3 → `17 passed, 1 skipped` each time
- `PERSIST_LIVE_TEST=1 uv run --env-file .env pytest -q tests/test_draft_backends.py tests/test_persistence.py -k live` → `2 passed`
- Two local uvicorn instances (ports 8771/8772) on Supabase, GUIDE_LLM=offline: create + op on A → B sees 1 step;
  Builder proposal on A → applied on B (200, 2 steps); save on A → listed on B, session on B 200, Guide route on B 200;
  `GUIDE_USER_DIR` never created (nothing written to disk). Smoke rows deleted afterwards.
- `cd frontend/app && npm run build` → `✓ built`
- `python3 scripts/check_links.py` → `OK: all links resolve in 32 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (M3 built, next: deploy)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none formal; M3 decisions recorded in the spec (owner change by Utku)
- [x] docs touched: M3 plan, builder-edit-mode spec, ai-agents.md, commands.md, docs/README.md

## Known gaps / not done
- Task 6 (deploy to Vercel + public smoke test) not done.
- Old drafts are never cleaned up; Supabase has an unused empty `building_edits` table (left alone).
- A drag on instance A while a Builder turn runs on instance B makes B's turn end with "send the message again".

## Verification rounds
- Round 1: VERDICT PASS (tree ad5b60b4)

---

# Verification report

VERDICT: PASS
TREE: ad5b60b491d71091a8113795a9267bab47917c3e

## Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | DraftBackend Protocol + File/Memory/Postgres backends; backend_from_env → Postgres iff db_url(); -k "round_trip or claimed" → 7 passed, 1 skipped |
| C2 | MET | DraftStore(source, catalogue); change() loops SAVE_ATTEMPTS=3, re-raises Conflict on last; -k "interleaved or retried or proposal_version" → 3 passed |
| C3 | MET | save loops slugs via insert_building (on conflict do nothing); -k same_name → 1 passed |
| C4 | MET | refresh (5 s TTL, forced in known()), path only when building_path; sessions user_buildings/known/load_session; -k opens_on_another → 1 passed |
| C5 | MET | PostgresConnection extracted unchanged, db_url(); tests/test_persistence.py → 7 passed, 1 skipped |
| C6 | MET | Builder.dump/restore (format 1, preview None), BuilderTools.next_id; -k dump_restore → 1 passed |
| C7 | MET | load_builder/store_builder, stream "send the message again", Conflict→409, psycopg.Error→503, /buildings quiet refresh; -k "another_instance or lost_a_race or keeps_losing or database_down" → 4 passed |
| C8 | MET | migration idempotent, RLS on both, no policies; live -k live → 2 passed |
| C9 | MET | EditMode.tsx run(): 409 → api.draft → setState; npm run build ✓ |
| C10 | MET | plan, spec, ai-agents, commands, README, project-state, log; check_links OK 32 files |

## Standard checks
- pytest: 746 passed, 2 skipped. test_draft_backends ×3: 17 passed, 1 skipped. Live: 2 passed. npm build ok. Links OK.
- secrets: none; no .env staged. score.py unchanged. hard-coding: none. TODO/FIXME: none.

## Undeclared changes
- None of significance. Minor (implied by C7): tell_builder takes a Draft; drops the note silently on a second Conflict (commented; close to known gap 3). Not a blocker.

## Required fixes
None.
