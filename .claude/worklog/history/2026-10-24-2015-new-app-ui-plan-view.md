# New app UI: building search, vector plan view, floor plan export

- **Author:** Claude session (with Atahan) · **Date:** 2026-10-24 19:00
- **Related:** D-011 (React app), Q-015 (visual direction), PRODUCT.md, .impeccable/surfaces/frontend-app.md

## Summary
Replaces the point-cloud scene in the app with a new "Drawing Set" UI: building search landing, a building screen
over an orthographic vector plan (rooms, walls with door gaps, doors, furniture), floating Guide conversation. Backend
gets `GET /sessions/{id}/plan` from the new `core/floorplan.py`. Old scene code and the pointcloud prototype leave the
repo (kept locally in gitignored `.viz-archive/`). Some pieces lost from the tree around the fast-forward to
`508a1ba` were rebuilt before committing (MapView.plan, Scene placeholder, lucide-react dependency).

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `export_plan(building_map, center)` returns floors, spaces (polygon, label point), walls per floor with door gaps cut, openings with swing side, connectors, assets in drawn spaces, closed ids | `core/floorplan.py` | read; `uv run pytest tests/test_backend.py -k plan_export` |
| C2 | `GET /sessions/{id}/plan` serves it, 404 for unknown session; `MapView.plan` caches it with the point-cloud export's `center` and drops the cache when the building object changes | `backend/app.py:plan`, `backend/sessions.py:MapView.plan/refresh` | `test_plan_export` (asserts plan center == points center) |
| C3 | Frontend: `main.tsx` renders `Root`; `Root.tsx` switches search ↔ `BuildingScreen` via `?building=`; `api.plan` + `Plan*` types match the export | `frontend/app/src/{main,Root}.tsx`, `api.ts`, `building/`, `plan/`, `search/` | read; `npm run build` |
| C4 | Old scene removed: `scene/BuildingCloud.tsx`, `RouteFlow.tsx`, `shaders.ts` deleted; `scene/BuildingCloud.ts` keeps only `SpaceSets` + `cloudExtent`; `scene/Scene.tsx` is a placeholder with the same props so unused `App.tsx` compiles | `frontend/app/src/scene/` | read; `npm run build` |
| C5 | `frontend/prototypes/pointcloud/` removed from the repo | git diff | `git diff --cached --stat` |
| C6 | `lucide-react` (ISC) added as dependency | `frontend/app/package.json`, lockfile | read |
| C7 | `.gitignore` ignores `.notes/`, `node_modules/`, `dist/`, `.viz-archive/` | `.gitignore` | read |
| C8 | Product brief + design contract added | `PRODUCT.md`, `.impeccable/surfaces/frontend-app.md` | read |
| C10 | Stale docs updated for the removed prototype/scene: CLAUDE.md tree line, docs/README.md entry, project-state "What exists" bullet, visualization.md (front matter, new "Current: vector plan view" section, point-cloud part marked superseded) | `CLAUDE.md`, `docs/README.md`, `memory-bank/project-state.md`, `docs/product/visualization.md` | read; `python3 scripts/check_links.py` |
| C9 | Memory bank: log entries for the UI work + this commit; project-state gets a frontend handoff paragraph; broken log anchor to a lost visualization.md section replaced by a plain file link | `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` |

## Checks I ran

Round 2 (after verifier FAIL round 1), on a checkout of the **staged index** (`git checkout-index -a` into scratchpad, node_modules symlinked):
- `uv run pytest -q --deselect tests/test_deploy.py::test_bundle_keeps_what_the_backend_reads_and_drops_the_rest -k "not commit_hook"` → `305 passed, 1 skipped, 11 deselected` (the deselected tests need a git repo; the staged checkout is not one — they pass in the real repo: full run there `316 passed, 1 skipped`)
- `npm run build` → `✓ built in 339ms`
- `npx oxlint src` → warnings only: TurnIcon.tsx:18,34 + pins.tsx:20 (only-export-components), useVoice.ts:250 + PlanView.tsx:591,699 (immutability)
- `python3 scripts/check_links.py` → `OK: all links resolve in 28 files`

Round 1 (working tree):

- `uv run pytest -q` → `316 passed, 1 skipped in 31.78s` (before the rebuild: `1 failed` — `MapView` has no `plan`)
- `cd frontend/app && npm run build` → `✓ built in 782ms` (only the >500 kB chunk warning)
- `npx oxlint src` → 0 errors, warnings only (pins.tsx only-export-components, PlanView.tsx immutability ×2)
- `python3 scripts/check_links.py` → `OK: all links resolve in 28 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (frontend handoff paragraph)
- [x] `memory-bank/log.md` entries added
- [ ] decisions / open questions touched: none (Q-015 not closed here)
- [x] docs touched: CLAUDE.md, docs/README.md, docs/product/visualization.md (C10)

## Known gaps / not done
- **Excluded on purpose (Atahan's call):** another window is live-editing the plan view (`wall_solids` in `core/floorplan.py`, `frontend/app/src/{api.ts,plan/geometry.ts,plan/PlanView.tsx}`, `tests/test_floorplan.py`, a log entry "Plan view: solid walls at their real thickness"). The staged `core/floorplan.py` is the version without `wall_solids` (written to the index only); those working-tree edits stay unstaged for that window's own commit, so `MM`/`AM` entries under frontend/ and core/ are expected.
- `docs/product/visualization.md`: plan-view section is short; the old point-cloud part is kept, marked superseded; the map-view section was lost.
- Old `App.tsx` and `ui/*` stay in the tree, unused, as reference for porting Guide events.
- Guide events (route, focus, closures) are not drawn on the plan yet.
- No frontend tests; UI checked by eye (headless screenshots per the log), not re-checked in this commit.
- Not committed: `Screenshot 2026-10-24 at 18.42.46.png` (local reference), `.impeccable/hook.cache.json` and `.impeccable/questions/` (tool cache).
- Rebuilt pieces (MapView.plan, Scene placeholder) are reconstructions from the log, not the original lost code.

## Verification rounds
- Round 1: FAIL — Plan type vs wall_solids mismatch, undeclared wall_solids, stale docs, oxlint record incomplete. Fixed by excluding wall_solids from the index (user's choice), C10 docs, round-2 checks on the staged tree.
- Round 2: PASS (tree 04f46501a28cfd5107b1cfec410579344e68fa93)

---

# Verification report (round 2)

VERDICT: PASS
TREE: 04f46501a28cfd5107b1cfec410579344e68fa93

C1–C10 all MET. Checks on a `git checkout-index -a` copy of the index: pytest 305 passed, 1 skipped, 11 deselected
(the 11 git-dependent tests passed in the real repo: 11 passed); `npm run build` ✓ built in 420ms; oxlint warnings
exactly as listed, no errors; check_links OK (28 files); no secrets; score.py unchanged; no hard-coding.
Undeclared: MapView docstring/comment update (trivial, covered by C2). Unstaged wall_solids work, tests/test_floorplan.py,
.impeccable/questions/ and the screenshot are excluded and declared in Known gaps.
Notes (non-blocking): some log entries describe work now in the gitignored .viz-archive/ (twin-lab, src/map/,
backPill.css); historical, no broken links.
