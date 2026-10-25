# Sunday runner hardening: crash-safe, hybrid by default, top-level ids in answers.json

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25 03:00
- **Related:** Q-001, Q-019, D-003, D-007; branch `4-sunday-agent` (worktree `.claude/worktrees/4-sunday-agent`)

## Summary
P0 of the Sunday plan: one bad question can no longer stop a benchmark run, the Sunday command uses the `hybrid`
parser (templates first, LLM only for unseen wording) with `.env` read automatically, and `answers.json` carries the
PDF's top-level ids next to the existing fields. The 145 test-set replies are unchanged.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `respond` never raises: unexpected exceptions (e.g. network) and an unreadable `building.json` become a `Response` with `error` and no `Answer:` line; `Response` has a new `parser` field (`regex`/`llm`) | `agent/answer.py:respond`, `Response` | `uv run pytest tests/test_answer.py -q -k error_reply` → 2 passed |
| C2 | The runner rewrites the answers file after every question (temp `.partial` file + replace), so an interrupted run keeps the answers written so far | `agent/run_benchmark_v1.py:run`, `write_answers` | `uv run pytest tests/test_run_benchmark.py -q -k interrupted` → passed |
| C3 | Each .json answer has `parser`, `item_id`, `space_id`, `reachable`, `space_path` (whole route, legs joined), `element_path`, `length_m`; warm-up locate ids and route paths/lengths match the gold answers incl. unreachable routes and a tour | `agent/run_benchmark_v1.py:top_level_ids`, `run` | `uv run pytest tests/test_run_benchmark.py -q` → 10 passed (2 buildings in the parametrized test) |
| C4 | `--layout dict` writes the .json keyed by question id; `main(argv)` accepts an argument list | `agent/run_benchmark_v1.py:main`, `write_answers` | `uv run pytest tests/test_run_benchmark.py -q -k dict_layout` → passed |
| C5 | The runner reads the repo `.env` for variables not already set (comments, `export`, quotes handled; missing file ignored); tests never load the real `.env` | `agent/run_benchmark_v1.py:load_env_file`, `ENV_FILE`; `tests/test_run_benchmark.py` | `uv run pytest tests/test_run_benchmark.py -q -k env_file` → 2 passed; read `test_dict_layout_keys_answers_by_question_id` (monkeypatches `ENV_FILE`) |
| C6 | LLM parser client retries API errors up to 4 times | `agent/llm_parser.py:API_RETRIES`, `LlmQuestionParser.__init__` | read the diff |
| C7 | `SUBMISSION/answers.json` regenerated with the new runner (`PARSER_MODE=regex`, test set): same 145 ids, identical `reply`/`answer`/`result`/`route`/`inputs`, only new keys added; folder still holds exactly 2 files | `SUBMISSION/answers.json` | `git diff --cached SUBMISSION/answers.json` shows only added keys; `ls SUBMISSION` → 2 files |
| C8 | Docs: BENCHMARK.md and commands.md give the hybrid Sunday command (no `PARSER_MODE=regex`), document the new fields, `--layout dict`, per-question error entries; project-state next priority 00, Q-019 and log updated | `SUBMISSION/BENCHMARK.md`, `docs/guides/commands.md`, `memory-bank/project-state.md`, `memory-bank/open-questions.md`, `memory-bank/log.md` | read; `python3 scripts/check_links.py` → OK |

## Checks I ran
- `uv run pytest tests/test_answer.py tests/test_run_benchmark.py -q` → `15 passed in 58.75s`
- New tests watched failing first (stub `load_env_file`): 9 failed for the expected reasons (ConnectionResetError
  raised, JSONDecodeError raised, KeyError 'parser'/'space_id'/'item_id', `main()` takes 0 positional arguments,
  answers file missing after interrupt, env not filled).
- Test-set regeneration: `PARSER_MODE=regex uv run python -m agent.run_benchmark_v1 data/test data/test/questions.csv SUBMISSION/answers.json`
  → `145 answers written … (0 without an answer, 0 read by the LLM)`; diff script vs the previous file:
  `changed replies/results: []`, new keys `element_path, item_id, length_m, parser, reachable, space_id, space_path`.
- Rehearsal of the Sunday command without `--env-file` on `data/dev/proc-factory-dev-004` (27 questions: its 13
  benchmark + warm-up questions plus 14 reworded probes) → `27 answers written … (3 without an answer, 10 read by the LLM)`, 73 s.
