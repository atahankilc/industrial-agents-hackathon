# Plan import: floor stacking fix, API errors end cleanly, Creator docs

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** docs/superpowers/specs/2026-10-25-plan-import-design.md, plan Tasks 12–14

## Summary
The Urban Colab live run read all 5 floors but left 80 rooms unreachable because the floors were misaligned (each
photo has its own px/m estimate) and stairs only joined within 3 m. Stacking now searches a relative scale per floor,
joins stairs / lifts by name before distance, and gives consecutive floors that would stay apart their nearest pair
(marked synthetic). API errors (e.g. no credits) end an import with a readable reason. Creator docs added.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `align` tries relative scales (1.0, 0.93, 1.07, 0.87, 1.15, 0.8, 1.25) with ECC and keeps the best (≥ 0.6), updating the floor's `m_per_px` | `core/plan_import/stack.py` `align`, `SCALE_FACTORS` | `uv run pytest tests/test_plan_import_stack.py -q -k scale_search` |
| C2 | `connectors` returns (kind, stops, guessed): same name first, then nearest within `max_dist_m`; consecutive floors with no join get their nearest stair (else lift) pair, guessed=True | `core/plan_import/stack.py` `connectors` | `uv run pytest tests/test_plan_import_stack.py -q` → 10 passed |
| C3 | Guessed connectors are written with `synthetic: true`; `stack_floors` reports `guessed` | `core/plan_import/assemble.py`, `agent/creator_tools.py` | `uv run pytest tests/test_plan_import_assemble.py tests/test_creator_tools.py -q` |
| C4 | Creator prompt asks for the same name for the same stair / lift on every floor | `agent/creator.py` `INSTRUCTIONS` | read |
| C5 | An Anthropic API error ends `Creator.run` with status failed and "Claude API error: …" | `agent/creator.py` `run` | `uv run pytest tests/test_creator.py -q` → 7 passed |
| C6 | Docs: Creator section in ai-agents.md (with the live numbers), "Plan import (Creator)" commands section | `docs/architecture/ai-agents.md`, `docs/guides/commands.md` | read; `python3 scripts/check_links.py` → OK |
| C7 | Whole suite green, frontend typechecks | — | `uv run pytest -q` → 829 passed, 2 skipped; `cd frontend/app && npx tsc --noEmit -p .` → exit 0 |

## Checks I ran
- `uv run pytest -q` → `829 passed, 2 skipped, 15 warnings in 220.77s`
- `cd frontend/app && npx tsc --noEmit -p .` → exit 0
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- Browser (not automated in tests): headless Chrome over CDP against backend :8777 (`GUIDE_PERSIST=off`) + Vite :5197:
  `?view=import` → file picked → Creator lines streamed → Edit mode "Editing Residence 439", NO PROBLEMS.

## Knowledge base updates
- [x] `memory-bank/project-state.md` — plan import bullet: stacking fix, browser check done, blocked on API credits
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: ai-agents.md (Creator section), commands.md (Plan import section)

## Known gaps / not done
- The stacking fix is not yet re-run live on Urban Colab: the API key's credit balance ran out (live runs blocked).
- `eval_import.py --full` not run yet (same reason).
- Pre-existing, not touched: EditMode's header class `.guide-line` has no CSS, so the Edit mode header is unstyled.

---

## Verifier report (round 1)

VERDICT: PASS
TREE: f0ac7b52e455d44b0f6608b80c065ec8cdcaa00b
C1–C7 MET. Suite 829 passed, 2 skipped; tsc exit 0; links OK; no secrets; score.py unchanged; no hard-coding. Note: same-name stair matching has no distance cap (generic names like "Treppe" pick the nearer one).
