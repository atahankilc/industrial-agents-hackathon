# Conversation persistence on Supabase Postgres

- **Author:** Claude (persistence session) · **Date:** 2026-10-24
- **Related:** D-006 (Supabase for Postgres), docs/research/stack-options.md §2/§9, docs/guides/commands.md

## Summary
Serverless instances share no memory, so the Guide's conversation state now lives in a Supabase `conversations`
table. `backend/persistence.py` turns a BuildingSession + Guide into JSON and back. Applied changes are replayed
from the base building to restore it. `SessionStore` uses this when `SUPABASE_DB_URL` is set and saves after every
turn, with optimistic version checks (a lost race gives a 409). Without the variable, behaviour is unchanged
(in-memory).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `dump`/`restore` round-trip profile, applied changes (replayed via `changed_building`, same snapshots), pending, events, last_route, change-id counter, Guide system/messages/corpus/turn/proposed_in_turn/usage/profile_note | `backend/persistence.py:dump`, `restore` | read; `uv run pytest -q tests/test_persistence.py` |
| C2 | `MemoryConversations` and `PostgresConversations` share one contract (version/load/insert/save); save is optimistic and raises `Conflict` on a version mismatch | `backend/persistence.py` | read; `test_concurrent_save_conflicts_and_drops_stale_copy` |
| C3 | Postgres uses `prepare_threshold=None` (Transaction pooler) and one reused connection that is reopened after an `OperationalError` | `PostgresConversations.execute` | read |
| C4 | `SessionStore` caches conversations; with a backend, `get` checks the stored version and restores the conversation when it is newer; `create`/`get_or_create` insert; `save` drops the stale cached copy on conflict; `switch_building` saves | `backend/sessions.py:SessionStore` | read; tests in `tests/test_persistence.py` |
| C5 | Without `SUPABASE_DB_URL` (or with `GUIDE_PERSIST=off`) the store is in-memory as before | `persistence.from_env`, `SessionStore.__init__` | `test_without_backend_store_stays_in_memory`; `uv run pytest -q tests/test_backend.py` → 17 passed |
| C6 | `/chat` saves after the turn (Conflict → 409); `PUT /sessions/{id}/building` Conflict → 409; `/v1/chat/completions` saves and, on Conflict, speaks an apology instead | `backend/app.py:save_or_409`, `chat`, `switch_building`, `chat_completions` | read |
| C7 | Migration creates `public.conversations(id, building, state jsonb, version, created_at, updated_at)` idempotently with RLS enabled and no policies | `supabase/migrations/20261024120000_conversations.sql` | read |
| C8 | New dependency `psycopg[binary]>=3.2` (locked 3.3.6) | `pyproject.toml`, `uv.lock` | `git diff --cached pyproject.toml` |
| C9 | `.env.example` lists `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL` with empty values only; `.env` is not staged | `.env.example` | `git diff --cached .env.example`; `git diff --cached --name-only` has no `.env` |
| C10 | Docs: commands.md has a persistence section (pooler, GUIDE_PERSIST, tests, how to apply migrations); project-state priority 3 and a log entry updated | `docs/guides/commands.md`, `memory-bank/project-state.md`, `memory-bank/log.md` | read; `python3 scripts/check_links.py` |

## Checks I ran

- `uv run pytest -q` → `154 passed, 1 skipped in 18.81s` (the skip is the live test)
- `uv run pytest -q tests/test_persistence.py` → `7 passed, 1 skipped`
- `PERSIST_LIVE_TEST=1 uv run --env-file .env pytest -q tests/test_persistence.py` → `8 passed in 1.77s` (live Supabase)
- Migration applied on Supabase via the pooler → columns `id text, building text, state jsonb, version integer,
  created_at/updated_at timestamptz`; `relrowsecurity = True`; re-applied with the documented command →
  `applied-idempotent`
- Anon key `GET /rest/v1/conversations?select=id` → `status 200 rows 0` (RLS blocks the public API)
- Live Claude (`claude-sonnet-5-5`, effort low), two stores on one Postgres: "I use a wheelchair." on A
  (`set_profile`, v2) → route asked on B (`find_route`, v3, route profile `step-free, doors at least 0.8 m wide
  (assumed)`, ungrounded `[]`, cache_read_input_tokens 11312). Test rows deleted afterwards.
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (priority 3: Supabase done, Vercel next)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none (implements accepted D-006)
- [x] docs touched: `docs/guides/commands.md`

## Known gaps / not done
- Vercel config not done yet (next chunk); nothing has been deployed.
- Per-user profile persistence across conversations isn't covered: there is no user identity yet. Only the
  conversation is persisted.
- The point-cloud/route caches (`MapView`) aren't persisted; they are rebuilt per instance (CPU on the first `/points`).
- Each request does one `select version` round trip; no connection pool (one connection per process).
- A turn that loses a save race is lost (409 / spoken apology); there is no automatic retry.
- Prompt changes in a deploy reach only new conversations, because the system blocks are stored.

## Verification rounds
- Round 1: VERDICT: PASS (tree f4427f3e2b86c544c1b95bf4cc563991f133ac28)

## Verification report (round 1)

VERDICT: PASS
TREE: f4427f3e2b86c544c1b95bf4cc563991f133ac28

### Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | `dump` covers profile/applied/pending/events/last_route and the guide's system/messages/corpus/turn/proposed_in_turn/usage/profile_note; `restore` replays `changed_building`, rebuilds snapshots and resets `_ids` to max+1; replay and id tests pass; `7 passed, 1 skipped` |
| C2 | MET | Both backends have version/load/insert/save; Memory and Postgres `update … where version = %s returning version` raise `Conflict`; conflict test passes |
| C3 | MET | `psycopg.connect(..., autocommit=True, prepare_threshold=None, connect_timeout=10)` on one reused connection under a lock; on `OperationalError` it resets the connection and retries once |
| C4 | MET | `get` compares versions and restores; `create`/`get_or_create` insert; `save` drops the cache on Conflict and re-raises; `switch_building` saves |
| C5 | MET | `from_env` returns None without `SUPABASE_DB_URL` or with `GUIDE_PERSIST=off`; test_backend `17 passed` |
| C6 | MET | `save_or_409`; chat saves after reply; switch_building 409; completions apology on Conflict |
| C7 | MET | `create table if not exists public.conversations` (6 columns), RLS enabled, no policies |
| C8 | MET | `psycopg[binary]>=3.2`; uv.lock psycopg + psycopg-binary 3.3.6 |
| C9 | MET | 4 SUPABASE_* vars with empty values; no `.env` staged |
| C10 | MET | commands.md persistence section; project-state priority 3 and log entry staged; links OK on the working tree and on a staged export |

### Standard checks
- pytest `154 passed, 1 skipped in 17.67s`; links OK; no secrets; score.py unchanged; no hard-coding (only the train building and `test-<uuid>` in tests).
- Not re-run: live Supabase test, migration, anon REST check, live Claude (they need credentials and spend).

### Undeclared changes
- None staged. Unstaged edits in docs/kit/route-model.md, memory-bank/open-questions.md, log.md and project-state.md belong to a separate handoff chunk and are not part of this commit.
- Minor, not blocking: `SessionStore.create` ignores a False result from `insert`; its only caller passes a fresh uuid.
