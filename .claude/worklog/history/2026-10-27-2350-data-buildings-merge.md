# One data/buildings/ folder, kit ids without the split, no floor renders

- **Author:** Claude Code session (Atahan) · **Date:** 2026-10-27 23:40
- **Related:** D-028 (new), D-005, Q-003

## Summary
Merges the kit's `data/train`, `data/dev`, `data/test` into `data/buildings/<building_id>/`, deletes the floor PNG/SVG
renders and `scripts/eval_import.py` (their only user), and makes a kit building's id its directory name
(`proc-campus-train-000` instead of `train/proc-campus-train-000`). A Supabase migration rewrites stored ids.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | All 280 building folders moved (renames, content unchanged) to `data/buildings/`; no `data/train`, `data/dev`, `data/test` left | `data/` | `git diff --cached -M --name-status -- data \| grep -c '^R100.*building.json'` → 280; `git ls-files data/train data/dev data/test` → empty |
| C2 | Every `floor_*.png` / `floor_*.svg` deleted (1,594 PNG + 797 SVG); data now 280 building.json, 281 csv, 520 jsonl, 1 md | `data/buildings/` | `git ls-files data \| sed 's/.*\.//' \| sort \| uniq -c` |
| C3 | `manifest.csv`: only the `path` column changes, `<split>/<id>` → `buildings/<id>`; `split` column kept | `data/manifest.csv` | diff the file with `path` normalised |
| C4 | Test set `questions.csv` / `submission_template.csv` moved unchanged to `archive/hackathon/test-set/` | archive | `git diff --cached -M --name-status` → R100 |
| C5 | Catalogue: id = directory name in `data/buildings/`, `split` from the manifest, kind from `building_id` prefix; default building = first train building | `backend/api/sessions.py:load_catalogue`, `building_kind`, `default_building`, `DEMO_BUILDING` | read; `uv run pytest -q tests/test_backend.py` |
| C6 | Tests/scripts read `data/buildings/`; labelled-question tests keep only rows with an `answer` (test-split rows have none, 145 = the test CSV); unlabelled parser test reads jsonl rows without `answer` | `tests/test_question_parser.py`, `test_solvers_*.py`, `test_routes.py`, `test_validate.py`, scripts `validate_*`, `check_routes.py` (dev buildings via manifest), `fit_locations.py` | `uv run pytest -q` |
| C7 | `scripts/eval_import.py` deleted; `vercel.json` drops the now-pointless png/svg excludes (bundle unchanged) | `scripts/`, `vercel.json` | `uv run pytest -q tests/test_deploy.py` |
| C8 | Migration rewrites `(train\|dev\|test)/` ids in conversations, builder_drafts, saved_buildings, access_buildings, access_members, fleet_objects (text columns and kit-id strings inside jsonb); idempotent | `supabase/migrations/20261027120000_building_ids.sql` | read |
| C10 | Root README repo layout line for `data/` says `data/buildings/<id>/` + manifest.csv (only that line staged; Atahan's other README edits stay unstaged) | `README.md` (layout block) | `git diff --cached README.md` → one line; `git diff README.md` has no `kit's buildings` line |
| C11 | Map landing: a building without a name shows its id (kit ids have no `/` now); was `split('/')[1]` → `undefined` | `frontend/src/map/MapLanding.tsx:87` `nameOf` | read; `cd frontend && npx tsc -b` → exit 0 |
| C9 | Docs/memory bank: D-028 added, D-005 update note, project-state, log, commands.md, data-format.md, repo-layout.md, ai-agents.md, open-questions Q-003 note, archived benchmark README note | listed files | `python3 scripts/check_links.py` |

## Checks I ran

- `uv run pytest -q` → `955 passed, 2 skipped in 119.04s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`
- `uv run python scripts/validate_solvers.py --kinds shared_walls_count` → `all 143 / 143`
- `uv run python scripts/validate_dataset.py` → `280 buildings`
- catalogue smoke: `load_catalogue()` → 280 entries; `proc-campus-train-000` split `train`; `proc-factory-dev-003` kind `factory`; `osm-way10053349` has a location
- fix round 1: `uv run pytest -q` → `955 passed, 2 skipped in 112.36s (0:01:52)`; `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`; `cd frontend && npx tsc -b` → exit 0 (no output); `git diff --cached --stat README.md` → `1 insertion(+), 1 deletion(-)`; `git diff README.md | grep -c "kit's buildings"` → `0`
- `scripts/check_routes.py` → crashes with MapError on dev `osm-way360544293`; same crash at HEAD in a temp worktree (pre-existing)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (Data line; Next 2 = apply migration)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: D-028 new, D-005 update line, Q-003 note
- [x] docs touched: commands.md, data-format.md, repo-layout.md, ai-agents.md, archive benchmark-code README

## Known gaps / not done
- Migration not applied yet (to be applied with the deploy of this commit).
- `scripts/check_routes.py` pre-existing crash not fixed.
- Old `?building=train/...` links no longer resolve (no alias, by Atahan's choice).
- Archived benchmark code still expects the old layout (run from `fd2b50a`).
- `README.md` has unrelated uncommitted changes by Atahan; not part of this commit (only the `data/` layout line is staged).
- CLAUDE.md:24 still says `train/ dev/ test/` for data/; left for Atahan to approve (CLAUDE.md edits need the user's OK).

## Fix round 1
- CLAUDE.md:24 stale `train/ dev/ test/`: claim corrected — not edited (needs Atahan's OK); declared in Known gaps.
- README.md:22 stale `data/` line: implemented — line replaced in the index (patched blob via `git update-index`) and in the working tree; Atahan's other README edits remain unstaged (C10).
- MapLanding `nameOf` assumed `<split>/<id>`: implemented — `b.name ?? b.id.split('/').pop() ?? b.id` in `frontend/src/map/MapLanding.tsx` (C11); `npx tsc -b` exit 0.

## Verification rounds

- Round 1: VERDICT: FAIL (tree bbfcc88): stale train/dev/test in CLAUDE.md:24, README.md data line, MapLanding nameOf split. Fixed by commit-fixer (README line + nameOf); CLAUDE.md declared as known gap.
- Round 2: VERDICT: PASS (tree ca4e550)

## Verification report (round 2)

VERDICT: PASS
TREE: ca4e5504cc0f301a4c81ae4ee1c607e9deb65747

## Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | 280 building.json renames R100, 0 non-R100; `git ls-files data/train data/dev data/test` → 0 |
| C2 | MET | 1594 png + 797 svg deleted; data: 281 csv, 280 json, 520 jsonl, 1 md |
| C3 | MET | manifest: 280 rows, 0 differences outside `path`; `path` = `buildings/<id>` |
| C4 | MET | R100 test CSVs → archive/hackathon/test-set/ |
| C5 | MET | sessions.py catalogue/kind/default/DEMO as claimed; smoke 280 entries |
| C6 | MET | tests/scripts read data/buildings/; `answer` filter; 145 unlabelled = archived CSV |
| C7 | MET | eval_import.py deleted; vercel.json drops png/svg excludes; test_deploy passes |
| C8 | MET | migration covers all id columns + jsonb; idempotent; not applied (declared) |
| C9 | MET | D-028 and docs updated; check_links OK |
| C10 | MET | README: only the data line staged; Atahan's edits unstaged |
| C11 | MET | MapLanding nameOf fallback; `npx tsc -b` exit 0 |

## Standard checks
- pytest: 955 passed, 2 skipped in 116.77s
- links: OK: all links resolve in 24 files
- secrets: none found
- score.py unchanged: yes
- hard-coding: none found

## Notes (non-blocking)
- CLAUDE.md:24 stale (declared, needs Atahan's OK). PRODUCT.md:68 loosely stale. visualization.md:197 historical. tests/test_add_floor.py:107 uses an old-style id for a 404 check (still valid).
