---
id: guide-commands
summary: Setup and every command for chatting, evaluating on dev, scoring and producing the test submission.
sources: [archive/initial-repo/README.md §5-6, archive/initial-repo/starter_agent/README.md, benchmark/evaluate.py, agent/run_benchmark.py, BENCHMARK.md]
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
uv run --env-file .env run_benchmark data/test data/test/questions.csv submissions/team_jaRAG.csv
# same replies via the kit evaluator (checked identical on 2026-10-24):
uv run --env-file .env python -m benchmark.evaluate data/test --agent agent.answer:answer --submission-csv submissions/team_jaRAG.csv
```

Format rules: [scoring.md](../challenge/scoring.md#submission-format).

## Talk to the Guide

```bash
# terminal REPL (multi-turn, remembers position / step-free / closures); --show-tools prints each tool call
uv run --env-file .env python -m agent.guide data/dev/proc-campus-dev-001 --show-tools
# scripted conversations (tests/guide_conversations/*.json) against the live API: PASS/FAIL per turn + cost, exit 1 on a failure
uv run --env-file .env python scripts/eval_guide.py [tests/guide_conversations/lift_closure.json ...]
# offline checks of the conversation files and of the checker (no API)
uv run pytest tests/test_guide_conversations.py -q
```

Design: [guide-agent spec](../superpowers/specs/2026-10-24-guide-agent-design.md). A full eval run costs about $0.27.

## Sunday benchmark

`uv run --env-file .env run_benchmark <building_dir> <questions> <answers>` — inputs, outputs and scores in
[BENCHMARK.md](../../BENCHMARK.md). The exact Sunday format is still open →
[Q-001](../../memory-bank/open-questions.md#q-001).

## Related
- [starter-agent.md](../kit/starter-agent.md#evaluation) · [scoring.md](../challenge/scoring.md)
