# Merge dev c3ab8f0; chat Guide gets compute + find_nearest closures; readable Claude API errors

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25 08:30
- **Related:** PR #2, D-022 (Sunday layers), Atahan's 6fa882e (`find_nearest`, step card) and c3ab8f0 (landing account)

## Summary
Merges `origin/dev` (6fa882e, c3ab8f0) into the Sunday branch and brings the Sunday layers into the chat Guide: a
`compute` tool (the solver agent's Python sandbox, whose `route()` routes exactly as `find_route` does) and per-question
closures + a candidate shortlist on Atahan's `find_nearest`. Claude API failures (e.g. the credit ran out) now reach
the user as a readable sentence instead of `BadRequestError: Error code: 400 - {...}`. Measured against the old dev
Guide before shipping (log 08:30).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Merge of `origin/dev` c3ab8f0 into 4-sunday-agent (ed7e974); no merge conflicts; dev's committed `.claude/worklog/PENDING.md` (c3ab8f0's) archived unchanged to `history/2026-10-25-0753-landing-account-button-from-dev.md` | merge state | `cat "$(git rev-parse --git-dir)/MERGE_HEAD"` → c3ab8f0…; compare the archived file with `git show origin/dev:.claude/worklog/PENDING.md` |
| C2 | `backend/service_errors.py`: `friendly(error)` → `{"code", "message"}` (credits for 402 / "credit balance" / billing, auth 401/403, busy 429, unavailable ≥500 incl. 529, offline for connection/timeout, internal otherwise; raw error logged only); `error_line` for NDJSON; Guide and Builder streams use it; conflict lines get code/message (detail text kept); `anthropic.APIError` on plain requests → 503/429 `{"detail": message, "code"}` | `backend/service_errors.py`, `backend/app.py` (`chat_stream`, `draft_chat_stream`, `claude_failed`) | `uv run pytest tests/test_service_errors.py -q` → 13 passed |
| C3 | Frontend: stream error lines become `ServiceError(message, code)`; the Guide shows the message as is (no "Error:" prefix) and says it on voice turns; plain-request errors with `{detail, code}` show the detail | `frontend/app/src/api.ts` (`ServiceError`, `streamError`, `failed`), `frontend/app/src/building/BuildingScreen.tsx` (`send` catch) | `cd frontend/app && npx tsc -b` → exit 0; read |
| C4 | Guide tool `compute`: Python over a copy of the session's building (solver agent sandbox); its `route()` uses the Guide's route rules, the user's profile (step-free, profile closures) and "here" — never disagrees with `find_route` | `agent/tools.py` (`tool_compute`, TOOL_DEFINITIONS), `core/route_query.py` (`rules=` parameter) | `uv run pytest tests/test_guide_sunday_tools.py -q` → 5 passed (incl. `test_compute_routes_like_the_guide_does`, which failed first: `True` vs `False`) |
| C5 | `find_nearest` (Atahan's) takes `closed` (closures for this question only, passed to ranking and to the final `find_route`) and routes to at most 12 candidates nearest in a straight line (`core/route_query.shortlist`); `find_route` takes an internal `closed` kwarg (not in its schema); our `route_to_nearest` tool is not added (one nearest tool for the model) | `agent/tools.py` (`tool_find_nearest`, `tool_find_route`, find_nearest schema) | `tests/test_guide_sunday_tools.py::test_nearest_item_holder_and_a_closure_for_this_question_only`; `grep -c route_to_nearest agent/tools.py` → 0 |
| C6 | Docs + memory bank: `/chat/stream` error line documented; log 08:30 (comparison numbers); project-state bullet | `docs/guides/commands.md`, `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` → OK |
| C7 | `docs/architecture/ai-agents.md` matches `agent/tools.py`: tool-table row and "Nearest place" paragraph give `find_nearest(start, query, floor_id?, closed?)` (per-question closures for ranking + final route; 12-candidate straight-line shortlist via `core/route_query.shortlist`); new `compute(code)` row (solver-agent sandbox: restricted builtins, module whitelist, 30 s; `route()` as find_route incl. rules/profile/closures/"here"; no access-mode penalties; D-022) and `compute` in the "Implemented" list; log 08:30 gets a Docs line; front-matter `sources` already had solver_agent.py and route_query.py | `docs/architecture/ai-agents.md`, `memory-bank/log.md` | read against `tool_find_nearest`, `tool_compute`, TOOL_DEFINITIONS; `python3 scripts/check_links.py` → OK |

## Checks I ran
- `git merge --no-ff --no-commit origin/dev` → "Automatic merge went well"; stashed work reapplied (tag `sunday-guide-tools-utku-0800`), one conflict in `agent/tools.py` resolved (imports; tool list: Atahan's `find_nearest` + our `compute`).
- RED first: `tests/test_service_errors.py` → `ModuleNotFoundError: backend.service_errors`; `tests/test_guide_sunday_tools.py` → `KeyError: 'reachable'`, `Unknown tool 'compute'`; consistency test → `{'output': 'True\n'} != {'output': 'False\n'}`.
- `uv run pytest -q -p no:cacheprovider` (after every edit except the `compute` description text and commands.md) → `888 passed, 2 skipped, 17 warnings in 246.22s`; `ls llm_cache` → no such directory.
- `cd frontend/app && npx tsc -b` → exit 0 (after the merge).
- Live UI (old backend with an invalid key): the Guide panel showed "The Guide is offline right now: its AI access key was not accepted. Please try again later." under the question.
- Comparison, old dev Guide (c3ab8f0 worktree) vs new, one run each: capability set 3/5 vs 5/5; `scripts/eval_guide.py` 17/18 vs 18/18; `scripts/interaction_eval.py` averages asks 3.33/3.83, shows 4.17/4.00, directions 3.67/3.67, remembers 4.17/4.33, goal 4/6 vs 3/6. After the `route()` fix, technician scenario rerun: goal user=Y judge=Y (was N/N), no route contradiction in the judge's issues.
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added (2026-10-25 08:30)
- [x] decisions / open questions touched: none (D-022 covers the layers; this extends them to the Guide)
- [x] docs touched: `docs/guides/commands.md`, `docs/architecture/ai-agents.md` (fix round 1)

## Known gaps / not done
- `compute`'s `route()` does not apply the access-mode preference penalties (`Penalties`) that `find_route` applies;
  off by default (ACCESS_MODE).
- The interaction judge still flags Guide phrasing issues unrelated to this change (filler openers, rounding of leg
  sums, few landmarks in spoken steps).
- The same readable-error change also sits uncommitted on the main checkout's branch `5-friendly-api-errors`
  (not part of this commit; that branch can be dropped).
- The comparison is one run per scenario; judge scores are noisy.

## Verification rounds
- Round 1: VERDICT FAIL (medium) — docs/architecture/ai-agents.md tool reference not updated (find_nearest closed/shortlist, compute missing).
- Fix round 1: claim C7 added — docs/architecture/ai-agents.md: implemented (find_nearest row + paragraph with `closed?` and the 12-candidate shortlist; `compute(code)` row + in the Implemented list); memory-bank/log.md 08:30 Docs line. `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`. No code changed, so pytest not rerun.
- Round 2: VERDICT PASS (fresh commit-verifier, effort medium, tree 4730700c).


---

# Verification report (final round)

VERDICT: PASS
TREE: 4730700c649d11d754d8d4f683a6e60f0472055b

C1–C7 MET: merge of c3ab8f0 clean (only the 8 claimed files differ from dev; dev's PENDING archived unchanged);
service_errors codes + handlers (18 tests pass); ServiceError in the app (tsc exit 0); compute with Guide-consistent
route() (5 tests); find_nearest closed + shortlist, no route_to_nearest; docs, log, state; ai-agents.md matches the
code. Standard checks: pytest 888 passed, 2 skipped; links OK (35 files); secrets none; score.py unchanged;
hard-coding none. Not re-checkable: the technician rerun and the live invalid-key UI check (no claim depends on them).
Notes: httpx2 is a transitive dependency of anthropic; compute's route() ignores access-mode Penalties (Known gaps).
