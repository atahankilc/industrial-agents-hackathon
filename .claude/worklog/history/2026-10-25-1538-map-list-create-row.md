# Map list: style the "New building from floor plans / Create →" row again

- **Author:** Claude session industrial-agents-hackathon · **Date:** 2026-10-25
- **Related:** found while verifying the 7-buildings-from-plans merge (65fee4d, Known gaps); 3113a99 dropped `.ml-more`

## Summary
The last row of the map's list panel (`<button className="ml-more">`, MapLanding.tsx) had no CSS since 3113a99, so
"New building from floor plans" and "Create →" ran together. A `.ml-more` rule on the HUD tokens puts them apart.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `.ml-more` is a full-width flex row (space-between, 14 px × 20 px padding, top hairline `--hud-line`, `--hud-ink` text, `font: 500 13.5px var(--font-ui)`), its last span `--hud-ink-2` and nowrap; focus-visible = `--hud-fill` + 2 px `--hud-route` outline; hover (in the `(hover: hover)` block) = `--hud-fill`; only HUD tokens that the file already uses | `frontend/app/src/map/map.css` | read the diff; `grep -n "hud-route\|font-ui" frontend/app/src/map/map.css` |
| C2 | Nothing else changes: the button's markup in MapLanding.tsx is untouched | `frontend/app/src/map/MapLanding.tsx` | `git diff --cached --stat` |
| C3 | Log entry for the change | `memory-bank/log.md` (top) | read |

## Checks I ran
- `cd frontend/app && npx tsc -b` → exit 0; `npx vite build` → `✓ built in 564ms`
- `python3 scripts/check_links.py` → `OK: all links resolve in 42 files`
- Headless Chrome (backend :8775 `ACCESS_MODE=off`, vite :5185): `.ml-more` box wide `{x: 17, y: 836, width: 398, height: 47}`, phone 390 px `{x: 17, y: 780, width: 356, height: 47}`; screenshots dark, light, phone: name left, "Create →" right, hairline above

## Knowledge base updates
- [ ] `memory-bank/project-state.md`: not needed (a style fix, no state change)
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none
- [ ] docs touched: none (visualization.md doesn't describe this row)

## Known gaps / not done
- Hover and keyboard focus were not looked at in a browser, only the resting row; no Python change, so the Python suite was not re-run.

## Verification rounds
- Round 1: PASS (tree 3a5cbaf).


---

# Verification report

VERDICT: PASS
TREE: 3a5cbaf8f114d13334a074296f9ee97b155d0e4c
C1–C3 MET. pytest 1088 passed, 2 skipped; links OK (42 files); tsc exit 0; vite build OK; no secrets; score.py unchanged.
Undeclared: none significant (cosmetic: blank lines around the new log entry).
