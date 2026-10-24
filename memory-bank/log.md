---
id: log
summary: Append-only session log, newest first. One entry per session/work chunk.
related: [project-state.md, decisions.md, open-questions.md]
---

# Log

[Memory bank](README.md)

Template: `## YYYY-MM-DD HH:MM — title` then *Did / Learned / Changed docs / Opened-closed Q / Next*.

## 2026-10-24 19:47 — Builder Edit mode M1 Task 4: drafts store + API

- **Did:** `backend/drafts.py` — drafts as base + steps persisted in `data/user/.drafts/<id>.json`, saved buildings in
  `data/user/<slug>/` registered as `user/<slug>`; `/drafts` endpoints in `backend/app.py`; endpoints table in
  [commands.md](../docs/guides/commands.md#backend-guide-api). `.gitignore`: `data/user/`, `.superpowers/`.
  `uv run pytest` 670 passed, 1 skipped.
- **Next:** Task 5 — frontend View/Edit switch, plan view, 3D inset.

## 2026-10-24 19:40 — Builder Edit mode M1 Tasks 2–3: wall moves, validator

- **Did:** `core/edits.py` gained `move_vertex` (moves a corner in every room that has it) and `set_polygon`; both
  shrink overlapped neighbours (`difference`), refuse when a neighbour would vanish, and put doors that were on a wall
  back on it. Opening snapping now buffers by wall thickness (gap ≤ 2.5 m). `core/validate.py` + calibration script.
  `uv run pytest` 658 passed, 1 skipped (280-building validator parametrisation included).
- **Learned:** with thickness-aware snapping, off-wall doors in the dataset drop to osm 61 / swiss 46 / resplan 1;
  overlaps osm 281 / resplan 13 / swiss 38 pairs → validator compares against the base building.
- **Next:** Task 4 — drafts store (`data/user/`) + `/drafts` API.

## 2026-10-24 19:40 — Builder Edit mode: design, M1 plan, core edit ops (branch `2-builder-edit`)

- **Did:** brainstormed Level 4 with Utku → three Builder projects in order: Edit mode, build from scratch
  (PDF/image/conversation), scan ingest. Design of Edit mode
  ([spec](../docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md), status proposed, approved by Utku) and
  milestone-1 plan ([plan](../docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md), 7 tasks). Work happens on
  branch `2-builder-edit` in the worktree `.claude/worktrees/2-builder-edit`. Task 1 done: `core/edits.py`
  (11 JSON ops, deterministic ids, opening snapping, `apply_steps` replay), `tests/test_edits.py` 16 passed;
  full suite 320 passed, 1 skipped.
- **Learned:** Blueprint-Bench 2 (Andon Labs): models get room counts right but mostly miss which rooms connect →
  validator-first Builder. Dataset scan: all 280 buildings have an entrance and every space is reachable; OSM /
  Swiss / ResPlan have pre-existing overlaps and doors off the shared wall, Swiss walls up to ~2 m thick → the
  validator must separate pre-existing from newly introduced issues, and snapping must tolerate thick walls.
- **Next:** M1 Task 2 (`move_vertex`, `set_polygon` with neighbour fitting).

## 2026-10-24 — Guide eval ported to the canonical Guide

- **Did:** `scripts/eval_guide.py` and `tests/test_guide_conversations.py` now test `agent/guide.py` (they tested
  `agent/guide_v1` before, so the 16/16 below was v1's score). Same expect keys; `route_to` compares the turn's last
  reachable `find_route` with a fresh `core.navigation.find_route` under the session's profile, applied changes and
  route rules after the turn. Per-turn seconds + cost, `--model` / `--effort`. `lift_closure.json` gained two
  "Yes, go ahead." turns (propose → confirm → apply), `update_session` → `set_profile`/`propose_change`.
- **First live run (Opus 5.5 medium):** 14/18 PASS, 95 s, ~$0.24. Failures: `lift_closure` t6 repeated the earlier
  route without calling `find_route` (reply correct); `printers_two_rooms` t1 ended with an offer question; t2 routed
  to the nearer printer instead of asking (against the prompt and D-012), so t3 had no route.
- **Fixes:** `route_to` falls back to the conversation's last route (still checked against the current state, so a
  stale route fails); `asked` = a question anywhere in the reply; Guide prompt: ask which room when items of the
  kind sit in several rooms, even if one is nearer, and no closing offers; `lift_closure` user now uses a wheelchair
  (step-free route goes via Lift 1 at 101.64 m, via Lift 2 at 109.63 m once Lift 1 is closed — the scenario now
  tests something).
- **Second live run:** 17/18, 89 s, ~$0.22; the miss asked mid-reply (checker bug, fixed); `printers_two_rooms`
  re-run 3/3, ~$0.03.
- **Learned:** Level 3 "several buildings" is unsupported in data and code → [Q-016](open-questions.md#q-016).
- **Next:** LLM judge + simulated tricky user on top of this suite; Q-016.

## 2026-10-24 — Merge `origin/dev` into `1-agentic-yarag` (Utku's session)

- **Did:** merged dev's 3 commits (Sunday geodesic route model + route rules, handoff, AI layer: live steps, cards,
  voice orb, camera photo turns). Code conflicts: `Guide.__init__` keeps the rewriter and `on_step`; `agent/tools.py`
  imports both `places` and `route_models`, `tool_tour` resolves stops and passes `model`/`rules`. Not flagged by
  git: `destination_options` (route fan-out) now also passes `model`/`rules`, so option lengths obey the route
  rules. `Guide.reply` auto-merged in the right order (rewrite → note → voice style → photo).
- **Docs:** solver-plan keeps both the warm-up-kinds and the Sunday-routes sections; Q-014 takes dev's progress
  (it implemented the branch's open details) plus a Q-015 link.
- **Checks:** `uv run pytest -q` 301 passed, 1 skipped; live `scripts/live_guide.py` (Sonnet 5.5 low) 7 turns, all
  end_turn, 0 ungrounded, $0.057.

## 2026-10-24 — Voice transcript rewriter (D-013) (Utku's session)

- **Did:** `agent/rewriter.py`: `TranscriptRewriter` (claude-haiku-5-5, effort low, JSON schema, building vocabulary
  cached); `Guide.reply(..., channel="voice")` sends rewritten + "[speech transcript as heard: …]", both grounded,
  `GuideTurn.rewritten`. Only with the real API client; `GUIDE_REWRITER=off`. `tests/test_rewriter.py` (7).
- **Learned:** live, Haiku normalises "lab two seventeen" → "Lab 2.17", "office zero oh two" → "Office 0.02", "defib"
  → "defibrillator", keeps "the kitchen"; ~1–2 s, < $0.001 per call. A prompt example "the second floor → Floor 2"
  made it interpret ordinals (US vs UK floors), so ordinal floor words are now kept as said. End to end (Sonnet low
  Guide): voice turn 4.7 s, one `find_route`, 0 ungrounded.
- **Remote:** `origin/dev` has 3 commits ahead of main (Sunday geodesic route model + rules, live Guide steps,
  camera photo turns, browser voice orb) touching `agent/guide.py` / `agent/tools.py`; not merged here yet.

## 2026-10-24 — v1 Guide strengths ported into `agent/guide.py` (Utku's session)

- **Did:** `agent/places.py` + `BuildingSession.resolve`: articles dropped, exact asset type → its room, repeated
  names → `MapError` listing `id (name, ref, type, floor)` per candidate ([D-012](decisions.md#d-012)), typos → "Did
  you mean"; `find_route` / `tour` pre-resolve stops; an ambiguous destination returns each option with its route
  length. Grounding: unit-glued numbers, list lengths, clock times, half-up rounding. `tests/test_places.py` (10).
- **Learned:** `Resolver.asset_type` / `navigation.resolve_asset_type` are fuzzy ("office" → `office_chair`), so
  places.py accepts only an exact type (plural ok). Python `round()` is half-even: the old check flagged "about
  43 m" for 42.5 m. Live (Sonnet 5.5 low): 7-turn script 0 ungrounded, $0.06; the model already fixed "Ofice" and
  picked the nearest printer itself, so the new paths are a safety net rather than the common path.
- **Next:** voice transcript rewriter (D-013); measure the Vercel preview (protected by Vercel Authentication).

## 2026-10-24 — Merge `origin/main` into `1-agentic-yarag` (Utku's session)

- **Why:** Vercel build failed on the branch (no `vercel.json`, `frontend/app/`, `backend/`). Main and the branch had
  built two parallel stacks; main's is broader (edits, profiles, voice, backend + UI), benchmark scores are equal.
- **Did:** main's stack stays canonical (`agent/guide.py`, `agent/tools.py`, `core/solvers/`, `agent/run_benchmark.py`,
  backend, frontend, `vercel.json`). The branch's modules moved beside it: `agent/guide/` → `agent/guide_v1/`,
  `core/solvers.py` → `core/solvers_v1.py`, `agent/run_benchmark.py` → `agent/run_benchmark_v1.py` (the same names
  would have shadowed each other: a package wins over a module). Text conflicts: main's text kept, branch content
  added as "v1" sections.
- **Decisions / questions:** branch D-010 / D-011 renumbered to [D-012](decisions.md#d-012) /
  [D-013](decisions.md#d-013) (main's D-010 guardrails, D-011 monochrome keep their ids). Both sides opened Q-014 for
  the same organiser note: merged into main's entry; branch Q-015 (factory schema) keeps its id; next free Q-016.
- **Next:** port v1 strengths (name resolution / candidate fan-out, grounding fallback, voice transcript rewriter)
  into `agent/guide.py`; then retire one stack.

## 2026-10-24 — AI layer of the app: live steps, cards, voice orb, camera walk mode

- **Did:** (parallel to another session's visual concepts in `frontend/prototypes/twin-lab/`; file split agreed by
  message: this session owns `src/ui/Chat.tsx`, `src/ui/cards/`, `src/voice/`, the orb, the camera view, `chat.css`,
  `/chat/stream`.) Backend: `Guide.on_step` callback + `POST /chat/stream` (NDJSON steps → reply), `channel` and
  `photo` on `/chat`, photo shown for one turn then replaced by a text placeholder, `core/directions.py` turn-by-turn
  legs on route events. Frontend: live tool checklist, route card (steps, show on map, walk with camera), pending
  change card (Apply / Keep as is → plain messages to the Guide), applied note, profile chip, follow-up chips,
  voice mode (browser SpeechRecognition + speechSynthesis, canvas point-cloud orb, EN/DE/TR, hands-free), camera
  walk mode (rear camera, floor arrow, spoken steps, "Where am I?" sends a frame, mic for next/back/repeat or a
  question).
- **Learned:** Starlette GZip flushes streamed chunks (Z_SYNC_FLUSH), so NDJSON is live behind it; `.chat` has
  `backdrop-filter`, so the full-screen camera view must be portalled to `body`. Live Opus 5.5 photo turn: read the
  sign "3.07 Meeting room", confirmed it with `search`, highlighted it; 5.2 s, 0 ungrounded.
- **Changed docs:** [commands.md](../docs/guides/commands.md#backend-guide-api), [project-state.md](project-state.md).
- **Then (Atahan: "no feedback, looks cheap"):** orb rebuilt in WebGL (three.js points, simplex-noise shader, rim +
  depth fade, CSS glow driven by the level); always visible (large in the empty chat, small in the composer); voice
  mode became a stage (orb, live transcript, Guide steps, spoken reply as captions); recognition never fails
  silently (per-error messages, "didn't catch that"); the mic meter starts only on `audiostart`, and an
  `audio-capture` error retries once without it (a parallel mic stream cost recognition the device in Chrome with a
  fake device). Optional `--accent` (fallback `--ink`) for the other session's HUD tokens.
- **Next:** test voice + camera on a phone over HTTPS (deployed URL); ElevenLabs can replace `useVoice` later.

## 2026-10-24 — Vercel deploy config

- **Did:** `vercel.json` (services `web` = Vite `frontend/app/` and `api` = FastAPI `backend.app:app`, `/api/(.*)`
  rewrite, `excludeFiles`, `maxDuration` 300); `StripPrefix` ASGI middleware and `CORS_ORIGINS` in `backend/app.py`;
  `tests/test_deploy.py`; deploy section in [commands.md](../docs/guides/commands.md#deploy-vercel).
- **Learned:** the Vercel rewrite keeps the `/api` prefix, so the backend strips it; the backend reads only
  `building.json` + `manifest.csv` from `data/` (bundle about 49 MB of code+data).
- **Changed docs:** [commands.md](../docs/guides/commands.md#deploy-vercel), [project-state.md](project-state.md#next-priorities).
- **Next:** Atahan imports the repo into Vercel and sets the env vars; pushing `dev` needs Atahan's OK.

## 2026-10-24 — Handoff: app deployed, frontend polish next

- **Did:** Recorded that Atahan has deployed the app; reordered project-state "Do next": frontend polish first
  (next session), Q-014 organiser follow-up and Q-001 output format parked by Atahan's choice; listed the small
  gaps (numpy undeclared, `route_model` not persisted, no live smoke test yet).
- **Next:** frontend polish ([project-state](project-state.md#-start-here-handoff-for-the-next-session-2026-10-24-evening)).

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

## 2026-10-24 — D-013 (was D-011 on the branch): transcript rewriter for voice input (Utku)

- **Decided:** Phase 4 voice path gets a transcript rewriter (STT → rewriter → Guide) that only normalises names and
  numbers to the building vocabulary; the original transcript is passed along; typed chat stays rewriter-free.
  [D-013](decisions.md#d-013).

## 2026-10-24 — Guide: final review fixes (branch `1-agentic-yarag`)

- **Did:** Grounding now checks numbers glued to a unit ("999m", "45m²", "37.4m"; "3D", "2nd" still ignored);
  `building_fact` / `route` not_found and ambiguous summaries name the slot that failed or varies (not always
  `place` / `to`); a failed `update_session` says "Nothing was saved; call update_session again with all fields…"
  and the prompt only acknowledges a constraint after an ok result; any tool exception becomes an `error`
  tool_result, any turn exception rolls the turn back and re-raises, the REPL and `scripts/eval_guide.py` survive
  any exception; the code fallback strips raw `[id]` tags from steps and ends an ambiguous result with the options
  and "Which one do you mean?"; prompt: closures by name only for lifts/stairs, clarifying questions list ≤ 3
  options. New conversation `compact_units.json`. +10 tests; full suite 117 passed.
- **Live run:** `scripts/eval_guide.py`, 9 conversations: 16/16 turns PASS, ~$0.32 (single run).
- **Changed docs:** project-state.md, ai-agents.md (live run count).
- **Next:** deferred review items: plural closures ("both lifts"), raw opening ids in route summaries.

## 2026-10-24 — Guide Task 6: scripted conversations, live runner, docs (branch `1-agentic-yarag`)

- **Did:** 8 scripted conversations (`tests/guide_conversations/*.json`: two-room and same-room printers, unknown
  room, follow-up "there", wheelchair stated once, lift closed and reopened, Turkish, out of scope),
  `scripts/eval_guide.py` (`check_turn` recomputes `route_to` lengths with `core.solvers.route` from the session
  state; PASS/FAIL per turn + cost) and 7 offline tests in `tests/test_guide_conversations.py`; full suite 107 passed.
- **Live run (dev campus + factory):** first run 12/15 turns; failures were prompt behaviour (closing offer "Would
  you like directions?" counted as a question; route reused from memory instead of calling `route` after a
  clarifying answer and after a lift reopened). Three RULES lines in `agent/guide/prompt.py` fixed it: 15/15 PASS
  (a single run, not a stability measure), ~$0.27 per full run; after the review-round checker fixes the three changed
  conversations re-ran 9/9 PASS (~$0.19).
- **Changed docs:** commands.md (Guide section), ai-agents.md (Guide v1 status), project-state.md.
- **Next:** UI / voice on top of `TurnResult`; Guide edit tools (Builder).

## 2026-10-24 — Organisers' note on Sunday route scoring (Utku's session)

- **Learned:** Sunday routes are scored as a space sequence, re-measured with the organisers' own model
  (door-to-door geodesic ~15 cm off walls; stairs 2 m per metre climbed; lift 15 m + 1 m per metre); score =
  best ÷ ours, full marks within 1%, invalid = 0. New factory rules (forklift aisles, openings ≥ 3 m, no
  pass-through production bays). Current `data/` has no aisle/walkway/bay space types.
- **Changed docs:** [route-model.md](../docs/kit/route-model.md#sunday-scoring-model-organisers-note-2026-10-24)
  (new section).
- **Questions:** Q-001 progress (format partly answered, tolerance answered); opened Q-014 (scoring distance
  model / router), Q-015 (factory schema).
- **Next:** decide on a second cost profile for the router (Q-014).

## 2026-10-24 — Guide Task 5: loop, prompt and REPL (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/prompt.py` (cached RULES + building overview, no per-room facts), `agent/guide/guide.py`
  (`Guide.turn` tool loop, one grounding repair then `fallback_text`, API errors roll the turn back, `TurnResult`
  with ids/routes/options for the UI) and `agent/guide/__main__.py` (REPL with `--show-tools` and a cost line);
  15 tests in `tests/test_guide_loop.py` (+1 empty-list test in `tests/test_guide_route.py`); full suite 100 passed.
- **Learned (live smoke):** the API rejects strict tool sets with more than 16 nullable/union parameters, so
  `via` / `close` / `reopen` are now plain arrays (`[]` = none). The model split "the 3D printer" into one route per
  room until a prompt rule said to pass the user's own words; `locate` now ignores a leading "the".
- **Review fix:** a refusal / cut-off response with tool calls now gets `is_error` tool results (append-only), so the
  next turn's history stays valid.
- **Next:** Task 6+ (UI / voice on top of `TurnResult`).

## 2026-10-24 — Guide Task 4: grounding checker (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/grounding.py` (`grounded_tokens`, `ungrounded`, `fallback_text`); numbers in a reply must
  appear in tool results, rounded to 0/1/2 dp, or be a list length; 14 tests in `tests/test_guide_grounding.py`.
- **Next:** Task 5 wires it into the Guide loop (one repair round, then `fallback_text`).

## 2026-10-24 — Guide Task 3: route + update_session tools (branch `1-agentic-yarag`)

- **Did:** Added `route` and `update_session` to `agent/guide/tools.py`; session closures are fan-out slots
  (ambiguous "the lift" only asks when routes differ), `bmap.closed` restored after each call;
  `tests/test_guide_route.py` (13 tests); full suite 69 passed.
- **Next:** Task 4+ (agent loop / fallback reading `result.space_path`, `steps`, `options`).

## 2026-10-24 — Guide Task 2: lookup tools (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/tools.py` (`Session`, `TOOLS`, `run_tool`; tools locate, find_places, place_info,
  building_fact via a name -> handler dict) and `tests/test_guide_tools.py` (12 tests); `building_fact` equals
  `core.solvers.solve` on gold inputs for every dev question of its kinds; full suite 56 passed.
- **Next:** Task 3 adds `route` and `update_session` to `HANDLERS` / `TOOLS`.

## 2026-10-24 — Guide Task 1: place resolution + candidate fan-out (branch `1-agentic-yarag`)

- **Did:** Added `agent/guide/resolve.py` (`resolve_places`, `resolve_elements`, `nearest_names`, `describe`,
  `fan_out`) and `tests/test_guide_resolve.py` (11 tests); full suite 47 passed.
- **Next:** plan Tasks 2-6 ([plan](../docs/superpowers/plans/2026-10-24-guide-agent.md)).

## 2026-10-24 — Phase 3 Guide agent: design + plan (Utku's session, branch `1-agentic-yarag`)

- **Did:** Brainstormed the Phase 3 "brain" with Utku: terminal-first, multi-turn Q&A + directions, no building
  edits, no UI/voice yet. Wrote and got approval for the
  [design](../docs/superpowers/specs/2026-10-24-guide-agent-design.md) and wrote the
  [implementation plan](../docs/superpowers/plans/2026-10-24-guide-agent.md) (6 tasks, subagent-driven).
- **Decided (in conversation):** Anthropic SDK directly, no LangChain; code (not the model) runs every candidate and
  compares answers; grounding check on numbers + refs; closures last for the session; default model
  `claude-opus-5-5` via `GUIDE_MODEL`.
- **Learned:** `locate` silently picks the first of several matching assets (e.g. two 3D printers) — the Guide must
  list or ask instead.
- **Next:** execute the plan task by task.

## 2026-10-24 — Warm-up kinds in parser + solvers (Utku's session)

- **Did:** 6 warm-up templates in `core/question_parser.py` (+ `destination`, tour `stops`, asset label → type
  fallbacks); solvers `locate`, `count_assets`, `route` (step-free / closure / unreachable), tour via `solve()`;
  replies in `agent/answer.py`; LLM parser schema + prompt; `run_benchmark` `route` = `{reachable: false}` when cut off.
- **Result:** `tests/test_warm_up.py` 2,120/2,130 from text (count 239/239, locate 553/553, route 715/720,
  step-free 239/240, closure 136/138, tour 238/240); all 10 misses are duplicate-name texts. Live LLM on 12 reworded
  dev warm-up questions: 12/12 (≈ $0.33, mostly cache writes). Benchmark unchanged: dev 138/138, test CSV identical.
- **Learned:** warm-up `locate`/`count` name assets by a label that is sometimes not the type ("seating row" →
  `lecture_seating_row`, "air compressor" → `compressor`).

## 2026-10-24 — Route paths in the warm-up format (Utku's session)

- **Did:** cloned the organisers' repo to `upstream-challenge/` (read-only, push disabled, ignored via
  `.git/info/exclude`) — identical to our kit copy. Read README §3–4: warm-up answers hold `space_path` and
  `element_path`. Added `RouteResult.legs` / `.element_path` and `BuildingMap.leg()`; errand returns `legs`;
  `run_benchmark` .json gets `route`. Submission renamed to `submissions/team_jaRAG.csv` (team name jaRAG).
- **Result:** `tests/test_routes.py`: 1,338 / 1,338 warm-up route questions exact (length, both paths,
  unreachable cases). `uv run pytest -q` → 30 passed. Test CSV unchanged; JSON has `route` for 20 errands.
- **Open:** Q-001 — question for the organisers drafted there; Utku will ask. Warm-up kinds (route, tour,
  locate…) have no parser templates/solvers yet in case Sunday asks them.

## 2026-10-24 — run_benchmark, BENCHMARK.md, test submission (Utku's session)

- **Did:** `agent/run_benchmark.py` (+ `run_benchmark` script in pyproject); `agent/answer.py` now exposes
  `respond()` (reply + kind + ids + solver result); `BENCHMARK.md`; `submissions/test_submission.csv` and
  `submissions/test_answers.json` generated by the agent (hybrid mode); commands.md uses `agent.answer:answer`.
- **Result:** 145/145 test questions answered, 0 errors; CSV ids == `submission_template.csv`; replies identical
  to `benchmark.evaluate --submission-csv`. `uv run pytest -q` → 28 passed.
- **Open:** Sunday route node ids (Q-001); team name for the `team_<name>.csv` file.

## 2026-10-24 — Live LLM parser accuracy (Utku's session)

- **Did:** `ANTHROPIC_API_KEY` added to `.env` (git-ignored); ran `scripts/eval_llm_parser.py --per-kind 3`
  with and without `--paraphrase` (24 dev questions, 3 per kind; step_free 1, what_if 2).
- **Result:** original wording: regex, llm, hybrid all 24/24. Reworded questions: regex 0/24 (no template
  matches), llm 24/24, hybrid 24/24 → hybrid is the right default for unseen wording (D-007).
- **Cost:** parser tokens at evaluate.py prices ≈ $0.42 first run (66.9k cache-write tokens), ≈ $0.19 second
  (331.7k cache reads); paraphrase calls not included in that count.
- **Caveat:** small sample (24 questions, one paraphrase each); the paraphrases keep names exactly.

## 2026-10-24 — Answer formatter + first official dev score (Utku's session)

- **Did:** `agent/answer.py`: `answer()` for `benchmark.evaluate`, formatter writes the `Answer:` line from solver
  results (refs only for space kinds, a single number for number kinds); `tests/test_answer.py` scores every
  train/dev reply with `benchmark/score.py`.
- **Result:** `benchmark.evaluate data/dev --agent agent.answer:answer` (PARSER_MODE=regex) → **138/138**; train
  515/517; test 145/145 replies, none fail. API spend: $0.
- **Learned:** every space has a `ref` and every train/dev `accept` list holds it. The solver test's "655/655 via
  text" skipped the 7 ambiguous texts; real text → answer is 653/655 (H02 and H04 of osm-way37850565, where
  the text names a duplicate "Büro" and H02/H03 have identical text with different answers).
- **Next:** test CSV, `run_benchmark` + `BENCHMARK.md`; measure LLM parser once `.env` has a key.

## 2026-10-24 — Solvers for every benchmark kind (Utku's session)

- **Did:** `core/solvers.py` with one solver per kind + `solve(bmap, kind, params)`; `tests/test_solvers.py`
  (gold `inputs` and text → parser → solver). Written first in a scratch package before the foundation commit
  landed, then moved into `core/`. Root `README.md` added (setup + how to run the kit from `archive/`).
- **Learned:** shared walls count `type` ∈ {room, hall} (Q-003 resolved); width rule on all opening kinds
  matches 80/80; parser's `step_free` slot for errands is now honoured by the solver.
- **Result:** 655/655 train+dev both ways; 145/145 test questions solve without error. API spend: $0.
- **Next:** formatter + `answer()` + dev evaluation + test CSV ([project-state.md](project-state.md#next-priorities)).

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
