# Guide Task 3: route and update_session tools

- **Author:** implementer agent · **Date:** 2026-10-24
- **Related:** docs/superpowers/plans/2026-10-24-guide-agent.md (Task 3)

## Summary
Adds `route` and `update_session` tools to `agent/guide/tools.py`. Session position, step-free setting and closures feed routes; closure phrases fan out so an ambiguous "the lift" only asks when routes differ.

## Claims
| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | route result equals `core.solvers.route`; unreachable is ok with reachable False | `tools.py:route` | `uv run pytest tests/test_guide_route.py -q` |
| C2 | `from` null uses session position; neither -> `need_start` | `tools.py:route` | same |
| C3 | session closures never leak into `bmap.closed` | `tools.py:route` | `test_session_step_free_and_closures...` |
| C4 | update_session position/close/reopen with fan-out contract; ambiguous position leaves session untouched | `tools.py:update_session` | same |
| C5 | both tools in TOOLS and HANDLERS | `tools.py` | `test_tools_registered` |

## Checks I ran
- RED: `uv run pytest tests/test_guide_route.py -q` before implementation -> 11 failed
- `uv run pytest tests/test_guide_route.py tests/test_guide_tools.py -q` -> 25 passed (after fix round 1)
- `uv run pytest -q` -> 69 passed in 21.64s
- `uv run python scripts/check_links.py` -> OK: all links resolve in 28 files

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: none

## Known gaps / not done
(fix round 1: reopen of unknown phrase -> not_found, of non-closed -> not_closed, session unchanged; ambiguous closure test now asserts ambiguous + option shape; collapsed closures name every candidate, e.g. 'Lift 1 / Lift 2'.)
Closure phrases that name a door by free text beyond exact id/name or connector kind are not found.

## Fix round (verifier)
- Stale counts: implemented - log.md (index and working tree, Task 3 entry only) and project-state.md now say 13 tests / 69 passed.
- PENDING.md: claim corrected - removed stray trailing backtick in Known gaps; links check now shows real output.

## Verification rounds
- Round 1: FAIL (stale counts; PENDING tidy) → commit-fixer (index-only edit, foreign hunks excluded)
- Round 2: PASS

## Final verification report
VERDICT: PASS — TREE 728c4799; C1–C5 MET; pytest 69 passed (25 route+tools); links OK; no secrets; score.py unchanged; no hard-coding; foreign unstaged Sunday-note work excluded.
