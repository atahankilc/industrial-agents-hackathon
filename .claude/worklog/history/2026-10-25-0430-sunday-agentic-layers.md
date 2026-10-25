# Sunday agentic layers: route specs on the canonical core, a solver agent, a committed decision cache

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25 04:00
- **Related:** D-015 (proposed, this change), D-003, D-007, D-012, Q-001, Q-008; P1 of the Sunday plan; P0 = b1805d4

## Summary
Questions in unseen wording, with combined constraints or of a new kind now get an answer instead of a near-miss
kind: the LLM parser fills one general route spec (solved by the new `core/route_query.py` on `core.navigation`)
and an `asks_for` slot; kind `other` or a mismatch goes to a new solver agent (Python sandbox over the building,
2 runs + tie-break, Answer line by code). Every model decision is stored in `llm_cache/decisions.json` and replayed,
so a re-run without an API key reproduces the answers. Regex templates and the test-set answers are unchanged.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `resolve_place` maps a phrase to candidate spaces (id, exact name/ref, room type, item — items first when `is_item` — then word search, optional floor); `route_query` routes through ordered stops taking the nearest candidate per leg, with closures (connector/space/opening names or ids), step-free, forklift and min door width combined; unreachable → `reachable: False` | `core/route_query.py` | `uv run pytest tests/test_route_query.py -q` → 11 passed |
| C2 | LLM schema: general `route` spec (places with `is_item`, stops, `step_free`, `forklift`, `min_width_m`, `closures`) + `asks_for`; a spec that is exactly a warm-up kind keeps `route` / `route_step_free` / `route_with_closure` / `tour`, otherwise `route_query`; kind `other`/`unsupported` or an `asks_for` the kind cannot answer raises `NeedsAgent`; a space without a floor is found by name; unresolvable slots are sent back once; old route kind names still accepted; the schema has at most 16 union-typed parameters (API limit) | `agent/llm_parser.py` (`SCHEMA`, `check_kind`, `route_spec`, `build`, `floor_of`, `make_client`) | `uv run pytest tests/test_llm_route_spec.py tests/test_parsing_modes.py -q` → all pass (15 new + existing) |
| C3 | Solver agent: `python` tool (restricted builtins, module whitelist, 30 s limit, variables persist, deep copy of the building per run, helpers over the canonical core), `submit_answer` validated and sent back on error, Answer line written by code (integers stay integers, 2 decimals otherwise, room name + ref), 2 runs + a third on disagreement with majority, no submission → error; effort `medium` by default (`SOLVER_AGENT_EFFORT`); a cached answer is replayed without the model | `agent/solver_agent.py` | `uv run pytest tests/test_solver_agent.py -q` → 13 passed |
| C4 | Decision cache: decisions keyed by building content hash + question text + version; the parser and the agent read it before calling a model and create their API client only on a miss; `LLM_CACHE` path / `off` | `agent/llm_cache.py`; `LlmQuestionParser.parse`, `SolverAgent.solve` | `tests/test_llm_route_spec.py::test_cached_decisions_replay_without_the_model`, `::test_the_cache_is_per_building_and_question`, `tests/test_solver_agent.py::test_a_cached_answer_is_replayed_without_the_model` |
| C5 | `respond`: outside regex mode any failure goes to the solver agent (`SOLVER_AGENT=off` disables); agent answers have kind `agent`, parser `agent`/`agent-cache` and `parser_failure`; `route_query` replies end in the length or "no route"; a second run with no model reproduces the first run's answers (`llm-cache`/`agent-cache`) | `agent/answer.py` (`respond`, `agent_response`, `failure`), `core/solvers_v1.py:solve`, `agent/run_benchmark_v1.py` (`ROUTE_KINDS`, summary line) | `uv run pytest tests/test_answer_agentic.py -q` → 6 passed |
| C6 | No test reads or writes the committed cache | `tests/conftest.py` (autouse `LLM_CACHE=off`) | after the full suite `ls llm_cache` → no such directory |
| C7 | Test-set answers unchanged | `SUBMISSION/answers.json` not in the diff | `git diff --cached --quiet -- SUBMISSION/answers.json`; regenerate with `PARSER_MODE=regex uv run python -m agent.run_benchmark_v1 data/test data/test/questions.csv <tmp>.json` and `cmp` with `SUBMISSION/answers.json` |
| C8 | Probe set with expected answers computed by direct code + eval script that runs the real path and scores with `benchmark/score.py` (plus `no_route`); uses its own cache in `agent_output/` | `tests/sunday_probe/proc-factory-dev-004.json`, `scripts/eval_sunday_probe.py` | read; live run (calls Claude, ~$0.3): `uv run python scripts/eval_sunday_probe.py` |
| C9 | Docs + memory bank: BENCHMARK.md (layers, reproducible without a key, kinds), ai-agents.md section, commands.md (commit the cache with answers.json, probe command), D-015, project-state, log | `SUBMISSION/BENCHMARK.md`, `docs/architecture/ai-agents.md`, `docs/guides/commands.md`, `memory-bank/decisions.md`, `memory-bank/project-state.md`, `memory-bank/log.md` | read; `python3 scripts/check_links.py` → OK |

