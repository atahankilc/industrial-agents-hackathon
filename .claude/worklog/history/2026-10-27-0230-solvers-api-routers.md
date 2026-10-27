# One solver implementation; split the FastAPI app into routers

- **Author:** Claude session for Atahan · **Date:** 2026-10-27 02:30
- **Related:** D-025 (new), D-024

## Summary
Removes the duplicate v1 solvers (`backend/core/solvers_v1.py`): the Guide's `compute` sandbox now calls the
canonical `backend/core/solvers/`. Splits `backend/api/app.py` (1164 lines) into an assembling `app.py`, shared
`deps.py` and one router per area under `backend/api/routes/`. No endpoint changes.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `backend/core/solvers_v1.py` deleted; no code imports it | tree | `git grep -n solvers_v1 -- backend tests scripts` → only a docstring mention in `route_query.py` saying it was removed |
| C2 | `compute`'s `solve(kind, **inputs)` runs `backend.core.solvers.solve` and returns `SolverResult.to_dict()`; `tool_solve` returns the same `to_dict()` (same keys as before: value, unit, area_m2, explanation, evidence) | `backend/agents/compute.py`, `backend/agents/tools.py:tool_solve`, `backend/core/solvers/__init__.py:SolverResult.to_dict` | read; `uv run pytest tests/test_compute.py -q` (new `test_solve_helper_runs_the_canonical_solvers`) |
| C3 | `tests/test_solvers.py` checks the canonical solvers: 655/655 on gold inputs and from question text | `tests/test_solvers.py` | `uv run pytest tests/test_solvers.py -q -s` → both tables `all 655 / 655` |
| C4 | The v1 errand-walkability test moved to canonical evidence and now covers all labelled errands; removed from `test_routes.py` | `tests/test_solvers_routing.py:test_errand_evidence_legs_are_walkable_and_sum`, `tests/test_routes.py` | read; `uv run pytest tests/test_solvers_routing.py tests/test_routes.py -q` |
| C5 | `backend/api/app.py` only assembles: middleware (CORS, gzip, StripPrefix, drafts_admin_only), exception handlers, `/health`, `include_router` for the six route modules + live, fleet, devtools | `backend/api/app.py` | read (~120 lines) |
| C6 | Shared stores (`store`, `drafts`, `access`, `live`, `fleet`) and guards (`viewer_or_401`, `conversation_or_404`, `with_*`, `save_or_409`, `admin_or_403`, `known_or_422`, `viewer_restricted`, `draft_or_404`, `ndjson_with_pings`) live in `backend/api/deps.py`; routers read stores as `deps.X` | `backend/api/deps.py`, `backend/api/routes/*.py` | read; `grep -nE '^from backend.api.deps import' backend/api/routes/*.py` shows no store names |
| C7 | Endpoint code moved verbatim to `routes/{guide,voice,accounts,drafts,imports,openai_chat}.py` (only `@app.`→`@router.` and store reads → `deps.X`) | `backend/api/routes/` | compare with `git show HEAD:backend/api/app.py` |
| C8 | The app serves the same API: OpenAPI paths, methods, parameter names and schema names identical before/after (58 operations) | — | dump `app.openapi()` of `git show HEAD:backend/api/app.py` and of the new app, compare sorted |
| C9 | Tests patch the new homes (`backend.api.deps`, `backend.api.routes.drafts`, `backend.api.routes.imports`) instead of `backend.api.app` globals | `tests/test_*.py` | `git grep -nE 'backend_app\.(store\|drafts\|make_creator\|load_builder)' tests` → empty |
| C10 | Docs/memory bank: D-025 accepted (Next free id D-026), log entry, project-state backend line, CLAUDE.md tree, overview layout, solver-plan + ai-agents solver notes, stt/tts/devtools docstrings | those files | read; `python3 scripts/check_links.py` → OK |
| C11 | Full suite passes | — | `uv run pytest -q` → 955 passed, 2 skipped |
| C12 | No new lint errors (pyflakes rules) | — | `uvx ruff check --select F,E9 backend tests scripts` → 16 errors, all pre-existing F811 pytest-fixture redefinitions in `tests/test_import_location.py` etc. (same count as before the change) |

## Checks I ran
- `uv run pytest tests/test_solvers.py -q -s` → `all 655 / 655` twice, `2 passed`
- `uv run pytest tests/test_solvers_routing.py tests/test_routes.py -q` → `7 passed`
- `uv run pytest tests/test_compute.py -q` → `6 passed`
- OpenAPI comparison old vs new → `SAME-SET` (58 operations + 30 schema names; recount: `app.openapi()` → 58 operations, 30 schemas); declaration order differs (routes grouped by router), no overlapping path patterns across routers
- `uv run pytest -q` → `955 passed, 2 skipped in 112.95s`
- `GUIDE_LLM=offline uv run uvicorn backend.api.app:app --port 8799` → `/api/health` `{"ok":true,"llm":"offline",...}`, `POST /api/sessions` returns a session, `GET /buildings` returns the list
- `uvx ruff check --select F,E9 backend tests scripts` → 16 errors (baseline before the change: 16), all F811 in fixtures
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions: D-025 added
- [x] docs touched: overview.md, solver-plan.md, ai-agents.md, commands.md (sources), CLAUDE.md tree

## Known gaps / not done
- `compute`'s `solve()` lost the v1-only kinds (`locate`, `count`, `route*`, `tour`, `route_query`); the sandbox's `route()` and the Guide's own tools cover them. Not tried against a live model.
- `backend/agents/tools.py` (~1175 lines) and `backend/api/live.py` (~1080 lines) are still large; not split here.
- Real Vercel deploy not run.
- `collab-edits` branch will conflict with the `app.py` split (endpoints now in `routes/`).

## Verification rounds
- Round 1: FAIL — C8 count says 59 operations, real count 58

## Fix round 1
- C8 operation count: claim corrected — "59 operations" → "58 operations" (recounted with `app.openapi()`: 58 operations, 30 schemas) in `.claude/worklog/PENDING.md` (C8, Checks I ran), `memory-bank/log.md` (2026-10-27 entry), `memory-bank/decisions.md` (D-025 Evidence)
- Stale path comments: implemented — `tests/test_imports_api.py:1` now points to `backend/api/routes/imports.py`; `frontend/src/api.ts:1` now says `(backend/api/, routes in backend/api/routes/)`
- Checks: `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`; `uv run pytest tests/test_imports_api.py -q` → `9 passed in 11.65s`
- Round 2: PASS — all claims C1–C12 MET

## Verification report (round 2)

VERDICT: PASS
TREE: e778f09e17e65fe1f2cfa52f33bbca99adc9c055

C1–C12 MET. pytest 955 passed / 2 skipped; test_solvers 655/655 x2; OpenAPI identical (58 operations, 30 schemas); AST check: every old top-level def/class/assign present and identical after normalisation; ruff 16 = baseline; check_links OK; uvicorn boot ok; no secrets; score.py unchanged.
