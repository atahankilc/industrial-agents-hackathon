# <Short title of the change — becomes the commit subject>

- **Author:** <agent/session or person> · **Date:** YYYY-MM-DD HH:MM
- **Related:** D-### / Q-### / docs that motivated this

## Summary
1–3 sentences: what this change does and why.

## Claims
Every promise the verifier must check. One row per claim; be specific and checkable.

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | e.g. `largest_room` solver matches all train+dev answers | `core/solvers.py:largest_room` | `uv run pytest tests/test_solvers.py -k largest_room` → 96/96 |
| C2 | e.g. docs updated: solver-plan status row = VERIFIED | `docs/architecture/solver-plan.md` | read the table |

## Checks I ran
Commands + their actual result (paste the key line, don't paraphrase).

- `uv run pytest -q` → …
- `python3 scripts/check_links.py` → …

## Knowledge base updates
- [ ] `memory-bank/project-state.md` updated (or: not needed because …)
- [ ] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: …
- [ ] docs touched: …

## Known gaps / not done
Anything promised elsewhere but not in this change, shortcuts, TODOs. Empty is suspicious.
