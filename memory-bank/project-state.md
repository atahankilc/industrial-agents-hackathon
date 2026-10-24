---
id: project-state
summary: Current phase, what exists, what works, next priorities, blockers. Read first every session.
updated: 2026-10-24
related: [decisions.md, open-questions.md, log.md, ../docs/architecture/solver-plan.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-24** (foundation session)

## Phase

**Phase 0 — Foundation ✅ → Phase 1 — Deterministic core + solvers (next)**

Planned phases (proposal, see [overview.md](../docs/architecture/overview.md)):

| Phase | Goal | Done when |
|---|---|---|
| 0 Foundation | docs, memory bank, CLAUDE.md | ✅ 2026-10-24 |
| 1 Core + solvers | per-kind solvers verified on train+dev `inputs` | every row in [solver-plan](../docs/architecture/solver-plan.md) is VERIFIED |
| 2 Benchmark runner | question text → solver → `Answer:` reply; dev score via `benchmark.evaluate`; test CSV | dev ≥ target score; `team_<name>.csv` written |
| 3 Agent + interaction | conversational agent with clarifications, directions, closures, edits | scripted tricky-user conversation works |
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
- Git: `main`; `origin` = https://github.com/atahankilc/industrial-agents-hackathon.git (public), no commits
  yet — first commit in progress.

## What works (verified 2026-10-24)

- `uv sync` at root; starter oracle on dev **369/369**; `core.building_map` reproduces 120/120 dev warm-up routes < 1 cm.
- `core/question_parser.py`: 655/655 train+dev params match `inputs`; 145/145 test questions parse (`uv run pytest`).
- `agent/parsing.py` modes + `agent/llm_parser.py`: offline tests pass (21 total); live LLM accuracy not yet measured (no API key).
- `benchmark/score.py` parsing behaviour checked ([scoring.md](../docs/challenge/scoring.md#formatting-pitfalls-cost-real-points)).

## Pending decisions (Atahan)

- [D-006](decisions.md#d-006) cloud stack.
- [Q-002](open-questions.md#q-002) times — Atahan will provide.

## Next priorities

1. First commit + push via `/ship` (in progress); then Supabase/Railway/Vercel/ElevenLabs setup per the
   [stack checklist](../docs/research/stack-options.md#7-day-one-setup-checklist-human-actions--ask-before-creating-anything).
2. Solvers in test-share order (floor_area_total → shared_walls_count → largest_room → errand →
   wide_delivery_count → straight_line_3d → room_stacked → what_if_door), verified on train+dev → resolves
   [Q-003](open-questions.md#q-003)–[Q-005](open-questions.md#q-005). Then formatter + `answer()` + test CSV + `run_benchmark`.
3. In parallel: FastAPI skeleton + frontend skeleton (2D plan + route) deployed; Supabase schema.
4. Routing profiles ([routing-profiles.md](../docs/product/routing-profiles.md)) + Guide agent + voice.

## Blockers

- None hard. Sunday output format unknown ([Q-001](open-questions.md#q-001)) — solvers return structured results + prose.
