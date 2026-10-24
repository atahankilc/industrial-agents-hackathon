---
id: project-state
summary: Current phase, what exists, what works, next priorities, blockers. Read first every session.
updated: 2026-10-24
related: [decisions.md, open-questions.md, log.md, ../docs/architecture/solver-plan.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-24** (Guide session: conversation loop + backend skeleton, offline)

## Phase

**Phase 1 ✅ · Phase 2 ✅ (dev 138/138) · Phase 3 — Agent + interaction ✅ (offline tests + live check on Opus/Sonnet) → Phase 4 UI + voice**

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
  ([commands.md](../docs/guides/commands.md#backend-guide-api)). `uv run pytest` **87 passed**.
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

## ▶ Start here (handoff for the next session, 2026-10-24)

- Guide verified live. **Next:** (1) frontend 2D plan view polling `GET /events` and drawing `space_path` +
  chat box; (2) voice-friendly step text (no bracketed ids, no markdown); (3) model per channel (Q-012, Atahan);
  (4) ElevenLabs Custom LLM wiring — needs a public deploy; ask Atahan before creating anything in any account.
- Test submission: `PARSER_MODE=regex uv run python -m agent.run_benchmark data/test data/test/questions.csv
  agent_output/test_answers.json --csv team_<name>.csv` — team name needed from Atahan before submitting.
- **Ways of working:** keep `.claude/worklog/PENDING.md` current; commit only via `/ship`.

## Next priorities

1. Frontend 2D plan with route overlay + chat on top of `backend/` (`/chat`, `/events`).
2. Voice-friendly replies: step text still contains bracketed ids; replies use markdown bullets/bold.
   Decide model per channel (Q-012).
3. (Atahan) Vercel + Supabase accounts and API key → [stack checklist](../docs/research/stack-options.md#7-day-one-setup-checklist-human-actions--ask-before-creating-anything).
4. Sunday hardening: wording robustness (LLM parser fallback measured with a key), Swiss per-floor frames for
   `straight_line_3d` (UNVERIFIED risk), output format once Q-001 is announced.

## Blockers

- None hard. Sunday output format unknown ([Q-001](open-questions.md#q-001)) — solvers return structured results + prose.
