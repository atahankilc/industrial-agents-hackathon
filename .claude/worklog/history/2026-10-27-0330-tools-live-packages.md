# Split the Guide's tool layer and the living building into packages

- **Author:** Claude session for Atahan · **Date:** 2026-10-27 03:30
- **Related:** D-026 (new), D-025

## Summary
`backend/agents/tools.py` (~1175 lines) becomes the package `backend/agents/tools/`: `BuildingSession` is built from
one mixin per area. `backend/api/live.py` (~1080 lines) becomes `backend/api/live/` (world, hub, reroute, endpoints).
Code moved verbatim; `__init__.py` re-exports keep every existing import working. No behaviour change.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `backend/agents/tools/` = `session.py` (`BuildingSession(LookupTools, RoutingTools, ProfileTools, LiveTools, ChangeTools, MapTools, NearbyTools)`: init, load, call, restricted_hit, place resolution, location, highlight, tool_definitions), mixins `lookup`, `routing`, `profile` (+ `RoutingProfile`, `PRESETS`, preference constants), `live`, `changes` (+ `Change`), `map`, `nearby`, plus `definitions.py` (all tool schemas) and `shared.py` (MAX_*, UNALIGNED_SOURCES, IMPACT_KEYS, HERE) | `backend/agents/tools/*.py` | read |
| C2 | All 63 `BuildingSession` entries (62 methods plus the `load` classmethod) exist and their source is identical to `git show HEAD:backend/agents/tools.py` apart from updated path comments (`BuildingSession.__init__`, `LiveTools.tool_live_status`); `TOOL_DEFINITIONS`, `CAMPUS_TOOLS`, `PREFERENCE_SET_PROFILE`, `SET_PREFERENCE`, `LIVE_STATUS`, `SEND_OBJECT`, `PLACE`, `SCOPE`, the shared limits, `PRESETS`/`PROFILE_FIELDS`/`PREFERENCE_FIELDS`/`PENALTIES_M`/`GUIDE_PREFERENCES`, `RoutingProfile` and `Change` equal | — | load the HEAD file as a module and compare with `inspect.getsource` / `==` (methods collected over the MRO) |
| C3 | `backend/api/live/` = `world.py` (constants, Kind, KINDS, LEFT_BEHIND, Device, LiveWorld, helpers, blockers), `hub.py` (LiveHub, SessionLive), `reroute.py` (route_walks, route_blocked, live_check, take_shorter, blocking_spot, …), `endpoints.py` (models, `router`, drop, …); imports between them are explicit and acyclic (world ← reroute ← hub ← endpoints) | `backend/api/live/*.py` | read; `grep '^from backend.api.live' backend/api/live/*.py` |
| C4 | All 27 top-level classes/functions of the old `live.py` exist once in the package with identical source apart from updated path comments (`SessionLive` docstring in hub.py, `live_check` in reroute.py; plus the package `__init__.py` module docstring); all 17 module constants equal | — | compare with `inspect.getsource` against `git show HEAD:backend/api/live.py` |
| C5 | Both `__init__.py` re-export the names importers use (`BuildingSession`, `Change`, `RoutingProfile`, `PRESETS`, `PROFILE_FIELDS`, `TOOL_DEFINITIONS`; `LiveHub`, `SessionLive`, `LiveWorld`, `router`, `route_walks`, `trimmed`, `wet_zones`, `WET_S`), so no importer changed | `__init__.py` files | `git diff --cached --stat` shows no change to importers' import lines |
| C6 | References to `backend/agents/tools.py` / `backend/api/live.py` in code comments, docs, frontend comments, open-questions now point at the packages (precise submodule where it is clear); `memory-bank/log.md` history and `archive/` untouched | those files | `git grep -n "agents/tools\.py\|api/live\.py" -- ':!archive' ':!.claude/worklog'` → only `memory-bank/log.md` and D-026's historical context lines in `memory-bank/decisions.md` |
| C7 | D-026 accepted (Next free id D-027), log entry, project-state updated | `memory-bank/` | read |
| C8 | Full suite passes | — | `uv run pytest -q` → 955 passed, 2 skipped |
| C9 | No new lint errors | — | `uvx ruff check --select F,E9 backend tests scripts` → 16 (same pre-existing F811 fixture redefinitions as before) |
| C10 | Links resolve | — | `python3 scripts/check_links.py` → OK |

## Checks I ran
- tools comparison: `methods old/new: 63 63 missing: set() extra: set()`, `source differs: []`, `constants, schemas, dataclasses identical`
- live comparison: `27 defs, differing: [] | 17 constants equal`
- `uvx ruff check --select F,E9 backend/agents/tools backend/api/live` → `All checks passed!`; whole tree → `Found 16 errors.` (baseline 16)
- `uv run pytest -q` → `955 passed, 2 skipped in 118.24s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

- Fix round 1 re-run (after path-comment fixes): tools comparison `old entries 63 classmethods ['load'] new 63 set()`, `tools differ: ['__init__', 'tool_live_status']` (path comments only); live comparison `27 live defs differ: ['SessionLive', 'live_check']` (path comments only)
- Fix round 1: `uv run pytest tests/test_live.py tests/test_agent_tools.py -q` → `44 passed in 9.25s`; `uvx ruff check --select F,E9 backend/agents/tools backend/api/live` → `All checks passed!`; `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`; `uv run pytest -q` → `955 passed, 2 skipped in 110.74s`
- Fix round 1: `git grep -n "agents/tools\.py\|api/live\.py" -- ':!archive' ':!.claude/worklog'` → only `memory-bank/log.md:14,15,51` and `memory-bank/decisions.md:421,422` (D-026 context)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions: D-026 added
- [x] docs touched: ai-agents.md, solver-plan.md, living-building.md, routing-profiles.md (paths)

## Known gaps / not done
- `backend/api/live/world.py` is still ~590 lines (mostly the `LiveWorld` class); not split further.
- Mixins use attributes set in `BuildingSession.__init__` (no type declarations on the mixins).
- `collab-edits` will need its `tools.py` / `live.py` edits re-applied in the packages.

## Verification rounds
- Round 1: FAIL — C6: five old-path comments left inside the new packages (git grep ran before they were tracked)

## Fix round 1
- Stale path comments in moved code: implemented — `backend/agents/tools/live.py:26`, `backend/agents/tools/session.py:54`, `backend/api/live/__init__.py:10`, `backend/api/live/hub.py:94`, `backend/api/live/reroute.py:77` now name the packages (`reroute.py` → `backend/agents/tools/routing.py reroute`).
- C2/C4/C6 wording: claim corrected — C2 counts 62 methods plus the `load` classmethod = 63 entries and says source is identical apart from updated path comments (`BuildingSession.__init__`, `LiveTools.tool_live_status`); C4 the same (`SessionLive`, `live_check`, plus the `__init__.py` module docstring); C6 expected result = only `memory-bank/log.md` and D-026's context in `memory-bank/decisions.md`.
- D-026 Evidence: claim corrected — "62 `BuildingSession` methods + the `load` classmethod … byte-identical apart from updated path comments" (`memory-bank/decisions.md`).
- Round 2: PASS — all claims C1–C10 MET

## Verification report (round 2)

VERDICT: PASS
TREE: 37279e9188aa3f8116444d1ac8e34077936183f8

C1–C10 MET. tools: 63/63 entries, differ only __init__/tool_live_status (path comments); live: 27 defs, differ only SessionLive/live_check (path comments); constants equal; acyclic imports; pytest 955/2; ruff 16 = baseline; links OK; no secrets.
