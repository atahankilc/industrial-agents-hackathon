# Archive the LLM parser, solver agent and decision cache; Guide sandbox to agent/compute.py; test oracles out of core/

- **Author:** Claude session industrial-agents-hackathon-48 (for Atahan) · **Date:** 2026-10-26
- **Related:** commits fd2b50a, 61b1c4f (archive steps 1–2); Atahan: "delete llm_cache", then "you decide — everything
  hackathon is archived, the focus is developing the app beyond the hackathon", then "evet başla" to Claude's plan

## Summary
The app used only two small parts of the benchmark's LLM modules: the python sandbox of `agent/solver_agent.py` (the
Guide's `compute` tool) and `LlmUsage` / `building_vocabulary` of `agent/llm_parser.py` (the voice rewriter). Those
parts move to app modules unchanged; `llm_parser.py`, `solver_agent.py`, `llm_cache.py` and their tests go to the
archive; the parsers and formatter that only tests use move from `core/` to `tests/kit_oracles/`. No behaviour change.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | New `agent/compute.py` = `CODE_TIME_LIMIT_S`, `MAX_OUTPUT_CHARS`, `ALLOWED_MODULES`, `SAFE_BUILTINS`, `namespace`, `run_code` copied verbatim from `agent/solver_agent.py` (HEAD) with only the imports they need; `agent/tools.py` imports `ALLOWED_MODULES, namespace, run_code` from `agent.compute` | agent/compute.py, agent/tools.py | diff the bodies against `git show HEAD:agent/solver_agent.py` |
| C2 | `LlmUsage` and `building_vocabulary` copied verbatim from `agent/llm_parser.py` into `agent/rewriter.py` (their only user); the import from llm_parser removed; docstring mention updated | agent/rewriter.py | diff against `git show HEAD:agent/llm_parser.py` |
| C3 | Archived with `git mv` (R100) to `archive/hackathon/benchmark-code/`: `agent/llm_parser.py`, `agent/solver_agent.py`, `agent/llm_cache.py`, `tests/test_llm_route_spec.py`, `tests/test_solver_agent.py`, `tests/fake_llm.py`, `tests/conftest.py` (it only set `LLM_CACHE=off`) | archive | `git diff --cached -M --name-status` |
| C4 | `tests/test_compute.py` (new) = the 5 sandbox tests of `test_solver_agent.py` verbatim (`test_python_tool_sees_the_building`, `…keeps_variables_and_reports_errors`, `…has_no_files_and_only_whitelisted_imports`, `test_code_that_runs_too_long_is_stopped`, `test_helpers_route_and_place_use_the_canonical_core`), against `agent.compute`; the timeout test monkeypatches `compute.CODE_TIME_LIMIT_S` | tests/test_compute.py | read; pytest |
| C5 | `core/question_parser.py`, `core/basic_parser.py`, `core/formatter.py` moved with `git mv` to `tests/kit_oracles/` (+ new `__init__.py` docstring); only import paths/path mentions changed (basic_parser R098); importers updated: test_navigation, test_question_parser, test_solvers, test_solvers_{geometry,reachability,routing,walls}, scripts/validate_solvers.py, scripts/validate_warmup.py | tests/, scripts/ | `git diff --cached -M` |
| C6 | Nothing reachable from `backend.app` imports the archived modules or the oracles: after `import backend.app`, no `llm_parser`, `solver_agent`, `llm_cache`, `question_parser`, `basic_parser`, `formatter` module is loaded; no non-archived code imports them | — | `GUIDE_LLM=offline uv run python -c "import sys, backend.app; …"` → `[]`; `git grep -nE "agent\.(llm_parser\|solver_agent\|llm_cache)\|core\.(question_parser\|basic_parser\|formatter)" -- agent core backend scripts tests` → nothing |
| C7 | Comment-only updates: core/route_query.py docstring, core/solvers_v1.py comment (point to the archived llm_parser) | core/ | diff |
| C8 | Docs: ai-agents.md (compute row → `agent/compute.py`; archived note under Benchmark pipeline extended; front-matter `sources` → `agent/compute.py` + the 3 archived paths under `archive/hackathon/benchmark-code/agent/`; Guide "Model" row points to the archived `llm_parser.py`; outside "## Benchmark pipeline" no archived module is named as current), overview.md (core tree line), solver-plan.md (3 path mentions), question-parsing.md (sources + heading), CLAUDE.md (agent/ line, tests/ line), archive/hackathon/benchmark-code/README.md (table rows, "still in the repo" paragraph, restore note → work from fd2b50a) | those files | read; `python3 scripts/check_links.py` |
| C9 | memory-bank: project-state.md (Benchmark line, pytest 955) and log.md (new entry) — my hunks only; Atahan's uncommitted Q-021 edits in log.md, open-questions.md, project-state.md stay unstaged | memory-bank/ | `git diff --cached -- memory-bank` has no Q-021; `git diff -- memory-bank` = only Q-021 hunks |
| C10 | The untracked `llm_cache/` folder was deleted (at Atahan's request; never committed) — not a staged change | — | `ls llm_cache` → no such file |

## Checks I ran
- `uv run pytest -q` → 955 passed, 2 skipped in 114.94s. Expected: HEAD had 978; the 2 archived test files collect 28
  tests at HEAD (`pytest --collect-only` in a temporary HEAD worktree → "28 tests collected"); +5 in test_compute → 955.
- `python3 scripts/check_links.py` → OK: all links resolve in 24 files
- `GUIDE_LLM=offline uv run python -c "import sys, backend.app; …"` → `app import ok; archived/oracle modules loaded: []`
- `uv run python scripts/validate_solvers.py --kinds largest_room` → `all 96 / 96`
- `uv run python scripts/validate_warmup.py --help` → usage line (imports resolve)
- Atahan's unstaged memory-bank hunks compared before/after my edits → identical (16 lines)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (my hunks only)
- [x] `memory-bank/log.md` entry added (my hunks only)
- [ ] decisions / open questions: none
- [x] docs touched: see C8

## Known gaps / not done
- `core/solvers/` and `core/solvers_v1.py` are two solver implementations, both used by the app (tools vs the compute
  sandbox); merging them is a separate refactor.
- Dated memory-bank history (decisions.md D-007/D-022, open-questions.md, older log entries) still names the old paths.
- `docs/architecture/ai-agents.md` "Benchmark pipeline" subsections still describe the archived pipeline in the
  present tense, covered by the section's archived note.

## Verification rounds
- Round 1: FAIL — ai-agents.md sources + Model row still named archived agent/llm_parser.py etc.

## Fix round 1
- ai-agents.md front matter `sources`: implemented — removed `../../agent/{llm_parser,solver_agent,llm_cache}.py`; added
  `../../agent/compute.py` and `../../archive/hackathon/benchmark-code/agent/{llm_parser,solver_agent,llm_cache}.py`
  (docs/architecture/ai-agents.md). Each entry checked with `test -e` + `git ls-files --error-unmatch` → all 12 ok.
- ai-agents.md Guide "Model" row: implemented — "as in `agent/llm_parser.py`" → "as in the archived benchmark parser
  (`archive/hackathon/benchmark-code/agent/llm_parser.py`)"; the comparison is still true (archived llm_parser.py:33
  `FALLBACK_BETA = "server-side-fallback-2026-07-01"`, :344 `fallbacks="default"`; agent/guide.py:43, :664 same).
