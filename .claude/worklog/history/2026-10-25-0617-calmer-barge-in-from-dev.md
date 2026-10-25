# Calmer barge-in, readable nearby-buildings card, bigger map click target

- **Author:** Claude Code session · **Date:** 2026-10-25
- **Related:** D-018 (barge-in), user report: Guide interrupted by anything, nearby-building buttons unreadable in dark mode, buildings hard to click on the map

## Summary
Barge-in needs real speech (≥3 own words or a short stop phrase, 1 s grace, confirmed on two results); the nearby-buildings card gets its own theme-safe buttons and a layout that ellipsises names; map buildings open from pin, name, halo or block with 14 px slop.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `interruption` returns "stop" only for a stop word in ≤3 words, "talk" only for ≥3 own words that are ≥ half of the words; single stray words → null | `frontend/app/src/voice/bargeIn.ts` | read; `node --experimental-strip-types` check in log |
| C2 | barge-in ignores results for 1 s after the voice starts and needs "talk" on two consecutive results or a final one; judged on `userPart` | `frontend/app/src/voice/useVoice.ts` `watch`, `BARGE_GRACE_MS`, `spokeAt` | read |
| C3 | `.hud-pill` scoped as `.screen .hud-pill` so `.screen button {color: inherit}` no longer overrides its text colour | `frontend/app/src/building/hud.css` | read; computed style in Chrome |
| C4 | nearby card: Directions (route blue) + Open (outline) in `.acts`, names ellipsised, rows wrap | `building/Elsewhere.tsx`, `building/hud.css` "found in the buildings nearby" | read |
| C5 | map click/hover hit-test over pins, names, halos and model blocks with 14 px slop; block under pointer, else nearest pin | `frontend/app/src/map/MapLanding.tsx` `HIT_LAYERS`, `HIT_SLOP`, `hit` | read |
| C6 | ai-agents.md barge-in paragraph matches the new rules; log entry added | `docs/architecture/ai-agents.md`, `memory-bank/log.md` | read |

## Checks I ran
- `npx tsc -b` (frontend/app) → no output (clean)
- `npx oxlint …` → 3 warnings in useVoice.ts (react immutability on existing ref-sync effects), no errors
- `python3 scripts/check_links.py` → OK: all links resolve in 35 files
- Chrome dark/light: card buttons readable; off-pin click opened nearest building

## Knowledge base updates
- [x] `memory-bank/project-state.md` — not needed (polish of existing features)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: docs/architecture/ai-agents.md

## Known gaps / not done
- Barge-in not tested with a live microphone; thresholds may need tuning.
