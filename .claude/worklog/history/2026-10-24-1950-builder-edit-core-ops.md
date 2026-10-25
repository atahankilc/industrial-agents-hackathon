# Builder Edit mode: design, M1 plan, and core edit operations (core/edits.py)

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 19:27
- **Related:** brief Level 4 (Build); docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md;
  docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md (Task 1)

## Summary
Adds the approved design of the app's Edit mode (edit a copy of a building by prompt and drag), the milestone-1
implementation plan, and Task 1 of that plan: `core/edits.py`, pure JSON edit operations on building dicts with
deterministic ids, opening snapping onto shared walls, and replay (`apply_steps`).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Design doc exists with front matter (id, summary, sources, related) and is linked from the docs index and the Builder section of ai-agents.md | `docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md`, `docs/README.md`, `docs/architecture/ai-agents.md` | read; `python3 scripts/check_links.py` → OK |
| C2 | M1 plan exists (7 tasks) with front matter (id `plan-builder-edit-mode-m1`), points at the spec, is linked from docs/README.md, and the spec links back to it | `docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md` | read |
| C3 | `apply_op(building, op)` returns a deep copy and never mutates the input; `apply_steps(base, steps)` replays steps deterministically | `core/edits.py` | `uv run pytest tests/test_edits.py -q -k "mutate or deterministic"` |
| C4 | Ops implemented: add_space, delete_space (also removes its openings + assets), set_space, add_opening, move_opening, set_opening, delete_opening, add_asset, move_asset (recomputes space_id from position), set_asset, delete_asset | `core/edits.py` | `uv run pytest tests/test_edits.py -q` → 16 passed |
| C5 | New ids follow `<floor_id>-S-new<n>`, `<floor_id>-O-new<n>`, `<building_id>-A-new<n>` | `core/edits.py:new_id` | tests `test_add_space_gets_new_id`, `test_add_opening_snaps_onto_shared_wall`, `test_add_asset_and_move_recomputes_space` |
| C6 | Openings snap onto the wall shared by their two spaces (within WALL_TOLERANCE_M buffer); no shared wall → EditError | `core/edits.py:snapped`, `wall_target` | tests `test_add_opening_*`, `test_move_opening_snaps` |
| C7 | Unknown ids / unknown op names raise EditError naming them | `core/edits.py:find`, `apply_op` | `test_unknown_id_raises` |
| C9 | `apply_steps` always returns a copy, also for `[]` and `[[]]` (verifier round 1 finding) | `core/edits.py:apply_steps` | `uv run pytest tests/test_edits.py -q -k without_ops` |
| C8 | No dataset file, benchmark scorer or existing core module changed; full suite green | — | `git diff --cached --stat`; `uv run pytest -q` → 320 passed, 1 skipped |

## Checks I ran
- `uv run pytest tests/test_edits.py -q` before implementation → collection error (module missing); after → `15 passed in 0.77s`; after round-1 fix → `16 passed`
- `uv run pytest -q` → `319 passed, 1 skipped in 56.78s`; after round-1 fix → `320 passed, 1 skipped in 58.58s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 30 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — Builder Edit mode bullet under "What works" (Task 1 done, next Task 2).
- [x] `memory-bank/log.md` — entry "2026-10-24 19:40 — Builder Edit mode: design, M1 plan, core edit ops".
- [x] decisions / open questions touched: none (design choices listed in the spec under "Calls made by Claude").
- [x] docs touched: new spec + plan; links in docs/README.md and docs/architecture/ai-agents.md.

## Known gaps / not done
- `move_vertex` and `set_polygon` (with neighbour fitting) are Task 2 — not in this commit although the spec table lists them.
- `delete_space` refuses spaces that are stops of a stair/lift (connectors are out of scope per the spec's non-goals) — a ruling, not in the spec text.
- No validator, drafts store, API or UI yet (Tasks 3–7).

## Verification rounds
- Round 1: FAIL — memory-bank not updated; `apply_steps([[]])` returned the base. Fixed by the implementer (test `test_apply_steps_returns_a_copy_even_without_ops` RED→GREEN, memory-bank entries added).
- Round 2: FAIL — plan had no front matter and no docs/README.md link. Fixed: front matter added, index bullet added, spec backlink added; check_links OK.

---

# Verification report (round 3)

VERDICT: PASS
TREE: 94fb40509944c1198f35fd0c4c327d66e0c14b8b

All claims C1–C9 MET. Standard checks: pytest 320 passed, 1 skipped (59.21s); check_links OK (30 files); no secrets;
score.py unchanged; no hard-coded test ids (train fixture proc-campus-train-000 only); "Checks I ran" re-run match;
no unstaged/untracked files. Undeclared changes: none significant; memory-bank and docs edits declared. Known gaps
declared: move_vertex/set_polygon deferred to Task 2; delete_space refuses stair/lift stops.
