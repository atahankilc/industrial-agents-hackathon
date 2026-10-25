# Plan import: Creator agent, private import drafts, /imports/stream, import screen

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** docs/superpowers/specs/2026-10-25-plan-import-design.md, docs/superpowers/plans/2026-10-25-plan-import.md (Tasks 8–12, part of 13), Q-018

## Summary
The Creator agent (Claude tool loop over the plan-import stages) turns uploaded floor plans into a building; the
backend streams its progress and opens the result as a draft on a private base `import/<id>`; the app gets a
"Create from floor plans" screen that hands over to the existing Edit mode. Plus fixes found in live runs (open
rooms, coarse-box gaps, invalid polygons, tool exceptions), HEIC support, retuned wall-mask thresholds, a dataset eval
and a live runner script.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Draft store supports private import bases: `create_import`, `import/<id>` not in the catalogue, validated without a base (errors stay errors), save keeps `source_ref.import` and `source: imported`; file, memory and Postgres backends (`insert_import`/`load_import`); migration file for `builder_imports` (NOT applied) | `backend/drafts.py`, `supabase/migrations/20261025180000_builder_imports.sql` | `uv run pytest tests/test_import_drafts.py tests/test_drafts.py tests/test_draft_backends.py -q` |
| C2 | Creator tools: 11 tools (list/view sources, register_plan, segment, coarse_rooms, add_rooms incl. cell 0 = outside, label_cells, set_scale, stack_floors, finish with one repair chance, no_plan); one plan per level; unexpected exceptions become error results | `agent/creator_tools.py`, `core/plan_import/cells.py` `carve` | `uv run pytest tests/test_creator_tools.py -q` → 12 passed |
| C3 | Creator loop: steps (say / tool / tool_done), ends on finish / no_plan, one nudge when it stops without a tool, image pruning to the last 6, no key → failed with a clear reason | `agent/creator.py` | `uv run pytest tests/test_creator.py -q` → 6 passed |
| C4 | `POST /imports/stream`: warnings per unreadable file, step lines, then done (draft_id, base, name, issues, notes) / no_plan / error; > 20 files or > 25 MB per file → 413 | `backend/app.py` `import_stream`, `make_creator` | `uv run pytest tests/test_imports_api.py -q` → 7 passed (incl. the > 25 MB case) |
| C5 | Frontend: "Create from floor plans" screen (drop / pick files, Creator lines streaming, warnings, no-plan / error states) → EditMode on the import base; entry buttons on the map landing and the search; `api.importPlans` | `frontend/app/src/import/*`, `api.ts`, `Root.tsx`, `map/MapLanding.tsx`, `search/*` | `cd frontend/app && npx tsc --noEmit -p .` → exit 0 (NOT yet checked in a browser) |
| C6 | HEIC (iPhone) photos are read via pillow-heif; videos (.mov) become warnings | `core/plan_import/ingest.py`, `pyproject.toml` | `uv run pytest tests/test_plan_import_ingest.py -q` → 5 passed |
| C7 | Fixes from live runs: coarse boxes grow 3 % so they touch; autofix repairs self-intersecting outlines; wall mask defaults dark 190 / contrast 50 (tuned on the dataset eval, not on demo files) | `core/plan_import/cells.py`, `assemble.py`, `prepare.py` | `uv run pytest tests/test_plan_import_cells.py tests/test_plan_import_assemble.py -q`; eval below |
| C8 | Eval script: `--segment-only` (no model) and `--full` (Creator) on a seeded sample of dataset floor renders | `scripts/eval_import.py` | `uv run python scripts/eval_import.py --segment-only --n 30` → last line "median count ratio 1.07 · within ±20 %: 16/30 · median mean-IoU 0.40 …" |
| C9 | Live runner prints the Creator's steps and token use, saves the building and the images shown to the model | `scripts/live_creator.py` | read; live runs listed below |
| C10 | Whole suite green | — | `uv run pytest -q` → 825 passed, 2 skipped |

## Checks I ran
- `uv run pytest -q` → `825 passed, 2 skipped, 15 warnings in 227.25s` (after adding the 25 MB test; 824 before)
- `cd frontend/app && npx tsc --noEmit -p .` → exit 0
- `uv run python scripts/eval_import.py --segment-only --n 30`: dark/contrast 150/70 → IoU 0.30, 11/30 within ±20 %; 190/50 → 0.40, 16/30; 210/40 → 0.38, 17/30 (kept 190/50)
- Live (real Claude, Opus 5.5 medium): resplan-439 floor 0 render → done in 23 s, 8/8 rooms, 0 errors; Residenz PDF → done in 174 s, 2 floors, 56 spaces, 63 openings, 3 connectors, 0 errors (coarse boxes, legend names); Urban Colab HEIC originals → first run crashed in `finish` (GEOSException) → fixed (C2, C7), re-run in progress

## Knowledge base updates
- [x] `memory-bank/project-state.md` — Plan import bullet: Tasks 8–12 built, live results, what is pending
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: docs/guides/commands.md endpoint table (`POST /imports/stream`); plan Task 4 box growth 1 % → 3 %; full docs with Task 14

## Verification rounds
- Round 1: FAIL — C2 test count said 13, actual 12 → fixed; added the 25 MB test and the commands.md row

## Known gaps / not done
- Import screen not yet checked in a browser (Task 12 step 2).
- Migration not applied to Supabase (needs Utku's go); the deployed app would 503 on imports until then.
- Segmentation is weak on Swiss / OSM renders (eval IoU ~0.1–0.3) and on the demo plans: the Creator falls back to coarse boxes (marked low_confidence) on the Urban Colab ground floor and on Residenz.
- `/imports/stream` runs one Creator per request (minutes); serverless timeouts on the deployed app are not handled.
- Round 2: FAIL — C10 suite count not updated after the added test (824 → 825) → fixed

---

## Verifier report (round 3)

VERDICT: PASS
TREE: dba6e4cd0118a9ef30a812901ae4bcde07678ffd
All claims C1–C10 MET (C5 typecheck only, C9 read only). Full suite 825 passed, 2 skipped (two runs); links OK (35 files); no secrets; score.py unchanged; no hard-coding; no unstaged files. Required fixes: none.
