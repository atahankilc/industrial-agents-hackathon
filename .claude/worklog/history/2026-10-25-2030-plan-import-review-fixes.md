# Plan import: final review fixes (admin-only imports, no silent merges, bar scales kept, cancel on leave, PDF limits)

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** final whole-branch review (opus, "With fixes"); plan Task 14; Q-018

## Summary
Fixes the Critical and Important findings of the final review, each with a test written first, and closes the plan:
spec status built, Q-018 note, project-state and log updated.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Access mode: `/imports` (with or without `/api`) is admin-only like `/drafts` (anonymous / non-admin 403, bad token 401) | `backend/app.py` `drafts_admin_only` | `uv run pytest tests/test_access.py -q -k imports` |
| C2 | Frontend: `importPlans` sends the bearer token (no JSON content-type on the multipart body), takes an AbortSignal, throws when the stream ends without done / no_plan / error; ImportScreen aborts on unmount; import buttons hidden when `access.mode && !access.admin` | `frontend/app/src/api.ts`, `import/ImportScreen.tsx`, `map/MapLanding.tsx`, `search/BuildingSearch.tsx` | `cd frontend/app && npx tsc -b --noEmit` → exit 0; read |
| C3 | Closing the stream cancels the Creator (shared Event; checked before each model request; no draft is made after a cancel); `CreatorResult.status` can be "cancelled" | `backend/app.py` `import_stream`, `agent/creator.py` | `uv run pytest tests/test_creator.py tests/test_imports_api.py -q -k cancel` → 2 passed |
| C4 | Merging two cells that are not adjacent is refused with a problem (no cell lost) | `core/plan_import/labels.py` `merge` | `uv run pytest tests/test_plan_import_labels.py -q -k touch` |
| C5 | Alignment never rescales a `bar` scale; a scale it corrects is noted `<method>+aligned` (once) | `core/plan_import/stack.py` `align` | `uv run pytest tests/test_plan_import_stack.py -q` → 12 passed |
| C6 | PDF pages render straight at ≤ PROCESS_MAX_SIDE; ≤ 40 sources per import (rendering stops there, the rest named in a warning); an embedded image with its page's aspect ratio (a scan) is not added again | `core/plan_import/ingest.py` | `uv run pytest tests/test_plan_import_ingest.py -q` → 8 passed |
| C7 | Docs / memory bank: commands.md endpoint row (limits, admin-only, cancel), spec status built, Q-018 "built anyway" note, project-state "plan done", log entry with deferred minors | `docs/guides/commands.md`, `docs/superpowers/specs/2026-10-25-plan-import-design.md`, `memory-bank/*` | read; `python3 scripts/check_links.py` → OK |
| C8 | Whole suite green, frontend typechecks | — | `uv run pytest -q` → 958 passed, 2 skipped; `npx tsc -b --noEmit` → exit 0 |

## Checks I ran
- `uv run pytest -q` → `958 passed, 2 skipped, 18 warnings in 241.88s`
- `cd frontend/app && npx tsc -b --noEmit` → exit 0
- `python3 scripts/check_links.py` → `OK: all links resolve in 37 files`
- RED first for each fix: imports admin test (200 ≠ 403), Creator cancel (no attribute `cancel`), stream cancel (Event never set), non-adjacent merge (no problem), bar scale (rescaled), aligned note (missing), PDF tests (huge page → 2 sources, 45 pages → 45, scan → p + img duplicates)
- Demo files re-ingested after the PDF change: Residenz 2 pages, Projektsteckbrief 5 pages + 2 landscape images, Rathaus 1, Urban Colab 11 + 11 .mov warnings (as before)
- End-to-end via the running backend (real Claude, documented in the log): Builder proposed a door on the Urban Colab draft, apply → 23→22 issues, Save → `user/munich-urban-colab`, route F0 → F4 104 m

## Knowledge base updates
- [x] `memory-bank/project-state.md` — plan done; next = merge to dev + migration
- [x] `memory-bank/log.md` entry (fixes + deferred minors)
- [x] decisions / open questions touched: Q-018 note (stays open)
- [x] docs touched: commands.md, spec status

## Known gaps / not done
- Deferred minors (log): no reachability check without an entrance; carved / coarse rooms not marked per space; imports never cleaned up; photos decoded at full size first; `%PDF-` only at byte 0; door scale not recomputed after door changes.
- The UI "ended early" path has no automated test (no frontend unit-test harness in the repo); typechecked only.
- Merge to dev and the Supabase migration come after this commit.

---

## Verifier report (round 1)

VERDICT: PASS
TREE: 77f1287cfe1eb1b449cf0a2790ffc72d819fa92b
C1–C8 MET. Suite 958 passed, 2 skipped; tsc -b exit 0; links OK; no secrets; score.py unchanged. Note: pdf_parts still opens a PDF when the 40-source budget is used up (wasted work, within the listed minor).
