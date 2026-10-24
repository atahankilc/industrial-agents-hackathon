# Guide: final review fixes (grounding units, slot summaries, session updates, exception safety)

- **Author:** Claude (fix-wave implementer, branch `1-agentic-yarag`) · **Date:** 2026-10-24
- **Related:** `.superpowers/sdd/2026-10-24-guide-agent/final-findings.md` (items 1–7), spec
  `docs/superpowers/specs/2026-10-24-guide-agent-design.md`

## Summary
Fixes every finding of the final whole-branch review of the Building Guide: unit-glued numbers are now
grounding-checked, code-written summaries name the slot that failed / varies, failed session updates say nothing
was saved, any exception is answered (tool) or rolled back (turn), the fallback is cleaner, and the prompt is
softened for doors and capped at 3 options. One new live conversation; live run 16/16 PASS.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `NUMBER` checks numbers glued to a unit (m², m2, km, cm, mm, min, m, s, %, x): "999m"/"45m²" flagged when ungrounded, "37.4m" passes for 37.42; "3D", "2nd", "3rd", "1st" still not numbers | `agent/guide/grounding.py` `UNIT`, `NUMBER` | `uv run pytest -q tests/test_guide_grounding.py -k glued` → 1 passed |
| C2 | `fallback_text` strips `[id]` tags from route steps and, for an ambiguous result, appends option summaries and ends with "Which one do you mean?" | `agent/guide/grounding.py` `fallback_text`, `ID_TAG`, `CHOOSE` | `uv run pytest -q tests/test_guide_grounding.py -k fallback` → 4 passed |
| C3 | `building_fact` and `route` not_found / ambiguous summaries use the user's text of the slot that failed (`out["slot"]`) or the slots that vary (route from "3D printer" to "Main lobby" names '3D printer') | `agent/guide/tools.py` `slot_text`, `building_fact`, `route` | `uv run pytest -q tests/test_guide_tools.py tests/test_guide_route.py -k "slot"` → 2 passed |
| C4 | Every non-ok `update_session` summary ends with "Nothing was saved; call update_session again with all fields once this is resolved."; validation stays all-or-nothing; ok summaries do not carry it | `agent/guide/tools.py` `update_session`, `apply_session_update`, `NOTHING_SAVED` | `uv run pytest -q tests/test_guide_route.py -k nothing_was_saved` → 1 passed |
| C5 | A tool (or `json.dumps`) exception becomes an `error` tool_result for that tool_use; any exception in a turn rolls back messages, tool_results and session and re-raises; REPL prints `error: …` for any exception and continues; `scripts/eval_guide.py` records any exception as a turn failure | `agent/guide/guide.py` `Guide.run`, `Guide.turn`; `agent/guide/__main__.py` `repl`; `scripts/eval_guide.py` `run_conversation` | `uv run pytest -q tests/test_guide_loop.py -k "exception"` → 3 passed |
| C6 | Prompt: acknowledge a constraint only after update_session returned ok (else nothing was saved, call again with all fields); closures by name only for lifts/stairs (tool description: doors only by id); clarifying question lists at most 3 options | `agent/guide/prompt.py` `RULES`; `agent/guide/tools.py` `TOOLS` (update_session) | `uv run pytest -q tests/test_guide_loop.py -k prompt_rules` → 1 passed |
| C7 | New conversation `tests/guide_conversations/compact_units.json` (route_to Lab 2.20 + grounded, compact "120m" style); file-count assertion raised to ≥ 9 | `tests/guide_conversations/compact_units.json`, `tests/test_guide_conversations.py` | `uv run pytest -q tests/test_guide_conversations.py` → 7 passed |
| C8 | Message history stays append-only (rollback only truncates this turn's additions); core/, agent/answer.py, agent/run_benchmark.py, benchmark/ untouched | — | `git diff --cached --stat -- core agent/answer.py agent/run_benchmark.py benchmark` → empty |
| C9 | Full suite green: 117 passed (guide files: grounding 17, tools 14, route 16, loop 19, conversations 7, resolve 11) | `tests/` | `uv run pytest -q` → 117 passed |
| C10 | Live run: 9 conversations, 16/16 turns PASS, ~$0.3228 (single run) | `scripts/eval_guide.py` | output pasted below (costs money; do not re-run) |
| C11 | Knowledge base: log.md top entry (only my hunk staged), project-state.md bullet, ai-agents.md live count 16/16 | `memory-bank/log.md`, `memory-bank/project-state.md`, `docs/architecture/ai-agents.md` | `git diff --cached memory-bank/log.md`; `uv run python scripts/check_links.py` → OK |

## Checks I ran

- RED (before the fix, new tests only): `uv run pytest -q tests/test_guide_grounding.py tests/test_guide_tools.py tests/test_guide_route.py tests/test_guide_loop.py` → `10 failed, 56 passed` (e.g. `assert [] == ['999', '45']`; `"No place matches '1.14'..."`; `"'Main lobby' could mean 2 different places..."`; `RuntimeError: core blew up`)
- GREEN: same command → `66 passed in 3.71s`; `uv run pytest -q tests/test_guide_*.py` → `84 passed in 4.75s`
- `uv run pytest -q` → `117 passed in 21.52s`
- `uv run --env-file .env python scripts/eval_guide.py` →
  ```
  compact_units.json   PASS turn 1
  follow_up_there.json PASS turn 1, PASS turn 2
  lift_closure.json    PASS turns 1-4
  out_of_scope.json    PASS turn 1
  printers_same_room.json PASS turn 1
  printers_two_rooms.json PASS turns 1-3
  turkish_printer.json PASS turn 1
  unknown_room.json    PASS turn 1
  wheelchair_once.json PASS turns 1-2
  16/16 turns PASS, total cost ~$0.3228
  ```
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (new "Guide final review fixes" bullet with counts)
- [x] `memory-bank/log.md` entry added (index-blob procedure; foreign "Organisers' note" hunk stays unstaged)
- [x] decisions / open questions touched: none
- [x] docs touched: `docs/architecture/ai-agents.md` (live run 16/16, 9 conversations)

## Known gaps / not done
- Deferred by the controller: plural closures ("both lifts") fan out as one-of-N; raw opening ids in route
  summaries when a door id is closed.
- The live run prints replies only on failure, so it does not show whether the compact reply actually glued the
  unit ("NNm"); the offline test covers the checker itself.
- Live result is a single run, not a stability measure.
- No ruff in the environment; lint not run.

## Verification rounds
- Round 1: PASS (run in parallel with scoped re-review: all findings addressed)

## Final verification report
VERDICT: PASS — TREE ac4437d9; C1–C11 MET (C10 live 16/16 single run ≈$0.32 = implementer evidence); pytest 117 passed; links OK; no secrets; score.py unchanged; core/benchmark untouched; foreign unstaged work excluded.
