---
id: project-state
summary: Current phase, what exists, what is next, blockers. Read first every session.
updated: 2026-10-26
related: [decisions.md, open-questions.md, log.md, ../archive/hackathon/README.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-26** (post-hackathon cleanup)

## Phase

**Ongoing development.** The Industrial Agents Hackathon 2026 is over: the project was submitted on 2026-10-25.
Everything from the hackathon weekend (submission files, organiser PDF, demo runbook, technical explanation, the
weekend's design specs and plans, the full session log and the last hackathon project state) is in
[archive/hackathon/](../archive/hackathon/README.md). Read it when you need the history behind a feature.

## What exists

- **App** (`frontend/app/`, React + Vite, [D-011](decisions.md#d-011)): a map landing with buildings at real
  positions (`src/map/`, `backend/locations.json`) and a list of all kit buildings (`src/search/`). The building
  screen has a vector plan view (`src/plan/`, data from `core/floorplan.py`), a floating Guide with voice
  (`src/voice/`, [D-016](decisions.md#d-016)–[D-019](decisions.md#d-019)), route overview then step-by-step
  following ([D-020](decisions.md#d-020)), Edit mode (`src/edit/`), access mode (`src/access/`,
  [D-015](decisions.md#d-015)), the living building (`src/live/`) and buildings created from floor plans
  (`src/import/`, [D-023](decisions.md#d-023)).
- **Backend** (`backend/app.py`, FastAPI): sessions, plan, chat and chat/stream, drafts, imports, live/fleet,
  STT/TTS, an OpenAI-compatible `/v1/chat/completions`, Supabase persistence (`backend/persistence.py`).
- **Agents** (`agent/`): the Guide (`guide.py` + `tools.py`), the Builder (`builder.py`), the Creator / plan
  import (`creator.py`, `core/plan_import/`), campus / nearby buildings (`campus.py`,
  [D-021](decisions.md#d-021)), the transcript rewriter (`rewriter.py`, [Q-020](open-questions.md#q-020)).
- **Core** (`core/`): the kit 1.1.0 route model (`building_map.py`, [D-014](decisions.md#d-014)), solvers,
  directions, edits and validation, access, live obstacles and fleet, geoplacement.
- **Benchmark tooling** (kept for re-scoring): `benchmark/` (official kit scorer, never edit `score.py`),
  `agent/run_benchmark_v1.py` + `agent/answer.py` (the submission pipeline), `agent/run_benchmark.py` +
  `agent/benchmark_agent.py`, `agent/guide_v1/`, `core/formatter.py`, `llm_cache/`. Commands:
  [commands.md](../docs/guides/commands.md).
- **Deploy:** Vercel (`vercel.json`: services `web` + `api`) + Supabase (`supabase/migrations/`),
  [D-006](decisions.md#d-006).
- **Data:** kit dataset committed in `data/` ([D-005](decisions.md#d-005)); licences in `NOTICE.md`,
  `ATTRIBUTION.md`, `data/README.md` ([D-009](decisions.md#d-009)).
- **Workflow:** verified commits via `/ship` ([D-008](decisions.md#d-008),
  [dev-workflow.md](../docs/guides/dev-workflow.md)); work on `dev`, never on `main`.

## What works (verified 2026-10-26)

- `uv run pytest -q` → 1088 passed, 2 skipped.
- `python3 scripts/check_links.py` → all links resolve.
- `main` and `dev` are on the same commit (`25c79b5`) since the 2026-10-26 cleanup.

## Next

1. **Decide the fate of the benchmark-only code.** Candidates: `agent/answer.py`, `agent/benchmark_agent.py`,
   `agent/parsing.py`, `agent/run_benchmark*.py`, `agent/guide_v1/`, `core/formatter.py`, `core/basic_parser.py`
   (unused, only a script and one test reference it) plus their scripts and tests. None of them is reachable from
   `backend/app.py`. Held on 2026-10-26 while another session re-scored the jury's eval questions; Atahan to decide:
   keep for re-scoring, move to `archive/`, or delete. Finding from that re-score (2026-10-26, reported by the
   other session, UNVERIFIED here): the jury's eval data marks factory bays with `through: false`, our core ignores
   the flag, and that is the main reason our routes scored 0. Fixing it in `core/` and re-scoring with
   `agent/run_benchmark_v1.py` is an argument for keeping the runners.
2. **Slim `data/`?** 208 MB / 3,475 files; `data/train` alone is 122 MB. Only worth it if the app needs fewer
   buildings (the list shows all of them). Keep the licence files in step.
3. **Branch `collab-edits`** (worktree `../iah-collab-edits`): 1 commit not in `dev` (shared building edits,
   collaboration phase 1) plus uncommitted changes. Finish or drop.
4. **Old stashes** saved as branches `archive/stash-0` … `archive/stash-3` (2026-10-24/25 pull and rebase
   backups). Delete once nobody needs them.
5. **Small gaps:** `BuildingSession.route_model` is not saved by `backend/persistence.py`; live smoke test of the
   deployed app (URL not recorded here).
6. **Product:** phone-layout check; in-space walk polylines instead of straight door-to-door lines; closure ripple
   for edits; ElevenLabs Custom LLM on `/v1/chat/completions` (ask before creating anything in any account).

## Blockers

- None.
