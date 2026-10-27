---
id: log
summary: Append-only dated session log, newest on top. The hackathon weekend's log is archived.
related: [project-state.md, ../archive/hackathon/log-2026-10-24-to-25.md]
---

# Log

[Memory bank](README.md) · Hackathon weekend (2026-10-24 – 2026-10-25):
[archive/hackathon/log-2026-10-24-to-25.md](../archive/hackathon/log-2026-10-24-to-25.md)

## 2026-10-27 — Local folder moved to `~/Documents/steward`

- Repo folder `~/Documents/industrial-agents-hackathon` → `~/Documents/steward`; worktree `collab-edits` →
  `~/Documents/steward-collab-edits` (`git worktree list` shows both paths). Claude's project memory copied over.
- The moved `.venv` broke `npm run dev`: its scripts' shebangs still pointed at the old folder, so `uv run uvicorn`
  ran Anaconda's Python 3.9 uvicorn and the backend died with `No module named 'anthropic'`. Fixed by recreating it
  (`rm -rf .venv && uv sync`); `pnpm run dev` then served backend `/docs` 200 on 8390 and the app 200 on 5390.
- WebStorm (local, `.idea/` is git-ignored): module file renamed to `steward.iml`, `.idea/.name` = `steward`.
- A `[vite] http proxy error … ECONNREFUSED 127.0.0.1:8390` right after start is the frontend asking before the
  backend listens (backend start took ~18 s on the fresh `.venv`); it stops once uvicorn is up.

## 2026-10-27 — Steward outside the repo: GitHub, Vercel, Supabase

- GitHub repo renamed `atahankilc/industrial-agents-hackathon` → `atahankilc/steward` (`gh repo rename`); `origin`
  points at the new URL; `dev` pushed (`9251dd8..b33c47c`); repo homepage → https://steward-io.vercel.app.
- Vercel project renamed by Atahan; `steward.vercel.app` and `steward-app.vercel.app` were taken, the app is at
  **https://steward-io.vercel.app** (`/` 200 with title "Steward", `/api/health` 200). The old
  `industrial-agents-hackathon.vercel.app` first answered 404 `DEPLOYMENT_NOT_FOUND`; later
  it answers a 308 to https://steward-io.vercel.app/ (`/api/health` → `/api/health` on steward-io).
