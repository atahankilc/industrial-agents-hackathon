---
id: project-state
summary: Current phase, what exists, what is next, blockers. Read first every session.
updated: 2026-10-27
related: [decisions.md, open-questions.md, log.md, ../archive/hackathon/README.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-27** (repo restructure [D-024](decisions.md#d-024), solvers + API routers [D-025](decisions.md#d-025), tool layer + live packages [D-026](decisions.md#d-026))

## Phase

**Ongoing development.** The Industrial Agents Hackathon 2026 is over: the project was submitted on 2026-10-25.
Everything from the hackathon weekend (submission files, organiser PDF, demo runbook, technical explanation, the
weekend's design specs and plans, the full session log and the last hackathon project state) is in
[archive/hackathon/](../archive/hackathon/README.md). Read it when you need the history behind a feature.

## What exists

Layout ([D-024](decisions.md#d-024)): `frontend/` (React) and `backend/` (all Python: `api/` → `agents/` → `core/`).

- **App** (`frontend/`, React + Vite, [D-011](decisions.md#d-011)): a map landing with buildings at real
  positions (`src/map/`, `backend/api/locations.json`) and a list of all kit buildings (`src/search/`). The building
  screen has a vector plan view (`src/plan/`, data from `backend/core/floorplan.py`), a floating Guide with voice
  (`src/voice/`, [D-016](decisions.md#d-016)–[D-019](decisions.md#d-019)), route overview then step-by-step
  following ([D-020](decisions.md#d-020)), Edit mode (`src/edit/`), access mode (`src/access/`,
  [D-015](decisions.md#d-015)), the living building (`src/live/`) and buildings created from floor plans
  (`src/import/`, [D-023](decisions.md#d-023)).
- **Backend** (`backend/api/`, FastAPI: `app.py` assembles the routers in `routes/`, shared stores in `deps.py`): sessions, plan, chat and chat/stream, drafts, imports, live/fleet,
  STT/TTS, an OpenAI-compatible `/v1/chat/completions`, Supabase persistence (`backend/api/persistence.py`).
- **Agents** (`backend/agents/`): the Guide (`guide.py` + the `tools/` package), the Builder (`builder.py`), the Creator / plan
  import (`creator.py`, `backend/core/plan_import/`), campus / nearby buildings (`campus.py`,
  [D-021](decisions.md#d-021)), the transcript rewriter (`rewriter.py`, [Q-020](open-questions.md#q-020)).
- **Core** (`backend/core/`): the kit 1.1.0 route model (`building_map.py`, [D-014](decisions.md#d-014)), solvers,
  directions, edits and validation, access, live obstacles and fleet, geoplacement.
- **Benchmark:** the runners, kit evaluator and v1 Guide are archived in
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md) (2026-10-26). The LLM parser, solver agent and decision cache followed
  (2026-10-26); the Guide's python sandbox is now `backend/agents/compute.py`. Test oracles for the solvers the app uses:
  `tests/kit_oracles/score.py` (official kit scorer, never edit) and `tests/kit_oracles/` (question parsers, formatter).
- **Deploy:** Vercel (`vercel.json`: services `web` + `api`) + Supabase (`supabase/migrations/`),
  [D-006](decisions.md#d-006).
- **Data:** kit dataset committed in `data/` ([D-005](decisions.md#d-005)); licences in `NOTICE.md`,
  `ATTRIBUTION.md`, `data/README.md` ([D-009](decisions.md#d-009)).
- **Workflow:** verified commits via `/ship` ([D-008](decisions.md#d-008),
  [dev-workflow.md](../docs/guides/dev-workflow.md)); work on `dev`, never on `main`.

## What works (verified 2026-10-27)

- `npm run dev` (repo root) → backend http://127.0.0.1:8390 + app http://localhost:5390.
- `uv run pytest -q` → 955 passed, 2 skipped (after archiving the benchmark tests).
- `python3 scripts/check_links.py` → all links resolve.
- `main` and `dev` are on the same commit (`25c79b5`) since the 2026-10-26 cleanup.

## Next

1. **Bays marked `through: false`.** The jury's eval data marks factory bays with `through: false` and our core
   ignores the flag; another session's re-score (2026-10-26, UNVERIFIED here) says that is the main reason our routes
   scored 0, and that with it and the right answer format we would have reached ~0.89 on the 36 sample questions.
   Worth handling in `backend/core/` for the app too (people should not be routed through a bay). The benchmark runners
   to re-score are archived in [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md) with how to restore them.
2. **Slim `data/`?** 208 MB / 3,475 files; `data/train` alone is 122 MB. Only worth it if the app needs fewer
   buildings (the list shows all of them). Keep the licence files in step.
3. **Branch `collab-edits`** (worktree `../iah-collab-edits`, started before the D-024 restructure, so it needs a
   rebase onto the new paths): 1 commit not in `dev` (shared building edits,
   collaboration phase 1) plus uncommitted changes. Finish or drop.
4. **Old stashes** saved as branches `archive/stash-0` … `archive/stash-3` (2026-10-24/25 pull and rebase
   backups). Delete once nobody needs them.
5. **Small gaps:** `BuildingSession.route_model` is not saved by `backend/api/persistence.py`; live smoke test of the
   deployed app (URL not recorded here).
   Living building state is in-memory per function instance, not production-ready for real devices
   ([Q-021](open-questions.md#q-021)).
6. **Product:** phone-layout check; in-space walk polylines instead of straight door-to-door lines; closure ripple
   for edits; ElevenLabs Custom LLM on `/v1/chat/completions` (ask before creating anything in any account).

## Blockers

- None.
