# Creator: keep images so the prompt cache is read, not rewritten, every turn

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** docs/superpowers/plans/2026-10-25-plan-import.md (Task 10 constants), Utku: "şu anda çok pahalı oluyor"

## Summary
The Creator dropped one old image per turn to keep the context small. That changed the conversation's prefix on every
request, so the whole cached history was written again each turn: the Urban Colab run spent ≈ 0.87 M cache-write
tokens (≈ $4.4 of ≈ $4.8). Images now stay; only past MAX_IMAGES = 40 are all but the newest KEEP_IMAGES = 8 replaced
by a note, in one cut.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Below MAX_IMAGES nothing is dropped: every request's messages start with the previous request's messages (stable cached prefix) | `agent/creator.py` `prune`, `MAX_IMAGES`, `KEEP_IMAGES` | `uv run pytest tests/test_creator.py -q -k cached_prefix` |
| C2 | Past MAX_IMAGES, all but the newest KEEP_IMAGES images become a text note in one cut, then the prefix grows again | `agent/creator.py` `prune` | `uv run pytest tests/test_creator.py -q -k one_go` → image counts per request [0…6, 2, 3] with limits 6 / 2 |
| C3 | Plan doc, log and project-state record the change and the measured costs | `docs/superpowers/plans/2026-10-25-plan-import.md`, `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` → OK |
| C4 | Whole suite green | — | `uv run pytest -q` → 830 passed, 2 skipped |

## Checks I ran
- `uv run pytest tests/test_creator.py -q` → `8 passed`
- `uv run pytest -q` → `830 passed, 2 skipped, 15 warnings in 217.95s`
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- Cost figures: computed from the token counts printed by `scripts/live_creator.py` in earlier runs (Opus 5.5 prices: input $4, output $20, cache read $0.20 per MTok; cache write taken as 1.25 × input)

## Knowledge base updates
- [x] `memory-bank/project-state.md` — cost fix noted in the plan import bullet
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: plan Task 10 constants

## Known gaps / not done
- The saving is an estimate (≈ $1.5–2 per Urban Colab run); it can only be measured once the API key has credits again.

---

## Verifier report (round 1)

VERDICT: PASS
TREE: bf334a73869e83e203430a0d231e27a80f65b598
C1–C4 MET. Suite 830 passed, 2 skipped; links OK; no secrets; score.py unchanged; cost arithmetic consistent (0.87 M × ~$5/MTok ≈ $4.35).
