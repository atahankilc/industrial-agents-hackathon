# AI layer of the app: live Guide steps, reply cards, voice orb, camera walk mode

- **Author:** Claude session industrial-agents-hackathon-83 · **Date:** 2026-10-24
- **Related:** docs/research/elevenlabs.md (voice later), D-011 (monochrome tokens)

## Summary
Makes the AI side of `frontend/app` richer: the chat shows what the Guide is doing while it works (streamed tool
steps), structured route/change cards and follow-ups, a voice mode with an orb (browser speech, no keys) and a camera
walk mode with turn-by-turn legs and "Where am I?" photo turns. Backend gains `/chat/stream`, `channel`/`photo` on chat,
and `core/directions.py`.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `Guide.on_step` reports tool start/finish and self-check re-runs; default None changes nothing | `agent/guide.py` (`step`, `run`, `reply`) | read diff; `uv run pytest tests/test_guide.py` |
| C2 | `POST /chat/stream` streams NDJSON steps then the `/chat` payload (or an error line); 422 on bad channel | `backend/app.py:chat_stream` | `tests/test_backend.py::test_chat_stream_steps_then_reply`, `::test_chat_voice_channel_and_bad_channel` |
| C3 | `/chat` accepts `channel` ("voice" fills `spoken`) and `photo` (data URL, jpeg/png/webp, 422 otherwise, 413 when > 1.5 M chars) | `backend/app.py` (`photo_or_422`, `channel_or_422`) | `tests/test_backend.py::test_photo_turn_is_answered_and_not_kept` |
| C4 | A photo is shown to the model for one turn and replaced by a text placeholder in history (never persisted) | `agent/guide.py:reply` (`PHOTO_KEPT`) | same test asserts no image block remains |
| C5 | Offline client answers photo turns from their text | `agent/offline_llm.py:create` | same test (offline) |
| C6 | `core/directions.py` legs: turn from plan geometry, kit-matching distances, merged connector hops; route events carry `legs` | `core/directions.py`, `backend/sessions.py:enrich` | `uv run pytest tests/test_directions.py` |
| C7 | Frontend: streamed steps, route card, change card, profile chip, follow-ups, voice orb (always visible: large in the empty chat, small in the composer; optional `--accent` with `--ink` fallback), camera walk mode; type-checks and builds | `frontend/app/src/{App.tsx,api.ts,ui/*,voice/*}` | `cd frontend/app && npx tsc -b && npx vite build` |
| C8 | Docs: commands.md endpoint table; memory-bank log + project-state | `docs/guides/commands.md`, `memory-bank/` | read; `python3 scripts/check_links.py` |
| C9 | Voice orb is WebGL (three.js points + simplex-noise shader, rim/depth fade, CSS glow from the level), follows `--accent`/`--ink` and light/dark blending | `frontend/app/src/ui/VoiceOrb.tsx` | read; screenshots in light + dark |
| C10 | Voice mode is a stage (orb, live transcript, live steps, spoken reply caption); recognition errors are shown per code, no silent end; meter starts on `audiostart`, `audio-capture` retries once without it | `frontend/app/src/ui/Chat.tsx:VoiceStage`, `frontend/app/src/voice/useVoice.ts` | read; fake-mic Chrome run shows the messages |
| C11 | Only this session's work is staged: memory-bank log/state contain only the AI-layer entry/bullet; the other session's files (Root.tsx, main.tsx, map/, search/, twin-lab/, package*.json, visualization.md, open-questions.md, .gitignore, build_map_assets.py) are not staged | staged diff | `git diff --cached --stat` |
| C12 | Third-party code declared: the `NOISE` GLSL (3D simplex noise) in VoiceOrb.tsx is adapted from stegu/webgl-noise (fork of ashima/webgl-noise), MIT; the full upstream copyright + permission + warranty text sits in a JS comment above `NOISE`, and NOTICE.md lists it (D-009) | `frontend/app/src/ui/VoiceOrb.tsx`, `NOTICE.md` | `grep -n "Gustavson\|Ashima" frontend/app/src/ui/VoiceOrb.tsx NOTICE.md`; compare with `curl -s https://raw.githubusercontent.com/stegu/webgl-noise/master/LICENSE` |

