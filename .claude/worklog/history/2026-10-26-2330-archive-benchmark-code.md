# Archive the hackathon benchmark code, challenge docs and starter-agent doc

- **Author:** Claude session industrial-agents-hackathon-48 (for Atahan) · **Date:** 2026-10-26
- **Related:** previous commit fd2b50a (post-hackathon cleanup); Atahan: "move everything no more related with this app
  to the archive. Anything regarding hackathon"

## Summary
Moves the hackathon-only benchmark pipeline (runners, kit evaluator, v1 Guide, their scripts and tests) and the
challenge / starter-agent docs into `archive/hackathon/`, keeping repo paths, and updates every doc, comment and
config that pointed at them. Code the app uses stays; three benchmark helpers stay because tests of app code use them
as oracles.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Moved with `git mv` to `archive/hackathon/benchmark-code/<same path>`: `agent/answer.py`, `agent/benchmark_agent.py`, `agent/parsing.py`, `agent/run_benchmark.py`, `agent/run_benchmark_v1.py`, `agent/guide_v1/`, `benchmark/evaluate.py`, `scripts/eval_llm_parser.py`, `scripts/eval_sunday_probe.py`, `tests/sunday_probe/`, and tests `test_answer.py`, `test_answer_agentic.py`, `test_guide_grounding.py`, `test_guide_loop.py`, `test_guide_resolve.py`, `test_guide_route.py`, `test_guide_tools.py`, `test_parsing_modes.py`, `test_run_benchmark.py`, `test_warm_up.py`. `docs/challenge/` → `archive/hackathon/docs/challenge/`, `docs/kit/starter-agent.md` → `archive/hackathon/docs/kit/starter-agent.md`. Content unchanged (R100), except relinks inside moved docs | archive/hackathon/ | `git diff --cached -M --name-status` |
| C2 | None of the moved modules is reachable from `backend/app.py` (import graph); no remaining non-archived code imports them | agent/, core/, backend/, scripts/, tests/ | `git grep -nE "from agent\.(answer\|benchmark_agent\|parsing\|run_benchmark\|guide_v1)\|benchmark\.evaluate\|test_parsing_modes" -- agent core backend scripts tests` → nothing |
| C3 | Kept on purpose (tests of app code use them as oracles): `benchmark/score.py` (+`__init__.py`), `core/formatter.py`, `core/basic_parser.py`; kept because the app uses them: `core/solvers_v1.py`, `core/question_parser.py`, `agent/llm_parser.py`, `agent/solver_agent.py`, `agent/llm_cache.py` | — | files exist; `tests/test_solvers_*.py`, `tests/test_navigation.py`, `tests/test_solver_agent.py` import them |
| C4 | `tests/fake_llm.py` (new) holds `FakeClient` + `response`, copied verbatim from the archived `test_parsing_modes.py`; `tests/test_llm_route_spec.py` imports it from there | tests/ | read; pytest |
| C5 | `pyproject.toml`: `[project.scripts] run_benchmark` removed (its module is archived); `[tool.pytest.ini_options] testpaths = ["tests"]` added so pytest never collects the archived tests | pyproject.toml | read; `uv run pytest -q` collects only tests/ |
| C6 | Comment/docstring-only path updates: agent/guide.py, agent/llm_parser.py (2), agent/places.py, agent/solver_agent.py, core/formatter.py, scripts/interaction_eval.py; `.env.example` PARSER_MODE commented out with a note (only archived code reads it) | those files | `git diff --cached -- agent core scripts .env.example` → only comment/docstring lines |
| C7 | Markdown links and front matter `sources:`/`related:` rewritten for the moves; `check_links.py` OK; links inside `archive/hackathon/**/*.md` resolve | docs/, memory-bank/, archive/hackathon/, CLAUDE.md | commands below |
| C8 | `docs/guides/commands.md`: sections Starter agent, Evaluate on dev, Produce the test submission, Our deterministic pipeline (except `validate_solvers.py`, kept as "Solvers against the kit's gold answers"), the v1 Guide part and Sunday benchmark moved into the new `archive/hackathon/benchmark-code/README.md` (with a table of the moved files and how to restore them); commands.md has a short "Benchmark (archived)" pointer, "Guide evals (terminal)" heading, new front matter | docs/guides/commands.md, archive/hackathon/benchmark-code/README.md | read |
| C9 | Docs updated for the archive: CLAUDE.md (tree, doc map), README.md (Benchmark section), docs/README.md (challenge + starter-agent entries in the Archived section; v1 Guide spec entry notes `agent/guide_v1/` is archived), ai-agents.md (archived note under Benchmark pipeline; agents table rows Building Guide v1 / Benchmark pipeline and the "Model ids" line marked archived), docs/research/question-parsing.md (front matter `sources:` → archived evaluate.py path; body mentions of `benchmark/evaluate.py` and `scripts/eval_llm_parser.py` marked archived), docs/research/stack-options.md (`run_benchmark` mentions marked archived), solver-plan.md, overview.md, repo-layout.md, NOTICE.md (`benchmark/` row), archive/hackathon/README.md (benchmark-code/ and docs/ rows) | those files | read |
| C10 | memory-bank: project-state.md (Benchmark line, Next item 1 = `through: false` finding, pytest count) and log.md (new 2026-10-26 entry). **Atahan's own uncommitted edits in memory-bank/log.md, open-questions.md, project-state.md (Q-021 living-building positions, "Living building noted as demo-grade" log entry, project-state line) are NOT staged** — only my hunks are, built on HEAD | memory-bank/ | `git diff -- memory-bank` (unstaged) shows only Atahan's Q-021 hunks; `git diff --cached -- memory-bank` has no Q-021 |
| C11 | `llm_cache/` (untracked, from another session's run) not staged | — | `git diff --cached --name-only \| grep llm_cache` → nothing |

## Checks I ran
- `uv run pytest -q` → 978 passed, 2 skipped in 138.46s (was 1088 incl. the 110 archived tests)
- `python3 scripts/check_links.py` → OK: all links resolve in 24 files (re-run after fix round 1: same)
- link scan with `scripts/check_links.py` logic (files + `#anchors`, GitHub slugs, code fences excluded) over
  `archive/hackathon/**/*.md`, README.md, NOTICE.md → first run missed the anchor in archived scoring.md (it pointed at
  the removed commands.md#produce-the-test-submission); after fix round 1 → `broken: 0 in 25 files`
- `cmp` of the 4 files accidentally restored by a stray `git checkout fd2b50a -- …` (from an unquoted heredoc) against
  their archived copies → identical; removed from the old paths with `git rm`, so they show as renames again
- Atahan's unstaged memory-bank hunks compared with a backup taken before the move → identical
- No frontend files changed (no npm build needed)
- Fix round 2: `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`; `uv run pytest -q` → 978 passed, 2 skipped in 110.16s
- Fix round 2: `git grep --cached -nE "run_benchmark|benchmark\.evaluate|guide_v1" -- docs/architecture/ai-agents.md` → line 20
  (says "archived 2026-10-26 to `archive/hackathon/benchmark-code/agent/guide_v1/`") and lines 258, 259, 269, 270, 298, all
  inside "## Benchmark pipeline" under its "Archived 2026-10-26" note
- Fix round 2: front matter scan (every `sources:`/`related:` path in docs/**, CLAUDE.md, README.md, memory-bank/*.md
  checked for existence) → no moved path left; the only misses are unrelated non-paths / frontend-relative paths
  (e.g. `equipment.csv`, `src/plan/palette.ts`)
- Fix round 2: sweep of docs/**, CLAUDE.md, README.md for `run_benchmark|benchmark.evaluate|benchmark/evaluate|guide_v1|
  agent/answer.py|agent/parsing.py|eval_sunday_probe|eval_llm_parser|benchmark_agent` → every remaining hit is marked
  archived or sits in an archived section (overview.md 35/53, solver-plan.md 35/37/104 already marked)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (my hunks only)
- [x] `memory-bank/log.md` entry added (my hunks only)
- [ ] decisions / open questions: none new (open-questions.md / decisions.md only relinked)
- [x] docs touched: see C8, C9

## Known gaps / not done
- `core/basic_parser.py`, `core/formatter.py`, `benchmark/score.py` stay (test oracles), though they came from the
  benchmark work.
- `docs/kit/questions.md`, `docs/architecture/solver-plan.md`, `docs/research/question-parsing.md` stay: they describe
  the solvers / parser the app still uses; their benchmark wording is historical.
- Front matter inside archived files may still name old paths (read-only history).
- Push of `dev` and deletion of merged remote branches still need Atahan (denied by permissions earlier).

## Verification rounds
- Round 1: FAIL — archived scoring.md anchor to removed commands.md section
- Round 2: FAIL — ai-agents.md table and question-parsing.md sources still presented archived code as current

## Fix round 1
- Archived scoring.md "Easiest path" link: implemented — `archive/hackathon/docs/challenge/scoring.md` now links to
  `../../benchmark-code/README.md#produce-the-test-submission` (heading "## Produce the test submission" exists there).
- Link scan: implemented — re-ran over archive/hackathon/**/*.md + README.md + NOTICE.md → `broken: 0 in 25 files`;
  `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`.
- "Checks I ran" link-scan line: claim corrected to the real result (above).

## Fix round 2
- question-parsing.md sources: implemented — front matter now `archive/hackathon/benchmark-code/benchmark/evaluate.py
  (PRICE_PER_MILLION, …; archived 2026-10-26)`; body lines ~132 and ~140 say `benchmark/evaluate.py` /
  `scripts/eval_llm_parser.py` are archived to `archive/hackathon/benchmark-code/` (docs/research/question-parsing.md).
- ai-agents.md agents table: implemented — Building Guide row says the v1 Guide is archived 2026-10-26 to
  `archive/hackathon/benchmark-code/agent/guide_v1/`; Benchmark pipeline row marked "(archived 2026-10-26)" and its
  channel links `../../archive/hackathon/benchmark-code/README.md` instead of the CLIs; "Model ids" line no longer
  recommends `benchmark.evaluate`, says the evaluator comparison is archived (docs/architecture/ai-agents.md).
- Sweep of other live docs: implemented — docs/research/stack-options.md (3 `run_benchmark` mentions + "(archived
  2026-10-26)"), docs/README.md (v1 Guide spec entry). memory-bank files not edited (Atahan's unstaged hunks).
- check_links: `OK: all links resolve in 24 files`.

## Verification rounds (final)
- Round 1: FAIL — archived scoring.md anchor to removed commands.md section
- Round 2: FAIL — ai-agents.md table and question-parsing.md sources still presented archived code as current
- Round 3: PASS

## Verifier report (round 3)

VERDICT: PASS
TREE: ae150d0d3f43c8150ce8ff4dbcf87d3d0ae3e75e

Claims C1–C11: MET. pytest 978 passed, 2 skipped; check_links OK (24 files) on working and staged tree; archive,
README, NOTICE scan broken 0 in 25; secrets none; score.py unchanged; hard-coding none. Staged memory-bank holds no
Q-021; the unstaged memory-bank diff is only Atahan's Q-021 hunks. Not blocking: dated memory-bank history
(open-questions.md Q-006 :45, :147-151; decisions.md D-007 :95) still names old paths without "(archived)".
