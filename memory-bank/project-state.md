---
id: project-state
summary: Current phase, what exists, what works, next priorities, blockers. Read first every session.
updated: 2026-10-24
related: [decisions.md, open-questions.md, log.md, ../docs/architecture/solver-plan.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-24** (`origin/dev` merged into `1-agentic-yarag`: Sunday route model, AI layer, plus the branch's place resolution, grounding and voice transcript rewriter)

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

- **Builder Edit mode (branch `2-builder-edit`, in progress):** design
  [builder-edit-mode-design](../docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md) (proposed, approved by
  Utku 2026-10-24), plan [M1](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md). Done: Task 1
  `core/edits.py` — ops add/delete/set space, add/move/set/delete opening, add/move/set/delete asset, replay via
  `apply_steps` (`tests/test_edits.py`). Task 2: `move_vertex` / `set_polygon` keep shared walls (overlapped
  neighbours shrink, refused if one would vanish; doors re-projected; thick Swiss walls handled). Task 3:
  `core/validate.py` — `validate(building, base)`, issues already in the base are warnings
  (`scripts/validate_dataset.py`, `tests/test_validate.py` over all 280 buildings). Next: Task 4 drafts store + API.

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
- **AI layer of the app** (2026-10-24): `POST /chat/stream` live tool steps, route/change cards, follow-up chips,
  voice mode with the orb (browser speech, `frontend/app/src/voice/useVoice.ts`), camera walk mode with turn-by-turn
  legs (`core/directions.py`) and "Where am I?" photo turns (`Guide.reply(photo=…)`, one turn only). Verified
  headless in Chrome (offline Guide, fake camera) and one live Opus photo turn; WebGL orb + voice stage with
  explicit recognition errors. Real-mic recognition and phone camera not yet confirmed (automation can't feed
  Chrome's speech service).
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
- `agent/parsing.py` modes + `agent/llm_parser.py`: offline tests pass; live (2026-10-24, `scripts/eval_llm_parser.py --per-kind 3`, 24 dev
  questions): original text regex/llm/hybrid 24/24 each; `--paraphrase` regex **0/24**, llm 24/24, hybrid 24/24.
  Parser-only cost ≈ $0.42 (cold cache) and ≈ $0.19 (warm) per 24-question run. `.env` now has `ANTHROPIC_API_KEY`.
- **Second stack (v1)** from branch `1-agentic-yarag`, merged beside the canonical one on 2026-10-24 under `_v1`
  names (the backend, UI and `agent.run_benchmark` use the canonical stack above):
  - `core/solvers_v1.py` (`solve(bmap, kind, params)` → dict): every benchmark kind + warm-up kinds; 655/655
    train+dev on gold `inputs` (`uv run pytest tests/test_solvers.py -q -s`).
  - `agent/answer.py` (`benchmark.evaluate --agent agent.answer:answer`): dev **138/138**, train 515/517
    (`tests/test_answer.py`); `agent/run_benchmark_v1.py`: .csv or .json (reply, ids, solver result, `route`
    with per-leg `space_path`/`element_path`) out; produced `submissions/team_jaRAG.csv` (145 rows).
  - `BuildingMap.route()` per-leg paths exact on all 1,338 train+dev warm-up routes (`tests/test_routes.py`);
    warm-up kinds from text 2,120/2,130 (`tests/test_warm_up.py`; 10 misses = duplicate names, [D-012](decisions.md#d-012)).
  - v1 Guide `agent/guide_v1/` (plan: [guide-agent](../docs/superpowers/plans/2026-10-24-guide-agent.md)): 6 tools
    (locate, find_places, place_info, building_fact, route, update_session), candidate fan-out for ambiguous names,
    grounding check with one repair then a code fallback; REPL `uv run --env-file .env python -m agent.guide_v1
    <building_dir> [--show-tools]`. 9 scripted conversations (`tests/guide_conversations/`, `scripts/eval_guide.py`):
    16/16 turns PASS live (single run, ~$0.32).
  - 2026-10-24: `scripts/eval_guide.py` + `tests/test_guide_conversations.py` ported to the canonical Guide
    (`agent/guide.py`; `route_to` checked with `core.navigation.find_route` under the session's state after the
    turn). Conversations updated to its tools (`set_profile`; closures as `propose_change` → "Yes" → `apply_change`).
    First live run 14/18; after the fixes (log 2026-10-24) Opus 5.5 medium **17/18** (89 s, ~$0.22), the one miss
    was the checker's `asked` rule, fixed and re-run 3/3 (~$0.03).
  - Ported into the canonical Guide (2026-10-24): place resolution + described candidates + typo suggestions +
    route fan-out over an ambiguous destination (`agent/places.py`, `BuildingSession.resolve`), and grounding
    (unit-glued numbers, list lengths, clock times, half-up rounding) in `agent/guide.py`; `tests/test_places.py`.
    Not ported: the v1 code fallback reply (main's tools have no uniform `summary`).
  - Voice transcript rewriter ([D-013](decisions.md#d-013)) built 2026-10-24: `agent/rewriter.py` (Haiku 5.5),
    hooked into `Guide.reply(..., channel="voice")`; `tests/test_rewriter.py`.
- `benchmark/score.py` parsing behaviour checked ([scoring.md](../docs/challenge/scoring.md#formatting-pitfalls-cost-real-points)).

## Pending decisions (Atahan)

- none (D-006 zero-cost stack accepted 2026-10-24).
- [Q-002](open-questions.md#q-002) times — Atahan will provide.

## ▶ Start here (handoff for the next session, 2026-10-24 evening)

**Git (`dev`, not pushed — ask Atahan before pushing; never commit on `main`):** latest commits — the Q-014 route
model commit (this session) · `ec1b33e` Vercel deploy config (+ the Q-014 handoff) · `188abd3` conversation
persistence · `dc058f8` Sunday hardening · `46321b5` voice-ready replies. All via `/ship` (verifier PASS).

**Deployment work:** committed (`188abd3` Supabase persistence, `ec1b33e` Vercel config: `vercel.json`,
`StripPrefix` / `CORS_ORIGINS` in `backend/app.py`, `tests/test_deploy.py`, commands.md deploy section). **The app
is deployed** (Atahan, 2026-10-24; public URL not recorded here, no smoke test by Claude yet).

**What works:** benchmark dev 138/138, train 515/517 (2 irreducible Q-006); parser hybrid 31/31 on paraphrases;
Guide live on Opus 5.5 / Sonnet 5.5; FastAPI backend; React app `frontend/app/` (D-011). **New:** second route model
`geodesic` (door-to-door, 0.15 m off walls, height-based stair/lift costs) + route rules (production bays
destination-only, no outside shortcut, forklift preset) — selectable per call, kit model stays default
([route-model.md](../docs/kit/route-model.md#sunday-route-model-and-route-rules-q-014)). Guide routes always obey
the rules. `uv run pytest` 182 passed, 1 skipped (dev); 301 passed, 1 skipped after merging into `1-agentic-yarag`. API spend ≈ $1.4 of $150.

**Running locally (may still be up):** backend `uvicorn backend.app:app --port 8765` (real Claude), Vite on
`:5181` (port 5173 is another local project). Restart commands: [commands.md](../docs/guides/commands.md#frontend-app).

**▶ Do next, in order (Atahan's call 2026-10-24: frontend polish next session; Q-014 and Q-001 parked):**
1. **Frontend polish** (`frontend/app/`): phone-layout check, demo GIF (needs the Chrome extension), bundle split,
   closure ripple for edits, narrow doors for the active profile, draw geodesic in-space polylines
   (`core.geodesic.space_path`) instead of straight door-to-door lines.
2. Parked until Atahan picks them up: [Q-014](open-questions.md#q-014) organiser answers → switch Sunday route
   questions to `model="geodesic", rules=SUNDAY_RULES` (decide `no_outside`: 127 warm-up legs become unroutable
   without outside; start/end convention; aisle/walkway/bay markers; errand on geodesic if the rule covers it);
   Sunday output format ([Q-001](open-questions.md#q-001)) incl. the "no route under these rules" wording.
3. Small gaps: `numpy` used by `core/geodesic.py` but not declared in `pyproject.toml` (transitive via shapely;
   Atahan's file); `BuildingSession.route_model` is not saved by `backend/persistence.py` (irrelevant while the app
   stays on the kit model); live smoke test of the deployed app (needs the URL).
4. ElevenLabs Custom LLM on the deployed `/v1/chat/completions` — ask before creating anything in any account.
5. Open for Atahan: model per channel (Q-012), team name for the test CSV, push `dev`.

**Ways of working:** session protocol in CLAUDE.md; keep `.claude/worklog/PENDING.md` current; commit only via
`/ship`, staging/stamp/commit as separate commands; subagents get disjoint files.

## Next priorities

1. Frontend polish (next session): phone layout check, closure ripple for edits, narrow doors for the active profile, run against
   the real Guide (key set) and record a demo GIF/video.
2. Voice: ElevenLabs Custom LLM on the deployed `/v1/chat/completions` (replies are voice-ready); ask before
   creating anything in any account. Decide model per channel (Q-012).
3. Deploy ✅ (deployed by Atahan 2026-10-24): Supabase ✅ (project created, `conversations` table applied, sessions persisted via
   `backend/persistence.py`, live round trip incl. real Claude verified 2026-10-24). Vercel config ✅ (`vercel.json`
   with services `web` + `api`, `/api` rewrite, `excludeFiles`, `maxDuration` 300; `StripPrefix` and `CORS_ORIGINS`
   in `backend/app.py`; `tests/test_deploy.py`). Remaining: smoke-test the live URL; the first-deploy UNVERIFIED
   items are listed in [commands.md](../docs/guides/commands.md#deploy-vercel).
4. Preference extraction, remaining TODO: group composition (P20), profile lifetime/reset scope, persistence,
   soft penalties → [TODO](../docs/product/routing-profiles.md#todo-preference-extraction).
5. Sunday hardening: wording robustness ✅ (hybrid 31/31 on paraphrases), Swiss `straight_line_3d` ✅ (generator
   avoids Swiss; no correction needed); still open: output format once Q-001 is announced, new kinds.

## Blockers

- None hard. Sunday output format unknown ([Q-001](open-questions.md#q-001)) — solvers return structured results + prose.
