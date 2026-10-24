# Docs: organisers' note on Sunday route scoring (Q-001 progress, Q-014, Q-015)

- **Author:** Claude (Utku's session) · **Date:** 2026-10-24
- **Related:** Q-001, Q-014, Q-015, docs/kit/route-model.md

## Summary
Records the organisers' Discord note on how Sunday route answers are scored: a space sequence re-measured with
their own distance model (door-to-door ~15 cm off walls, stairs 2 m/m climbed, lift 15 m + 1 m/m), score =
best ÷ ours with full marks within 1%, plus new factory rules. Docs only, no code.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | route-model.md has a new section "Sunday scoring model (organisers' note, 2026-10-24)" with building model, rules, scoring, and a comparison table vs the warm-up graph; the note is listed in front-matter `sources` | `docs/kit/route-model.md` | read the section and front matter |
| C2 | Q-001 gets a progress entry (space path scored, own length ignored, 1% full marks, "no route" answer) and its "Still unknown" list is updated (tolerance struck through, item-start added) | `memory-bank/open-questions.md#q-001` | read Q-001 |
| C3 | New open questions Q-014 (Sunday distance model / second router cost profile) and Q-015 (factory schema: aisles, walkways, bays); next free id = Q-016 | `memory-bank/open-questions.md` | read |
| C4 | Claim "current data/ has no aisle/walkway/bay space types; forklift and forklift_charging_station exist only as equipment types" | Q-015, log entry | `grep -rhoE '"(room_type\|type\|kind)": *"[a-z_]*(aisle\|walkway\|forklift\|bay\|ramp)[a-z_]*"' data/ \| sort \| uniq -c` → only `forklift_charging_station` (69), `forklift` (107) |
| C5 | log.md has an entry for this chunk | `memory-bank/log.md` | read |
| C6 | No code changed | staged diff | `git diff --cached --stat` |

## Checks I ran
- `python3 scripts/check_links.py` → `OK: all links resolve in 28 files`
- grep in C4 → `69 "type": "forklift_charging_station"`, `107 "type": "forklift"`

## Knowledge base updates
- [ ] `memory-bank/project-state.md` — not updated (no change in what exists; Q-014 is a next-step candidate only)
- [x] `memory-bank/log.md` entry added
- [x] open questions touched: Q-001 (progress), Q-014, Q-015 opened
- [x] docs touched: docs/kit/route-model.md

## Known gaps / not done
- The Discord note itself is not stored verbatim in the repo; it is paraphrased in route-model.md.
- No decision (D-###) recorded yet for the second router cost profile; no code for it.

## Verification rounds
- Round 1: VERDICT: PASS (TREE 089cba0298eedb11b1cde453fa7793b3237717c4)

## Verification report (round 1)
VERDICT: PASS
C1–C6 MET. pytest: 117 passed in 21.27s; links: OK: all links resolve in 28 files; secrets: none; score.py unchanged; hard-coding: none; undeclared changes: none.
Notes: project-state.md not updated (declared, accepted); Discord note not in repo verbatim (declared gap), start/end marked UNVERIFIED in route-model.md.