- Sweep: implemented (no further change needed) — `grep -nE "llm_parser|solver_agent|llm_cache|question_parser|basic_parser|core/formatter"
  docs/architecture/ai-agents.md` → remaining hits only at lines 260–313, all inside "## Benchmark pipeline" (256–335,
  covered by its archived note). `git grep` of the same pattern over docs/ (excluding ai-agents.md), CLAUDE.md, README.md →
  only solver-plan.md:16/121/128 and question-parsing.md:5/61/140, each already saying "now `tests/kit_oracles/…`" /
  "was core/…" / "archived 2026-10-26".
- Checks: `python3 scripts/check_links.py` → OK: all links resolve in 24 files. `uv run pytest -q` → 955 passed, 2 skipped in
  121.43s.

## Verification rounds (final)
- Round 1: FAIL — ai-agents.md sources + Model row still named archived agent/llm_parser.py etc.
- Round 2: PASS

## Verifier report (round 2)

VERDICT: PASS
TREE: 110105d2c5f6a2de1eb6ad50889aa514fcbf8c89

C1–C10 MET. Moved code identical to HEAD by AST comparison (compute.py constants/namespace/run_code; rewriter
LlmUsage/building_vocabulary; test_compute 4 identical + timeout test monkeypatches compute). pytest 955 passed,
2 skipped; check_links OK (working tree and staged export); backend.app loads no archived/oracle modules; secrets
none; score.py unchanged. Staged memory-bank has no Q-021; unstaged memory-bank diff is only Atahan's Q-021 hunks.
