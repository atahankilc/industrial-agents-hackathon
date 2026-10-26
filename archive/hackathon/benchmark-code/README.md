# Benchmark code (archived 2026-10-26)

The hackathon's benchmark pipeline, moved out of the app on 2026-10-26 with its repo paths kept (`agent/`,
`benchmark/`, `scripts/`, `tests/` below mirror the repo root). Nothing reachable from `backend/app.py` imports any
of it.

| Path | What it was |
|---|---|
| `agent/answer.py`, `agent/run_benchmark_v1.py` | the submission pipeline (question → parser → `core/solvers_v1.py` → reply) that produced `../SUBMISSION/answers.json` |
| `agent/benchmark_agent.py`, `agent/run_benchmark.py` | the first benchmark runner (on `core/solvers/`) |
| `agent/parsing.py` | parser modes (`PARSER_MODE` = regex / llm / hybrid / crosscheck) |
| `agent/guide_v1/` | the v1 terminal Guide (superseded by `agent/guide.py`) |
| `benchmark/evaluate.py` | the kit's evaluator (`benchmark/score.py` stays in the repo: the solver tests use it) |
| `agent/llm_parser.py`, `agent/solver_agent.py`, `agent/llm_cache.py` | LLM slot parser, the solver agent and the decision cache (`llm_cache/decisions.json`); archived in a second step the same day. The solver agent's python sandbox moved to `agent/compute.py` (the Guide's `compute` tool), `LlmUsage` / `building_vocabulary` to `agent/rewriter.py` |
| `scripts/eval_llm_parser.py`, `scripts/eval_sunday_probe.py`, `tests/sunday_probe/` | parser and Sunday probes |
| `tests/test_*.py`, `tests/fake_llm.py`, `tests/conftest.py` | their tests (the sandbox tests of `test_solver_agent.py` live on in `tests/test_compute.py`); `conftest.py` only switched the decision cache off |

Still in the repo because the app uses them: `core/solvers_v1.py` and `core/route_query.py` (the `compute` sandbox).
Kept as test oracles (they check the app's core against the kit's gold answers): `benchmark/score.py`, and
`tests/kit_oracles/` (`question_parser.py`, `basic_parser.py`, `formatter.py`, moved there from `core/`).

**To run it again**, restore the files to their old paths (they import `agent.*` and `benchmark.*` from the repo
root and `core.question_parser`), most simply by working from commit `fd2b50a`, where every file is still in place. The commands below are as documented in `docs/guides/commands.md` before the move.

## Starter agent (archived, still runnable)

```bash
PYTHONPATH=archive/initial-repo uv run --env-file .env python -m starter_agent data/dev/proc-factory-dev-003
```

## Evaluate on dev (do this before touching test)

```bash
# warm-up questions, tools only, free (verified 369/369 on 2026-10-24 with kit 1.0.0 answers; not re-run on 1.1.0):
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

The graded hackathon submission (2026-10-25) is archived in `archive/hackathon/SUBMISSION/`. To re-score, write
new answers outside it, e.g. to `agent_output/` (gitignored):

```bash
PARSER_MODE=regex uv run python -m agent.run_benchmark_v1 data/test data/test/questions.csv agent_output/answers.json
uv run --env-file .env python -m agent.run_benchmark_v1 data/test data/test/questions.csv agent_output/team_jaRAG.csv
# same replies via the kit evaluator (checked identical on 2026-10-24):
uv run --env-file .env python -m benchmark.evaluate data/test --agent agent.answer:answer --submission-csv agent_output/team_jaRAG.csv
```

Format rules: [scoring.md](../docs/challenge/scoring.md#submission-format).


## Our deterministic pipeline

```bash
uv run python scripts/validate_solvers.py [--kinds errand] [-v]          # solvers on gold inputs, train+dev
PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name dev
PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv agent_output/test_answers.json --csv team_<name>.csv
```


## v1 Guide and pipeline (terminal)

The second Guide (`agent/guide_v1/`, branch `1-agentic-yarag`) and its benchmark pipeline (`agent/answer.py` →
`core/solvers_v1.py`) sit beside the canonical ones; the backend and UI use `agent/guide.py`.

```bash
# terminal REPL (multi-turn, remembers position / step-free / closures); --show-tools prints each tool call
uv run --env-file .env python -m agent.guide_v1 data/dev/proc-campus-dev-001 --show-tools
# v1 benchmark run: .csv (submission) or .json (reply + ids + solver result + route) out
uv run --env-file .env python -m agent.run_benchmark_v1 <building_dir> <questions> <answers.csv|answers.json>
```

Design: [guide-agent spec](../superpowers/specs/2026-10-24-guide-agent-design.md). A full eval run costs about $0.27.


## Sunday benchmark (hackathon, archived)

`uv run python -m agent.run_benchmark_v1 <building_dir> <questions file> <answers.json>` (default `hybrid`:
templates first, the LLM only for unseen wording; `.env` is read automatically; `--layout dict` keys the .json by
question id) — documented in [`archive/hackathon/SUBMISSION/BENCHMARK.md`](../SUBMISSION/BENCHMARK.md) (v1 is the submission
pipeline: it also answers the warm-up kinds, routes included; `agent.run_benchmark` has no solvers for them). Do not
use `PARSER_MODE=regex` on Sunday: on 14 reworded questions it answered 1 (2026-10-25). A failing question becomes an
`error` entry and the run goes on; the file is rewritten after every question. Model decisions go to
`llm_cache/decisions.json` — commit it together with the answers file, so a re-run without a key
reproduces the answers ([ai-agents.md](../../../docs/architecture/ai-agents.md#sunday-layers-route-specs-solver-agent-decision-cache-2026-10-25)).
Probe of the agentic layers: `uv run python scripts/eval_sunday_probe.py` (`tests/sunday_probe/`, calls Claude). Output format was never announced (closed:
[Q-001](../../../memory-bank/open-questions.md#q-001)).
