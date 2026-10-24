---
id: project-state
summary: Current phase, what exists, what works, next priorities, blockers. Read first every session.
updated: 2026-10-24
related: [decisions.md, open-questions.md, log.md, ../docs/architecture/solver-plan.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-24** (Guide session: conversation loop + backend skeleton, offline)

## Phase

**Phase 1 ✅ · Phase 2 ✅ (dev 138/138) · Phase 3 ✅ · Phase 4 — UI ✅ first version (`frontend/app/`), voice next**

Planned phases (proposal, see [overview.md](../docs/architecture/overview.md)):

| Phase | Goal | Done when |
|---|---|---|
| 0 Foundation | docs, memory bank, CLAUDE.md | ✅ 2026-10-24 |
| 1 Core + solvers | per-kind solvers verified on train+dev `inputs` | ✅ 2026-10-24 — 655/655 |
| 2 Benchmark runner | question text → solver → `Answer:` reply; dev score via `benchmark.evaluate`; test CSV | ✅ 2026-10-24 — dev 138/138, `agent.run_benchmark`, [BENCHMARK.md](../BENCHMARK.md) |
| 3 Agent + interaction | conversational agent with clarifications, directions, closures, edits | scripted tricky-user conversation works — ✅ 2026-10-24 offline (`tests/test_guide.py`) + live (`scripts/live_guide.py`) |
| 4 App/UI + voice | 2D view with route, then stacked floors; voice | demoable |
| 5 Build + extend | plan → building (L4), one add-in (L5) | demoable |
| 6 Submission | `BENCHMARK.md`, Sunday run, video, tech explanation | submitted before code freeze |

## What exists

- Repo root is the build root ([D-004](decisions.md#d-004)): `core/` (building_map from the kit + question_parser),
  `benchmark/` (official scorer), `data/` (committed, [D-005](decisions.md#d-005)), `tests/`, `pyproject.toml` (uv,
  pytest dev dep). Kit remainder in `archive/initial-repo/`.
- Knowledge base: [docs/](../docs/README.md) incl. architecture, agents, personas, routing profiles, research.
- Point-cloud 3D prototype: `frontend/prototypes/pointcloud/` (exporter + three.js viewer), see
  [visualization.md](../docs/product/visualization.md).
- Licensing: `LICENSE` (MIT, our code only), `NOTICE.md` (third-party paths + terms), `data/README.md`
  (per-source data licences) — [D-009](decisions.md#d-009) accepted.
- Verified-commit workflow in `.claude/` (verifier + fixer agents, `/ship` skill, commit-gate hook, worklog) —
  [D-008](decisions.md#d-008), [dev-workflow.md](../docs/guides/dev-workflow.md).
- Git: `main`; `origin` = https://github.com/atahankilc/industrial-agents-hackathon.git (public); first commit
  `3300e6c` pushed to `origin/main`.

## What works (verified 2026-10-24)

- **Solvers** `core/solvers/` (geometry, walls, reachability, routing): **655/655** train+dev on gold inputs
  (`scripts/validate_solvers.py`); rules + rejected variants in [solver-plan.md](../docs/architecture/solver-plan.md).
- **Benchmark pipeline** `agent/benchmark_agent.py` + `agent/run_benchmark.py`: from question text dev **138/138**,
  train **515/517** (2 inherently ambiguous names, Q-006); all 145 test questions answered without errors.
- **Navigation** `core/navigation.py` + `core/basic_parser.py`: warm-up 2120/2130 from text, 100% with gold ids,
  exact `space_path`/`element_path` (`scripts/validate_warmup.py`).
- **Agent tool layer** `agent/tools.py`: `BuildingSession` + Anthropic tool definitions (profile, propose/apply
  changes, `compare_routes`, UI events).
- **Building Guide** `agent/guide.py`: Claude tool-use loop (`GUIDE_MODEL`, cached overview system prompt,
  append-only history); same-turn `apply_change` refused and D-003 grounding check in code
  ([D-010](decisions.md#d-010) proposed). Offline client `agent/offline_llm.py` when no key.
  `tests/test_guide.py`: scripted tricky-user conversation passes offline.
- **Backend** `backend/` (FastAPI): sessions per conversation + building choice, `POST /chat`, `GET /events`,
  OpenAI-compatible streaming `/v1/chat/completions`; runs with `GUIDE_LLM=offline uv run uvicorn backend.app:app`
  ([commands.md](../docs/guides/commands.md#backend-guide-api)).
- **Frontend app** `frontend/app/` (Vite + React + r3f): monochrome point cloud ([D-011](decisions.md#d-011)) with
  emergence + scan, route flow, highlight / closure / lost-access states, floor solo + separation, camera fly-to,
  chat panel; light/dark. Backend serves `GET /sessions/{id}/points` (`core/pointcloud.py`) and enriches route /
  change events. Verified in Chrome with the offline Guide ([commands.md](../docs/guides/commands.md#frontend-app)).
- **Profiles:** `set_profile` presets (wheelchair, pram, trolley, no_lifts, default) + deterministic cue safety net
  in the Guide (`tests/test_profiles.py`); live Sonnet run uses the preset itself.
- **Voice replies:** `Guide.reply(…, channel="voice")` (used by `/v1/chat/completions`): spoken-style system
  message + deterministic `agent/speech.py`; live Sonnet low 7 turns ~3 s/turn, $0.054, clean speech.
  `uv run pytest` **146 passed**.
- **Live Guide** (API key set 2026-10-24): 7-turn tricky-user conversation correct on Opus 5.5 medium (~5.9–7.3 s/turn,
  ~$0.15) and Sonnet 5.5 low (~3.3–3.9 s/turn, ~$0.06), 0 ungrounded replies — table in
  [ai-agents.md](../docs/architecture/ai-agents.md#implementation--agentguidepy-2026-10-24).

- `uv sync` at root; starter oracle on dev **369/369**; `core.building_map` reproduces 120/120 dev warm-up routes < 1 cm.
- `core/question_parser.py`: 655/655 train+dev params match `inputs`; 145/145 test questions parse (`uv run pytest`).
- `agent/parsing.py` modes + `agent/llm_parser.py`: offline tests pass (21 total); live LLM accuracy not yet measured (no API key).
- `benchmark/score.py` parsing behaviour checked ([scoring.md](../docs/challenge/scoring.md#formatting-pitfalls-cost-real-points)).

## Pending decisions (Atahan)

- none (D-006 zero-cost stack accepted 2026-10-24).
- [Q-002](open-questions.md#q-002) times — Atahan will provide.

## ▶ Start here (handoff for the next session, 2026-10-24 ~15:30)

**Git (`dev`, not pushed — ask Atahan before pushing; never commit on `main`):** latest commits
`188abd3` conversation persistence · `dc058f8` Sunday hardening · `46321b5` voice-ready replies · `89070ba` frontend app + point-cloud API + profile
presets · `ed5f6c1` live Guide check · `a4e3efb` Guide loop + backend. All via `/ship` (verifier PASS).

**Deployment work (no longer uncommitted):** the conversation persistence on Supabase (`backend/persistence.py`,
`supabase/`, `tests/test_persistence.py`, …) was committed as `188abd3`. The Vercel deploy config (`vercel.json`,
`StripPrefix` / `CORS_ORIGINS` in `backend/app.py`, `tests/test_deploy.py`, the commands.md deploy section) lands in
the commit after it, and this handoff (Q-014 in `open-questions.md`, the warning in `docs/kit/route-model.md`, this
section and its `log.md` entry) ships together with that deploy commit.

**What works:** benchmark dev 138/138, train 515/517 (2 irreducible Q-006); parser hybrid 31/31 on paraphrases;
Guide live on Opus 5.5 / Sonnet 5.5 (grounding check, confirm-before-apply, profile presets + cue safety net, voice
channel); FastAPI backend (`/chat`, `/events`, `/sessions/{id}/points`, OpenAI-compatible streaming
`/v1/chat/completions` speaking); React app `frontend/app/` (monochrome point cloud, D-011). `uv run pytest` 147
passed (+ Atahan's persistence tests). API spend ≈ $1.4 of $150.

**Running locally (may still be up):** backend `uvicorn backend.app:app --port 8765` (real Claude), Vite on
`:5181` (port 5173 is another local project). Restart commands: [commands.md](../docs/guides/commands.md#frontend-app).

**▶ Do next, in order:**
1. **[Q-014](open-questions.md#q-014) — new Sunday route scoring rule (HIGH).** Send Atahan the 5 organiser
   questions (draft in Q-014), then build the second route model + production-bay / forklift / no-outside rules and
   measure sequence differences on train/dev. Stays in `core/` + `agent/` (not his deploy files).
2. Help finish the deploy if Atahan asks (Vercel: Vite frontend + FastAPI, `/api` rewrite or `VITE_API_BASE`).
3. ElevenLabs Custom LLM wiring once there is a public URL (ask before creating anything in any account).
4. Frontend: phone-layout check, demo GIF (needs the Chrome extension; it was disconnected), bundle split.
5. Open for Atahan: model per channel (Q-012; proposal Opus 5.5 medium for text, Sonnet 5.5 low for voice), team
   name for the test CSV, push `dev`.

**Ways of working:** session protocol in CLAUDE.md; keep `.claude/worklog/PENDING.md` current; commit only via
`/ship`, staging/stamp/commit as separate commands; subagents get disjoint files.

## Next priorities

1. Voice: ElevenLabs Custom LLM on `/v1/chat/completions` (replies are voice-ready) — needs the public deploy
   (Atahan working on it); ask before creating anything in any account. Decide model per channel (Q-012).
2. Frontend polish: phone layout check, closure ripple for edits, narrow doors for the active profile, run against
   the real Guide (key set) and record a demo GIF/video.
3. Deploy: Supabase ✅ (project created, `conversations` table applied, sessions persisted via
   `backend/persistence.py`, live round trip incl. real Claude verified 2026-10-24). Vercel config ✅ (`vercel.json`
   with services `web` + `api`, `/api` rewrite, `excludeFiles`, `maxDuration` 300; `StripPrefix` and `CORS_ORIGINS`
   in `backend/app.py`; `tests/test_deploy.py`; `uv run pytest` 162 passed, 1 skipped). Next: Atahan imports the repo
   into Vercel and sets the env vars (`ANTHROPIC_API_KEY`, `SUPABASE_DB_URL`), then smoke-test; the first-deploy
   UNVERIFIED items are listed in [commands.md](../docs/guides/commands.md#deploy-vercel).
4. Preference extraction, remaining TODO: group composition (P20), profile lifetime/reset scope, persistence,
   soft penalties → [TODO](../docs/product/routing-profiles.md#todo-preference-extraction).
5. Sunday hardening: wording robustness ✅ (hybrid 31/31 on paraphrases), Swiss `straight_line_3d` ✅ (generator
   avoids Swiss; no correction needed); still open: output format once Q-001 is announced, new kinds.

## Blockers

- None hard. Sunday output format unknown ([Q-001](open-questions.md#q-001)) — solvers return structured results + prose.
