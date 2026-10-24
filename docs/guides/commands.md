---
id: guide-commands
summary: Setup and every command for chatting, evaluating on dev, scoring and producing the test submission.
sources: [archive/initial-repo/README.md §5-6, archive/initial-repo/starter_agent/README.md, benchmark/evaluate.py, backend/app.py, agent/run_benchmark.py, agent/run_benchmark_v1.py, agent/guide_v1/__main__.py, BENCHMARK.md]
related: [../kit/starter-agent.md, ../challenge/scoring.md]
---

# Commands

[Docs index](../README.md)

All commands run from the **repo root**. Outputs go to `agent_output/` (git-ignored).

## Setup

```bash
uv sync                      # creates .venv with python ≥3.12 (system python3 is 3.9 — too old)
cp .env.example .env         # add ANTHROPIC_API_KEY
```

Without syncing, one-off scripts can run with `uv run --no-project --python 3.12 python …` (stdlib only).

## Starter agent (archived, still runnable)

```bash
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m starter_agent data/dev/proc-factory-dev-003
```

## Evaluate on dev (do this before touching test)

```bash
# warm-up questions, tools only, free (verified 369/369 on 2026-10-24):
PYTHONPATH=archive/initial-repo uv run python -m starter_agent.evaluate data/dev --oracle
# benchmark questions with the starter agent (~$0.10–0.25/question):
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m benchmark.evaluate data/dev --per-kind 3
# our agent, agent/answer.py (verified 138/138 on 2026-10-24):
uv run --env-file .env python -m benchmark.evaluate data/dev --agent agent.answer:answer
# only some kinds:
uv run --env-file .env python -m benchmark.evaluate data/dev --agent agent.answer:answer --kinds errand what_if_door
```

Results: `agent_output/benchmark/<--name, default results>.jsonl` (question, expected answer, reply, correct).

## Produce the test submission

```bash
uv run --env-file .env python -m agent.run_benchmark_v1 data/test data/test/questions.csv submissions/team_jaRAG.csv
# same replies via the kit evaluator (checked identical on 2026-10-24):
uv run --env-file .env python -m benchmark.evaluate data/test --agent agent.answer:answer --submission-csv submissions/team_jaRAG.csv
```