- Voice was off on the deployment (`ELEVENLABS_API_KEY` missing in Vercel, so `/api/health` said `tts`/`stt`
  false and the app fell back to the browser's voice). Atahan added the key and redeployed: `tts`/`stt` true,
  `POST /api/tts` returns a 20 KB MP3, `POST /api/stt/token` 200.
- Supabase: Atahan renamed the project and set Site URL / Redirect URLs to steward-io (his report). Local folder: still to move.

## 2026-10-27 — The app is called Steward

- [D-027](decisions.md#d-027): name chosen with Atahan over several rounds (job titles, architecture terms; Maze
  rejected). Mark = the clay cutaway (three floors, you in a doorway); a single bold floor at 32 px and below; icon
  ground `#060606`. Moving the app's own dark HUD to that black was tried and reverted at his request.
- Renamed in README, CLAUDE.md, PRODUCT.md, `pyproject.toml` / `uv.lock`, both `package.json` (+ lock), `index.html`
  title and home-screen title, the web manifest (now also 192/512 icons), the FastAPI title, backend docstrings and
  the two OSM User-Agent strings. History (archive, hackathon references, research notes) keeps the old name.
- `scripts/brand/marks.cjs` draws every icon; `outline.py` turned "Steward" in Geist 500 (kerned) into
  `steward-outline.json` so the wordmark needs no font.
- Not done yet: GitHub, local folder, Vercel, Supabase (see project-state Next 0).

## 2026-10-27 — One command to run the app; own local ports

- `npm run dev` at the repo root (`package.json` → `scripts/dev.sh`) starts the backend and the Vite app together;
  Ctrl-C, TERM or either side exiting stops both (only the script's own process trees). It refuses a busy port.
  Without `.env` the backend runs `GUIDE_LLM=offline`.
- Default ports moved off 8765 / 5181 (Vite's 5173 when started bare) to **8390** (backend) and **5390** (app), so
  this project no longer clashes with other local projects (north-star runs on 5288). `frontend/vite.config.ts`:
  `port: 5390`, `strictPort`, proxy default `127.0.0.1:8390`; `BACKEND_PORT` / `FRONTEND_PORT` override.
  README, `docs/guides/commands.md`, `backend/api/app.py` docstring and `scripts/sim_object.py` default updated;
  `vercel.json` leaves the root `package.json` out of the function bundle.
- Checked: `npm run dev` serves `/api/health` through the app on 5390; a second copy on 8391/5391 stops fully on TERM
  and when its backend is killed, and leaves the first copy running; a busy port exits 1 with a message;
  `uv run pytest tests/test_deploy.py -q` 8 passed.

## 2026-10-27 — Guide tools and living building split into packages

- [D-026](decisions.md#d-026): `backend/agents/tools.py` → `backend/agents/tools/` (session + 7 mixins + definitions +
  shared); `backend/api/live.py` → `backend/api/live/` (world, hub, reroute, endpoints). `__init__.py` re-exports
  keep every import working; code moved verbatim (checked with `inspect.getsource` against the old modules).
  References to the old paths in code comments, docs and the frontend now point at the packages.
- Checked: `uv run pytest -q` 955 passed / 2 skipped, `uvx ruff check --select F,E9` clean on both packages,
  `check_links.py` OK.

## 2026-10-27 — One solver implementation; API routers

- [D-025](decisions.md#d-025): `core/solvers_v1.py` removed; `compute`'s `solve()` runs `backend/core/solvers/`
  (`SolverResult.to_dict()`, shared with the `solve` tool). `tests/test_solvers.py` now checks the canonical solvers
  (655/655 on gold inputs and from text); the errand-walkability check moved from `tests/test_routes.py` to
  `tests/test_solvers_routing.py` (all 93 errands); `tests/test_compute.py` gained a `solve()` check.
- `backend/api/app.py` (1164 lines) split: `app.py` assembles (~120), `deps.py` shared stores + guards,
  `routes/{guide,voice,accounts,drafts,imports,openai_chat}.py`. Code moved verbatim except stores read as `deps.X`.
  Checked: identical OpenAPI (58 operations), `uv run pytest -q` 955 passed / 2 skipped, uvicorn boots and answers
  `/api/health`, `/sessions`, `/buildings`.

## 2026-10-27 — Repo restructure: frontend/ + backend/{api,agents,core}

- [D-024](decisions.md#d-024): `frontend/app/` → `frontend/`; `backend/` → `backend/api/`, `agent/` →
  `backend/agents/`, `core/` → `backend/core/` (one Python package `backend`); `benchmark/score.py` →
  `tests/kit_oracles/score.py` (unmodified). Imports, `vercel.json` (web root `frontend/`, entrypoint
  `backend.api.app:app`), `pyproject.toml` (`packages = ["backend"]`), `DATA_DIR` (`parents[2]`), CLAUDE.md, README,
  docs and memory-bank paths updated; archived-file paths and the worklog history left as they were.
- Checked: `uv run pytest -q` 955 passed / 2 skipped (same as before), `npm run build`, `check_links.py`.
  Not checked: a real Vercel deploy.

## 2026-10-26 — Location dot back after a reload inside a building

- `frontend/src/map/MapLanding.tsx`: the "show my location" step ran only on the map's first mount and skipped
  itself when a building was open, so a reload inside a building never showed the dot on the map. It now waits for
  the map to be shown (no open building) and runs once; a run undone before the browser answered (dev double mount)
  asks again. Checked with `npm run build`; not tried in a browser (extension not connected).

## 2026-10-26 — Living building noted as demo-grade

- Opened [Q-021](open-questions.md#q-021): `backend/api/live.py` keeps device positions in serverless-instance memory
  (no Supabase), so positions freeze without requests, differ between instances and vanish with the instance.
  Atahan: good enough for now; linked from [project-state.md](project-state.md) small gaps.

## 2026-10-26 — LLM parser, solver agent and decision cache archived

- Atahan: delete `llm_cache/` (done, it was untracked) and, on Claude's recommendation, archive what only the
  benchmark used. The app used just two small parts: the python sandbox of `agent/solver_agent.py` (now
  `backend/agents/compute.py`, the Guide's `compute` tool; its 5 tests in `tests/test_compute.py`) and `LlmUsage` /
  `building_vocabulary` of `agent/llm_parser.py` (now in `backend/agents/rewriter.py`). Archived to
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md): `agent/llm_parser.py`, `agent/solver_agent.py`, `agent/llm_cache.py`,
  `tests/test_llm_route_spec.py`, `tests/test_solver_agent.py`, `tests/fake_llm.py`, `tests/conftest.py`.
  `core/question_parser.py`, `core/basic_parser.py`, `core/formatter.py` (test oracles only) moved to
  `tests/kit_oracles/`. pytest 955 passed, 2 skipped (978 − 28 archived + 5 moved).

## 2026-10-26 — Benchmark code archived

- Atahan: move everything about the hackathon that the app does not use to the archive. Moved with `git mv` to
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md): `agent/answer.py`, `agent/benchmark_agent.py`, `agent/parsing.py`,
  `agent/run_benchmark.py`, `agent/run_benchmark_v1.py`, `agent/guide_v1/`, `benchmark/evaluate.py`,
  `scripts/eval_llm_parser.py`, `scripts/eval_sunday_probe.py`, `tests/sunday_probe/` and their 10 tests; the
  benchmark sections of commands.md went into that README. `docs/challenge/` and `docs/kit/starter-agent.md` moved to
  `archive/hackathon/docs/`. Kept (test oracles for app code): `tests/kit_oracles/score.py`, `core/formatter.py`,
  `core/basic_parser.py`. `tests/fake_llm.py` now holds the fake client `tests/test_llm_route_spec.py` needs;
  `pyproject.toml`: `testpaths = ["tests"]`, the `run_benchmark` script entry removed. pytest 978 passed, 2 skipped.
- Re-score by another session (scratchpad only, UNVERIFIED here): with the right answer format and the bay /
  forklift rules on, ~0.89 on the jury's 36 sample questions; our submitted answers scored 0.19–0.33.

## 2026-10-26 — Post-hackathon cleanup

- Git: `main` fast-forwarded into `dev` (same commit `25c79b5`); deleted the merged local branches
  `backup/dev-before-pull-1043` and `voice-improvements`; pruned the stale `.claude/worktrees/voice-improvements`
  worktree; saved the 4 stashes as branches `archive/stash-0` … `archive/stash-3` and cleared the stash list;
  `git gc` (131 MB → 102 MB). Not done (needs Atahan's permission): push `dev`, delete the merged remote branches
  `2-builder-edit`, `4-sunday-agent`, `7-buildings-from-plans`.
- Moved hackathon material to [archive/hackathon/](../archive/hackathon/README.md): `SUBMISSION/`, the organiser
  PDF, technical explanation, demo runbook, the superpowers specs and plans (from `docs/`), the weekend log and the last
  project state. Links rewritten; `check_links.py` OK.
- New short [project-state.md](project-state.md); CLAUDE.md, README.md and docs index rewritten for ongoing
  development; hackathon-only questions closed ([Q-001](open-questions.md#q-001),
  [Q-002](open-questions.md#q-002), [Q-014](open-questions.md#q-014), [Q-017](open-questions.md#q-017),
  [Q-018](open-questions.md#q-018), [Q-019](open-questions.md#q-019)).
- Removed the unused `frontend/src/ui/Chat.tsx`.
- Held: removing the benchmark-only code (another session was re-scoring with `agent/run_benchmark_v1.py`).
