# Guide Task 5: loop, prompt and REPL

- **Author:** Task 5 implementer (subagent) · **Date:** 2026-10-24
- **Related:** docs/superpowers/plans/2026-10-24-guide-agent.md (Task 5), spec docs/superpowers/specs/2026-10-24-guide-agent-design.md

## Summary
Adds the conversational Guide: a cached system prompt (rules + building overview), the `Guide.turn` tool loop with a
grounding check (one repair, then code-written fallback) and a terminal REPL. The live smoke test exposed an API
limit (max 16 union-typed parameters across strict tools) and a prompt gap; both fixed here.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `system_blocks(bmap)` = `[RULES, overview_text(bmap) with cache_control ephemeral]`; overview has floors, lifts/stairs, entrances, sorted room + asset types, no per-room facts; output is deterministic | `agent/guide/prompt.py` | `uv run pytest tests/test_guide_loop.py -q -k "system_blocks or request_shape"` |
| C2 | Request uses model `claude-opus-5-5` (env `GUIDE_MODEL`), effort `medium` (env `GUIDE_EFFORT`), `MAX_TOKENS = 16000`, `tools=TOOLS`, betas `["server-side-fallback-2026-07-01"]`, `fallbacks="default"`; no `thinking`, temperature or `tool_choice` | `agent/guide/guide.py:Guide.request` | `uv run pytest tests/test_guide_loop.py -q -k request_shape` |
| C3 | Full `response.content` appended as assistant message; all tool results of one response go in ONE user message of `tool_result` blocks (`content=json.dumps(result)`, `is_error` when status is error) | `Guide.run_loop`, `Guide.run` | `-k tool_round_then_answer` |
| C4 | Ungrounded reply → one repair message naming the values; still ungrounded → `fallback_text` of this turn's tool results, `grounded=False`; follow-up turns may restate numbers from earlier turns' tool results | `Guide.run_loop` | `-k "ungrounded or follow_up"` |
| C5 | `refusal` / `max_tokens` / empty text / `MAX_TOOL_ROUNDS = 8` exhausted → fallback text; `pause_turn` re-sends unchanged (one round) | `Guide.run_loop` | `-k "refusal or too_many"`; read docstring |
| C6 | `TurnResult` fields as in the brief; `asked` = last non-empty line ends with "?"; space/asset/connector ids from ok results (describe ids, route `space_path`, connectors in `element_path`, locate asset names mapped to ids); `routes` = ok route results; `options` = last ambiguous options | `Guide.result`, `collect`, `collect_located` | `-k "ambiguous or ok_route or tool_round"` |
| C7 | Session and messages persist across turns; blank input makes no API call; `anthropic.APIError` rolls messages, tool history and session back to the turn start and re-raises | `Guide.turn` | `-k "session_survives or blank or repl_ignores"` |
| C8 | REPL `repl(guide, lines, show_tools=False)` skips blank lines, prints tool calls (`--show-tools`), reply, tokens in/out + cache read/write and cost at $4/$20/$0.20/$5 per M; prints `error: …` on API errors and continues; `main()` reads `input("> ")` until EOF/`exit` | `agent/guide/__main__.py` | `-k repl` |
| C9 | Live-smoke fix: strict tool set has ≤ 16 union params — `route.via`, `update_session.close/reopen` are plain string arrays (`[]` = none) | `agent/guide/tools.py:TOOLS`, `TEXT_LIST` | `-k union` (failed before the change: RED shown below) |
| C10 | `locate` ignores a leading article ("the 3D printer" → 5 printers) | `agent/guide/tools.py:matching_assets` | `uv run pytest tests/test_guide_tools.py -q -k article` |
| C11 | Prompt rule: pass the user's own words to tools, don't split a multi-room phrase into per-room calls | `agent/guide/prompt.py:RULES` | read RULES; live transcript below |
| C12 | Tests: `tests/test_guide_loop.py` 15 passed, `tests/test_guide_route.py` 14 passed, `tests/test_guide_tools.py` 13 passed, full suite 100 passed; offline only (FakeClient) | tests | `uv run pytest -q` |
| C14 | Fix round 1 (I1): a `refusal` / `max_tokens` response containing `tool_use` blocks gets ONE appended user message of `is_error: true` tool_results (content "Not run: the response was cut off."), append-only (no earlier message popped or edited); the next turn's history has every tool_use id matched | `agent/guide/guide.py:Guide.run_loop`, `close_tool_uses`, `NOT_RUN` | `uv run pytest tests/test_guide_loop.py -q -k cut_off` |
| C15 | Fix round 1 (M3): `via=[]` gives the same route as `via=None`; `update_session` with `close=[]`, `reopen=[]` leaves closures unchanged | `tests/test_guide_route.py:test_empty_lists_mean_none` | `uv run pytest tests/test_guide_route.py -q -k empty_lists` |
| C13 | Memory bank: log entry (index-blob procedure, foreign hunk untouched) + project-state lines; links OK | `memory-bank/log.md`, `memory-bank/project-state.md` | `git diff --cached memory-bank/log.md`; `uv run python scripts/check_links.py` |

## Checks I ran

