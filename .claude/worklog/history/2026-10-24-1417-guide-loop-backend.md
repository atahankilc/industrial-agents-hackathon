# Building Guide conversation loop, compare_routes, FastAPI backend skeleton (offline-testable)

- **Author:** Claude (Guide session) + backend subagent · **Date:** 2026-10-24
- **Related:** D-003, D-006, D-010 (new, proposed), Q-012; docs/architecture/ai-agents.md#building-guide--behaviour-contract, docs/research/elevenlabs.md

## Summary
Adds the Building Guide (Claude tool-use loop over agent/tools.py) with code-enforced confirm-before-apply and a
D-003 grounding check, an offline rule-based client for running without an API key, the compare_routes tool, and
a FastAPI backend (sessions, /chat, /events, OpenAI-compatible streaming /v1/chat/completions). All offline-tested.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Guide loop: every tool_use goes to `BuildingSession.call`, all results return in one user message with `is_error` on errors; text from every round kept; ≤ 12 tool rounds; refusal / max_tokens / pause_turn handled | `agent/guide.py:Guide.run`, `Guide.execute` | read; `uv run pytest -q tests/test_guide.py` |
| C2 | Model from `GUIDE_MODEL` (default `claude-opus-5-5`), effort from `GUIDE_EFFORT` (default `medium`), read at Guide creation | `agent/guide.py:Guide.__init__` | `test_requests_cache_the_overview_and_only_append` sets GUIDE_MODEL=claude-sonnet-5-5 |
| C3 | Building overview in a cached system block (`cache_control` ephemeral), tools = TOOL_DEFINITIONS, system identical on every request, history append-only | `agent/guide.py:system_blocks`, `Guide.request` | same test |
| C4 | `apply_change` for a change proposed in the same user turn is refused; applied after the user confirms next turn | `agent/guide.py:Guide.execute` | `test_tricky_user_conversation` (state after "The lift is broken!" = pending C1, nothing closed) |
| C5 | Grounding check: numbers/ids not in tool results / overview / user messages trigger one repair round; leftovers reported in `GuideTurn.ungrounded` | `agent/guide.py:ungrounded`, `Guide.reply` | `test_invented_number_triggers_one_repair`, `test_still_ungrounded_after_repair_is_reported`, `test_ungrounded_rules` |
| C6 | Scripted tricky-user conversation: vague printer → ≤3 options; ambiguous meeting room → search → ≤3 options with floors; wheelchair → set_profile, remembered; lift broken → propose, confirm, apply; route 124.24 m → 132.2 m via Lift 2 after closure, compare_routes extra 7.96 m | `tests/test_guide.py` | `uv run pytest -q tests/test_guide.py` → 7 passed |
| C7 | `make_client()` returns the offline client without ANTHROPIC_API_KEY (or GUIDE_LLM=offline); `llm_mode()` shared by backend /health | `agent/guide.py:llm_mode/make_client`, `backend/app.py:health` | read; `test_offline_client_runs_the_same_conversation`, backend health test |
| C8 | Offline client composes replies only from tool results (grounded) and drives the same flow | `agent/offline_llm.py` | `test_offline_client_runs_the_same_conversation` |
| C9 | New tool `compare_routes(change_id, start?)` for pending or applied changes: lost/gained access, longer routes with before/after/extra metres, last route before/after; lost rooms emitted as highlight event; listed in TOOL_DEFINITIONS | `agent/tools.py:tool_compare_routes`, `room_distances`, `snapshots` | `uv run pytest -q tests/test_agent_tools.py` (`test_compare_routes_pending_and_applied`) |
| C10 | Predictions (propose_change effect, compare_routes) no longer add events or move `last_route` (no phantom route events for /events pollers); effect has `extra_m` | `agent/tools.py:predict_between`, `emitting` flag | same test asserts events unchanged |
| C11 | Tool errors: KeyError messages no longer lose their leading quote | `agent/tools.py:BuildingSession.call` | read |
| C12 | FastAPI backend: GET /health, GET /buildings, POST /sessions, GET /sessions/{id}, PUT /sessions/{id}/building, POST /chat, GET /events (cursor), POST /v1/chat/completions (non-stream + SSE with "... " first chunk and `data: [DONE]`); building ids validated against the catalogue | `backend/app.py`, `backend/sessions.py`, `backend/openai_compat.py` | `uv run pytest -q tests/test_backend.py` (13 tests) |
| C13 | Runs locally with uvicorn and the offline LLM | `backend/app.py` | `GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8766` → /health `{"ok":true,"llm":"offline"}`, /chat reply, SSE ends `data: [DONE]` |
| C14 | Deps added with uv: fastapi, uvicorn; dev: httpx; `backend` in hatch packages | `pyproject.toml`, `uv.lock` | read diff |
| C15 | benchmark_agent docstring shows the correct run_benchmark usage (matches BENCHMARK.md) | `agent/benchmark_agent.py:4-5` | compare with `BENCHMARK.md` line 11 |
| C16 | Benchmark unaffected: dev 138/138 | — | `PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name dev` |
| C17 | Docs: ai-agents.md (compare_routes, Guide implementation section, backend link), commands.md (Backend section + endpoint table), D-010, Q-012 note, project-state, log | `docs/`, `memory-bank/` | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q` → `86 passed in 11.03s`
- `uv run pytest -q tests/test_guide.py` → `7 passed`
- `PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name dev` → `all 138 / 138 (100%)`
- uvicorn smoke (port 8766, offline): `/health` → `{"ok":true,"llm":"offline"}`; `/chat` "Where is the printer?" → "There are 4, including Print room 0.17, Print room 1.15, Print room 2.08. …", `ungrounded: []`; streaming completions tail `data: [DONE]`
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: D-010 (new, proposed), Q-012 progress note
- [x] docs touched: docs/architecture/ai-agents.md, docs/guides/commands.md

## Known gaps / not done
- No live Claude run: ANTHROPIC_API_KEY empty, so real-model behaviour, caching hit rate and cost are UNVERIFIED.
- ElevenLabs: how the session id arrives and the request `tools` (system tools) are UNVERIFIED / ignored; nothing created in any account.
- Sessions are in memory, no expiry; CORS allows all origins (local dev only).
- Route step text contains bracketed space ids, awkward for TTS; not changed here.
- Offline client is keyword rules only (demo/test fixture), not a language model.

## Verification rounds
- Round 1: VERDICT: PASS (TREE a5672b548d70a531f8fa3bf3eaa08ce540631de0)

## Verification report (round 1)

VERDICT: PASS
TREE: a5672b548d70a531f8fa3bf3eaa08ce540631de0

Claims C1–C17: all MET.
- C1 Guide.run: MAX_TOOL_ROUNDS = 12, every tool_use goes through execute → session.call, all results in one user message with is_error, text from every round kept, refusal/pause_turn/max_tokens handled; test_guide.py 7 passed.
- C2 GUIDE_MODEL/GUIDE_EFFORT read at creation; test asserts claude-sonnet-5-5.
- C3 cached overview block, tools=TOOL_DEFINITIONS, identical system blocks, append-only history asserted.
- C4 same-turn apply refused; state after "The lift is broken!" == ({"C1"}, set(), 0).
- C5 grounding: one repair, leftovers reported; 3 tests pass.
- C6 tricky user: 3 options each, profile remembered, propose→confirm→apply, 124.24 → 132.2 m via V04, extra 7.96.
- C7 llm_mode()/make_client(); /health → {"ok":true,"llm":"offline"}.
- C8 offline client grounded; test passes.
- C9 compare_routes + snapshots + lost_access event; test passes.
- C10 emitting flag; events and last_route unchanged by predictions.
- C11 KeyError message handling.
- C12 backend routes, catalogue validation (422 on traversal ids), 13 tests pass, SSE "... " first, data: [DONE] last.
- C13 verifier's own uvicorn run on port 8771 confirmed health, chat, stream.
- C14 fastapi>=0.162.0, uvicorn>=0.54.0, dev httpx>=0.28.1, backend in hatch packages.
- C15 docstring matches BENCHMARK.md line 11.
- C16 dev 138/138.
- C17 docs + memory bank updated; check_links OK.

Standard checks: pytest 86 passed; links OK (26 files); no secrets, no .env staged; benchmark/score.py unchanged;
no hard-coding of test buildings or question ids (DEMO_BUILDING is a demo default, train split).
Undeclared changes (not significant): profile_closures optional building arg + main_entrance_space() (part of C9);
GET /buildings lists the test split too (catalogue browsing).
Required fixes: none.
