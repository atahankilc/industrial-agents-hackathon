# Phones: Guide voice no longer hangs on iOS, streams not gzipped + pings, home-screen app setup

- **Author:** Claude session (mobile/voice), worktree `6-mobile` · **Date:** 2026-10-25 12:40
- **Related:** user report "mobile view looks bad, AI assistant never works, no voice, stuck at calculation step" (iPhone home-screen app on the Vercel deployment); D-016, D-018, D-019

## Summary
On the deployment the ElevenLabs key is missing, so iPhones used the browser voice, which iOS drops silently outside a
tap — the voice loop then waited forever ("Working"). Also gzip buffered the NDJSON Guide stream until the turn ended.
This makes the voice loop robust on iOS, un-gzips and pings the streams, adds a client stall watchdog, and sets the
app up as a proper home-screen app (safe areas, no focus zoom).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Audio unlock also runs on pointerup/touchend/click; first unlock speaks a silent utterance; audioSession set to playback when no mic is live | `frontend/app/src/voice/tts.ts` `unlockAudio`, `playbackSession` | read |
| C2 | Browser voice speaks one utterance at a time; an utterance not started in 4 s (`START_MS`) ends the browser voice, one without an end event counts as ended after `START_MS + chars*MS_PER_CHAR`; `start()` (onStart) fires on the utterance's real start | `voice/tts.ts` `speakBrowser` | read |
| C3 | On iOS the kept-warm mic is closed before the voice plays and no barge-in watcher starts while speaking | `voice/mic.ts` `dropMicrophone`, `microphoneLive`; `tts.ts` `audioReady`; `useVoice.ts` `stream` onStart | read |
| C4 | Scribe's capture AudioContext resumes on pointerup/touchend/click; mic `open()` sets audioSession to auto before capturing | `voice/scribe.ts`, `voice/mic.ts` `open` | read |
| C5 | `/chat/stream` and the Builder stream are not gzipped (NDJSON excluded) and send `{"type":"ping"}` after 10 s quiet; other JSON still gzipped | `backend/app.py` `ndjson_with_pings`, `PING_S`, GZipMiddleware args | `uv run pytest -q tests/test_backend.py -k "gzipped or pings"` |
| C6 | App aborts a Guide/Builder stream after 45 s without a byte with "The connection to the Guide was lost. Send it again."; ping lines are ignored | `frontend/app/src/api.ts` `watchedStream`, `readChat`, `readBuilder` | read |
| C7 | Home-screen app: `viewport-fit=cover`, `maximum-scale=1`, apple/mobile web-app metas, manifest | `frontend/app/index.html`, `frontend/app/public/manifest.webmanifest` | read |
| C8 | Touch devices: fields ≥16 px (no iOS focus zoom), no overscroll, no tap highlight; map sheet + controls clear of the home bar (safe-area), dvh; map credits start collapsed | `styles.css`, `map/map.css`, `map/MapLanding.tsx` | read |
| C9 | Docs + memory bank updated | `docs/architecture/ai-agents.md` (Phones paragraph), `docs/guides/commands.md` (ELEVENLABS row), `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` |

## Checks I ran

- `npx tsc -b` (frontend/app) → no errors
- `npx vite build` → `✓ built in 2.47s`, `dist/manifest.webmanifest` present
- `uv run pytest -q tests/test_backend.py tests/test_deploy.py tests/test_builder.py tests/test_access.py` → `63 passed`
- `python3 scripts/check_links.py` → `OK: all links resolve in 37 files`
- Deployment probe: `curl https://industrial-agents-hackathon.vercel.app/api/health` → `{"ok":true,"llm":"anthropic","tts":false,"stt":false}`; `/chat/stream` with `--compressed` → `content-encoding: gzip`, first line ~40 s after headers, all lines within 2 s
- Headless Chromium, iPhone-size viewport, local backend with keys: tap "Toilet" → orb Working → back to "Tap or hold to talk" (ElevenLabs on, and with `/tts` blocked → browser voice)
- Phone screenshots 393×800 and 375×667: building screen and typing bar fit; input font-size computed 16px

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (Phones bullet under What works, blocker: Vercel key)
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: ai-agents.md, commands.md

## Known gaps / not done
- Not tested on a real iPhone (no device access); iOS `speechSynthesis` / `audioSession` behaviour reasoned from WebKit behaviour, not observed.
- `ELEVENLABS_API_KEY` must be added on Vercel by the user (no Vercel CLI/access here); without it iPhones still have no ElevenLabs voice/Scribe.
- `compute` tool code still has no time limit when run in a worker thread (`agent/solver_agent.py` `run_code`); not the observed hang.
- Imports stream (`/imports/stream`) left without pings (its client passes every line on).

## Verification
Not verified: the user asked to commit without the commit-verifier (2026-10-25).
