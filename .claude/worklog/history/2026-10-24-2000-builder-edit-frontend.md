# Builder Edit mode M1 Tasks 5–7: frontend Edit mode (2D plan editor, 3D inset, undo, save → Guide)

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 19:58
- **Related:** docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §5; plan Tasks 5–7

## Summary
The app gets a View / Edit switch. Edit mode opens (or resumes) a draft copy of the current building and shows a 2D
plan of one floor where corners, doors and assets can be dragged, a live 3D preview, the validator's issues, undo,
and Save, which writes `user/<slug>` and switches the session (and the Guide) to the edited building.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `api.ts` has typed draft calls: createDraft, draft, draftPoints, applyOps, undo, saveDraft, and types BuildingJson, Issue, DraftState, Op | `frontend/app/src/api.ts` | read |
| C2 | Header has a View / Edit switch; Edit renders `EditMode` instead of the 3D scene, floor rail, status and chat | `frontend/app/src/App.tsx` | read |
| C3 | EditMode resumes the draft id stored in `localStorage["draft:<base>"]` or creates one; strip shows "Copy of <name> · N changes · Undo · Save"; ⌘/Ctrl-Z undoes; errors from the API are shown in the strip | `frontend/app/src/edit/EditMode.tsx` | read |
| C4 | PlanEditor: SVG of one floor (y flipped), spaces/labels/assets/doors; click selects; drag selected room's corner → `move_vertex` (snap to vertices within 0.25 m else 0.05 m grid) with live preview of every room sharing the corner + coordinate/area readout; drag door → `move_opening` projected on its wall; drag asset → `move_asset`; R / Shift+R rotates ±15°; wheel zoom, drag pans; error-issue ids outlined red | `frontend/app/src/edit/PlanEditor.tsx`, `geometry.ts`, `edit.css` | read |
| C5 | 3D inset reuses `Scene` with a new optional `inset` prop that drops the chat-panel principal-point shift | `frontend/app/src/scene/Scene.tsx` | read diff |
| C6 | Issues list (errors then warnings, max 30); clicking one switches floor and selects the element | `EditMode.tsx:focusIssue` | read |
| C7 | Save dialog (default name "<name> (edited)", "Save anyway" when errors exist) → saveDraft → clears the localStorage draft → reload building list → switch to View on the new building; first chat line is a note that the conversation restarted | `EditMode.tsx:save`, `App.tsx:onSaved`, `reset` | read |
| C8 | Type-check + bundle clean | — | `cd frontend/app && npm ci && npm run build` → built, no TS errors |
| C9 | Verified in headless Chrome (playwright-core, Chrome channel) against backend :8775 + Vite :5191, offline Guide: Edit shows plan + inset, "No problems"; corner drag → 1 change and the shared corner moved in two rooms, validator listed 2 assets now outside Office 0.02; door slide → 2; asset drag → 3; R → 4; 4× ⌘Z → 0 changes; save "Forschungsbau edited" → View on `user/forschungsbau-edited` with the restart note; Guide "from Main lobby to Meeting room 3.07" → route line 99 m; no console errors | scratch driver scripts (not committed, under gitignored `.superpowers/scratch/pw/`) | not re-runnable by the verifier without Chrome; read log.md entry |
| C10 | Docs: Builder section in ai-agents.md marks M1 implemented; commands.md documents Edit mode; memory bank updated | `docs/architecture/ai-agents.md`, `docs/guides/commands.md`, `memory-bank/*` | read; check_links OK |
| C11 | Backend suite unchanged and green | — | `uv run pytest -q` → 670 passed, 1 skipped |

## Checks I ran
- `npm run build` → `✓ built in 487ms` (only the existing >500 kB chunk warning)
- `npx oxlint src` → warnings only; new one: `EditMode.tsx:39 set-state-in-effect` (resetting state when the base building changes); the rest are pre-existing in BuildingCloud.tsx
- headless Chrome runs (drive1/2/3.mjs): outputs as in C9, `errors: []` each time; screenshots inspected (plan, inset, red outlines, route after save)
- `uv run pytest -q` → `670 passed, 1 skipped in 80.81s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 30 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — Tasks 5–7 done, M1 done, next: branch review, milestone 2 plan.
- [x] `memory-bank/log.md` — entry "2026-10-24 19:58 — Builder Edit mode M1 Tasks 5–7".
- [x] decisions / open questions touched: none.
- [x] docs touched: ai-agents.md (Builder status), commands.md (Edit mode usage).

## Known gaps / not done
- Tasks 5, 6 and 7 shipped as one commit (no frontend test runner; one browser verification covers all three) — ruling in the plan ledger.
- No automated frontend tests; browser verification was manual-scripted and is not in the repo.
- Chat panel is hidden in Edit mode: prompt edits come with milestone 2 (Builder agent).
- EditMode has its own floor rail (same CSS) instead of App's.
- The deployed app can't write drafts (read-only filesystem) until milestone 3.
- Touch/phone layout only lightly adjusted (media query), not checked on a device.

---

# Verification report (round 1)

VERDICT: PASS
TREE: bac82cbfc70f0e2439b0ae080ae4a9c6897ab4fd

Claims C1–C8, C10, C11 MET; C9 MET (log only — scratch browser scripts not committed). npm run build clean;
pytest 670 passed, 1 skipped; links OK; no secrets; score.py unchanged; no hard-coding. Wording note: the other
oxlint warnings are spread over TurnIcon.tsx, Scene.tsx, useVoice.ts, RouteFlow.tsx and BuildingCloud.tsx (all
pre-existing), not only BuildingCloud.tsx. Undeclared: useTheme `mode` renamed to `themeMode` in App.tsx (trivial).