- RED: `uv run pytest tests/test_guide_loop.py -q` before implementation → `E   ModuleNotFoundError: No module named 'agent.guide.__main__'` / `1 error in 2.39s`
- RED (C9): with tools.py stashed → `FAILED tests/test_guide_loop.py::test_tools_fit_the_strict_union_limit` / `1 failed, 13 deselected`
- RED (C10): `FAILED tests/test_guide_tools.py::test_locate_ignores_leading_article` / `1 failed, 12 deselected`
- `uv run pytest tests/test_guide_loop.py -q` → `15 passed in 2.34s`
- `uv run pytest tests/test_guide_route.py -q` → `14 passed in 0.32s`
- `uv run pytest tests/test_guide_tools.py -q` → `13 passed in 1.91s`
- `uv run pytest tests/test_guide_loop.py tests/test_guide_route.py tests/test_guide_tools.py -q` → `42 passed in 3.64s`
- `uv run pytest -q` → `100 passed in 20.52s`
- RED (C14): before the fix → `FAILED tests/test_guide_loop.py::test_cut_off_tool_use_gets_error_results_so_next_turn_is_valid` / `1 failed, 28 passed` (loop + route files); C15's test passed immediately (it confirms existing handler behaviour).
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files`
- First live run (before C9) → `error: Error code: 400 - ... 'Schemas contains too many parameters with union types (17 parameters with type arrays or anyOf) ... (limit: 16 parameters with unions).'` (REPL printed it and continued, as designed)
- Second live run (after C9, before C11/C10): model called `route` once per printer room and returned both routes instead of asking (grounded, but not the intended ambiguity flow) → added C11; third run then showed `locate("the 3D printer") → not_found` → fixed C10.

### Final live smoke transcript (`printf 'Where is the 3D printer?\nhow do I get there from the main lobby?\n' | uv run --env-file .env python -m agent.guide data/dev/proc-campus-dev-001 --show-tools`)

```
>   · locate({"thing": "the 3D printer"}) → ok: 'the 3D printer': 5 in 2 room(s): Makerspace 1.14 (1.14) on Floor 1 x4; Lab 2.20 (2.20) on Floor 2 x1.
There are 5 3D printers in two rooms:

- **Makerspace 1.14** (ref 1.14) on Floor 1 has 4 printers, labelled 1.14-A to 1.14-D.
- **Lab 2.20** (ref 2.20) on Floor 2 has 1 printer, labelled 3D printer 2.20.

If you'd like directions, tell me where you are now and which room you want.
[tokens in/out 536/217, cache read 6060, cache write 0 | ~$0.0077 this turn, ~$0.0077 total]
>   · update_session({"position": "Main lobby", "step_free": null, "close": [], "reopen": []}) → ok: Position: Main lobby (0.14) on Ground floor. Step-free: no. Closed: none.
  · route({"to": "the 3D printer", "from": "Main lobby", "via": [], "step_free": null}) → ambiguous: 'the 3D printer' could mean 2 different places with different answers.
I've noted that you're starting in the Main lobby (0.14) on the Ground floor. The two rooms with 3D printers need different routes. Which one do you want: **Makerspace 1.14** (ref 1.14, Floor 1, 4 printers) or **Lab 2.20** (ref 2.20, Floor 2, 1 printer)?
[tokens in/out 3990/424, cache read 6060, cache write 0 | ~$0.0257 this turn, ~$0.0333 total]
> ```

Total live spend for all smoke runs ≈ $0.14 (per cost lines: 0.0573 + 0.0522 + 0.0333; the two 400s cost nothing).

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (What exists + What works lines)
- [x] `memory-bank/log.md` entry added (staged via index blob; the foreign "Organisers' note" hunk stays unstaged)
- [x] decisions / open questions touched: none
- [x] docs touched: none

## Known gaps / not done
- `grounded` is False whenever the code fallback replaced the model's text (refusal, cut-off, round budget), even
  though the fallback is itself tool-written.
- Grounding checks numbers only, not room names; user-supplied numbers not echoed by a tool count as ungrounded.
- Prices in the cost line are the brief's estimates for the default model; other `GUIDE_MODEL`s are not priced.
- Pre-existing >120-char lines in `agent/guide/tools.py` left as they were.

## Fix round 1
- I1: `Guide.run_loop` now computes `tool_uses` before the stop_reason check; on refusal/max_tokens `close_tool_uses`
  appends one user message with an `is_error` tool_result per tool_use id. Nothing earlier is popped or rewritten.
  Test `test_cut_off_tool_use_gets_error_results_so_next_turn_is_valid` (RED then GREEN).
- M3: `test_empty_lists_mean_none` in `tests/test_guide_route.py`.
- Counts updated everywhere: loop 15, route 14, tools 13, full suite 100 (PENDING, log.md entry, project-state.md).
- No new live run: the change only affects refusal/cut-off paths, which the smoke dialogue does not hit.

## Verification rounds
- Round 1: PASS

## Final verification report
VERDICT: PASS — TREE 24847ff3; C1–C15 MET; pytest 100 passed; links OK; no secrets; score.py unchanged; no hard-coding; foreign unstaged work excluded; live smoke evidence from implementer (not re-run).
