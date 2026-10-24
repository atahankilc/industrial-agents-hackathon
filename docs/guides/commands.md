---
id: guide-commands
summary: Setup and every command for chatting, evaluating on dev, scoring and producing the test submission.
sources: [archive/initial-repo/README.md §5-6, archive/initial-repo/starter_agent/README.md, benchmark/evaluate.py, backend/app.py]
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
# our agent (function answer(building_directory: Path, question_text: str) -> str):
uv run --env-file .env python -m benchmark.evaluate data/dev --agent my_agent:answer
# only some kinds:
uv run --env-file .env python -m benchmark.evaluate data/dev --agent my_agent:answer --kinds errand what_if_door
```

Results: `agent_output/benchmark/<--name, default results>.jsonl` (question, expected answer, reply, correct).

## Produce the test submission

```bash
uv run --env-file .env python -m benchmark.evaluate data/test --agent my_agent:answer --submission-csv team_<name>.csv
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
curl -s localhost:8765/health
curl -s -X POST localhost:8765/sessions -H 'content-type: application/json' -d '{"building":"train/proc-campus-train-000"}'
curl -s -X POST localhost:8765/chat -H 'content-type: application/json' -d '{"session_id":"<id>","message":"Where is the printer?"}'
curl -sN -X POST localhost:8765/v1/chat/completions -H 'content-type: application/json' -H 'X-Session-Id: demo' \
     -d '{"stream":true,"messages":[{"role":"user","content":"I use a wheelchair"}]}'
uv run pytest -q tests/test_guide.py tests/test_backend.py                      # offline tests
```

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | – | `{"ok", "llm": "anthropic"\|"offline"}` |
| GET | `/buildings` | – | `[{"id": "train/proc-campus-train-000", "split", "name"}]` |
| POST | `/sessions` | `{"building"?}` | `{"session_id", "building", "overview"}` (unknown building → 422) |
| GET | `/sessions/{id}` | – | building, profile, applied/pending changes, event count |
| PUT | `/sessions/{id}/building` | `{"building"}` | fresh session on another building, same id |
| POST | `/chat` | `{"session_id", "message"}` | `{"reply", "tool_calls", "events", "ungrounded"}` |
| GET | `/events` | `?session_id=&after=N` | `{"events": [...since N], "next"}` — UI highlights, routes, changes |
| POST | `/v1/chat/completions` | OpenAI body, `stream` | OpenAI-compatible (SSE: `"... "` first, then sentences, `data: [DONE]`) for an ElevenLabs Custom LLM |

`/v1/chat/completions` uses only the last user message (the Guide keeps its own history). Session id, first
match wins: body `session_id`, `elevenlabs_extra_body.session_id`, header `X-Session-Id`, body `user`; none → a
shared `default` session. How ElevenLabs actually sends it, and its system `tools`, are UNVERIFIED
([elevenlabs.md](../research/elevenlabs.md)). Sessions are in memory (lost on restart; Supabase later, D-006).

## Sunday benchmark

`agent.run_benchmark <building_dir> <questions file> <answers.json> [--csv …]` — documented in
[`BENCHMARK.md`](../../BENCHMARK.md). Output format still unannounced →
[Q-001](../../memory-bank/open-questions.md#q-001).

## Related
- [starter-agent.md](../kit/starter-agent.md#evaluation) · [scoring.md](../challenge/scoring.md) · [ai-agents.md](../architecture/ai-agents.md)
