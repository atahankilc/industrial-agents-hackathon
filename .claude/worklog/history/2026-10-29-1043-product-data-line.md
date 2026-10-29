# PRODUCT.md: data line after D-028

- **Author:** Claude Code session (data merge) · **Date:** 2026-10-29
- **Related:** D-028 (kit data merged into data/buildings/)

## Summary
PRODUCT.md "Evidence on Hand" still described `data/` as train/dev/test folders; since D-028 every kit building is in `data/buildings/<id>/`. One-line doc fix.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | PRODUCT.md data line names `data/buildings/` and 280 kit buildings, no train/dev/test | `PRODUCT.md:68` | `git diff --cached PRODUCT.md`; `grep -n "train/dev/test" PRODUCT.md` → nothing |
| C2 | 280 is correct: `data/buildings/` holds 280 building folders | `data/buildings/` | `ls data/buildings \| wc -l` → 280 |
| C3 | Only PRODUCT.md and this worklog are staged | index | `git diff --cached --stat` |

## Checks I ran
- `ls data/buildings | wc -l` → `280`
- `grep -n "train/dev/test" PRODUCT.md` → no output
- `python3 scripts/check_links.py` → `OK: all links resolve in 25 files`

## Knowledge base updates
- [ ] `memory-bank/project-state.md`: not needed (D-028 already recorded as deployed in 3fc8aab; this is a stale-line fix)
- [ ] `memory-bank/log.md`: not needed for a one-line doc correction
- [ ] decisions / open questions: none
- [x] docs touched: PRODUCT.md

## Known gaps / not done
- archive/hackathon/benchmark-code/README.md commands still use `data/dev`, `data/test` on purpose (archived, note points to commit fd2b50a).

## Verification rounds
- Round 1: PASS

## Verification report (round 1)
VERDICT: PASS
TREE: c89f39e4e03c98fd32fd5f1f900595cc52c35b93

| # | Status | Evidence |
|---|---|---|
| C1 | MET | PRODUCT.md:68 names `data/buildings/`; grep train/dev/test returns nothing |
| C2 | MET | `ls -d data/buildings/*/ \| wc -l` → 280 |
| C3 | MET | only PRODUCT.md and the worklog staged |

Standard checks: pytest 978 passed, 2 skipped; links OK (25 files); no secrets; score.py unchanged; no hard-coding.
Undeclared changes: none. Known gaps: accurate (archived benchmark README keeps old paths on purpose).