## Checks I ran
- `GUIDE_LLM=offline uv run pytest -q` → `188 passed, 1 skipped`
- `npx tsc -b` → no output; `npx vite build` → `✓ built` (existing >500 kB chunk warning)
- `npx oxlint src/ui src/voice src/App.tsx src/api.ts` → only `only-export-components` warnings in `TurnIcon.tsx`
- Headless Chrome (Playwright, fake camera, offline Guide on :8766, Vite :5182): route card, follow-ups, change turn, camera view steps 1–2, "Where am I?" answer, voice dock — screenshots, no page errors
- Live Opus 5.5 photo turn (synthetic "3.07 Meeting room" sign): search + show_on_map, correct room, 0 ungrounded, image not kept
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`
- Fake-mic Chrome (Playwright, `--use-file-for-fake-audio-capture`): with the parallel meter → `audio-capture` (now retried); after the fix → "I didn't catch that…" shown, no silent end. Chrome automation does not feed its speech service, so real recognition is unverified.
- Orb screenshots light + dark (empty chat) after thinning: 1300–1700 points, fainter alpha.
- Fix round 1: `curl -s https://raw.githubusercontent.com/stegu/webgl-noise/master/LICENSE` → notice copied verbatim; `grep -n "Gustavson\|Ashima" frontend/app/src/ui/VoiceOrb.tsx NOTICE.md` → `NOTICE.md:13`, `VoiceOrb.tsx:19`, `VoiceOrb.tsx:20`; `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`; `cd frontend/app && npx tsc -b` → no output (exit 0); `GUIDE_LLM=offline uv run pytest -q` → `188 passed, 1 skipped`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions touched: none
- [x] docs touched: `docs/guides/commands.md`

## Known gaps / not done
- Real-microphone recognition not confirmed by me (Atahan to try); voice and camera not tried on a real phone (needs HTTPS: the deployed URL); browser speech quality varies by OS.
- Turns are relative to the walking direction (no compass/positioning); corridor anchors are centroids, so a
  "turn left" in a long corridor is approximate.
- ElevenLabs voice not wired; `useVoice` is the adapter to swap.

## Verification rounds
- Round 1: FAIL — missing MIT notice for the simplex-noise GLSL in VoiceOrb.tsx (+ NOTICE.md entry)

## Fix round 1
- MIT notice for simplex-noise GLSL: implemented — upstream copyright lines (Ashima Arts 2011, Stefan Gustavson 2011-2016) + full MIT permission and warranty text as a JS comment block above `NOISE` in `frontend/app/src/ui/VoiceOrb.tsx`
- NOTICE.md entry: implemented — new row for `frontend/app/src/ui/VoiceOrb.tsx` (upstream URLs, MIT, copyright holders) in `NOTICE.md`
- PENDING.md: implemented — added claim C12 and the round-1 checks
- Round 2: PASS (TREE 2bed13a2)

---

# Verification report (round 2)

VERDICT: PASS
TREE: 2bed13a208c6a263c38dd9794f970c210e09063d

Claims C1–C12 MET. Standard checks: pytest 188 passed / 1 skipped (repo root); check_links OK (26 files); no secrets; score.py unchanged; no hard-coded test ids. Frontend: tsc -b and vite build clean on an index export (only the >500 kB chunk warning). C9/C10 verified by code reading (headless/fake-mic/live runs not re-run). C11: none of the other session's files staged. C12: MIT notice in VoiceOrb.tsx matches upstream LICENSE word for word; NOTICE.md entry present.
Undeclared (minor, within intent): 'applied' message role, auto-growing composer, media_type check in Guide.reply.
Round 1 (FAIL): missing MIT notice for the simplex-noise GLSL; fixed by commit-fixer.
