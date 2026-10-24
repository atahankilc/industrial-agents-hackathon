---
id: log
summary: Append-only session log, newest first. One entry per session/work chunk.
related: [project-state.md, decisions.md, open-questions.md]
---

# Log

[Memory bank](README.md)

Template: `## YYYY-MM-DD HH:MM — title` then *Did / Learned / Changed docs / Opened-closed Q / Next*.

## 2026-10-24 — Vercel deploy config

- **Did:** `vercel.json` (services `web` = Vite `frontend/app/` and `api` = FastAPI `backend.app:app`, `/api/(.*)`
  rewrite, `excludeFiles`, `maxDuration` 300); `StripPrefix` ASGI middleware and `CORS_ORIGINS` in `backend/app.py`;
  `tests/test_deploy.py`; deploy section in [commands.md](../docs/guides/commands.md#deploy-vercel).
- **Learned:** the Vercel rewrite keeps the `/api` prefix, so the backend strips it; the backend reads only
  `building.json` + `manifest.csv` from `data/` (bundle about 49 MB of code+data).
- **Changed docs:** [commands.md](../docs/guides/commands.md#deploy-vercel), [project-state.md](project-state.md#next-priorities).
- **Next:** Atahan imports the repo into Vercel and sets the env vars; pushing `dev` needs Atahan's OK.

## 2026-10-24 — Q-014: second route model (geodesic) + route rules

- **Did:** `core/geodesic.py` (in-space door-to-door distance, polygon shrunk 0.15 m, visibility graph; subagent),
  `core/route_models.py` (`kit` | `geodesic` per call, height-based stair/lift costs, `RouteRules`: production bays
  destination-only, no outside shortcut, forklift; `sequence_length` = organiser-style re-measure), wired into
  `core/navigation.py`, `core/basic_parser.run_parsed` and `agent/tools.py` (rules always on, `forklift` preset,
  `route_model` attribute). `scripts/compare_route_models.py`; tests `tests/test_geodesic.py`,
  `tests/test_route_models.py`. Gave Atahan the 5 organiser questions as a Discord message.
- **Learned:** on 1,457 warm-up legs the models pick different sequences in 115 (7.9 %); kit answers would score
  0.930 mean (0.984 with the rules), worst legs = kit lift vs new-rule stairs (score 0.36). 202 kit legs pass
  `outside`; 127 have no route without it (Swiss stair blocks) — the outside question decides a lot. No warm-up
  route crosses a production bay. Kit default unchanged: warm-up 2120/2130, solvers 655/655.
- **Changed docs:** route-model.md (new section), solver-plan.md (Sunday routes), routing-profiles.md (forklift
  preset), Q-014 progress, project-state.
- **Next:** organiser answers → switch Sunday route questions to geodesic + rules.

## 2026-10-24 — Organiser route-scoring rules (Discord) → Q-014; session handoff

- **Did:** Analysed the organisers' Discord note on how route answers are scored and compared it with our model
  and the data → [Q-014](open-questions.md#q-014) (door-to-door geodesic distance, height-based stair/lift costs,
  production bays destination-only, forklift ≥ 3 m, likely no `outside` shortcut, score = best ÷ ours). Warning added
  to [route-model.md](../docs/kit/route-model.md). Wrote the handoff in
  [project-state.md](project-state.md#-start-here-handoff-for-the-next-session-2026-10-24-evening).
- **Learned:** under the new costs the stairs-vs-lift choice can flip; any route through a production bay would
  score 0; whether `errand` distances change too is the key question for the organisers.
- **Next:** Q-014 implementation (see project-state).

## 2026-10-24 — Conversation persistence on Supabase

- **Did:** `backend/persistence.py`: conversation ⇄ JSON (profile, applied changes replayed from the base building,
  pending, events, Guide history + system blocks), Memory and Postgres backends with optimistic `version` saves.
  `SessionStore` uses it when `SUPABASE_DB_URL` is set; `/chat` and switch-building save, conflict → 409. Migration
  `supabase/migrations/20261024120000_conversations.sql` applied (RLS on, no policies). `tests/test_persistence.py`.
- **Learned:** the Supabase direct host is IPv6-only (doesn't resolve on our network; Vercel is IPv4) → use the
  Transaction pooler (6543, no prepared statements). Restored history is accepted by the real API (Sonnet, two
  stores, wheelchair profile honoured on the second; cache reads hit). Anon key on `/rest/v1/conversations` → 0 rows.
- **Changed docs:** [commands.md](../docs/guides/commands.md#conversation-persistence-supabase-postgres), `.env.example`.
- **Next:** Vercel config ([project-state.md](project-state.md#next-priorities)).

## 2026-10-24 — Sunday hardening: paraphrases, Swiss frames, end-to-end checks

- **Did:** Live paraphrase eval of the parser (31 dev questions, all kinds): regex 0/31, llm 31/31, hybrid 31/31.
  Checked the Swiss `straight_line_3d` risk: every train/dev/test question of that kind is procedural/OSM; 84 of 108
  multi-floor Swiss buildings have every floor's space-bbox centre within 2 m of the origin on each axis (82 with a
  Euclidean 2 m radius) → `room_facts` no longer reports above/below on Swiss buildings. Full train run 515/517 (unchanged, the 2 known Q-006 cases). Real-Claude conversation through
  the app proxy (`/api/chat`): preset, route with 15 vertices, closure → change event with 4 lift-shaft spaces,
  re-route via Lift 2; all grounded. Browser re-check not possible (Chrome extension disconnected).
- **Budget:** parser eval ≈ $0.59 + paraphrasing + 3 app turns on Opus ≈ $0.8 → ≈ $1.4 total.
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Voice-ready replies

- **Did:** `agent/speech.py` (`speakable`: markdown, list markers, ids, symbols → plain sentences, units spelled
  out, never adds numbers); `Guide.reply(channel="voice")` with `VOICE_STYLE` as a mid-conversation system message
  (models that support it) or a user-turn note; `/v1/chat/completions` speaks; `live_guide.py --channel voice`;
  prompt: don't offer to show the map. Doc nits from the last review fixed.
- **Learned:** Sonnet 5.5 low in voice mode answers in ~3 s with natural spoken steps; only nit was offering to
  "put it on the map" (fixed in the prompt).
- **Budget:** +$0.054 → ≈ $0.63 total.
- **Next:** Sunday hardening (parser paraphrases, Swiss `straight_line_3d`, full train run).

## 2026-10-24 — Frontend app (monochrome point cloud) + point-cloud API + profile presets

- **Did:** Reviewed the teammate's gap check (routing-profiles TODO, personas P19–P26): accurate; fixed P21's Q-004
  link. Built `frontend/app/` (Vite/React/r3f): monochrome cloud with emergence + scan plane, route comets,
  highlight/closure/lost-access per-space states, floor solo + separation, camera rig, chat panel, light/dark.
  Subagents: `core/pointcloud.py` + `GET /sessions/{id}/points` + enriched route/change events; `set_profile`
  presets + cue safety net. Route events now carry `element_path`, `length_m`, `profile`.
- **Learned:** the route only reads well when off-route rooms step back; overlapping event polls replayed events
  (now chained); port 5173 is taken by another local project (we use 5181).
- **Decisions:** D-011 accepted (monochrome, Atahan).
- **Budget:** +$0.058 (one live Sonnet regression run) → ≈ $0.58 total.
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Preference-extraction gap check + new personas

- **Did:** Compared the profile plan in routing-profiles.md with `agent/tools.py`; wrote the gap list as a TODO.
  Added personas P19–P26.
- **Learned:** `RoutingProfile` has only `step_free`, `min_door_width_m`, `avoid_lifts`; it is session-only; it
  depends on the model calling `set_profile` (no presets, no safety net).
- **Changed docs:** [routing-profiles.md](../docs/product/routing-profiles.md#todo-preference-extraction),
  [personas.md](../docs/product/personas.md#added-personas-2026-10-24), project-state priority 4.
- **Next:** [project-state.md](project-state.md#next-priorities).


## 2026-10-24 — Live Guide check (API key set)

- **Did:** `scripts/live_guide.py` (7-turn tricky user against the real API: tools, replies, ungrounded, cache,
  seconds, $). Runs: Opus 5.5 medium ×2, Opus 5.5 low, Sonnet 5.5 low ×2. Fixed what the runs exposed:
  `compare_routes` capped lost rooms at 15 → `lost_access_by_floor` with counts, uncapped; `propose_change` now
  includes the impact (Sonnet had called `compare_routes` in parallel with a guessed id); id errors list valid
  ids; two prompt sentences (no unsupported general claims; change ids only from tool results).
- **Learned:** all models handled the conversation correctly with 0 ungrounded replies and working caching;
  Sonnet 5.5 low is ~1.5–2.2× faster (3.3–3.9 vs 5.9–7.3 s/turn) and ~2.5× cheaper than Opus 5.5 medium;
  Opus low gave no clear speed gain (6.8 s/turn, one pre-fix run; not directly comparable). The first Opus medium
  run had one failed `find_route` (invalid via id `proc-campus-train-000-V04`, "No place matches") that the
  model recovered from.
  Replies use markdown (bad for TTS).
- **Budget:** ≈ $0.52 API spent (5 live runs: 0.157 + 0.055 + 0.118 + 0.061 + 0.129).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Building Guide loop + backend skeleton (offline)

- **Did:** `agent/guide.py` (manual Claude tool-use loop over `agent/tools.py`, cached overview, model via
  `GUIDE_MODEL`), `agent/offline_llm.py` (rule-based client when no key), `compare_routes` tool (pending or applied
  change: lost access, longer routes, `extra_m`), `tests/test_guide.py` (scripted tricky user). A subagent built
  `backend/` (FastAPI: sessions, `/chat`, `/events`, OpenAI-compatible SSE `/v1/chat/completions`) +
  `tests/test_backend.py`; fixed after its review: predictions no longer touch `session.events` (a poll could see
  phantom routes), `llm_mode()` shared with `/health`. Fixed the `run_benchmark` usage in the
  `agent/benchmark_agent.py` docstring.
- **Learned:** with a step-free profile Main lobby → Meeting room 3.07 (train campus 000) is 124.24 m via Lift 1,
  132.2 m via Lift 2 after closing Lift 1; closing both lifts cuts every upper-floor room for a wheelchair user.
  Grounding by rounding is strict enough to catch invented numbers but accepts "about 124 m".
- **Decisions:** D-010 proposed (guardrails in code).
- **Budget:** $0 API (no key yet; all tests offline).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Deterministic core: all solvers verified, benchmark runner, navigation, agent tools

- **Did:** Scaffolding (`core/solvers` registry + `SolverResult`, `core/formatter.py`, `scripts/validate_solvers.py`),
  then 5 parallel subagents: geometry (4 kinds), shared walls, reachability, routing (errand, what_if_door),
  warm-up navigation + parser. I wrote the pipeline (`agent/benchmark_agent.py`, `agent/run_benchmark.py`,
  `BENCHMARK.md`) and the Guide tool layer (`agent/tools.py`).
- **Learned:** "room" differs per kind (walls: not corridor/stair/lift/outdoor, halls count; counts: `type ==
  room` = manifest `rooms`); every opening kind is width-checked; errand via is on any floor with stairs;
  what-if uses full graph + `type == room`; formatter labels spaces `<ref> (<name>)` (repeated OSM names);
  Dijkstra tie-breaking matches gold only while `BuildingMap.graph()` order is unchanged.
- **Scores:** solvers 655/655; text pipeline dev 138/138, train 515/517; warm-up 2120/2130.
- **Questions:** Q-003, Q-004 resolved; Q-005, Q-006 progressed. Spend: $0 API.
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Zero-cost cloud stack

- **Did:** Re-checked free tiers (Vercel Python runtime, Supabase, Render, Modal, HF Spaces, Koyeb); wrote
  [stack-options.md §9](../docs/research/stack-options.md#9-zero-cost-variant-added-2026-10-24); rewrote the setup
  checklist; `.env.example` now lists `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `PARSER_MODE`.
- **Learned:** HF Docker Spaces now need a paid plan; Koyeb needs a card; Vercel runs FastAPI natively (500 MB bundle,
  streaming, no WebSockets) → frontend + backend in one free project.
- **Decisions:** D-006 accepted (zero-cost revision); Q-007 resolved.
- **Next:** Atahan signs up for Vercel + Supabase; Claude configures; solvers in parallel.

## 2026-10-24 — Licensing, configurable parsing, point-cloud prototype

- **Did:** Checked licences: data CC BY 4.0 / ODbL / CC0 (redistributable with attribution; ODbL share-alike);
  upstream kit repo has no licence → kit code flagged (Q-013). Added `LICENSE` (MIT; Atahan confirmed MIT), `NOTICE.md`,
  `data/README.md`. Added parser modes (`agent/parsing.py`) + LLM parser (`agent/llm_parser.py`) + offline tests
  + live eval script. Point-cloud 3D prototype (three.js) built and verified in Chrome by a background agent;
  viewer shows building attribution (ODbL credit for OSM).
- **Learned:** Opus 5.5 rejects forced `tool_choice` → structured outputs (`output_config.format`) for extraction.
- **Decisions:** D-007 accepted (configurable, hybrid default); D-009 accepted (MIT, Atahan confirmed).

## 2026-10-24 — Verified-commit workflow (.claude/)

- **Did:** Added `commit-verifier` + `commit-fixer` agents, `/ship` skill, worklog template/history, commit-gate
  hook + stamp script, `.claude/settings.json`; documented in [dev-workflow.md](../docs/guides/dev-workflow.md).
- **Learned:** the hook went live immediately and blocked a test command containing a `git commit --amend` string —
  test hook inputs via a script file, not inline.
- **Decisions:** D-008 accepted.
- **Next:** first commit via `/ship` once the GitHub repo question is answered.

## 2026-10-24 — Restructure, setup, research (4 parallel agents)

- **Did:** `uv sync` + oracle on dev (369/369). Moved data + scorer to root, copied `building_map.py` to `core/`,
  archived the kit, root `pyproject.toml`. Research agents wrote ElevenLabs, cloud-stack, question-parsing docs and
  personas + routing profiles; I wrote [overview.md](../docs/architecture/overview.md) and
  [ai-agents.md](../docs/architecture/ai-agents.md) (renamed from agents.md: macOS case-insensitivity made it match
  `AGENTS.md`).
- **Learned:** one template per benchmark kind → regex parser 100%; Lovable can't sync a monorepo subfolder;
  ElevenLabs Custom LLM lets one Claude brain serve voice + text; only 30/23,748 openings have steps (all
  entrances) — lifts and door widths are the real accessibility constraints; 77 multi-floor buildings have no lift.
- **Decisions:** D-004, D-005 accepted (Atahan); D-006, D-007 proposed.
- **Budget:** $150 Claude credits announced (Q-012). Spend so far: $0 API (all deterministic).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Foundation: docs + memory bank

- **Did:** Read the PDF brief, kit README, ATTRIBUTION, starter agent and benchmark code; scanned all 280
  buildings and all question files for schemas and counts. Created `CLAUDE.md`, `docs/` (challenge, kit,
  architecture, guides) and `memory-bank/`.
- **Learned:**
  - Test set = 145 questions in 8 kinds; floor_area_total + shared_walls_count = 41%.
  - Route model fully specified and implemented in `starter_agent/building_map.py`.
  - Scorer: units like `m2` are safe; room refs / extra numbers on a number answer line are fatal.
  - PDF and README disagree on Sunday output format (Q-001).
  - System `python3` is 3.9; the kit needs ≥3.12 → use `uv`.
- **Decisions:** D-001 accepted; D-002, D-003 proposed.
- **Questions opened:** Q-001 … Q-012.
- **Next:** see [project-state.md](project-state.md#next-priorities).
