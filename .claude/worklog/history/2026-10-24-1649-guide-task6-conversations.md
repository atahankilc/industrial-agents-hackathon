# Guide Task 6: scripted conversations, live runner, docs

- **Author:** implementer session · **Date:** 2026-10-24
- **Related:** docs/superpowers/plans/2026-10-24-guide-agent.md (Task 6)

## Summary
Adds 8 scripted Guide conversations, `scripts/eval_guide.py` (per-turn PASS/FAIL, cost, `check_turn` recomputing routes with `core.solvers.route`), offline tests, three prompt rules found by the live run, and docs.

## Claims
| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | 8 conversation files, valid, unknown expect keys rejected | `tests/guide_conversations/*.json`, `scripts/eval_guide.py:load_conversation` | `uv run pytest tests/test_guide_conversations.py -q` → 7 passed |
| C2 | `check_turn` passes a matching route and flags a wrong `optimal_length_m` | `scripts/eval_guide.py:check_turn` | same test file |
| C3 | Full suite green | all | `uv run pytest -q` → 107 passed |
| C4 | Live run 15/15 turns PASS, ~$0.27 (first run 12/15, ~$0.25) | `scripts/eval_guide.py` | output below |
| C5 | Prompt RULES gained 3 lines (re-call tool after clarifying answer, call route afresh, no closing offers) | `agent/guide/prompt.py` | `git diff --cached agent/guide/prompt.py` |
| C6 | Docs: commands.md Guide section, ai-agents.md Guide v1 status, project-state, log entry (index blob only; foreign Organisers' entry untouched) | docs, memory-bank | `git diff --cached` |

## Checks I ran
- `uv run pytest tests/test_guide_conversations.py -q` → 7 passed
- `uv run pytest -q` → 107 passed
- `uv run python scripts/check_links.py` → OK: all links resolve in 28 files
- Live run 1: `12/15 turns PASS, total cost ~$0.2498`; live run 2 (after prompt fix): `15/15 turns PASS, total cost ~$0.2687`

## Knowledge base updates
- [x] project-state.md updated
- [x] log.md entry added (index blob; working tree has foreign unstaged hunks)
- [x] docs touched: commands.md, ai-agents.md

## Known gaps / not done
- Live run is single-sample; model behaviour is nondeterministic, so a rerun may flake.
- `asked` is a "last line ends with ?" heuristic.
- `route_to` closure recompute applies the union of every candidate id of each closure.

## Fix round 1
- I1: `fresh_routes` now computes a core route per reading of the closures (one candidate per closure); `route_to` passes only if all readings agree with the Guide's length, else fails ("the Guide should have asked").
- I2: `route_to` requires the Guide's route and every reference to be `reachable: True`.
- M3: new expect key `asset_total` (locate total and reply must equal the core count); used in printers_two_rooms turn 1.
- M4: follow_up_there turn 2 has `asked: false`. M7: docs note the 15/15 is a single run.
- Tests: `uv run pytest tests/test_guide_conversations.py -q` → 7 passed; `uv run pytest -q` → 107 passed; `uv run python scripts/check_links.py` → OK
- Live sanity (3 changed conversations): `9/9 turns PASS, total cost ~$0.1904`.

## Verification rounds
- Round 1: PASS

## Final verification report
VERDICT: PASS — TREE 13418b5a; C1–C6 MET; pytest 107 passed (7 conversations tests); links OK; no secrets; score.py unchanged; no hard-coding; live results are implementer evidence (15/15 single run, $0.27; fix-round sanity 9/9, $0.19); foreign unstaged work excluded.
