# Creator: stable door numbers, a definition of a floor plan, live results

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** docs/superpowers/plans/2026-10-25-plan-import.md (Tasks 13–14), docs/architecture/ai-agents.md

## Summary
Door candidates keep the number they were drawn with, so "d<n>" still means the same door after cells are merged
(before, merges dropped self-doors and shifted the numbers: 49 doors landed between rooms 3–28 m apart on the Urban
Colab run). The Creator's prompt now says what a floor plan is and forbids made-up rooms (it had filled a landscape plan
with "blocks"). Live results recorded in the docs.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `DoorCandidate.number` is set once per segmentation (1..n), drawn as "d<number>" and resolved by number in `apply_labels`; a merged-away door gives a problem naming it | `core/plan_import/model.py`, `cells.py` `from_labels` / `render_cells`, `labels.py` `apply_labels` | `uv run pytest tests/test_plan_import_labels.py -q` → 9 passed (incl. `test_door_numbers_stay_the_ones_the_model_saw_after_a_merge`) |
| C2 | Prompt step 1 defines a floor plan (rooms divided by walls, names / numbers, doors, stairs), excludes site / landscape plans, maps and unreadable outlines, and forbids made-up rooms | `agent/creator.py` `INSTRUCTIONS` | read |
| C3 | Docs and memory bank carry the live results (eval 0.97 / 0.91 / 89 % / ≈ $1.09; Urban Colab 104 spaces, 23 errors, ≈ $1.73; Rathaus; Projektsteckbrief no_plan) | `docs/architecture/ai-agents.md`, `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` → OK |
| C4 | Whole suite green | — | `uv run pytest -q` → 831 passed, 2 skipped |

## Checks I ran
- `uv run pytest -q` → `831 passed, 2 skipped, 15 warnings in 245.77s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- Live (not reproducible without API credits, numbers from `scripts/live_creator.py` / `scripts/eval_import.py` output):
  eval `--full --n 8` → "median count ratio 0.97 · median mean-IoU 0.91 · median doors found 89% · runs with 0 errors 6/8
  · finished 8/8", tokens out 32,383 / cache read 428,120 / cache write 71,099; Urban Colab → "done in 766s · 40 requests ·
  cache read 2200793, write 160612 · out 24732", 5 floors, 104 spaces, 23 errors; Rathaus → 59 spaces, 0 errors, 139 s;
  Projektsteckbrief → "no_plan in 10s · 3 requests" (after the prompt change, saved in `.superpowers/runs/live_projekt_after.log`;
  before it, 14 made-up spaces in `live_projekt.log`). The "before" Urban Colab figures (49 off-wall doors, 69 errors)
  come from the previous run, whose log was overwritten by the re-run — marked UNVERIFIED in log.md.

## Knowledge base updates
- [x] `memory-bank/project-state.md` — plan import bullet rewritten to the current state (measured results, next steps incl. Task 14 leftovers)
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: ai-agents.md Creator section (measured results)

## Known gaps / not done
- The Urban Colab draft still has 23 errors (Builder fixes them in Edit mode).
- origin/dev (new UI) not merged into this branch yet — next step.
- Rest of plan Task 14 open: cross-floor Guide route on the saved Urban Colab building, end-to-end app run (upload →
  Builder fix → Save → 3D + route), Q-018 note, spec status → built.

## Verification rounds
- Round 1: FAIL — project-state contradicted itself, Task 14 leftovers dropped, Projektsteckbrief result had no saved log → fixed (bullet rewritten, re-run saved)

---

## Verifier report (round 2)

VERDICT: PASS
TREE: 4a630cc8c4cb0dde4b3cbb2f9b91a277f21009d8
C1–C4 MET; live figures match .superpowers/runs/*.log (unsaved before-figures marked UNVERIFIED). Suite 831 passed, 2 skipped; links OK; no secrets; score.py unchanged.
