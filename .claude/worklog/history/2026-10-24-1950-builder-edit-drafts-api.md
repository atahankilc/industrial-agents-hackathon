# Builder Edit mode M1 Task 4: drafts store and /drafts API

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 19:47
- **Related:** docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §3; plan Task 4

## Summary
Local store for Edit-mode drafts (base + steps of ops) and saved buildings (`user/<slug>`), and the `/drafts` HTTP
endpoints the frontend will use. Saved buildings join the shared catalogue, so sessions and the Guide use them.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `POST /drafts {base}` creates a draft (422 unknown base); `GET /drafts/{id}` returns `{draft: {id, base, name, steps}, building, issues}` | `backend/app.py`, `backend/drafts.py:DraftStore.create/state` | `uv run pytest tests/test_drafts.py -q -k "roundtrip or unknown_base"` |
| C2 | `POST /drafts/{id}/ops` applies the ops as one undo step; a failing op → 422 with the reason and the draft unchanged | `DraftStore.apply` | `-k "roundtrip or ops_error"` |
| C3 | `POST /drafts/{id}/undo` drops the last step; nothing to undo → 409 | `DraftStore.undo` | `-k "roundtrip or undo_empty"` |
| C4 | Draft ids are checked against `^[0-9a-f]{32}$` before any path use; malformed / unknown → 404 | `DraftStore.get`, `DRAFT_ID` | `-k "bad_draft_id or unknown_base"` |
| C5 | Save writes `<root>/<slug>/building.json` + `draft.json`, building meta id=slug, name, source "edited", source_ref {base}; returns `user/<slug>`, listed in `/buildings`; a session can be created on it and `tool_find_route` works | `DraftStore.save`, `register` | `-k save_lists_building_and_guide_routes` |
| C6 | Same name twice → `user/foo`, `user/foo-2`; a saved building can itself be a draft base | `DraftStore.save` | `-k "suffixes or draft_of_saved"` |
| C7 | Drafts persist to `<root>/.drafts/<id>.json` and load in a new store | `DraftStore.store/get` | `-k survives` |
| C8 | `GET /drafts/{id}/points` returns the point-cloud export of the draft | `backend/app.py:draft_points` | `-k points_endpoint` |
| C9 | The dataset building file is byte-identical after create/ops/save | — | `-k dataset_untouched` |
| C10 | `.gitignore` ignores `data/user/` and `.superpowers/`; store root `GUIDE_USER_DIR`, default `data/user/` | `.gitignore`, `backend/app.py` | read |
| C11 | Endpoints documented in commands.md and the app docstring | `docs/guides/commands.md`, `backend/app.py` docstring | read; check_links OK |
| C12 | Full suite green | — | `uv run pytest -q` → 670 passed, 1 skipped |

## Checks I ran
- `uv run pytest tests/test_drafts.py -q`: before → collection error (backend.drafts missing); after → `12 passed in 5.87s`
- `uv run pytest -q` → `670 passed, 1 skipped in 83.60s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 30 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — Task 4 done, next Task 5.
- [x] `memory-bank/log.md` — entry "2026-10-24 19:47 — Builder Edit mode M1 Task 4".
- [x] decisions / open questions touched: none.
- [x] docs touched: `docs/guides/commands.md` endpoints table.

## Known gaps / not done
- Plan said `backend/sessions.py` `SPLITS` gains "user"; instead DraftStore registers saved buildings from its root at start (works with any GUIDE_USER_DIR). `backend/sessions.py` unchanged.
- Local store only: on Vercel the filesystem is read-only, so /drafts writes fail there until milestone 3 (Supabase).
- No auth: every saved building is visible to everyone (spec call 10). No delete endpoint.
- Frontend: Tasks 5–7.

---

# Verification report (round 1)

VERDICT: PASS
TREE: 06c920f9d22cf7d617486b0be99f8e1af15b95d8

Claims C1–C12 MET (tests/test_drafts.py 12 passed; full suite 670 passed, 1 skipped). Links OK (30 files). No
secrets; score.py unchanged; no hard-coded test ids. No undeclared changes; memory bank and commands.md updated;
known gaps match the diff. Observation (not a failure): DraftStore.apply/undo mutate a draft without the store lock,
so two concurrent requests on one draft could race.
