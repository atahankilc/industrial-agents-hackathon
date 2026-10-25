# BENCHMARK — how to reproduce our answers

One command from the repo root, no manual steps between input and output. The default `hybrid` mode reads each
question with deterministic templates first (no API key, no LLM) and calls an LLM only for wording no template
matches; the repo's `.env` (`ANTHROPIC_API_KEY`) is read automatically. `PARSER_MODE=regex` is fully offline and
deterministic (template parser + solvers) — it reproduces our test-set answers, but questions in unseen wording then
get no answer.

```bash
uv sync
# Sunday: one building directory (holds building.json) + its question file
uv run python -m agent.run_benchmark_v1 <building_dir> <questions file> SUBMISSION/answers.json
# Public test set (145 questions, buildings under data/test/<building_id>/) — this produced SUBMISSION/answers.json
PARSER_MODE=regex uv run python -m agent.run_benchmark_v1 data/test data/test/questions.csv SUBMISSION/answers.json
```

- `<building_dir>`: one building, or a split directory with one sub-directory per `building_id`.
- Question file: `.jsonl`, `.json` (a list, or `{"questions": [...]}`) or `.csv`; each question needs an id
  (`id` or `question_id`) and its text (`question`), plus `building_id` when the first argument is a split.
- The output extension picks the format. `.json` (our submission): one object per question with `question_id`,
  the full `reply` (ending in the `Answer:` line), `answer`, `kind`, `parser` (`regex` or `llm`), resolved
  `inputs`, the top-level ids `item_id` (located item), `space_id` (its room, or the answer room), `space_path`
  (the whole route as one ordered list of spaces, stops joined), `element_path`, `length_m` and `reachable`
  (`false` = no route under the question's rules), the solver's structured `result`, and for routing kinds
  `route` = `{optimal_length_m, legs: [{from_space_id, to_space_id, optimal_length_m, space_path,
  element_path}]}` (the kit's warm-up answer format); `error` when unanswered. `--layout dict` writes the same
  objects keyed by question id. `.csv` writes `question_id,answer` with the full replies (the test-set CSV format).
- The answers file is rewritten after every question; a failing question (unknown wording, API error) becomes an
  `error` entry and the run goes on.

How it works: question text → template parser (`core/question_parser.py`, `agent/parsing.py`) → solver per kind
(`core/solvers_v1.py`) → reply with a deterministic `Answer:` line (`agent/answer.py`). Routes are Dijkstra on the
kit's door-to-door route model (`core/building_map.py`). Every number comes from code, not from an LLM.

Kinds covered: the benchmark kinds (`largest_room`, `floor_area_total`, `shared_walls_count`, `room_stacked`,
`straight_line_3d`, `errand`, `what_if_door`, `wide_delivery_count`, `step_free_reachable_count`) and the warm-up
kinds (`locate`, `count`, `route`, `route_step_free`, `route_with_closure`, `tour`).

## Our own scores

```bash
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.answer:answer   # dev 138/138
uv run pytest tests/test_routes.py -q     # 1,338/1,338 train+dev warm-up routes exact (length, space_path, element_path)
uv run pytest tests/test_warm_up.py -q    # warm-up from question text: 2,120/2,130
```

The 10 warm-up misses (and 2 of 517 train benchmark questions) name a room whose name several rooms share, so the
text cannot say which one is meant.

## Second pipeline (kept for comparison)

`agent/run_benchmark.py` → `agent/benchmark_agent.py` → `core/solvers/` gives the same benchmark answers (test set:
same rooms and numbers; solvers 655/655 on gold inputs) with richer `evidence` fields, but has no solvers for the
warm-up kinds (routes, locate, count), so it is not the submission pipeline:

```bash
PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv /tmp/answers.json --csv /tmp/answers.csv
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer   # 138/138
```
