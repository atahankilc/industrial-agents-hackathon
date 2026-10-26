# Talk to Your Building

Agent-first indoor navigation. Ask a building where things are, how to get there, and what changes when a lift
closes or a forklift blocks an aisle; edit the building or create one from floor plans. A deterministic
geometry/graph core computes every answer and the LLM handles the language.

Started at the Industrial Agents Hackathon 2026, Track 01 (Synera); submitted 2026-10-25, now in ongoing
development. The submission and the weekend's history are in [archive/hackathon/](archive/hackathon/README.md).

Project knowledge base: [CLAUDE.md](CLAUDE.md) → [docs/README.md](docs/README.md). All commands:
[docs/guides/commands.md](docs/guides/commands.md).

## Setup

You need Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node.js for the app, and an Anthropic API key. The
organiser kit's dataset is committed in `data/`, so one clone is enough.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # if uv is missing
git clone https://github.com/atahankilc/industrial-agents-hackathon.git
cd industrial-agents-hackathon
uv sync
cp .env.example .env                                  # put ANTHROPIC_API_KEY in .env (never commit it)
```

## Running the app

```bash
uv run --env-file .env uvicorn backend.app:app --port 8765     # backend (GUIDE_LLM=offline: no key needed)
cd frontend/app && npm install && npx vite --port 5181         # app on http://localhost:5181
```

## Tests

```bash
uv run pytest -q                                      # offline tests
python3 scripts/check_links.py                        # docs and memory-bank links
cd frontend/app && npm run build                      # type-check + production bundle
```

## Benchmark (kit scorer)

`benchmark/score.py` is the organisers' official scorer; never edit it. To re-score our pipeline:

```bash
uv run --env-file .env python -m benchmark.evaluate data/dev --agent agent.answer:answer
uv run python -m agent.run_benchmark_v1 <building_dir> <questions> agent_output/answers.json
```

The rest of the organiser kit (starter agent) is in `archive/initial-repo/`; run it from the repo root with
`PYTHONPATH=archive/initial-repo`, see [commands.md](docs/guides/commands.md).

## Licences

Our code is MIT ([LICENSE](LICENSE)). Kit code and data keep their own terms: see [NOTICE.md](NOTICE.md),
[ATTRIBUTION.md](ATTRIBUTION.md) and [data/README.md](data/README.md). Anything derived from the OpenStreetMap
buildings stays under the ODbL and credits © OpenStreetMap contributors.