## Checks I ran
- Targeted: `uv run pytest -p no:cacheprovider -q tests/test_route_query.py tests/test_solver_agent.py tests/test_llm_route_spec.py tests/test_answer_agentic.py tests/test_parsing_modes.py tests/test_answer.py tests/test_run_benchmark.py` → `68 passed` (before the union-limit test, the room-type and per-building test rewrites and the `parser_failure` assertion; each of those added later and run: `25 passed`, `31 passed`, `6 passed`).
- RED first: `test_route_query.py` → `ModuleNotFoundError: core.route_query`; `test_llm_route_spec.py` → `ImportError: cannot import name 'NeedsAgent'`; union-limit test → `assert 21 <= 16`; `parser_failure` assertion → `KeyError: 'parser_failure'`. Exception: `agent/solver_agent.py` was written before its tests; to compensate, faults were injected one at a time and each test watched fail (10/10 caught: building not in scope, scope copied per call, `open`/any import allowed, number formatting, ref label, code result dropped, tie-break run removed, space_id not validated, no deep copy, no-submission error removed).
- Fault injection on the other P1 code (one at a time, restored after): 12/12 caught after strengthening two tests that missed (cache key without building hash; room-type tier removed — "toilet" items sit in toilet rooms, so the test now moves a toilet into an office). The injection scripts lived in the session scratchpad, which is gone; the results are as observed.
- Live probe (Claude): before the schema fix 14/14 but all through the agent (parser HTTP 400: 21 union parameters); after the fix `14/14 correct in 76 s` (effort high) and `14/14 correct in 71 s` (effort medium): regex 1, LLM parser 10 (`route` ×4, `route_step_free`, `route_query` ×3, `locate` ×2, `tour`), agent 3.
- Replay without API access (`ANTHROPIC_API_KEY="" ANTHROPIC_BASE_URL=http://127.0.0.1:9 … --keep-cache`) → `14/14 correct in 0 s`, answers identical 14/14, parsers `regex`, `llm-cache`, `agent-cache`.
- Test-set regeneration in regex mode → `145 answers … (0 without an answer; read by: regex 145)`, `cmp` → byte-identical to `SUBMISSION/answers.json`.
- `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`.
- Full suite: before the schema fix `807 passed, 2 skipped`; final run after every edit `uv run pytest -q -p no:cacheprovider` → `808 passed, 2 skipped, 15 warnings in 224.74s`, then `ls llm_cache` → `No such file or directory`.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (What works: Sunday agentic layers; next priority 00: commit the cache with answers.json)
- [x] `memory-bank/log.md` entry added (2026-10-25 04:00)
- [x] decisions / open questions touched: D-015 proposed
- [x] docs touched: `SUBMISSION/BENCHMARK.md`, `docs/architecture/ai-agents.md`, `docs/guides/commands.md`

## Known gaps / not done
- P2 not done: production-bay and forklift rules as the Sunday questions may state them (Q-014/Q-015); `route_query`
  applies forklift only when the question says so, never the bay rule.
- The probe covers one factory building (14 questions); no campus / OSM / Swiss probe yet.
- `llm_cache/decisions.json` does not exist yet (the test set is all template wording); it is created by the Sunday
  run and must be committed with `SUBMISSION/answers.json`.
- The sandbox is an accident guard (restricted `exec`), not a security boundary.
- Branch not merged into `dev`, not pushed.

## Verification rounds
- Round 1: VERDICT PASS (commit-verifier at effort medium, tree cefe1060).


---

# Verification report (final round)

VERDICT: PASS
TREE: cefe1060965987172709137cdf1578ab143e4de6

| # | Status | Evidence |
|---|---|---|
| C1 | MET | tests/test_route_query.py → 11 passed; tiers, nearest per leg, closures via find_element, step-free, forklift, min width, reachable False. |
| C2 | MET | test_llm_route_spec + test_parsing_modes → 25 passed; union limit holds; old route kind names checked by hand with build() (no unit test). |
| C3 | MET | tests/test_solver_agent.py → 13 passed; sandbox, deep copy, answer_line, tie-break, majority, effort medium. |
| C4 | MET | the 3 cache tests pass; key = namespace/version/building hash/question hash; lazy clients after the cache check. |
| C5 | MET | tests/test_answer_agentic.py → 6 passed; agent fallback outside regex, parser_failure, route_query branch, summary line. |
| C6 | MET | conftest LLM_CACHE=off; no llm_cache/ after the full suite. |
| C7 | MET | answers.json not in the diff; regex regeneration byte-identical. |
| C8 | MET | probe JSON + script read; replay with no API access 14/14 (regex 1, llm-cache 10, agent-cache 3); 3 expected values spot-checked against the building. |
| C9 | MET | docs + memory bank staged; links OK. |

Standard checks: pytest 808 passed, 2 skipped · links OK · secrets none · score.py unchanged · hard-coding none.
Undeclared changes: none significant. Notes: no unit test for old route kind names (checked by hand); the 30 s code
limit applies on the main thread only (documented; runner is single-threaded).
