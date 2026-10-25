# Docs: access-roles design (demo, not built) + factory bay-rule finding

- **Author:** Claude session (Utku) · **Date:** 2026-10-24
- **Related:** Q-015, docs/product/routing-profiles.md, docs/kit/route-model.md

## Summary
Docs only, no code. New design spec for an access-roles demo feature (roles with room access and physical limits
set by the facility manager in conversation), linked from the docs index and routing-profiles; log entry; the
factory bay-rule finding recorded under Q-015.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | New spec with front matter (id, summary, sources, related) and sections Intent, Goals, Non-goals, Anti-goals, Constraints, Decided, My calls, Left to the builder; status draft, nothing built | `docs/superpowers/specs/2026-10-24-access-roles-design.md` | read |
| C2 | Spec "Decided" holds Utku's answers: open conversations get rules on their next turn; building changes building-wide; only a claimed `manager` may edit; demo only, benchmark untouched; UI later | same file, § Decided | read |
| C3 | Facts cited in the spec match the code: building.json space keys (id, floor_id, type, room_type, name, ref, polygon, synthetic); `RoutingProfile`/`PRESETS`/`profile_closures` in agent/tools.py; closed spaces leave the graph (core/building_map.py); per-conversation persistence (backend/persistence.py) | spec § Constraints | grep the cited files |
| C4 | Spec linked from `docs/README.md` and backlinked from `docs/product/routing-profiles.md` § Related | docs/README.md, routing-profiles.md | read; check_links |
| C5 | Q-015 gains the bay-rule finding: 26/26 factory buildings cut office ↔ hall under bays + no-outside; dev-004 example (no route vs 61.56 m without rules); production-only still 706 cut off; rule text is our summary of the Discord note, not PDF/README | memory-bank/open-questions.md Q-015 | read; re-run check below |
| C6 | log.md entry for the design + bay finding | memory-bank/log.md | read |
| C7 | No code changed | `git diff --cached --stat` | only .md files |

## Checks I ran
- `uv run python scripts/check_links.py` → `OK: all links resolve in 29 files`
- Space keys from a scan of all `data/*/*/building.json`: `{'id','floor_id','type','room_type','name','ref','polygon','synthetic'}` (22,725 spaces)
- Bay scan (throwaway script in /tmp, not committed): `26/26 factory buildings lose reachable spaces under the rules`; all zone types: total 1716 unreachable from the worst entrance, worst 126; production only: total 706, worst 125
- dev-004: `BuildingSession.call("find_route", Locker room 0.30 → Production zone H-A2)` → reachable False; `navigation.find_route` without rules → True 61.56 via Assembly zone H-A1
- PDF (3 pages) and `archive/initial-repo/README.md` read/grepped: no production-bay rule

## Knowledge base updates
- [ ] `memory-bank/project-state.md`: not changed (no new working capability; design is draft)
- [x] `memory-bank/log.md` entry added
- [x] open questions: Q-015 finding added
- [x] docs touched: new spec, docs/README.md, docs/product/routing-profiles.md

## Known gaps / not done
- No implementation plan (Utku: not now) and no code.
- Bay-rule decision still open (Utku); organiser's original Discord wording not in the repo.
- The bay scan script is not committed (throwaway).

## Verification rounds
- Round 1: VERDICT: PASS (TREE e2be40ab1429d55377af82adfb77513890db9dd1)

## Verification report (round 1)

VERDICT: PASS
TREE: e2be40ab1429d55377af82adfb77513890db9dd1

| # | Status | Evidence |
|---|---|---|
| C1 | MET | spec front matter (id, summary, sources, related, status draft) and all eight sections |
| C2 | MET | § Decided: open conversations on next question; building changes building-wide; manager-only edits enforced in code; demo only; UI later |
| C3 | MET | space keys scan (22725 spaces) matches; PRESETS/RoutingProfile/profile_closures in agent/tools.py; closed elements leave the graph; per-conversation persistence; SessionStore |
| C4 | MET | docs/README.md link + routing-profiles backlink; links OK (29 files) |
| C5 | MET | bay scan rebuilt independently: 26 buildings, 1716/126 all types, 706/125 production only; dev-004 no route vs 61.56 m; kit README has no bay rule |
| C6 | MET | log entry present |
| C7 | MET | only .md files staged |

Standard checks: pytest 315 passed / 1 skipped; links OK under uv; no secrets; score.py unchanged; no hard-coding. Undeclared changes: none. project-state not updated (docs-only draft) — accepted.
