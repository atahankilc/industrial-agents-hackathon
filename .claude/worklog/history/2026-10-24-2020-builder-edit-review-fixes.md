# Builder Edit mode M1: final-review fixes (shared walls, concurrency) + milestone-2 plan

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 20:17
- **Related:** final whole-branch review of M1 (opus); spec call #12; docs/superpowers/plans/2026-10-24-builder-edit-mode-m2.md

## Summary
Fixes the three Important findings of the M1 review — an overlap left when a corner shared by two rooms moves into
a corridor, holes when a room shrinks (neighbours never grew), and lost changes under overlapping requests — and adds
the milestone-2 plan (prompt edits by a Builder agent).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `settle` fits every neighbour against every changed outline (fitted neighbours are no longer skipped) | `core/edits.py:settle` | `uv run pytest tests/test_edits.py -q -k shared_corner_into_corridor` (failed before: overlap Corridor 0.01 / Office 0.03) |
| C2 | The area changed rooms give up goes to the neighbour it borders most (unioned), so moving a corner away from a corridor leaves no hole; bordering nobody it stays outside | `core/edits.py:settle` | `-k corner_moved_away_from_corridor` (failed before: 4.85 m² lost) |
| C3 | A neighbour that would split gets "would split", one that would vanish "would remove" | `core/edits.py:settle` | read |
| C4 | `DraftStore.apply`, `undo` and `state` hold a per-draft lock, so overlapping requests each build on the latest state | `backend/drafts.py:draft_lock` | `uv run pytest tests/test_drafts.py -q -k concurrent` (failed before: 10 of 80 assets in the building) |
| C5 | The Edit UI sends no new edit (drag, R, undo) while one is in flight and keeps the dropped preview until the response (revision counter) | `frontend/app/src/edit/PlanEditor.tsx` (`busy`, `revision`, `sent`), `EditMode.tsx` | read; `cd frontend/app && npm run build` clean |
| C6 | Spec call #12 records how it is implemented | `docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md` | read |
| C7 | M2 plan exists with front matter, 5 tasks, linked from docs/README.md and the spec; spec op table gains `move_edge` (marked milestone 2) | `docs/superpowers/plans/2026-10-24-builder-edit-mode-m2.md`, spec, `docs/README.md` | read; check_links OK |
| C8 | Full suite green | — | `uv run pytest -q` → 673 passed, 1 skipped |

## Checks I ran
- new tests first: `-k corridor` → 2 failed (overlap 2.0 m²; 4.85 m² lost); concurrency test → failed `assert 10 == 80` (after making the ops accumulate and forcing thread switches); after fixes all pass
- `uv run pytest -q` → `673 passed, 1 skipped in 95.22s`
- `npm run build` → `✓ built in 578ms`; `npx oxlint src/edit` → only the known set-state-in-effect warning
- headless Chrome re-run (backend restarted): corner, door, asset, R, 4× ⌘Z → 1,2,3,4,0 changes, no console errors
- `python3 scripts/check_links.py` → `OK: all links resolve in 31 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — fixes, M2 plan, next: merge origin/dev.
- [x] `memory-bank/log.md` — entry "2026-10-24 20:17 — Builder Edit mode M1 final review fixes; M2 plan; dev merge analysis".
- [x] decisions / open questions touched: none.
- [x] docs touched: spec (call #12 note, move_edge row, plan links), docs/README.md (M2 plan link), new M2 plan.

## Known gaps / not done
- Review minors deferred: malformed op arguments → 500 (to handle in M2 when the agent sends ops), cache keeps one copy per op, base issues recomputed per request, sliver check for shared-corner rooms, `DRAFT_ID.match` vs `fullmatch`, a malformed saved building stops DraftStore init.
- M2 plan Task 5 (frontend) will be revised after merging origin/dev (new UI structure).

---

# Verification report (round 1)

VERDICT: PASS
TREE: ce247c9b2776137b7a96a366c46856e0f58eeb63

Claims C1–C8 MET (targeted tests pass; pytest 673 passed, 1 skipped; build clean; oxlint only the known warning;
links OK). No secrets, score.py unchanged, no hard-coding; headless Chrome run not reproducible, not used as evidence.
Note (not blocking): in `settle`, a vacated part whose union with the bordering room is not a single Polygon is
skipped silently and can still leave a hole.
