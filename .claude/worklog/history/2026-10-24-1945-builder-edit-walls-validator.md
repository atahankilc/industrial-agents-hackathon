# Builder Edit mode M1 Tasks 2–3: wall moves keep shared walls; validator calibrated on the dataset

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 19:40
- **Related:** docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §1–2; plan docs/superpowers/plans/2026-10-24-builder-edit-mode-m1.md Tasks 2–3

## Summary
`move_vertex` and `set_polygon` ops that keep shared walls shared (overlapped neighbours shrink, refused if one
would vanish, displaced doors re-projected), thickness-aware door snapping, and `core/validate.py` — a validator
that reports issues and treats issues the base building already has as warnings.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `move_vertex(floor_id, from_xy, to_xy)` moves the corner (within 0.01 m) in every space on the floor that has it | `core/edits.py:move_vertex` | `uv run pytest tests/test_edits.py -q -k shared_corner` |
| C2 | `set_polygon` / `move_vertex` shrink overlapped neighbours via `difference`; neighbour area drops by exactly the taken strip | `core/edits.py:settle` | `-k widen_room_shrinks_neighbour` |
| C3 | A change that would remove a neighbour (empty, split, or < 0.5 m²) raises EditError and leaves the input unchanged | `core/edits.py:settle` | `-k erase_neighbour` |
| C4 | Doors that were on their wall before a change are re-projected onto the new shared wall | `core/edits.py:settle` | `-k doors_follow_moved_wall` |
| C5 | Invalid (self-intersecting) outlines raise EditError | `core/edits.py:checked_outline` | `-k self_intersecting` |
| C6 | Door snapping tolerates thick walls: buffer = WALL_TOLERANCE_M + gap between the two spaces (gap ≤ 2.5 m) | `core/edits.py:wall_target` | `-k thick_wall` (Swiss train building) |
| C7 | `validate(building, base=None)` returns `{severity, code, message, ids}` issues, errors first; codes polygon_invalid, duplicate_id, dangling_ref, overlap, opening_off_wall, asset_outside, unreachable, no_entrance (warning) | `core/validate.py` | `uv run pytest tests/test_validate.py -q` → 332 passed |
| C8 | Issues the base already has (same code + ids) are downgraded to warnings; every one of the 280 dataset buildings validated against itself has 0 errors; the first 40 procedural buildings have 0 errors without a base | `core/validate.py:validate` | `tests/test_validate.py::test_dataset_has_no_errors_against_itself`, `test_procedural_buildings_are_clean_without_base` |
| C9 | Calibration script prints per-source counts; docstring numbers match its output (osm overlap 281 / off-wall 61, resplan 13 / 1, swiss 38 / 46) | `scripts/validate_dataset.py`, `core/validate.py` docstring | `uv run python scripts/validate_dataset.py` |
| C10 | No dataset, benchmark or existing core module changed; full suite green | — | `git diff --cached --stat`; `uv run pytest -q` → 658 passed, 1 skipped |

## Checks I ran
- `uv run pytest tests/test_edits.py -q`: new tests first → 5 failed, 17 passed (unknown op / snapping error); after implementation 2 test-helper bugs fixed (unrounded target; wall length measured through the 0.35 m band) → `22 passed`
- `uv run pytest tests/test_validate.py -q`: before → collection error (module missing); after → 1 failed (test shifted the room out of the building; test fixed to draw it on top of another room) → `332 passed in 18.66s`
- `uv run python scripts/validate_dataset.py` → 280 buildings; osm_indoor opening_off_wall 61, overlap 281; resplan 1, 13; swiss_dwellings 46, 38
- `uv run pytest -q` → `658 passed, 1 skipped in 83.50s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 30 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — Builder Edit mode bullet: Tasks 2–3 done, next Task 4.
- [x] `memory-bank/log.md` — entry "2026-10-24 19:40 — Builder Edit mode M1 Tasks 2–3: wall moves, validator".
- [x] decisions / open questions touched: none.
- [x] docs touched: none besides memory bank (validator calibration lives in the module docstring).

## Known gaps / not done
- The plan's `test_dataset_has_no_errors` was changed to "against itself" + procedural-only-without-base, because real OSM/Swiss/ResPlan data has overlaps and off-wall doors (ruling recorded in the plan ledger).
- Spec §1 says mid-edge neighbours get "a matching point inserted"; implemented as `neighbour.difference(changed)`, which gives the same outline.
- Drafts store, API and UI: Tasks 4–7.

---

# Verification report (round 1)

VERDICT: PASS
TREE: 73a57ad806f90c76f719d57eec05b87d2416f60a

Claims C1–C10 MET (test_edits subsets 1 passed each, thick_wall ran not skipped; test_validate 332 passed;
calibration counts match docstring; full suite 658 passed, 1 skipped). Links OK (30 files). No secrets (only
"envelope" false positive). score.py unchanged. No hard-coded test ids. Checks re-run match. No undeclared changes.
Memory bank consistent; known gaps accurate.
