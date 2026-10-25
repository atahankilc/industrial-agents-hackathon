# Guide Task 2: lookup tools (locate, find_places, place_info, building_fact)

- **Author:** implementer agent · **Date:** 2026-10-24
- **Related:** docs/superpowers/plans/2026-10-24-guide-agent.md Task 2

## Summary
Adds `agent/guide/tools.py` with `Session`, strict Anthropic `TOOLS`, and `run_tool` dispatch (name -> handler dict) for four lookup tools, built on Task 1's resolve/fan_out.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | locate lists every room with counts; unknown thing is not_found with nearest | `agent/guide/tools.py:locate` | `uv run pytest tests/test_guide_tools.py -q` |
| C2 | place_info matches core and asks when names repeat; summary has name, ref, floor | `place_info` | same |
| C3 | building_fact result == core.solvers.solve on gold inputs for all 138 dev questions of its kinds | `building_fact`, `fact_plan` | same (test_building_fact_equals_solver_on_gold_inputs) |
| C4 | TOOLS strict, additionalProperties false, all props required, order stable; bad args never raise | `TOOLS`, `run_tool` | same |
| C6 | Unresolvable floor/room type/asset type -> not_found + nearest; truncated and ambiguous options share one shape {choices, summary, result} | `Unresolved`, `finish` | same (3 added tests) |
| C5 | No protected files touched | git diff --cached --stat | read |

## Checks I ran
- RED: `uv run pytest tests/test_guide_tools.py -q` -> `ModuleNotFoundError: No module named 'agent.guide.tools'`
- GREEN: `uv run pytest tests/test_guide_tools.py -q` -> `9 passed in 2.04s`
- Fix round 1: `uv run pytest tests/test_guide_tools.py tests/test_guide_resolve.py -q` -> `23 passed in 2.30s`
- `uv run pytest -q` -> `56 passed`
- gold check status counts over dev questions -> `Counter({'ok': 138})`
- `uv run python scripts/check_links.py` -> `OK: all links resolve in 28 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: none

## Known gaps / not done
- `route` and `update_session` tools come in Task 3.
- Ambiguous building_fact options carry per-option summaries; option `result` is the raw `{"result": ...}` wrapper from fan_out.

## Verification rounds
- Round 1: PASS

## Final verification report
VERDICT: PASS — TREE cd6f9a40; C1–C6 MET; pytest 56 passed (12 in test_guide_tools.py); links OK; no secrets; score.py unchanged; no hard-coding; memory-bank consistent.
