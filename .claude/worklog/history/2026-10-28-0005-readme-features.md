# README: features overview and live link

- **Author:** Atahan (text), shipped by a Claude Code session · **Date:** 2026-10-28 00:05
- **Related:** D-027 (Steward), D-028

## Summary
Atahan's README addition: the live URL and a "Features" section (map, plan view, Guide, Edit mode, plans import,
living building, access mode …). Docs only; no code change.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Only README.md changes; 104 added lines, no deletions | `README.md` | `git diff --cached --stat` |
| C2 | Every repo path the new text cites exists: backend/agents/{builder,creator,guide}.py, backend/api/locations.json, backend/core/{edits,floorplan}.py, backend/core/plan_import/, frontend/src/{edit,map,plan}/, frontend/src/ui/CameraGuide.tsx; `ACCESS_MODE=on` and `POST /live/devices` exist in backend/api | `README.md` | `ls` each; `grep -rn ACCESS_MODE backend/api/access.py`; `grep -n '/live/devices' backend/api/live/endpoints.py` |
| C3 | "the 17 OSM buildings in backend/api/locations.json" matches the file | `README.md` | `len(json.load(...)["buildings"])` → 17 |

## Checks I ran

- every cited path → exists (no MISSING)
- `backend/api/access.py:39` reads `ACCESS_MODE`; `backend/api/live/endpoints.py:145` `@api.post("/live/devices")`
- locations.json buildings → 17
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

## Knowledge base updates
- [ ] project-state / log: not needed (README text only, written by Atahan)

## Known gaps / not done
- Prose claims about behaviour were written by Atahan and are not each re-verified here beyond the cited paths.

## Verification rounds

- Round 1: VERDICT: PASS (tree 2e135ea)

## Verification report (round 1)

VERDICT: PASS
TREE: 2e135ea9fa2c98bf0ba1b70849a73bcb3c2c2707

| # | Status | Evidence |
|---|---|---|
| C1 | MET | README.md 104 insertions only; only other staged file is the worklog |
| C2 | MET | all 11 cited paths exist; access.py:39 reads ACCESS_MODE; live/endpoints.py:145 POST /live/devices |
| C3 | MET | locations.json buildings → 17 |

Spot checks: 280 buildings, /v1/chat/completions, CameraGuide not wired in, README links to decisions/project-state resolve (check_links.py does not scan README.md; checked by hand).

Standard checks: pytest 955 passed, 2 skipped; links OK; no secrets; score.py unchanged; no hard-coding.
