# Restructure the repo: frontend/ and backend/{api,agents,core}; kit scorer under tests

- **Author:** Claude session for Atahan · **Date:** 2026-10-27 01:30
- **Related:** D-024 (new), D-004, D-006, D-009

## Summary
The React app moves from `frontend/app/` to `frontend/`; all Python becomes one package `backend` with
`backend/api/` (FastAPI, was `backend/`), `backend/agents/` (was `agent/`) and `backend/core/` (was `core/`); the
kit scorer `benchmark/score.py` moves unmodified to `tests/kit_oracles/score.py`. Imports, config, docs and the
memory bank follow. No behaviour change.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Directories moved with git renames: `frontend/app/*` → `frontend/*`, `backend/*.py` + `locations.json` → `backend/api/`, `agent/` → `backend/agents/`, `core/` → `backend/core/`; root `core/`, `agent/`, `benchmark/`, `frontend/app/` no longer exist | tree | `git diff --cached -M --name-status \| grep -c '^R'`; `ls core agent benchmark frontend/app` fails |
| C2 | `tests/kit_oracles/score.py` is byte-identical to the old `benchmark/score.py` | `tests/kit_oracles/score.py` | `git diff --cached -M --stat -- tests/kit_oracles/score.py benchmark/score.py` shows a pure rename (0 lines changed) |
| C3 | Every Python import uses the new package paths (`backend.core`, `backend.agents`, `backend.api`, `tests.kit_oracles.score`); no `from core`/`from agent`/`from benchmark`/`from backend.<api module>` left outside `archive/` | `backend/`, `tests/`, `scripts/` | `git grep -nE '^\s*(from\|import) (core\|agent\|benchmark)\b' -- ':!archive'` → empty |
| C4 | `backend/__init__.py` is a short package docstring; `backend/api/__init__.py` carries the old HTTP-backend docstring | both files | read them |
| C5 | `DATA_DIR` still points at the repo's `data/` (now `parents[2]` from `backend/api/sessions.py`); `LOCATIONS` unchanged (moved with the file) | `backend/api/sessions.py:36-40` | read; tests that load buildings pass |
| C6 | `vercel.json`: web root `frontend/`, api entrypoint `backend.api.app:app`, functions key `backend/api/app.py`; `tests/test_deploy.py` updated to match | `vercel.json`, `tests/test_deploy.py` | `uv run pytest tests/test_deploy.py -q` |
| C7 | `pyproject.toml` wheel packages = `["backend"]` | `pyproject.toml` | read |
| C8 | Path references in docs, CLAUDE.md, README, NOTICE, `.env.example`, `.claude/agents`, `.impeccable`, `PRODUCT.md`, memory bank and code comments rewritten to new paths; paths to archived files (e.g. `agent/answer.py`) and `.claude/worklog/history/`, `archive/` and `supabase/migrations/` left unchanged | those files | `git diff --cached` on docs; `git diff --cached --stat -- archive supabase .claude/worklog/history` → empty |
| C9 | CLAUDE.md tree, README "Repository layout" section and overview.md "Repo layout" describe the new layout, incl. the honest exception that the Builder imports `backend/api/drafts.py`/`persistence.py`; `core` imports neither `agents` nor `api` | `CLAUDE.md`, `README.md`, `docs/architecture/overview.md` | read; `grep -rnE '^\s*(from\|import) backend\.(agents\|api)' backend/core` → empty |
| C10 | D-024 recorded (accepted), "Next free id" = D-025; log entry 2026-10-27; project-state updated (layout line, date, collab-edits needs rebase) | `memory-bank/` | read |
| C11 | Test suite unchanged in outcome | — | `uv run pytest -q` → 955 passed, 2 skipped |
| C12 | Frontend builds from its new place | `frontend/` | `cd frontend && npm run build` → built |
| C13 | All doc links resolve | — | `python3 scripts/check_links.py` → OK |

## Checks I ran
- Before the change: `uv run pytest -q` → `955 passed, 2 skipped in 116.54s`
- After: `uv run pytest -q` → `955 passed, 2 skipped in 139.07s`
- `uv run python -c "from backend.api.app import app"` → `app ok 46` (routes)
- `cd frontend && npm run build` → `✓ built in 629ms`
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`
- Fix round 1: `grep -rn 'from backend.api' backend/agents` → `builder.py:24 backend.api.drafts`, `builder.py:25 backend.api.persistence`, `builder_tools.py:13 backend.api.drafts` (matches new README/overview wording)
- Fix round 1: `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions: D-024 added
- [x] docs touched: overview.md (repo layout), repo-layout.md, commands.md (anchor + paths), all docs' paths

## Known gaps / not done
- A real Vercel deploy was not run; only `tests/test_deploy.py` checks the config.
- Branch `collab-edits` (worktree `../iah-collab-edits`) must be rebased onto the new paths.
- The Builder's upward import of `backend/api/drafts.py` / `persistence.py` was not refactored (pre-existing).
- `ruff` is not installed in the venv, so no lint run.
- Local untracked `agent_output/` (gitignored, old benchmark outputs) left alone.

## Verification rounds
- Round 1: FAIL — C9 partial (Builder exception names only drafts.py; overview front matter says layout proposed)

## Fix round 1
- README Builder exception: implemented — `README.md` now says the only upward imports are the Builder (`builder.py`, `builder_tools.py`) using `backend/api/drafts.py` and `backend/api/persistence.py`.
- overview.md Builder exception: implemented — `docs/architecture/overview.md` "Repo layout" names both `backend/api/drafts.py` and `backend/api/persistence.py`.
- overview.md front matter: implemented — `summary`/`status` now say repo layout accepted (D-024); only build order remains a proposal.
- Cosmetic: removed the double blank line after the "Layout" line in `memory-bank/project-state.md`.
- Round 2: PASS — all claims C1–C13 MET

## Verification report (round 2)

VERDICT: PASS
TREE: 146430348a714eb7671a125b914d06cab4d596b4

C1–C13 MET. pytest 955 passed / 2 skipped; npm build ok; check_links OK; score.py R100 rename (blob identical); no secrets; no hard-coding. Undeclared: only path rewrites in .claude/agents, TEMPLATE.md, open-questions.md and historical memory-bank entries (covered by C8 / D-024).
