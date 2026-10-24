# Archive

`initial-repo/` is the organiser student kit (Track 01) as delivered on 2026-10-24, kept for reference.
We do **not** build here. Extracted to the repo root:

| Kit path | Now at | Change |
|---|---|---|
| `data/` | `/data/` | moved, unchanged |
| `benchmark/` (official scorer + evaluator) | `/benchmark/` | moved, unchanged — never edit `score.py` |
| `starter_agent/building_map.py` | `/core/building_map.py` | copied, docstring only |
| `ATTRIBUTION.md`, `.env.example` | `/` | copied |

Still only here: `starter_agent/` (agent, tools, viewer, evaluator), kit `README.md`, `pyproject.toml`.
Run the starter oracle against the moved data from the repo root:
`PYTHONPATH=archive/initial-repo uv run python -m starter_agent.evaluate data/dev --oracle`
