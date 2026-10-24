# Builder M2: final-review fixes (proposal lifetime, strict confirm, text fields, stale proposals) + M3 plan

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24 21:22
- **Related:** whole-branch review of M2 (opus); docs/superpowers/plans/2026-10-24-builder-edit-mode-m3.md (owner Atahan)

## Summary
Fixes the critical and important findings of the M2 review — a proposal the user no longer saw (or cancelled) could
still be applied by "ok"/"yes", "yes, but…" skipped the model, numeric text fields broke search, and a hand edit during
a Builder turn turned the reply into an error — and adds the milestone-3 plan for Atahan.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | A proposal is confirmable only by the very next message: any non-confirm turn closes open proposals; Cancel (`Builder.cancel`, `POST /drafts/{id}/proposals/{pid}/cancel`, called by the card) and hand edits / undo (`drafted_by_hand` via `tell_builder`) close them too | `agent/builder.py`, `backend/app.py:cancel_proposal/tell_builder`, `BuilderChat.tsx:cancel`, `api.ts:cancelProposal` | `uv run pytest tests/test_builder.py tests/test_drafts.py -q -k "ok_after or cancelled or hand_edit or cancel_proposal"` |
| C2 | Applying a closed proposal says why (draft changed / cancelled / replaced by a newer message) | `Builder.closed`, `Builder.apply` | `-k apply_stale_proposal_409` |
| C3 | Only a message that is nothing but a confirmation (`CONFIRM_ONLY`) applies without the model; "yes, but …" goes to the model | `agent/builder.py:CONFIRM_ONLY` | `-k yes_with_more_words` |
| C4 | Text fields (name, ref, type, room_type, category) in ops: numbers → strings, other types → EditError | `core/edits.py:text`, add_space / set_space / add_asset / set_asset | `uv run pytest tests/test_edits.py -q -k text_fields` |
| C5 | The stream sends no proposal when the draft changed during the turn (the reply still goes out); the ghost is the dry-run building stored on the Proposal (no second replay) | `backend/app.py:proposal_payload`, `Proposal.preview` | `-k proposal_payload_skips` |
| C6 | M3 plan (owner Atahan) with front matter, 6 tasks, linked from docs/README.md, the spec and the M2 plan; ai-agents.md / memory bank updated | `docs/superpowers/plans/2026-10-24-builder-edit-mode-m3.md`, docs, memory-bank | read; check_links OK |
| C7 | Suite + build green; browser flow unchanged | — | `uv run pytest -q` → 729 passed, 1 skipped; `npm run build` ok |

## Checks I ran
- new tests first → `7 failed, 61 passed` (the hand-edit stream test already passed through the staleness refusal); after fixes one existing test changed message ("no open proposal") → added close reasons → `81 passed` (builder, edits, drafts, builder_tools)
- `uv run pytest -q` → `729 passed, 1 skipped in 87.79s`; `npm run build` → `✓ built in 562ms`
- headless Chrome drive5 (offline, backend restarted): 1 / 2 / 3 changes as before, proposal card dropped on drag, `errors: []`
- `python3 scripts/check_links.py` → `OK: all links resolve in 32 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — M2 review fixes, M3 plan link.
- [x] `memory-bank/log.md` — entry "2026-10-24 21:22 — Builder M2 review fixes; M3 plan for Atahan".
- [x] decisions / open questions touched: none.
- [x] docs touched: new M3 plan; spec / M2 plan / docs/README.md links; ai-agents.md (proposal lifetime, M3 link); commands.md unchanged.

## Known gaps / not done
- Review minors deferred (plan ledger): non-finite coordinates, two `/ops` 500 cases, Apply clickable during a turn, revision bump on "yes", richer `find` candidates.
- M3 is a plan only (Atahan implements).

---

# Verification report (round 1)

VERDICT: PASS
TREE: a0f9983270b80d7e9cb59f193ff1076ece01fa0e

C1–C7 MET (targeted tests pass; pytest 729 passed, 1 skipped; build ok; links OK in 32 files; M3 plan facts
spot-checked against vercel.json / persistence.py / drafts.py). No secrets, score.py unchanged, no hard-coding.
Note: deferred minors are recorded in log.md and this worklog (the plan ledger is in the gitignored workspace).
