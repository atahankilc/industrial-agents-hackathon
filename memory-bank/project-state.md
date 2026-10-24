---
id: project-state
summary: Current phase, what exists, what works, next priorities, blockers. Read first every session.
updated: 2026-10-24
related: [decisions.md, open-questions.md, log.md, ../docs/architecture/solver-plan.md]
---

# Project state

[Memory bank](README.md) · Last updated: **2026-10-24** (zero-cost stack session, after first commit `3300e6c`)

## Phase

**Phase 0 — Foundation ✅ · Phase 1 — Deterministic core + solvers ✅ · Phase 2 — Benchmark runner ✅ → next:
Phase 3 — Agent + interaction and Phase 4 — App/UI + voice (see [Next priorities](#next-priorities) 3–4)**

Planned phases (proposal, see [overview.md](../docs/architecture/overview.md)):

| Phase | Goal | Done when |
|---|---|---|
| 0 Foundation | docs, memory bank, CLAUDE.md | ✅ 2026-10-24 |
| 1 Core + solvers | per-kind solvers verified on train+dev `inputs` | ✅ 2026-10-24, all rows VERIFIED in [solver-plan](../docs/architecture/solver-plan.md) |
| 2 Benchmark runner | question text → solver → `Answer:` reply; dev score via `benchmark.evaluate`; test CSV | ✅ 2026-10-24: dev 138/138; test CSV at `submissions/team_jaRAG.csv` (team name jaRAG) |
| 3 Agent + interaction | conversational agent with clarifications, directions, closures, edits | scripted tricky-user conversation works |
| 4 App/UI + voice | 2D view with route, then stacked floors; voice | demoable |
| 5 Build + extend | plan → building (L4), one add-in (L5) | demoable |
| 6 Submission | `BENCHMARK.md`, Sunday run, video, tech explanation | submitted before code freeze |

## What exists

- Repo root is the build root ([D-004](decisions.md#d-004)): `core/` (building_map from the kit + question_parser),
  `benchmark/` (official scorer), `data/` (committed, [D-005](decisions.md#d-005)), `tests/`, `pyproject.toml` (uv,
  pytest dev dep). Kit remainder in `archive/initial-repo/`.
- Phase 3 in progress ([plan](../docs/superpowers/plans/2026-10-24-guide-agent.md)): `agent/guide/resolve.py` —
  resolve_places / resolve_elements / nearest_names / describe / fan_out; 11 tests in `tests/test_guide_resolve.py`;
  full suite 47 passed.
- `agent/guide/tools.py` — Session, TOOLS, run_tool; locate / find_places / place_info / building_fact (strict
  schemas); 12 tests in `tests/test_guide_tools.py`; full suite 56 passed.
- `route` + `update_session` tools in `agent/guide/tools.py` (session position / step-free / closures feed routes; closures fan out as slots and never leak into `bmap.closed`); 13 tests in `tests/test_guide_route.py`; full suite 69 passed.
- `agent/guide/grounding.py` — grounded_tokens / ungrounded / fallback_text (numbers in replies must come from tool results); 14 tests in `tests/test_guide_grounding.py`; full suite 83 passed.
- `agent/guide/prompt.py` + `guide.py` + `__main__.py` — Guide loop (`Guide.turn` → `TurnResult`, one grounding repair then code fallback, API errors roll the turn back) and REPL `uv run --env-file .env python -m agent.guide <building_dir> [--show-tools]`; 15 tests in `tests/test_guide_loop.py` (+1 in `tests/test_guide_route.py`: `[]` for via/close/reopen means none); full suite 100 passed.
- Guide v1 done (Phase 3, Task 6): 8 scripted conversations in `tests/guide_conversations/*.json` + `scripts/eval_guide.py` (`check_turn` recomputes `route_to` with `core.solvers.route` from the session state); 7 offline tests in `tests/test_guide_conversations.py`; full suite 107 passed. Live run (campus + factory dev): 12/15 turns first, after 3 prompt rules (re-call the tool after a clarifying answer, call `route` afresh each time, no closing offers) 15/15 PASS (single run, so not a stability measure), ~$0.27 per full run.
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

- `uv sync` at root; starter oracle on dev **369/369**; `core.building_map` reproduces 120/120 dev warm-up routes < 1 cm.
- `core/question_parser.py`: 655/655 train+dev params match `inputs`; 145/145 test questions parse (`uv run pytest`).
- `agent/parsing.py` modes + `agent/llm_parser.py`: offline tests pass; live (2026-10-24, `scripts/eval_llm_parser.py --per-kind 3`, 24 dev
  questions): original text regex/llm/hybrid 24/24 each; `--paraphrase` regex **0/24**, llm 24/24, hybrid 24/24.
  Parser-only cost ≈ $0.42 (cold cache) and ≈ $0.19 (warm) per 24-question run. `.env` now has `ANTHROPIC_API_KEY`.
- `core/solvers.py`: every benchmark kind; 655/655 train+dev on gold `inputs`; via text → parser → solver
  648/648 plus 7 ambiguous texts the test skips (`uv run pytest tests/test_solvers.py -q -s`); 145/145 test questions parse and solve without error.
- `agent/answer.py` (`answer(building_dir, text)` for `benchmark.evaluate --agent agent.answer:answer`): parser →
  solver → deterministic `Answer:` line. Official scorer: dev **138/138**, train 515/517, train+dev 653/655
  (`uv run pytest tests/test_answer.py -q -s`); the 2 misses are ambiguous duplicate names (H02, H04 of
  osm-way37850565) whose text cannot identify the room. Test: 145/145 replies, none fail.
- `run_benchmark <building_dir> <questions> <answers>` (`agent/run_benchmark.py`, `[project.scripts]`): .jsonl/.json/.csv
  in; .csv (submission) or .json (reply + ids + solver result) out. Test CSV = 145 rows, same ids as
  `submission_template.csv`, replies identical to `benchmark.evaluate --submission-csv` (`tests/test_run_benchmark.py`).
- Route paths: `BuildingMap.route()` gives per-leg `space_path` + `element_path` in the warm-up answer format,
  exact on all 1,338 train+dev warm-up route/step-free/closure/tour questions (`tests/test_routes.py`); errand
  returns its 2 legs; `run_benchmark` .json has `route` (20 test errands). Sunday format assumed = warm-up (Q-001).
- Warm-up kinds (locate, count, route, route_step_free, route_with_closure, tour): parser templates + solvers +
  replies; from text 2,120/2,130 train+dev (`tests/test_warm_up.py`; 10 misses = duplicate room names); LLM
  parser knows them (offline fake-client test; live 12/12 reworded).
- Guide REPL live (2026-10-24, campus dev-001): "Where is the 3D printer?" → both rooms from `locate`; "how do I get there from the main lobby?" → `update_session` + `route` ambiguous → asks which room; ≈ $0.03 for the 2 turns.
- `benchmark/score.py` parsing behaviour checked ([scoring.md](../docs/challenge/scoring.md#formatting-pitfalls-cost-real-points)).

## Pending decisions (Atahan)

- none (D-006 zero-cost stack accepted 2026-10-24).
- [Q-002](open-questions.md#q-002) times — Atahan will provide.

## ▶ Start here (handoff for the next session, 2026-10-24)

- **Focus now: implementing the app.** Atahan handles the cloud accounts (Vercel, Supabase) later — don't block on it.
- **Benchmark pipeline is done:** solvers, formatter, `answer()`, `run_benchmark`, [BENCHMARK.md](../BENCHMARK.md),
  test CSV in `submissions/`. Next: structured route output for Sunday ([Q-001](open-questions.md#q-001)), then the app.
- **Ways of working:** keep `.claude/worklog/PENDING.md` current; commit only via `/ship`
  ([dev-workflow.md](../docs/guides/dev-workflow.md)). Parallel subagents are welcome (Atahan: quota is fine).
- `.env` has `ANTHROPIC_API_KEY` (Utku's machine); no ElevenLabs key yet.

## Next priorities

1. (Later, Atahan) Accounts per the zero-cost [stack checklist](../docs/research/stack-options.md#7-day-one-setup-checklist-human-actions--ask-before-creating-anything):
   Atahan signs up for Vercel + Supabase (free) and puts keys in `.env`; Claude then configures Vercel (frontend +
   FastAPI as Services) and the Supabase schema. First commit is pushed (`3300e6c`).
2. Benchmark: done — `run_benchmark` ([BENCHMARK.md](../BENCHMARK.md)), `submissions/team_jaRAG.csv` (145/145
   answered). Route paths are in the .json output in the warm-up format; adjust once organisers answer [Q-001](open-questions.md#q-001) (message drafted there).
   Solvers are done; [Q-004](open-questions.md#q-004)/[Q-005](open-questions.md#q-005) stay open (rules match, few labels).
3. In parallel: FastAPI skeleton + frontend skeleton (2D plan + route) deployed; Supabase schema.
4. Routing profiles ([routing-profiles.md](../docs/product/routing-profiles.md)) + Guide agent + voice.

## Blockers

- None hard. Sunday output format unknown ([Q-001](open-questions.md#q-001)) — solvers return structured results + prose.
