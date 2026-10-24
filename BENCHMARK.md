# BENCHMARK — how to reproduce our answers

One command, no manual steps, no API key needed (deterministic regex parser + solvers; `PARSER_MODE=regex`
makes that explicit — the default `hybrid` only calls an LLM for wording no template matches).

```bash
uv sync
# Sunday: one building directory + its question file
PARSER_MODE=regex uv run python -m agent.run_benchmark <building_dir> <questions file> answers.json --csv answers.csv
# Public test set (145 questions, buildings under data/test/<building_id>/)
PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv agent_output/test_answers.json --csv team_submission.csv
```

- Question files: `.jsonl`, `.json` (list or `{"questions": [...]}`) or `.csv`; fields `id`/`question_id`,
  `question`, and `building_id` when the first argument is a directory of buildings.
- `answers.json`: per question id → `kind`, resolved `params`, `answer` (number or space id), `unit`, `area_m2`,
  structured `evidence` (space ids, route node/element paths, lengths), the full `reply` and any `error`.
- `--csv`: `question_id,answer` with full replies ending in the `Answer:` line (the test-set format).

How it works: question text → template parser (`core/question_parser.py`) → solver per kind
(`core/solvers/`) → formatter (`core/formatter.py`). Every number comes from code, not from an LLM.

Our own scores (official `benchmark/score.py`):

```bash
uv run python scripts/validate_solvers.py                                        # solvers on gold inputs: 655/655
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer   # 138/138
```

The Sunday output format is not yet announced; `answers.json` keeps every structured field so the final format
can be derived without re-running.