Format rules: [scoring.md](../challenge/scoring.md#submission-format).

## Our deterministic pipeline

```bash
uv run python scripts/validate_solvers.py [--kinds errand] [-v]          # solvers on gold inputs, train+dev
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name dev
PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv agent_output/test_answers.json --csv team_<name>.csv
```

## Backend (Guide API)

FastAPI app in `backend/` wrapping the Building Guide ([ai-agents.md](../architecture/ai-agents.md#implementation--agentguidepy-2026-10-24)).
Without `ANTHROPIC_API_KEY` it runs the offline rule-based client; `GUIDE_LLM=offline|anthropic` forces either.

```bash
GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765          # no key needed
uv run --env-file .env uvicorn backend.app:app --port 8765            # real Claude once the key is set
# GUIDE_MODEL (default claude-opus-5-5), GUIDE_EFFORT (default medium), GUIDE_BUILDING (default train/proc-campus-train-000)
# voice turns: GUIDE_REWRITER=off disables the transcript rewriter (D-013), GUIDE_REWRITER_MODEL (default claude-haiku-5-5)
curl -s localhost:8765/health
curl -s -X POST localhost:8765/sessions -H 'content-type: application/json' -d '{"building":"train/proc-campus-train-000"}'
curl -s -X POST localhost:8765/chat -H 'content-type: application/json' -d '{"session_id":"<id>","message":"Where is the printer?"}'
curl -sN -X POST localhost:8765/v1/chat/completions -H 'content-type: application/json' -H 'X-Session-Id: demo' \
     -d '{"stream":true,"messages":[{"role":"user","content":"I use a wheelchair"}]}'
uv run pytest -q tests/test_guide.py tests/test_backend.py                      # offline tests
uv run --env-file .env python scripts/live_guide.py [--model claude-sonnet-5-5] [--effort low] [--channel voice]   # live, ~$0.05–0.16
```

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | – | `{"ok", "llm": "anthropic"\|"offline"}` |
| GET | `/buildings` | – | `[{"id": "train/proc-campus-train-000", "split", "name"}]` |
| POST | `/sessions` | `{"building"?}` | `{"session_id", "building", "overview"}` (unknown building → 422) |
| GET | `/sessions/{id}` | – | building, profile, applied/pending changes, event count |
| PUT | `/sessions/{id}/building` | `{"building"}` | fresh session on another building, same id |
| POST | `/chat` | `{"session_id", "message", "channel"?, "photo"?}` | `{"reply", "tool_calls", "events", "ungrounded", "spoken"}` — `channel: "voice"` fills `spoken`; `photo` = base64 data URL (jpeg/png/webp, ≤1.5 M chars), shown to the Guide for this turn only |
| POST | `/chat/stream` | same as `/chat` | NDJSON: `{"type":"step","kind":"tool"\|"tool_done"\|"check",…}` while the Guide works, then `{"type":"reply",…/chat payload}` or `{"type":"error","detail"}` |
| GET | `/events` | `?session_id=&after=N` | `{"events": [...since N], "next"}` — UI highlights, routes (with `vertices` + turn-by-turn `legs`, `core/directions.py`), changes |
| POST | `/drafts` | `{"base"}` (catalogue id) | Edit mode: new draft copy → `{"draft": {id, base, name, steps}, "building", "issues"}` (unknown base → 422) |
| GET | `/drafts/{id}` | – | same shape (unknown / malformed id → 404) |
| GET | `/drafts/{id}/points` | – | point-cloud export of the draft (3D preview) |
| POST | `/drafts/{id}/ops` | `{"ops": [{"op": …}]}` (`core/edits.py`) | applied as one undo step → same shape; bad op → 422 with the reason |
| POST | `/drafts/{id}/undo` | – | drops the last step (nothing to undo → 409) |
| POST | `/drafts/{id}/save` | `{"name"}` | `{"building": "user/<slug>", "issues"}` — written to `GUIDE_USER_DIR` (default `data/user/`, gitignored), listed in `/buildings`; name clash → `-2` |
| POST | `/v1/chat/completions` | OpenAI body, `stream` | OpenAI-compatible (SSE: `"... "` first, then sentences, `data: [DONE]`) for an ElevenLabs Custom LLM |

`/v1/chat/completions` uses only the last user message (the Guide keeps its own history). Session id, first
match wins: body `session_id`, `elevenlabs_extra_body.session_id`, header `X-Session-Id`, body `user`; none → a
shared `default` session. How ElevenLabs actually sends it, and its system `tools`, are UNVERIFIED
([elevenlabs.md](../research/elevenlabs.md)). Sessions are in memory unless
`SUPABASE_DB_URL` is set (see below).

### Conversation persistence (Supabase Postgres)

With `SUPABASE_DB_URL` in `.env` (the **Transaction pooler** URI, port 6543; the direct `db.<project>.supabase.co`
host is IPv6-only and doesn't resolve here) every conversation is stored in the `conversations` table and every turn
is saved, so any backend instance can continue it ([backend/persistence.py](../../backend/persistence.py)).
`GUIDE_PERSIST=off` forces in-memory sessions. A save that loses a race to another instance → HTTP 409.

```bash
uv run --env-file .env uvicorn backend.app:app --port 8765                     # persisted sessions
uv run pytest -q tests/test_persistence.py                                     # offline (two stores, one fake DB)
PERSIST_LIVE_TEST=1 uv run --env-file .env pytest -q tests/test_persistence.py  # + live round trip on Supabase
```

Schema changes go in `supabase/migrations/` (idempotent SQL). Apply one with:

```bash
uv run --env-file .env python -c "import os,sys,psycopg; psycopg.connect(os.environ['SUPABASE_DB_URL'], autocommit=True, prepare_threshold=None).execute(open(sys.argv[1]).read())" supabase/migrations/<file>.sql
```

## Frontend app

```bash
GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765    # or: uv run --env-file .env uvicorn … (real Claude)
cd frontend/app && npm install && npx vite --port 5181          # open http://localhost:5181 (?building=<id>)
cd frontend/app && npm run build                                # type-check + production bundle in dist/
```

**Edit mode** (header switch View / Edit): edits a draft copy of the current building on a 2D plan — click a room
and drag its corners, drag doors along walls, drag things (R / Shift+R rotates), ⌘Z undoes; problems are listed on
the right; **Save** writes `user/<slug>` (local `data/user/`, or `GUIDE_USER_DIR`) and switches the Guide to it
(the conversation restarts). The draft id is kept in `localStorage` per building. Local store only for now — on the
deployed app `/drafts` can't write (milestone 3).

Vite proxies `/api/*` to the backend (`BACKEND_URL`, default `http://127.0.0.1:8765`). Design and data path:
[visualization.md](../product/visualization.md#app-and-data-path).

## Deploy (Vercel)

One Vercel project, two [Services](https://vercel.com/docs/services) in [`vercel.json`](../../vercel.json) (D-006):
`web` = the Vite app in `frontend/app/`, `api` = FastAPI `backend.app:app` from the repo root. The rewrite
`/api/(.*)` → `api` keeps the `/api` prefix in the path, so `backend/app.py` strips it (`StripPrefix`); everything
else goes to `web`. The function excludes everything the backend doesn't read (kept: code, `data/**/building.json`,
`data/manifest.csv`, about 49 MB plus packages). `maxDuration` is 300 s, the Hobby maximum.

Atahan (once): Vercel → *Add New → Project* → import the GitHub repo. Leave Root Directory at the repo root
(`vercel.json` defines the services). Add the env vars below under *Settings → Environment Variables*. Deploy.

| Var | Value |
|---|---|
| `ANTHROPIC_API_KEY` | key (without it the Guide runs the offline rules) |
| `SUPABASE_DB_URL` | Transaction pooler URI (port 6543), same as `.env` |
| `GUIDE_MODEL` / `GUIDE_EFFORT` | optional (defaults `claude-opus-5-5` / `medium`; Sonnet + `low` is cheaper and faster) |
| `CORS_ORIGINS` | optional; the frontend is same-origin, so it isn't needed |

Smoke test after a deploy: `curl -s https://<deployment>/api/health` → `{"ok":true,"llm":"anthropic"}`. Then
in the app, say "I use a wheelchair" and ask for a route in the next message: the route must be step-free (proof
that persistence works across instances). `uv run pytest -q tests/test_deploy.py` checks the config locally.
UNVERIFIED until the first deploy: Services (beta) with a service root of `./` next to `frontend/app/`, the
exclude globs as Vercel applies them, cold-start time.

## v1 Guide and pipeline (terminal)

Scripted conversations (`tests/guide_conversations/*.json`) run against the canonical Guide (`agent/guide.py`):

```bash
# live API: PASS/FAIL per turn + seconds + cost, exit 1 on a failure; --model / --effort override GUIDE_MODEL / GUIDE_EFFORT
uv run --env-file .env python scripts/eval_guide.py [tests/guide_conversations/lift_closure.json ...] [--model claude-sonnet-5-5 --effort low]
# offline checks of the conversation files and of the checker (no API)
uv run pytest tests/test_guide_conversations.py -q
```

The second Guide (`agent/guide_v1/`, branch `1-agentic-yarag`) and its benchmark pipeline (`agent/answer.py` →
`core/solvers_v1.py`) sit beside the canonical ones; the backend and UI use `agent/guide.py`.

```bash
# terminal REPL (multi-turn, remembers position / step-free / closures); --show-tools prints each tool call
uv run --env-file .env python -m agent.guide_v1 data/dev/proc-campus-dev-001 --show-tools
# v1 benchmark run: .csv (submission) or .json (reply + ids + solver result + route) out
uv run --env-file .env python -m agent.run_benchmark_v1 <building_dir> <questions> <answers.csv|answers.json>
```

Design: [guide-agent spec](../superpowers/specs/2026-10-24-guide-agent-design.md). A full eval run costs about $0.27.

## Sunday benchmark

`agent.run_benchmark <building_dir> <questions file> <answers.json> [--csv …]` — documented in
[`BENCHMARK.md`](../../BENCHMARK.md). Output format still unannounced →
[Q-001](../../memory-bank/open-questions.md#q-001).

## Related
- [starter-agent.md](../kit/starter-agent.md#evaluation) · [scoring.md](../challenge/scoring.md) · [ai-agents.md](../architecture/ai-agents.md)
