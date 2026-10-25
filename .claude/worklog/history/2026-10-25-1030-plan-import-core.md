# Plan import (Creator) — design, plan and deterministic core (stages 0–6)

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** Q-018 (Level 4), docs/superpowers/specs/2026-10-25-plan-import-design.md, docs/superpowers/plans/2026-10-25-plan-import.md

## Summary
Adds the approved design and implementation plan for Builder project 2 (create a building from floor-plan PDFs /
images), and the deterministic core `core/plan_import/` that the Creator agent will drive: ingest, rectify / crop /
wall mask, cell segmentation (walls, colours, boxes), labels, scale, stacking + connectors, building.json assembly
with auto-fixes and validation. Tasks 1–7 of the plan; agent, backend and UI come in later commits.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Design + plan docs exist, have front matter and are linked from docs/README.md | `docs/superpowers/specs/2026-10-25-plan-import-design.md`, `docs/superpowers/plans/2026-10-25-plan-import.md`, `docs/README.md` | read; `python3 scripts/check_links.py` → OK |
| C2 | New deps added: numpy, opencv-python-headless, pypdfium2, pypdf, pillow, python-multipart (no PyMuPDF, D-009) | `pyproject.toml`, `uv.lock` | read the dependency list |
| C3 | Ingest: PDFs → one source per page (+ large embedded images), images EXIF-rotated and ≤ 2400 px, unreadable files become warnings | `core/plan_import/ingest.py` `load_sources`, `contact_sheet`, `grid_view`, `png` | `uv run pytest tests/test_plan_import_ingest.py -q` → 4 passed |
| C4 | Prepare: photographed sheets are flattened (auto quad or model corners), crop maps a source bbox through the homography, wall mask = locally dark + unsaturated, small blobs (text) removed | `core/plan_import/prepare.py` | `uv run pytest tests/test_plan_import_prepare.py -q` → 5 passed |
| C5 | Cells: walls path (door gaps closed at 6 × wall thickness, fat fills given back, outside = outside the footprint, cells grown to wall centre, door candidates), colours path (separator mask), coarse boxes; render with numbers | `core/plan_import/cells.py` | `uv run pytest tests/test_plan_import_cells.py -q` → 6 passed |
| C6 | Labels: merge / outside / room labels checked against closed type lists, doors as "d<n>" or [a, b] with adjacency check, entrances (candidate or longest free outline), cumulative calls, problems returned | `core/plan_import/labels.py` | `uv run pytest tests/test_plan_import_labels.py -q` → 8 passed |
| C7 | Scale (bar, doors, same sheet, prior), stacking (ECC on footprints, centred fallback, metres y up), stair / lift connectors across consecutive floors | `core/plan_import/scale.py`, `core/plan_import/stack.py` | `uv run pytest tests/test_plan_import_stack.py -q` → 7 passed |
| C8 | Assembly → dataset schema (ids `<id>-F<level>-S###`, `-O####`, `-V##`, assets []), import notes in `source_ref.import`, autofix (slivers, small overlaps, doors snapped), `check` = validate without base; two floors without stairs report `unreachable` | `core/plan_import/assemble.py` | `uv run pytest tests/test_plan_import_assemble.py -q` → 5 passed |
| C9 | Whole suite still green | — | `uv run pytest -q` → 788 passed, 2 skipped |
| C10 | Log entry added | `memory-bank/log.md` | read the 2026-10-25 "Plan import" entry |

## Checks I ran
- `uv run pytest -q` → `788 passed, 2 skipped, 15 warnings in 230.35s`
- per-file runs as in the claims table (all passed)
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- visual check (not automated) of cells on one Urban Colab photo and Residenz p1 (rendered PNGs in the session scratchpad)

## Knowledge base updates
- [x] `memory-bank/project-state.md` — "What works": Plan import / Creator in progress (Tasks 1–7 done, deps, pending tasks); "Last updated" line bumped
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none (Q-018 note comes with Task 14)
- [x] docs touched: new spec + plan, docs/README.md links; backlinks in docs/architecture/ai-agents.md (Builder row + "project 2" line) and the Edit-mode design (project 2 line + `related:`)

## Verification rounds
- Round 1: FAIL — project-state not updated, backlinks missing → fixed by the implementer

## Known gaps / not done
- No agent, backend endpoint, draft-store change or UI yet (plan Tasks 8–14).
- Thresholds tuned only by eye on two demo pages; dataset eval (Task 13) still to come.
- Residenz still has merged regions after both segmentation paths; a box-carving tool is planned for the Creator.
- `building_plans/` (demo inputs) deliberately not committed.

---

## Verifier report (round 2)

VERDICT: PASS
TREE: fc53c7147dd060d2ec35fe22a49aeb96771b09ad
All claims C1–C10 MET. Full suite 788 passed, 2 skipped; links OK (35 files); no secrets; score.py unchanged; no hard-coding. Required fixes: none.
