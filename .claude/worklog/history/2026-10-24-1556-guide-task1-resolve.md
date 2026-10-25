# Guide agent: place resolution and candidate fan-out

- **Author:** implementer agent (Task 1) · **Date:** 2026-10-24
- **Related:** docs/superpowers/specs/2026-10-24-guide-agent-design.md

## Summary
Adds `agent/guide/resolve.py`: resolves place/element phrases to candidate ids and a `fan_out` that runs a lookup per candidate and collapses identical answers or reports ambiguity.

## Claims
| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `resolve_places` order: id, ref/name (leading the/a/room stripped), asset type, asset name, search | `agent/guide/resolve.py` | `uv run pytest tests/test_guide_resolve.py -q` |
| C2 | `resolve_elements`, `nearest_names`, `describe` (space/connector/opening) behave per brief | same | same |
| C3 | `fan_out`: not_found, ok on equal results, ambiguous with options (<= MAX_OPTIONS, truncated flag), errors caught per combo | same | same |
| C4 | No existing code modified; full suite green | repo | `uv run pytest -q` |

## Checks I ran
- `uv run pytest tests/test_guide_resolve.py -q` -> 11 passed
- `uv run pytest -q` -> 44 passed

## Knowledge base updates
- [x] project-state/log: updated (memory-bank/log.md entry, memory-bank/project-state.md "What exists")
- [x] decisions / open questions: none
- [x] docs touched: none (docs/architecture/ai-agents.md is updated by plan Task 6)

## Known gaps / not done
`describe` returns a bare record (kind/floor None) for unknown ids so fan_out's truncated path works with arbitrary ids.

## Fix round 1
`resolve_elements` now maps the last word via a kind table (stairs/staircase/stairway, lift/elevator) instead of stripping "s"; test added for "stairs" and "the stairs". `uv run pytest tests/test_guide_resolve.py -q` -> 11 passed in 0.31s (re-run in fix round 2).

## Fix round 2
- Knowledge base: implemented — added entry to memory-bank/log.md and "What exists" bullet in memory-bank/project-state.md; ticked boxes above.
- Fix round 1 "see report": implemented — replaced with real output (11 passed).
- `uv run python scripts/check_links.py` -> OK: all links resolve in 28 files
- `uv run pytest -q` -> 44 passed in 19.11s

## Verification rounds
- Round 1: FAIL (memory-bank not updated; 'see report') → commit-fixer
- Round 2: PASS

## Final verification report
VERDICT: PASS — TREE 201fa1b9; C1–C4 MET; pytest 44 passed (11 in test_guide_resolve.py); links OK; no secrets; score.py unchanged; no hard-coding; knowledge base updated.
