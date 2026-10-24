# Guide eval: port scripts/eval_guide.py to the canonical Guide, fix the failures it found

- **Author:** Claude session (Utku) · **Date:** 2026-10-24
- **Related:** D-003, D-012, Q-016 (new); docs/guides/commands.md

## Summary
`scripts/eval_guide.py` and `tests/test_guide_conversations.py` tested `agent/guide_v1`; they now test the canonical
`agent/guide.py` used by the backend/UI. The live run surfaced 4 failures; fixed in the checker (2) and the Guide
prompt (1 behaviour, 1 consequential). Also records the multi-building gap as Q-016.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | eval_guide imports only the canonical stack (`agent.guide`, `agent.tools`, `core.navigation`, `scripts.live_guide`), no `guide_v1`/`solvers_v1` | `scripts/eval_guide.py` imports | `grep -n "_v1" scripts/eval_guide.py tests/test_guide_conversations.py` → no hits |
| C2 | Same expect keys as before; `route_to` compares the last reachable `find_route` (this turn, else the conversation's last via `earlier`) with a fresh `navigation.find_route` under the session's profile/closures/rules after the turn | `check_route`, `check_turn`, `run_conversation` | read; `tests/test_guide_conversations.py` route tests |
| C3 | `asked` = a question anywhere in the reply (regex `\?(?=\s|$)`) | `asks()` | `test_asked_counts_a_question_anywhere_in_the_reply` |
| C4 | `asset_total` accepts `locate.total` or `count_assets.count`; `space_ids_include` walks tool results + UI events | `check_asset_total`, `space_ids` | offline tests |
| C5 | CLI prints seconds + cost per turn and totals; `--model` / `--effort` | `main`, `run_conversation` | read; live run output below |
| C6 | Conversations use the new tool names: `wheelchair_once` t1 `set_profile`; `lift_closure` = wheelchair user, `propose_change` + "Yes, go ahead." `apply_change` turns for close and reopen; every `tools` name exists in `TOOL_DEFINITIONS` | `tests/guide_conversations/*.json` | `test_conversation_files_are_valid` |
| C7 | Guide prompt: when items of the asked kind are in several rooms and the user wants one, ask which before routing; no closing offer questions | `agent/guide.py` INSTRUCTIONS | read the diff |
| C8 | Offline tests pass: 10 in test_guide_conversations, full suite green | tests | `uv run pytest -q` |
| C9 | Docs/memory: commands.md section for the canonical eval; project-state + log entry with live numbers; Q-016 added (multi-building unsupported, with scan facts) | docs/guides/commands.md, memory-bank/* | read; `uv run python scripts/check_links.py` |

## Checks I ran
- `uv run pytest tests/test_guide_conversations.py -q` → `10 passed`
- `uv run pytest -q` → `304 passed, 1 skipped in 60.05s`
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files` (`python3` = 3.9 fails on the script's type hints)
- `GUIDE_LLM=offline uv run python scripts/eval_guide.py` → runs end to end (5/18, offline rule client; expected)
- Live, Opus 5.5 medium, before fixes: `14/18 turns PASS, 94.9s, total cost ~$0.2438`
- Live after fixes: `17/18 turns PASS, 88.8s, total cost ~$0.2232` (miss = question mid-reply, checker bug)
- Live after `asks` fix, `printers_two_rooms.json`: `3/3 turns PASS, 11.8s, total cost ~$0.0280`
- Multi-floor/multi-building facts for Q-016 from a read-only scan of `data/*/*/building.json` + `data/manifest.csv` (174/280 multi-floor, max 10 floors, unique group_ids, no walkway/bridge names)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] open questions: Q-016 added
- [x] docs touched: `docs/guides/commands.md`

## Known gaps / not done
- Full 18-turn live run not repeated after the final `asks` fix (only the affected conversation); single runs, no variance measured.
- `agent/guide_v1/` and its own tests (`test_guide_loop.py` etc.) are untouched; the v1 code fallback reply is still not ported.
- `check_links.py` fails under system `python3` (3.9) although CLAUDE.md says to use it; not changed here.
- Prompt change not re-checked against `scripts/live_guide.py`.

## Verification rounds
- Round 1: VERDICT: PASS (TREE 68ba137a8a90d5ec41ddd7dc60b026e9da98a433)

## Verification report (round 1)

VERDICT: PASS
TREE: 68ba137a8a90d5ec41ddd7dc60b026e9da98a433

| # | Status | Evidence |
|---|---|---|
| C1 | MET | no `_v1` in eval_guide.py / test_guide_conversations.py; imports agent.guide (Guide, GuideTurn, Usage, make_client), agent.tools.BuildingSession, core.navigation, scripts.live_guide (cost, delta) all exist |
| C2 | MET | EXPECT_KEYS unchanged; check_route uses `routes(turn) or [earlier]` then navigation.find_route with the session's step_free, profile_closures, route_model, route_rules (same call as agent/tools.py:165-167); tests pass |
| C3 | MET | asks() regex `\?(?=\s|$)`; test passes |
| C4 | MET | locate→total, count_assets→count; space_ids walks results + events; tests pass |
| C5 | MET | --model/--effort; per-turn seconds + cost; offline run "5/18 turns PASS, 0.1s, total cost ~$0.0000" |
| C6 | MET | wheelchair_once t1 set_profile; lift_closure wheelchair + propose/apply turns; tool names checked against TOOL_DEFINITIONS |
| C7 | MET | agent/guide.py INSTRUCTIONS 56-58, prompt text only (+3/-1) |
| C8 | MET | 10 passed; full suite 304 passed, 1 skipped |
| C9 | MET | commands.md section; project-state + log entries; Q-016 with anchor; Q-016 data facts re-scanned and match |

Standard checks: pytest 304 passed / 1 skipped; links OK under uv (python3 3.9 fails, pre-existing, declared); no secrets; score.py unchanged; no hard-coding. Live API runs not re-run (cost). Undeclared changes: none significant.
