# CLAUDE.md: data/ layout line after D-028

- **Author:** Claude Code session (Atahan approved) · **Date:** 2026-10-28 00:15
- **Related:** D-028

## Summary
CLAUDE.md's repo tree still described `data/` as `train/ dev/ test/`; since D-028 it is `buildings/<id>/` with the
split as a manifest column. Atahan approved the edit.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Only CLAUDE.md line 24 changes, to `kit dataset: buildings/<id>/ + manifest.csv (split = a column; D-005, D-028)` | `CLAUDE.md` | `git diff --cached` |
| C2 | Links still resolve | — | `python3 scripts/check_links.py` |

## Checks I ran

- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

## Knowledge base updates
- [ ] not needed: one-line correction of a layout description already recorded under D-028

## Known gaps / not done
- PRODUCT.md:68 still says "`data/` (train/dev/test, 280 buildings)" (loosely true, not changed).

## Verification rounds

- Round 1: VERDICT: PASS (tree dc60eca)

## Verification report (round 1)

VERDICT: PASS
TREE: dc60eca7a5cb373314b8ca16de6b9b1e123b69e0

| # | Status | Evidence |
|---|---|---|
| C1 | MET | CLAUDE.md:24 1 insertion / 1 deletion, new line matches `ls data` and the manifest; D-028 at decisions.md:457 |
| C2 | MET | check_links: OK, all links resolve in 24 files |

Standard checks: pytest 955 passed, 2 skipped; links OK; no secrets; score.py unchanged; no code staged.
