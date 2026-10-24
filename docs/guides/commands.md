---
id: guide-commands
summary: Setup and every command for chatting, evaluating on dev, scoring and producing the test submission.
sources: [archive/initial-repo/README.md §5-6, archive/initial-repo/starter_agent/README.md, benchmark/evaluate.py]
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

## Sunday benchmark

`agent.run_benchmark <building_dir> <questions file> <answers.json> [--csv …]` — documented in
[`BENCHMARK.md`](../../BENCHMARK.md). Output format still unannounced →
[Q-001](../../memory-bank/open-questions.md#q-001).

## Related
- [starter-agent.md](../kit/starter-agent.md#evaluation) · [scoring.md](../challenge/scoring.md)
