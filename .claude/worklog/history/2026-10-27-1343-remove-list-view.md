# Remove the ?view=list page and the unused Geist-outline brand files

- **Author:** Claude (session with Atahan) · **Date:** 2026-10-27
- **Related:** commit aa25ca8 (the map's search panel replaced the list view), docs/product/visualization.md

## Summary
Atahan asked to drop the separate list view (`?view=list`), unused since the map's search panel lists every building,
and the brand files the wordmark generator no longer reads (`steward-outline.json`, `outline.py`).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `frontend/src/search/` (BuildingSearch.tsx, search.css) is deleted and nothing imports it | `frontend/src/search/` | `git diff --cached --name-status` shows both `D`; `git grep -n "BuildingSearch\|search/" -- frontend/src` → no import |
| C2 | `Root.tsx` has `type Landing = 'map' \| 'import'`; `fromUrl` maps anything but `view=import` (including an old `?view=list`) to `'map'`; no list render branch; ImportScreen `onDone` → `go(base, 'map', true)`, `onExit` → `go(null, 'map')` | `frontend/src/Root.tsx` | read |
| C3 | `scripts/brand/steward-outline.json` and `scripts/brand/outline.py` are deleted; `marks.cjs` does not reference them and still writes all 10 brand SVGs byte-identical to the committed ones | `scripts/brand/` | `grep -n outline scripts/brand/marks.cjs` → no match; `node scripts/brand/marks.cjs /tmp/x && for f in /tmp/x/*.svg; do cmp -s $f frontend/public/brand/$(basename $f) \|\| echo DIFF $f; done` → no output |
| C4 | Comments no longer mention the list view / search page: AccessLayer.tsx header, map.css line 1, import.css line 1, Root.tsx header | those files | read the first lines |
| C5 | Docs: visualization.md section intro ("Current: vector plan view") says the landing's search panel lists every building (no list view), and the Landing paragraph says the list view was removed and an old link lands on the map, the app folder list has `src/brand` instead of `src/search`; project-state.md App line; log.md entry | docs/product/visualization.md, memory-bank/project-state.md, memory-bank/log.md | read; `python3 scripts/check_links.py` → OK |
| C6 | Type check clean; lint exits 0 with no warnings in the touched frontend files | `frontend/` | `cd frontend && npx tsc -b` → 0; `npx oxlint src` → exit 0, no line for Root.tsx / AccessLayer.tsx / map.css |

## Checks I ran
- `cd frontend && npx tsc -b` → `tsc 0`
- `npx oxlint src` → exit 0; warnings only in untouched files (Inspector, NextMove, useVoice, StreetView, PlanView, …)
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`
- generator into a scratch dir + `cmp` → no DIFF (`generator ok`)
- headless Chrome over CDP, `http://localhost:5390/?view=list` → `{"map":true,"search":true,"oldList":false}`
- `uv run pytest` not run: no Python changed.
- Fix round 1: `git grep -n -i "list view" -- docs` → only `docs/product/visualization.md:54:  have no position; the search panel lists them under "No location". (The separate list view, `?view=list` /` (the historical note)
- Fix round 1: `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (App line)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: `docs/product/visualization.md`

## Known gaps / not done
- The import flow's done/exit navigation was not clicked through in a browser (needs a Creator run / admin); covered by reading and `tsc` only.
- Older log entries and archived docs still mention `?view=list` / `src/search/` as history (left as written).

## Verification rounds
- Round 1: FAIL (visualization.md:21-22 intro still says "plus a list view")

## Fix round 1
- visualization.md:21-23 intro still claimed "plus a list view for the rest": implemented — reworded to "a map of the buildings with a real position, its search panel listing every building (the ones without a position after them; see **Landing** below)"; C5 extended to cover it (docs/product/visualization.md, .claude/worklog/PENDING.md)
- Round 2: PASS (tree 3879f0bfe4f4a48eb8064655be7c53aeb06ec4b8)
# Verification round 1 — VERDICT: FAIL

TREE: 7ca8f4cfbd0134d6e96aa30955914f978a281ad8

C1–C6 MET. Standard checks: pytest 955 passed, 2 skipped; links OK; secrets none; score.py unchanged; no
hard-coding. Knowledge base FAIL: docs/product/visualization.md:21-22 ("Current: vector plan view" intro) still says
"Landing is a map of the buildings with a real position plus a list view for the rest (see **Landing** below)".
Required fix: reword to match the current app (search panel lists every building); `git grep -n -i "list view" --
docs` must then show only the historical note at :53-55; check_links OK; restage.

# Verification round 2 — VERDICT: PASS

VERDICT: PASS
TREE: 3879f0bfe4f4a48eb8064655be7c53aeb06ec4b8

C1–C6 all MET (C5 now covers the intro at visualization.md:22-23). Standard checks: pytest 955 passed, 2 skipped
(118 s); links OK (24 files); secrets none; score.py unchanged; no hard-coding; nothing unstaged. Re-ran tsc 0,
oxlint exit 0 (no warnings in touched files), generator cmp no DIFF. Headless check not re-run (code supports it:
fromUrl maps ?view=list to 'map'). Undeclared: Root.tsx:41 comment reworded (trivial).
