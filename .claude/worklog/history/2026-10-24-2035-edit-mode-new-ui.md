# Edit mode re-homed in the new UI: BuildingScreen entry, PlanView preview, /drafts/{id}/plan

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 20:32
- **Related:** merge of origin/dev (ebcdb3d, Atahan's new UI); spec §5; M2 plan Task 5 updated

## Summary
After merging Atahan's new UI (Root → BuildingSearch / BuildingScreen, PlanView), the Edit mode was still wired into
the no-longer-rendered `App.tsx` and its 3D inset used the removed point-cloud scene. This moves the entry into
`BuildingScreen`, makes the preview Atahan's `PlanView` of the draft (new `GET /drafts/{id}/plan`), and fixes a
draft-resume race found while verifying.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `GET /drafts/{id}/plan` returns `export_plan` of the draft, centred on the base building's footprint (stable across edits); 404 for unknown drafts | `backend/drafts.py:DraftStore.plan`, `backend/app.py:draft_plan` | `uv run pytest tests/test_drafts.py -q -k plan_endpoint` (failed before: 404 route missing) |
| C2 | BuildingScreen has an "Edit this building" button (lucide PencilRuler) in the map controls; editing renders `EditMode` full screen inside `main.screen` | `frontend/app/src/building/BuildingScreen.tsx` | read |
| C3 | EditMode's 3D inset is `PlanView` (plan from `api.draftPlan`, current floor, spread, pins/hover off); a **Done** button returns to the building screen | `frontend/app/src/edit/EditMode.tsx`, `api.ts:draftPlan` | read |
| C4 | Save → `Root.open(user/<slug>)` (new prop `onOpen`), and the new screen shows a one-time note from `sessionStorage` | `BuildingScreen.tsx` (`noteKey`), `Root.tsx` | read |
| C5 | `App.tsx` and `scene/Scene.tsx` are byte-identical to origin/dev again | — | `git diff origin/dev -- frontend/app/src/App.tsx frontend/app/src/scene/Scene.tsx` → empty |
| C6 | Editor CSS no longer collides with dev's globals: `.plan` → `.plan-editor`, `.primary` → `.edit-primary`; layout moved up (no header in Edit mode) | `edit.css`, `PlanEditor.tsx`, `EditMode.tsx` | read |
| C7 | Opening a draft is deduped per base (`openDraft`), so StrictMode's double effect no longer creates two drafts and resumes the wrong one | `EditMode.tsx:openDraft` | read; browser check below |
| C8 | Docs: commands.md Edit-mode paragraph + `/drafts/{id}/plan` row; ai-agents.md Builder status; M2 plan Task 5 updated for the new UI; memory bank updated | docs, memory-bank | read; check_links OK |
| C9 | Suite and build green | — | `uv run pytest -q` → 686 passed, 1 skipped; `npm run build` ok |

## Checks I ran
- `-k plan_endpoint` before implementation → 1 failed; after → `tests/test_drafts.py` 14 passed
- headless Chrome (backend :8775 restarted, Vite :5191 restarted after `npm ci`), drive4: building screen → Edit → plan + PlanView inset rendered → corner drag → "1 change" → Done → Edit again → first run "0 changes" (bug: two drafts) → after `openDraft` fix "1 change" → Save "Forschungsbau v2" → URL `?building=user%2Fforschungsbau-v2-2` (the name was taken by the earlier run), title "Forschungsbau v2", note shown; `errors: []`; screenshots inspected (strip buttons fixed after the `.primary` rename)
- `uv run pytest -q` → `686 passed, 1 skipped in 90.94s`
- `npm run build` → `✓ built in 661ms`; oxlint on edit/building/Root → only the known `set-state-in-effect` in EditMode
- `python3 scripts/check_links.py` → `OK: all links resolve in 31 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — stale "Next: merge origin/dev" replaced (merged, re-homed, next M2).
- [x] `memory-bank/log.md` — entry "2026-10-24 20:32 — Edit mode re-homed in the new UI".
- [x] decisions / open questions touched: none.
- [x] docs touched: commands.md, ai-agents.md, M2 plan (Task 5).

## Known gaps / not done
- The Edit-mode panels still use the old monochrome tokens (`--panel`, `--ink`, …), not the screen's (`--surface`, `--ground`); visually acceptable, restyle with M2's chat.
- The one-time "Saved …" note renders in the Conversation's `note` style, which dev uses for errors (red text).
- `/drafts/{id}/points` is kept but unused by the new UI.
- Phone layout of the Edit mode not checked.

---

# Verification report (round 1)

VERDICT: PASS
TREE: 5c6b031d16fcc5d3c97bb7c66bfe010f4c65a6a7

C1–C9 MET (plan_endpoint passes; App.tsx/Scene.tsx identical to origin/dev; pytest 686 passed, 1 skipped; build ok;
links OK; oxlint only the known warning). Undeclared, trivial: app.py docstring lists "plan"; `.mode-switch` CSS now
unused; log.md says user/forschungsbau-v2 while the run produced user/forschungsbau-v2-2.
