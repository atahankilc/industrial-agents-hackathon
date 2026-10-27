# Steward

Talk to your building. Agent-first indoor navigation and building management. Ask a building where things are, how to get there, and what changes when a lift
closes or a forklift blocks an aisle; edit the building or create one from floor plans. A deterministic
geometry/graph core computes every answer and the LLM handles the language.

Started at the Industrial Agents Hackathon 2026, Track 01 (Synera); submitted 2026-10-25, now in ongoing
development. The submission and the weekend's history are in [archive/hackathon/](archive/hackathon/README.md).

Project knowledge base: [CLAUDE.md](CLAUDE.md) → [docs/README.md](docs/README.md). All commands:
[docs/guides/commands.md](docs/guides/commands.md).

## Repository layout

```
frontend/          React + Vite app: map, building search, plan view, Guide, Edit mode
backend/           all Python, one package `backend`
  api/             FastAPI server: HTTP endpoints, sessions, Supabase persistence, voice, live building
  agents/          LLM layer: the Guide, Builder and Creator agents and their tools
  core/            deterministic engine: route graph, geometry, solvers, edits, plan import (no LLM, no HTTP)
tests/             pytest; tests/kit_oracles/ holds the official kit scorer and question parsers used as oracles
data/              the kit's buildings, one folder each (data/buildings/<id>/) + manifest.csv
scripts/           repo tooling and eval scripts
docs/ memory-bank/ knowledge base and project state; archive/ is read-only history
```

A request goes `frontend → backend/api → backend/agents → backend/core`: the agents choose what to compute, the
core computes it. `core` never imports `agents` or `api`; the only upward imports are the Builder
(`builder.py`, `builder_tools.py`) using `backend/api/drafts.py` and `backend/api/persistence.py`.

## Setup

You need Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node.js for the app, and an Anthropic API key. The
organiser kit's dataset is committed in `data/`, so one clone is enough.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # if uv is missing
git clone https://github.com/atahankilc/steward.git
cd steward
uv sync
cp .env.example .env                                  # put ANTHROPIC_API_KEY in .env (never commit it)
```

## Running the app

```bash
npm run dev                                           # backend + app; open http://localhost:5390
```

`npm run dev` (repo root, `scripts/dev.sh`) starts the backend on **8390** and the app on **5390**, ports picked to
stay clear of other local projects; Ctrl-C stops both. Move them with `BACKEND_PORT=… FRONTEND_PORT=… npm run dev`.
Without a `.env` the Guide runs offline (no key needed). Each side on its own:

```bash
uv run --env-file .env uvicorn backend.api.app:app --port 8390  # backend
cd frontend && npm install && npm run dev                      # app on http://localhost:5390 (vite.config.ts)
```

## Tests

```bash
uv run pytest -q                                      # offline tests
python3 scripts/check_links.py                        # docs and memory-bank links
cd frontend && npm run build                          # type-check + production bundle
```

## Benchmark (archived)

The hackathon benchmark runners, the kit evaluator and the v1 Guide are in
[archive/hackathon/benchmark-code/](archive/hackathon/benchmark-code/README.md), with how to restore and run them.
`tests/kit_oracles/score.py` (the organisers' official scorer, never edit it) stays: the solver tests use it. The rest of the
organiser kit (starter agent) is in `archive/initial-repo/`.

## Licences

Our code is MIT ([LICENSE](LICENSE)). Kit code and data keep their own terms: see [NOTICE.md](NOTICE.md),
[ATTRIBUTION.md](ATTRIBUTION.md) and [data/README.md](data/README.md). Anything derived from the OpenStreetMap
buildings stays under the ODbL and credits © OpenStreetMap contributors.