- `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Full suite `uv run pytest -q -x -p no:cacheprovider` (after all P0 edits) → `763 passed, 2 skipped, 15 warnings in 231.29s`
- Not in this change: untracked P1 work (`core/route_query.py`, `agent/solver_agent.py`) is deliberately left unstaged.
- Fix round 1 re-checks: `uv run pytest tests/test_run_benchmark.py -q -p no:cacheprovider` → `10 passed in 29.54s`;
  `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`; `uv run pytest -q -p no:cacheprovider` →
  `763 passed, 2 skipped, 15 warnings in 214.79s`.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (next priority 00: hybrid Sunday command)
- [x] `memory-bank/log.md` entry added (2026-10-25 03:00)
- [x] decisions / open questions touched: Q-019 (new answers.json keys)
- [x] docs touched: `SUBMISSION/BENCHMARK.md`, `docs/guides/commands.md`

## Known gaps / not done
- P1 not in this change: compositional route spec (closures of spaces/doors, item endpoints, forklift, step-free +
  closure in one question), agentic fallback for unsupported kinds, answer-type check, nearest-of-many items. The
  rehearsal still shows the 3 errors and the near-miss kinds described in the log.
- Other Claude clients (`agent/guide.py`, `agent/rewriter.py`, `agent/builder.py`) keep the SDK default retries.
- Sunday `answers.json` schema still unknown (Q-001/Q-019); the new keys are a superset guess from the PDF.

## Verification rounds
- Round 1: VERDICT FAIL — C3 test count (10, not 13), log.md template/LLM split (14/13); non-blocking: P1 path wording.
- Round 2: VERDICT PASS (fresh verifier, tree e76ec1f4).
- Fix round 1: C3 count corrected to 10 passed; log.md split corrected to 14 template / 13 LLM; last "Checks I ran"
  bullet now names the untracked P1 files instead of a non-existent test path. Only PENDING.md and log.md restaged.

## Fix round 1
- C3 test count: claim corrected — "How to verify" now says `→ 10 passed` (real output of
  `uv run pytest tests/test_run_benchmark.py -q`), `.claude/worklog/PENDING.md`.
- log.md rehearsal split: claim corrected — `(13 template, 14 LLM …)` → `(14 template, 13 LLM …)` (13 benchmark/warm-up
  questions + probe-00 by templates; 13 sent to the LLM: 10 answered, 3 `unsupported`), `memory-bank/log.md`.
- P1 path wording (non-blocking): claim corrected — bullet no longer names `tests/test_route_query.py`; it says untracked
  P1 work (`core/route_query.py`, `agent/solver_agent.py`) is deliberately left unstaged, `.claude/worklog/PENDING.md`.


---

# Verification report (final round)

VERDICT: PASS
TREE: e76ec1f458a0a9a3a84867539addee7ad4c78218

## Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | `-k error_reply` → 2 passed; building load inside try; catch-all → error Response; parser field from notes. |
| C2 | MET | `-k interrupted` → 1 passed; write after each question via `.partial` + replace. |
| C3 | MET | `tests/test_run_benchmark.py` → 10 passed; both branches of top_level_ids exercised (osm-way360544293 unreachable routes + tour, proc-campus-dev-001 reachable tour). |
| C4 | MET | `-k dict_layout` → 1 passed; main(argv), --layout list/dict. |
| C5 | MET | `-k env_file` → 2 passed; only main test reaches load_env_file and it monkeypatches ENV_FILE. |
| C6 | MET | runtime check: SDK 2.3.0, API_RETRIES 4, client.max_retries 4. |
| C7 | MET | HEAD vs staged: 145 entries, same order, 0 changed, only 7 keys added; regeneration byte-identical; SUBMISSION has 2 files. |
| C8 | MET | BENCHMARK.md, commands.md, project-state 00, Q-019, log 03:00 updated; links OK; rehearsal numbers match rehearsal_answers.json. |

## Standard checks
- pytest: 763 passed, 2 skipped (217 s); targeted 15 passed · links OK (33 files) · secrets none · score.py unchanged · hard-coding none

## Undeclared changes
- None significant. Notes (non-blocking): load_env_file ignores inline `# note` comments; README/commands still show `--env-file .env` (still valid); Q-001 progress lists the old v1 field subset (new keys in Q-019); untracked P1 files present, not staged.
