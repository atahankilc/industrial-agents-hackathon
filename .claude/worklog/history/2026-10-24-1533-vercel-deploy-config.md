# Vercel deploy config: services, /api prefix, bundle excludes

- **Author:** Claude (persistence/deploy session) · **Date:** 2026-10-24
- **Related:** D-006 (Vercel Python runtime + Services), docs/research/stack-options.md §9, docs/guides/commands.md

## Summary
Adds `vercel.json`, which defines one Vercel project with two Services: `web` (the Vite app) and `api` (FastAPI
`backend.app:app` from the repo root). `/api/*` routes to the backend and everything else to the frontend. Vercel
passes the original path through, so the backend strips a leading `/api` segment. CORS origins are now
configurable. The deploy steps and env vars are documented.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `vercel.json` defines services `web` (root `frontend/app/`, vite) and `api` (root `./`, fastapi, entrypoint `backend.app:app`, functions key `backend/app.py` with `maxDuration` 300 and `excludeFiles`), with rewrites `/api/(.*)` → api, then `/(.*)` → web | `vercel.json` | read; `tests/test_deploy.py` |
| C2 | `StripPrefix` ASGI middleware serves `/api/x` as `/x` (path and raw_path), touches only a whole `/api` segment (`/apiary`, `/api-health` untouched), and is outermost | `backend/app.py:StripPrefix` | `uv run pytest -q tests/test_deploy.py` → 8 passed |
| C3 | CORS origins come from `CORS_ORIGINS` (comma-separated, default `*`) | `backend/app.py` | read |
| C4 | The bundle excludes keep every `building.json`, `data/manifest.csv` and the backend/core/agent code, and drop archive/frontend/tests/docs/png | `vercel.json`, `tests/test_deploy.py::test_bundle_keeps_what_the_backend_reads_and_drops_the_rest` | pytest |
| C5 | commands.md has a "Deploy (Vercel)" section: architecture, Atahan's import steps, env var table, smoke test, UNVERIFIED items | `docs/guides/commands.md` | read; `python3 scripts/check_links.py` |
| C6 | Knowledge base updated: project-state.md priority 3 marks the Vercel config done and names the next step (Atahan imports + env vars + smoke test); log.md has a "Vercel deploy config" entry on top. The other session's uncommitted edits (Q-014 in open-questions.md, the route-model.md warning, the "Start here" handoff, its log.md entry) ship in this commit at their request, unchanged except one factual correction: the handoff's "Uncommitted in the working tree" paragraph now says persistence is in `188abd3` and the deploy config is in this commit, and `188abd3` is prepended to the latest-commits list | `memory-bank/project-state.md`, `memory-bank/log.md`, `memory-bank/open-questions.md`, `docs/kit/route-model.md` | `git diff --cached memory-bank docs/kit`; `python3 scripts/check_links.py` |

## Checks I ran

- `uv run pytest -q tests/test_deploy.py` → `8 passed in 1.24s`
- `uv run pytest -q` → `162 passed, 1 skipped in 18.04s`
- TestClient smoke: `/health 200`, `/api/health 200`, `/api 404`, `/apiary 404`, `/api/buildings 200`,
  `POST /api/sessions 200`
- Bundle estimate (git ls-files minus excludes, recursive globs): `kept 322 49 MB; building.json 280 manifest True`;
  local site-packages `180M` (it includes dev deps), so about 230 MB against the 500 MB limit
- `npm run build` in `frontend/app` → `✓ built in 262ms` (only a chunk-size warning)
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md`: priority 3 (Vercel config done, next step), handoff paragraph corrected, `188abd3` on the Git line; plus the other session's handoff section shipped as is
- [x] `memory-bank/log.md`: new "Vercel deploy config" entry on top; the other session's entry shipped as is
- [x] decisions / open questions touched: no decisions (implements accepted D-006); Q-014 added by the other session ships here
- [x] docs touched: `docs/guides/commands.md`; `docs/kit/route-model.md` (other session's Q-014 warning)

## Known gaps / not done
- Nothing is deployed. The repo isn't imported into Vercel yet (Atahan's step), and `dev` isn't pushed.
- UNVERIFIED until the first deploy: Services (beta) with root `./` alongside `frontend/app/`; Vercel's glob
  semantics for `excludeFiles` (the test uses an approximation of node-glob); the real bundle size; cold start.
- The frontend JS chunk is over 500 kB (Vite warning); no code splitting.
- `CORS_ORIGINS` defaults to `*` on Vercel too (the API has no auth; the frontend is same-origin).

## Fix round 1
- Knowledge base not updated: implemented — `memory-bank/project-state.md` priority 3 marks the Vercel config done
  (vercel.json, StripPrefix, CORS_ORIGINS, tests/test_deploy.py, link to commands.md#deploy-vercel, 162 passed) and
  names the next step (Atahan imports + sets ANTHROPIC_API_KEY / SUPABASE_DB_URL, smoke test, first-deploy UNVERIFIED
  items); handoff paragraph "Uncommitted in the working tree" rewritten (persistence in `188abd3`, deploy config in
  this commit, handoff ships with it); `188abd3` prepended on the Git line. `memory-bank/log.md`: new top entry
  "2026-10-24 — Vercel deploy config". The other session's edits in project-state.md, log.md, open-questions.md
  (Q-014) and docs/kit/route-model.md are staged in full, otherwise unchanged. Claim C6 added.
- Re-run checks: `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`;
  `uv run pytest -q` → `162 passed, 1 skipped in 17.77s`

## Verification rounds
- Round 1: VERDICT: FAIL (tree 9c91ae6) — knowledge base not updated → fix round 1
- Round 2: VERDICT: PASS (tree bc372a60d4974728af9f732a1b6ce10e12731d1a)

## Verification report (round 2)

VERDICT: PASS
TREE: bc372a60d4974728af9f732a1b6ce10e12731d1a

| # | Status | Evidence |
|---|---|---|
| C1 | MET | vercel.json services web/api, entrypoint backend.app:app, functions key backend/app.py (maxDuration 300, excludeFiles), rewrites /api/(.*) → api then /(.*) → web; tests pass |
| C2 | MET | StripPrefix rewrites path + raw_path only for a whole /api segment; added last = outermost; tests 8 passed; smoke /health 200, /api/health 200, /api 404, /apiary 404, /api/buildings 200 |
| C3 | MET | CORS origins from CORS_ORIGINS (default *) |
| C4 | MET | bundle test passes; nothing in backend/core/agent reads an excluded file at runtime |
| C5 | MET | commands.md "Deploy (Vercel)" section; links OK |
| C6 | MET | project-state priority 3 + handoff paragraph (188abd3) + Git line; log entry on top; Q-014 (next free Q-015); route-model warning. "Unchanged otherwise" couldn't be checked against an original copy |

Standard checks: pytest 162 passed, 1 skipped (same without the untracked tests/test_geodesic.py); links OK; no secrets; score.py unchanged; no hard-coding.
Undeclared changes: none staged. The untracked core/geodesic.py and tests/test_geodesic.py are another session's in-progress Q-014 work and aren't included. Minor: the handoff's "147 passed" line is stale (the other session's text, shipped unchanged).
