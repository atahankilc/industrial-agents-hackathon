---
id: project-state
summary: Current phase, what exists, what is next, blockers. Read first every session.
updated: 2026-10-30
related: [decisions.md, open-questions.md, log.md, ../archive/hackathon/README.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-30** (organisations phases 1–3 and main-map badges [D-029](decisions.md#d-029), dataset in one folder [D-028](decisions.md#d-028), rename to Steward [D-027](decisions.md#d-027), repo restructure [D-024](decisions.md#d-024), solvers + API routers [D-025](decisions.md#d-025), tool layer + live packages [D-026](decisions.md#d-026))

## Phase

**Ongoing development.** The Industrial Agents Hackathon 2026 is over: the project was submitted on 2026-10-25.
Everything from the hackathon weekend (submission files, organiser PDF, demo runbook, technical explanation, the
weekend's design specs and plans, the full session log and the last hackathon project state) is in
[archive/hackathon/](../archive/hackathon/README.md). Read it when you need the history behind a feature.

## What exists

Layout ([D-024](decisions.md#d-024)): `frontend/` (React) and `backend/` (all Python: `api/` → `agents/` → `core/`).

- **App** (`frontend/`, React + Vite, [D-011](decisions.md#d-011)): a map landing with buildings at real
  positions (`src/map/`, `backend/api/locations.json`) under Steward's mark and wordmark (`src/brand/`, plan-wall
  letters) and a search pill; a click opens the list in a card round it (2026-10-27); the panel lists every kit building, the ones on the map first (the separate
  `?view=list` page was removed 2026-10-27). The building
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
- **Data:** kit dataset committed in `data/buildings/<id>/` ([D-005](decisions.md#d-005), [D-028](decisions.md#d-028):
  one folder, split only in `manifest.csv`, no floor renders, 65 MB); licences in `NOTICE.md`,
  `ATTRIBUTION.md`, `data/README.md` ([D-009](decisions.md#d-009)).
- **Organisations, phase 1** ([D-029](decisions.md#d-029) proposed, [organizations.md](../docs/product/organizations.md)):
  orgs with viewer / editor / owner roles, buildings owned by an org, listing listed / unlisted / private instead of
  `public`, `/orgs` API, per-building admin rights (`can_admin`), the Guide's neighbours filtered per viewer. Backend
  only; migration `20261028120000_orgs.sql` written, **not applied** to Supabase yet.
- **Organisations, phase 2a/2b** ([organizations.md](../docs/product/organizations.md)): maps (`backend/api/maps.py`,
  `/maps` routes; private / link / public, share key), `?map=<slug>[&k=]` scopes the landing to a map, the
  Organisations sheet (`frontend/src/org/`, account menu), Building settings for org editors with three listings.
  Migration `20261029120000_maps.sql` written, **not applied**.
- **Organisations, phase 2c:** org editors use Edit mode on their org's buildings and, in a verified org, create
  buildings from plans; saves belong to the org (and go onto the org map they were made from).
- **Organisations, phase 3 (first cut):** an org map (`?map=`) is an island board (`frontend/src/map/board.ts`,
  `boardTiles.ts`): sites side by side on tiles cut from the real ones in the browser, seams saying the real distance,
  the buildings and the open model moved with their island. Editors arrange (drag, pull to edges), name the
  islands and draw their (rectangular) areas, stored in the map's `layout`. The blue dot shows on the board when the user
  stands on an island, else the nearest site and its distance. Not yet: merging / splitting sites, areas of any shape.
- **Organisations, badges on the main map** (2026-10-30): an org's buildings carry its name (under the map label, a
  chip in the list); the picked one's chip opens the org's public map (`GET /buildings` `badge`).
- **Organisations, the Guide on a map:** on `?map=` the app sends the map (`X-Steward-Map[-Key]`); the Guide then
  counts the map's buildings the viewer may open through it among the neighbours (`deps.shown_by_map`).
- **Workflow:** verified commits via `/ship` ([D-008](decisions.md#d-008),
  [dev-workflow.md](../docs/guides/dev-workflow.md)); work on `dev`, never on `main`.

## What works (verified 2026-10-27, deploy 2026-10-28)

- `npm run dev` (repo root) → backend http://127.0.0.1:8390 + app http://localhost:5390.
- `uv run pytest -q` → 982 passed, 2 skipped (2026-10-30, with the organisations tests).
- `python3 scripts/check_links.py` → all links resolve.
- `main` is at `30ddf99` (PR #11, 2026-10-28: data/buildings merge, README features, CLAUDE.md); production serves it.
- Deployed app: https://steward-io.vercel.app → `/` 200 (title "Steward"), `/api/health` 200
  `{"ok":true,"llm":"anthropic","tts":true,"stt":true}`; `POST /api/tts` returns MP3, `POST /api/stt/token` 200
  (checked 2026-10-27, after `ELEVENLABS_API_KEY` was added to Vercel). After D-028 (2026-10-28): `/api/buildings` 286
  entries with kit ids like `osm-way10053349`; `POST /api/sessions` 200 for `proc-campus-train-000` and for the saved
  `user/arcisstra-e-21-edited`; the old id `train/proc-campus-train-000` → 422.

## Next

- **Organisations — handoff (2026-10-29, end of session):** phases 1–3 are committed on `dev`, last commit `d6de58c`.
  `origin/dev` is at `d6de58c` too (phases 1–3 pushed to `dev`), not merged to `main` (`30ddf99`); logs in
  `.claude/worklog/history/2026-10-29-*`. In order:
  1. **Apply the two migrations** `supabase/migrations/20261028120000_orgs.sql` and `20261029120000_maps.sql` to the
     shared Supabase DB: **only after Atahan says so explicitly** (asked, not yet answered). The code reads the new
     tables and columns, so `dev` must not be deployed before they are in. Then PR `dev` → `main` when asked.
     (2026-10-30: Atahan said go ahead; the apply was blocked by Claude Code's auto-mode permission check, so Atahan
     runs it or allows it. Still **not applied**.)
  2. After a deploy: the admin verifies an org and gives it buildings (no orgs exist yet).
  3. Done 2026-10-30: the `headers()` JSDoc in `frontend/src/api.ts` sits above `headers()` again (it was above
     `mapHeaders`, verifier note on `d6de58c`).
  4. Open work, Atahan to pick: a per-org Creator quota; merging / splitting sites;
     polygon areas (now rectangles); phase 4 (email-domain join, iframe embed, paged listing).
  5. Questions for Atahan: [Q-022](open-questions.md#q-022) (who may start an org), [Q-023](open-questions.md#q-023)
     (islands show streets: built as the default), [Q-024](open-questions.md#q-024) (name of a map, owner of `user/*`).
  Browser checks of the board were headless Playwright scripts in the session scratchpad (gone now): an in-memory
  backend with a fake owner token and a public map of four TUM buildings (Hauptgebäude, Mensa, StudiTUM, TUM 4107).

0. **Rename to Steward outside the repo** ([D-027](decisions.md#d-027)): done: GitHub repo → `atahankilc/steward`
   (remote updated, homepage set), Vercel project → `steward`, deployed at https://steward-io.vercel.app
   (`steward.vercel.app` and `steward-app.vercel.app` were taken). Supabase project renamed and Auth URL configuration
   (Site URL, Redirect URLs → steward-io) updated by Atahan by hand (his report; not checked from here). The old `industrial-agents-hackathon.vercel.app` now
   answers a 308 redirect to https://steward-io.vercel.app/, `/api/*` paths included (checked 2026-10-27). Local folder moved to `~/Documents/steward`, the
   `collab-edits` worktree to `~/Documents/steward-collab-edits` (`git worktree list` shows both), Claude's project
   memory copied over. After a folder move, recreate `.venv` (`rm -rf .venv && uv sync`): its scripts keep the old
   absolute path and `uv run uvicorn` then falls back to another Python on `PATH`.
1. **Bays marked `through: false`.** The jury's eval data marks factory bays with `through: false` and our core
   ignores the flag; another session's re-score (2026-10-26, UNVERIFIED here) says that is the main reason our routes
   scored 0, and that with it and the right answer format we would have reached ~0.89 on the 36 sample questions.
   Worth handling in `backend/core/` for the app too (people should not be routed through a bay). The benchmark runners
   to re-score are archived in [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md) with how to restore them.
2. **Production deploys from `main`** (PRs `dev` → `main`); a push to `dev` only makes a Vercel preview. Seen on
   2026-10-28: right after the PR #11 deploy every `/api/*` call answered 500 `FUNCTION_INVOCATION_FAILED` for
   ~2–3 min, then recovered by itself (cause unknown: no Vercel logs from here; the same bundle and DB ran fine locally).
   Worth a look in the Vercel logs if it repeats.
3. **Branch `collab-edits`** (worktree `../steward-collab-edits`, started before the D-024 restructure, so it needs a
   rebase onto the new paths): 1 commit not in `dev` (shared building edits,
   collaboration phase 1) plus uncommitted changes. Finish or drop.
4. **Old stashes** saved as branches `archive/stash-0` … `archive/stash-3` (2026-10-24/25 pull and rebase
   backups). Delete once nobody needs them.
5. **Small gaps:** `BuildingSession.route_model` is not saved by `backend/api/persistence.py`.
   Living building state is in-memory per function instance, not production-ready for real devices
   ([Q-021](open-questions.md#q-021)).
6. **Product:** phone-layout check; in-space walk polylines instead of straight door-to-door lines; closure ripple
   for edits; ElevenLabs Custom LLM on `/v1/chat/completions` (ask before creating anything in any account).

## Blockers

- None.
