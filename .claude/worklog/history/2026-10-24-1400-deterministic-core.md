# Deterministic core: verified solvers for every benchmark kind, benchmark runner, navigation, agent tool layer

- **Author:** Claude Code session (orchestrator + 5 subagents) · **Date:** 2026-10-24
- **Related:** Q-003, Q-004 (resolved), Q-005, Q-006 (progress), D-003, D-007, docs/architecture/solver-plan.md

## Summary
Implements one deterministic solver per benchmark question kind (verified on all train+dev answers), the
text → parse → solve → `Answer:` pipeline with a Sunday/test CLI, warm-up navigation tools with a text parser,
and the Guide agent's tool layer (session, profile, propose/apply changes). Docs and memory bank record the
rules the data settled.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Every solver matches all train+dev gold answers with the official scorer: 655/655 | `core/solvers/{__init__,geometry,walls,reachability,routing}.py`, `core/formatter.py` | `uv run python scripts/validate_solvers.py` → `all 655 / 655` |
| C2 | End-to-end from question text (regex parser) dev scores 138/138 | `agent/benchmark_agent.py` | `PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name verify` → `138 / 138` |
| C3 | Run CLI answers all 145 test questions with no errors and writes answers.json + CSV | `agent/run_benchmark.py`, `BENCHMARK.md` | `PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv /tmp/x.json --csv /tmp/x.csv` → `{'ok': 145}` |
| C4 | Warm-up navigation: 2120/2130 from text, 100% with gold ids | `core/navigation.py`, `core/basic_parser.py`, `scripts/validate_warmup.py` | `uv run python scripts/validate_warmup.py` |
| C5 | Agent tool layer: every TOOL_DEFINITION has a handler; changes need propose → apply; session never mutates the loaded building | `agent/tools.py`, `tests/test_agent_tools.py` | `uv run pytest tests/test_agent_tools.py -q` |
| C6 | Full test suite passes | `tests/` | `uv run pytest -q` → 65 passed |
| C7 | Docs/memory bank updated, links valid; Q-003/Q-004 moved to Resolved | `docs/architecture/solver-plan.md`, `docs/kit/route-model.md`, `docs/architecture/ai-agents.md`, `docs/guides/commands.md`, `docs/README.md`, `memory-bank/*` | `python3 scripts/check_links.py` → OK |
| C8 | No edit to `benchmark/score.py`, routing behaviour of `core/building_map.py` unchanged | — | `git diff --cached --stat` shows neither file |

## Checks I ran
- `uv run python scripts/validate_solvers.py` → `all 655 / 655`
- dev pipeline → `all 138 / 138 (100%)`; train → `515 / 517` (2 ambiguous OSM names, Q-006)
- `agent.run_benchmark` on test → `145 answers … {'ok': 145}`
- `uv run pytest -q` → `65 passed`
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] open questions: Q-003, Q-004 resolved; Q-005, Q-006 progress
- [x] docs: solver-plan (rewritten, VERIFIED), route-model (width rule, errand distance, tie note), ai-agents, commands, README; new BENCHMARK.md

## Known gaps / not done
- No LLM conversation loop yet (no API key); `compare_routes` tool not built.
- what_if_door (4) and step_free_reachable_count (2) rest on few examples; closure never changes the count in data.
- straight_line_3d on Swiss buildings (per-floor frames) is unverified — none in data.
- Sunday output format unknown (Q-001); answers.json keeps structured evidence.
- Team name for `team_<name>.csv` not chosen; test CSV not committed.

## Verification rounds
- Round 1: VERDICT: PASS (tree 91fd7f0f92fee9285644c1bbf84c03070a4a8589)

## Verification report (round 1)

VERDICT: PASS
TREE: 91fd7f0f92fee9285644c1bbf84c03070a4a8589

C1–C8 all MET: validate_solvers `all 655 / 655`; dev pipeline `all 138 / 138 (100%)`; run CLI `{'ok': 145}`;
validate_warmup `all 2130 answer 99.53%`, oracle 100%; test_agent_tools `4 passed`; pytest `65 passed`;
check_links OK; benchmark/score.py and core/building_map.py not in the diff.
Standard checks: no secrets, no .env, no test-building/question-id hard-coding, no untracked files.
Undeclared changes: none significant. Minor (non-blocking): agent/benchmark_agent.py docstring line 4 shows an
outdated run_benchmark usage (`--out`); BENCHMARK.md and commands.md are correct — fix in a later change.
