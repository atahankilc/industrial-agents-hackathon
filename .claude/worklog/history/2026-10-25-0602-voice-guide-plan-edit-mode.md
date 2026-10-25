# Voice (ElevenLabs + Scribe, barge-in), Guide on the plan + figure + step guide + nearby buildings, Edit mode inside the building view

- **Author:** Claude Code session (worktree `voice-improvements`) · **Date:** 2026-10-25
- **Related:** D-016 … D-021 (new), Q-020 (new), D-006, docs/research/elevenlabs.md, docs/architecture/ai-agents.md#voice-path

## Summary
The app spoke with the browser's robotic speechSynthesis; ElevenLabs was never wired up. Step 1 adds `POST /tts`
(ElevenLabs Flash v2.5, voice "River", key server-side) and a frontend voice module with browser fallback. Step 2
streams grounded sentences of voice replies as they are written (plus a fact-free "let me check" first). Step 3 makes
spoken questions a hands-free conversation with barge-in and a 1.0 s end-of-utterance pause (1.3 s before the C30 latency pass). Step 4 sends the
user's words to ElevenLabs Scribe Realtime with the building's keyterms (browser recognition as fallback).

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `POST /tts` streams `audio/mpeg` from ElevenLabs `/v1/text-to-speech/{voice}/stream`, text passed through `speakable()`, `language_code` from the first two letters of `lang` | `backend/tts.py`, `backend/app.py:text_to_speech` | `uv run pytest -q tests/test_tts.py` |
| C2 | No key → 503; empty after `speakable()` → 422; > 1,000 chars → 413; ElevenLabs HTTP error or network error → 502 | `backend/app.py:text_to_speech`, `backend/tts.py:open_stream` | `tests/test_tts.py` |
| C3 | Defaults voice `SAz9YHcvj6GT2YYXdXww` ("River") and `eleven_flash_v2_5`; `TTS_VOICE_ID` / `TTS_MODEL` override | `backend/tts.py` | `tests/test_tts.py::test_voice_and_model_come_from_the_environment` |
| C4 | `/health` returns `"tts": bool` (key set) | `backend/app.py:health` | `tests/test_tts.py`, `tests/test_backend.py::test_health_and_buildings` |
| C5 | Frontend speaks via `speakAloud` (ElevenLabs pieces fetched one ahead, Web Audio level → orb; browser speechSynthesis when `/health` says no tts, audio is locked, or a piece fails twice — one retry, then 15 s cool-off; values as amended by C30); `silence()` stops both voices; `useVoice`, `say`, `hearOnce`, `CameraGuide` no longer call speechSynthesis directly | `frontend/app/src/voice/tts.ts`, `voice/useVoice.ts`, `ui/CameraGuide.tsx`, `api.ts:speech` | read; `grep -n speechSynthesis frontend/app/src -r` → only `voice/tts.ts` and the `getVoices()`/`voiceSupported` lines in `useVoice.ts`; `npm run build --prefix frontend/app` |
| C6 | Sentence splitting keeps "Room 2.03" in one sentence | `voice/tts.ts:sentences` | read the regex (period must be followed by whitespace or end) |
| C7 | Voice state stays "thinking" until the first sound plays (`onStart` → "speaking") | `voice/useVoice.ts:speak` | read |
| C8 | Docs and memory bank updated (commands `/tts` row + env vars + smoke test, ai-agents voice path, elevenlabs.md tier + status, D-016, project-state, log, `.env.example`) | listed files | read; `python3 scripts/check_links.py` |
| C9 | Step 2: `SpokenStream` emits a sentence only when complete (whitespace after `.!?`, or newline; "3.07" and lone list markers never end one) and grounded; first ungrounded sentence or `hold()` stops live speech; `finish(reply)` emits only sentences not said yet | `agent/speech.py` | `uv run pytest -q tests/test_speech.py` |
| C10 | Guide: voice turns with `on_say` stream requests via `beta.messages.stream` (real `anthropic.Anthropic` only; other clients feed whole text blocks), hold speech before the grounding repair and profile redo, and from the start when the message has an unsatisfied profile cue; `speech` reset per turn | `agent/guide.py` `reply`, `spoken_stream`, `hold_speech`, `request`, `streamed` | `tests/test_speech.py::test_guide_*` |
| C11 | `VOICE_STYLE` asks for one fact-free sentence before the first tool call | `agent/guide.py` | read |
| C12 | `/chat/stream` voice turns send `{"type":"say","text"}` lines before `reply`, joined equal to `spoken` in the offline route test; text turns send none; `on_say` cleared after the turn | `backend/app.py:chat_stream` | `tests/test_backend.py::test_chat_stream_voice_says_sentences_before_the_reply` |
| C13 | Frontend: `openSpeech` queue (add/end; text arriving mid-play is fetched at once; fallback hands unspoken text to the browser voice); `voice.stream()`; `api.chatStream` `onSay`; `BuildingScreen` opens the voice on the first `say` and ends it after the reply (or on error) | `voice/tts.ts`, `voice/useVoice.ts`, `api.ts`, `building/BuildingScreen.tsx` | read; `npm run build --prefix frontend/app` |
| C14 | Step 2 docs: commands `/chat/stream` row, ai-agents voice path paragraph, D-017, project-state, log | listed files | read; `python3 scripts/check_links.py` |
| C15 | Step 3: recognition is `continuous`; an utterance ends 1.0 s after the last result (`END_PAUSE_MS`, lowered from 1.3 s by C30), 8 s with no words after a tap, 6 s when listening started by itself (quiet, no error), 2 s after carried-over words | `voice/useVoice.ts:listenWith` | read |
| C16 | `stream({ conversation: true })` (with `handsFree`): watcher recogniser (`watch`) starts on `onStart`, the reply's first sound, which can be the fact-free preamble while the Guide turn is still pending (`BuildingScreen.tsx` opens the stream on the first `say`); it runs while any part of the reply plays and is restarted after 250 ms if the browser ends it while still speaking; `unwatch` aborts it when a new stream opens, on speech end (`onEnd`), on `stop()`, when listening starts (`listenWith`), and once it has detected an interruption; after the reply ends (`onEnd`, state still speaking) it listens again (`auto`) after 200 ms. Words that interrupt while the turn is pending are queued and sent when it is done (C30) | `voice/useVoice.ts:stream`, `watch`, `unwatch` | read |
| C17 | Echo filter: `userWords` ignores the Guide's words, 3-letter stems of 4+ letter words, digits, number words and single letters; `interruption` → "talk" for ≥ 3 own words; otherwise "stop" if any own word is a stop word; otherwise "talk" for 2 own words or any own word of ≥ 3 letters; else null; `userPart` starts at the first mostly-own result | `voice/bargeIn.ts` | read; node smoke run in Checks |
| C18 | `BuildingScreen` no longer forces `setHandsFree(false)`; spoken replies use `conversation: true`, typed/walk-step speech doesn't; orb hint "Talk to interrupt · tap to stop" while the watcher runs | `building/BuildingScreen.tsx`, `building/Guide.tsx`, `building/Core.tsx` comment | read; `npm run build --prefix frontend/app` |
| C19 | Step 3 docs: ai-agents voice path paragraph, D-018, project-state, log; fix round 3: ai-agents.md#voice-path and the D-018 amendment say the watcher runs from the reply's first sound (preamble included) and that words heard while a turn is pending are queued and sent after it | listed files | read; `python3 scripts/check_links.py` |
| C20 | Step 4: `POST /stt/token` returns a single-use token from `POST /v1/single-use-token/realtime_scribe` (xi-api-key) and the session building's keyterms (none without session; unknown session → 404); Scribe off → 503, refusal → 502; `/health` `"stt"`; `STT_MODE=browser` turns it off | `backend/stt.py`, `backend/app.py:speech_to_text_token`, `health` | `uv run pytest -q tests/test_stt.py` |
| C21 | `keyterms`: ≤ 50 terms, ≤ 20 chars, no digits, case-insensitively unique; places (spaces, connectors, floors) before asset names before types, each by frequency | `backend/stt.py:keyterms` | `tests/test_stt.py::test_keyterms_fit_the_api_limits_and_put_places_first` |
| C22 | `ScribeRecognition` has the SpeechRecognition shape; mic first (AudioWorklet → 16 kHz int16, buffered until open), token fetched ahead, `commit_strategy=manual`, keyterms as repeated query params, only changed partials emitted, committed → finals, `stop()` commits and waits 0.8 s (`COMMIT_WAIT_MS`, lowered from 2 s by C30), errors → `not-allowed` / `audio-capture` / `no-speech` / `scribe-unavailable` (60 s cool-off) | `frontend/app/src/voice/scribe.ts` | read; `npm run build --prefix frontend/app` |
| C23 | `useVoice` uses Scribe when `scribeReady()`, else the browser; `scribe-unavailable` retries once with browser recognition; `hearOnce` stays on the browser's; `BuildingScreen` calls `setScribeSession(sessionId)`; `api.sttToken` | `voice/useVoice.ts`, `building/BuildingScreen.tsx`, `api.ts` | read |
| C24 | Step 4 docs: commands `/stt/token` row + `STT_MODE` + smoke test, ai-agents paragraph, elevenlabs.md status + verified limits, `.env.example`, D-019, Q-020, project-state, log | listed files | read; `python3 scripts/check_links.py` |

| C25 | Guide answers on the plan: `search` / `locate` / `room_facts` / `show_on_map` emit highlights with `asset_ids`; PlanView tints/badges rooms, rings items and frames them (`focus`) | `agent/tools.py`, `frontend/app/src/plan/PlanView.tsx` | read; full pytest |
| C26 | "You are here" figure: `PUT /sessions/{id}/location`, `session.user_location` + `guide.location_note` persisted; Guide tool `set_my_location` + event `location`; offline Guide understands "I'm in/at …" | `backend/app.py`, `backend/persistence.py`, `agent/guide.py`, `agent/tools.py`, `agent/offline_llm.py`, `dev/StoryLayer.tsx` | `uv run pytest -q tests/test_voice_location.py` |
| C27 | D-020: route replies are a summary + first step; app frames the whole route, Start → step by step with "I'm there" / "geldim" / "next" | `agent/guide.py` INSTRUCTIONS/VOICE_STYLE, `building/NextMove.tsx`, `building/BuildingScreen.tsx` | read |
| C28 | D-021: `agent/campus.py` `search_nearby_buildings` / `route_to_building` (pins ≤ 600 m, shortest entrance pair, straight-line outdoor leg), `POST /sessions/{id}/arrive` (`from_session` loaded through `conversation_or_404(body.from_session, authorization)` — the same access check as the target session; a session the viewer may not see is ignored, its profile not copied); app "found nearby" card + Continue | `agent/campus.py`, `backend/app.py`, `building/Elsewhere.tsx` | `uv run pytest -q tests/test_campus.py tests/test_backend.py` |
| C29 | Tapped questions answered aloud: `/chat` `heard: false` → spoken, not rewritten; `selected` → selection note | `backend/app.py`, `agent/guide.py`, `frontend/app/src/api.ts` | `tests/test_rewriter.py::test_tapped_voice_turn_is_spoken_but_not_rewritten`, `tests/test_backend.py::test_chat_voice_channel_and_bad_channel` |
| C30 | Voice latency/robustness: end pause 1.0 s, Scribe commit wait 0.8 s, warm mic (`voice/mic.ts`), TTS piece retried once, cool-off 15 s; an utterance spoken while a Guide turn is still pending is queued (`queued` ref in `BuildingScreen.tsx`) and sent once that turn is done | `voice/useVoice.ts`, `voice/scribe.ts`, `voice/tts.ts`, `voice/mic.ts`, `voice/bargeIn.ts`, `building/BuildingScreen.tsx` | read; build |
| C31 | Edit mode lives inside the building view: `EditMode.tsx`, `PlanEditor.tsx`, `BuilderChat.tsx` deleted; draft shown on the model, handles in `edit/EditLayer.tsx` aligned via PlanView `align`; Guide card talks to the Builder while editing (`Guide.tsx` `persona`/`card`); `EditBar`, `EditCard`, `Inspector`, `useDraft` (undo/redo), `place.ts`, `presets.ts`, `types.ts` | `frontend/app/src/edit/*`, `building/Guide.tsx`, `building/BuildingScreen.tsx`, `plan/PlanView.tsx` | read; `npx tsc -p tsconfig.app.json --noEmit`; build |
| C32 | Guide tool `open_edit_mode(request?)` → event `edit_mode`; offline intent `EDIT` | `agent/tools.py`, `agent/guide.py`, `agent/offline_llm.py` | `uv run pytest -q tests/test_edit_mode_tool.py` |
| C33 | PlanView view behaviour: labels kept when zoomed out, one tap on stacked view selects, floor change keeps camera, `FloorGlow` hover; a compass button (`CompassTracker` turns the rose with the camera) eases the camera round to north-up via `northUp`, keeping target, zoom and tilt; a refit keeps the user's own turn and tilt (a flat look on the stacked view goes back to the default tilt) | `plan/PlanView.tsx` | read |
| C34 | SUBMISSION/BENCHMARK.md documents the default hybrid command (with `--env-file .env`) and the regex no-key variant | `SUBMISSION/BENCHMARK.md` | read |
| C35 | Docs + memory bank for C25–C34: D-020, D-021, visualization.md, ai-agents.md, project-state, log; C30 values also in ai-agents.md voice path, project-state, and dated amendments to D-016 / D-018 / D-019; C30 `queued` behaviour (utterance during a pending Guide turn sent once it is done) in ai-agents.md#voice-path, project-state voice bullet and the D-018 amendment (fix round 3) | listed files | `python3 scripts/check_links.py`; `grep -rn "1\.3 s\|≤ 2 s\|60 s" docs memory-bank` → only historical/amendment text and Scribe's 60 s |
| C36 | UI pieces of the same change: the "Show where you are?" ask is a centred modal over a dimmed map (scrim, pin icon, Escape = Not now, "Allow location" first); `Story` gets `asset_ids` from highlights, `elsewhere` (nearby buildings), the route's `next` (route_to_building) and the `Outdoor` walk type; step labels for the Builder's tools (`overview`, `find`, `space_info`, `floor_plan`, `propose_edit`); hud.css styles answer markers (rooms, items, next-building badge), the "you are here" figure with its dock, the compass, the guide's actions and the Elsewhere list | `frontend/app/src/map/MapLanding.tsx`, `map/map.css`, `dev/story.ts`, `ui/guideSteps.ts`, `building/hud.css` | read `git diff --cached -- <file>`; `npm run build --prefix frontend/app`; `npx tsc -p tsconfig.app.json --noEmit` (frontend/app) |

## Checks I ran
- `uv run pytest -q` → `762 passed, 2 skipped in 123.31s`
- `npm run build --prefix frontend/app` → `✓ built in 1.32s` (only the existing chunk-size warning)
- `npm run lint --prefix frontend/app` (step 1 only, at that time) → no new warnings in the files step 1 touched (the `useVoice.ts` listenRef warning predates this change); see Fix round 2 for the full-branch lint result
- `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Live (real key): `/tts` en 200 audio/mpeg 1.29 s, de 0.34 s; Scribe STT heard back "Meeting room 3.07 is on your left, about 124 meters from here."
- Live in Chrome (offline Guide + real ElevenLabs): `speakAloud` first sound 371 ms, finished at 7.2 s, orb level peak 0.69, `speechSynthesis.speaking` false; `silence()` mid-speech → no onEnd; `/tts` forced to 502 → browser voice spoke and finished; network `POST /api/tts 200`.

Step 2:
- `uv run pytest -q` → `769 passed, 2 skipped in 111.63s`
- `npm run build --prefix frontend/app` → `✓ built in 502ms`; `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Live in-process trace (Opus 5.5 medium): preamble said at 2.16–2.25 s; after-tool answer deltas all arrived in one burst (with and without the fallback beta)
- Live in Chrome via `/chat/stream` + `openSpeech`: say "Let me check the toilets near that meeting room." 2.09 s, AUDIO START 2.35 s, answer says 10.44 s, reply 10.47 s, AUDIO END 28.85 s

Step 3:
- `npm run build --prefix frontend/app` → `✓ built in 516ms`; lint: only the existing ref-in-effect warning pattern in `useVoice.ts`
- node `--experimental-strip-types` smoke run of `bargeIn.ts`: echo sentence → null, "stop"/"Stopp" → stop, "wait where is the kitchen" → talk; `userPart(["About 60 m, stairs allowed.", "actually where is the nearest toilet"])` → the second only
- Chrome, real UI with a scripted SpeechRecognition (offline Guide, real ElevenLabs): 0.9 s mid-question pause kept, sent 1.3 s after last words; watcher started with the reply; echo "About 60 meters, stairs allowed." ignored; "actually where is the nearest toilet" interrupted and was sent as exactly that 2.0 s later; "stop" → off, no listener, no error; auto-listen stopped after 6 s quietly (traced: no-words timer)

Step 4:
- `uv run pytest -q` → `773 passed, 2 skipped in 95.58s`; `npm run build --prefix frontend/app` → `✓ built in 471ms`; `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- Live probes in Chrome with real tokens: repeated `keyterms` → session_started config lists them; JSON-array encoding and a 39-char term → `invalid_request` (20-char limit); 50 terms ok, 51 and 100 → "Number of keyterms cannot exceed 50"
- Chrome end to end (factory dev-003, offline Guide, ElevenLabs-spoken "Where is the CNC mill?" fed as the mic): ws opened with 50 keyterms, partial "Where is the CNC mill?" 10.2 s, committed 11.8 s, SENT "Where is the CNC mill?", Guide answered aloud, barge-in watcher opened its own Scribe session. First run found Scribe repeating the same partial every ~1 s (pause never fired) → fixed
- Token request forced to 502: Scribe cooled off, browser recognition used (question sent, reply spoken, watcher on browser recognition), no error shown

Full branch (all chunks, before shipping):
- `GUIDE_PERSIST=off uv run pytest -q` → `810 passed, 2 skipped in 94.37s`
- `npm run build --prefix frontend/app` → `✓ built in 550ms` (chunk-size warning only)
- `npx tsc -p tsconfig.app.json --noEmit` (frontend/app) → exit 0
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- Browser checks for C25–C33: see memory-bank/log.md 2026-10-25 entries (headless Chrome runs)

Fix round 1 (after verifier round 1 FAIL):
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- `uv run pytest -q` → `810 passed, 2 skipped in 95.34s (0:01:35)`
- `npm run build --prefix frontend/app` → `✓ built in 531ms` (chunk-size warning only)
- `npx tsc -p tsconfig.app.json --noEmit` (frontend/app) → exit 0
- `grep -rn "1\.3 s\|≤ 2 s\|60 s" docs/architecture memory-bank/decisions.md memory-bank/project-state.md` → only D-016/D-018
  original text with a dated amendment below it, the amendments themselves, the Scribe 60 s cool-off (unchanged), the
  "was 1.3 s" note in ai-agents.md, and an unrelated `/plan` timing in project-state.md:236
- Code values read: `useVoice.ts:90` `END_PAUSE_MS = 1000`; `scribe.ts:13` `COMMIT_WAIT_MS = 800`, `:14` `MIC_WARM_MS = 8000`,
  `:15` `COOL_OFF_MS = 60_000`; `tts.ts:39` `COOL_OFF_MS = 15_000`, one retry at `:205`; `bargeIn.ts:42-47` `interruption`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: D-016 … D-021 added; Q-020 opened
- [x] docs touched: commands.md, ai-agents.md, elevenlabs.md, visualization.md, SUBMISSION/BENCHMARK.md

## Known gaps / not done
- `.claude/worktrees/` (a git worktree) is deliberately not committed.
- Lint (oxlint, warnings only, exit 0): 26 warnings on the full branch. New ones in files this change touches, not
  refactored: `edit/EditLayer.tsx:64`, `:91` (set-state-in-effect), `:175`, `:185` (refs during render, `:185` twice);
  `plan/PlanView.tsx:109` (set-state-in-effect), `:1236-1237` (immutability); `voice/useVoice.ts:333` (immutability).
  Others in touched files of the same kinds also show (`edit/Inspector.tsx:72`, `edit/useDraft.ts:346`,
  `dev/StoryLayer.tsx`, `plan/PlanView.tsx:1242`, `:1342`, `voice/useVoice.ts:283`, `:409`); not all were checked
  against the previous commit.
- Route overview does not frame the other building's entrance (dashed line runs off screen); no street graph; the other building's leg ignores closures; interaction-eval "directions" rubric still expects full step lists.
- Edit mode: not checked on a real touch device; redo lost on reload.
- After-tool answers arrive from the API in one burst, so live sentence streaming mostly helps the first sentence.
- The live chat bubble does not show the streamed sentences until the reply arrives.
- `/v1/chat/completions` still answers at the end (could use `on_say` later).
- Barge-in / conversation not tried with a real mic and speakers (echo level, Bluetooth call-quality switch); Scribe tested with synthetic mic audio only.
- Words said over the preamble (turn still pending) do interrupt: the voice is cut and they are queued, then sent once the turn is done (`BuildingScreen.tsx` `queued`), so the rest of the first reply is not spoken (its voice run was stopped by `silence()`; it still appears in the chat); not tried with a real mic.
- `/tts` has no auth beyond the 1,000-char cap; units are spelled in English for de/tr voices.
- Not tested on Safari / iOS or with a real mic in the full UI loop (automation can't speak).
- `ELEVENLABS_API_KEY` must be added to Vercel env for the deployed app.
- Scribe usage cost (every listen and the barge-in watcher stream audio) against the Creator tier is UNVERIFIED; the rewriter still runs on Scribe transcripts (Q-020).
- No frontend unit tests (the app has no test runner); the voice modules are covered by the Chrome runs above.

## Verification rounds
- Round 1: FAIL (stale voice timings in docs/claims, C17 wording, undeclared UI files)

## Fix round 1
- Fix 1 (stale voice timings in KB): implemented — `docs/architecture/ai-agents.md` (TTS: one retry then 15 s pause;
  end pause 1.0 s, noting it was 1.3 s; Scribe `stop()` waits 0.8 s, warm mic via `voice/mic.ts` + 8 s `MIC_WARM_MS`,
  Scribe 60 s cool-off kept); `memory-bank/project-state.md` (1.0 s pause, D-018 amended); `memory-bank/decisions.md`
  dated "Amendment (2026-10-25)" lines added under D-016, D-018 and D-019 (original text left as is)
- Fix 2 (C5, C15, C22 values): claim corrected — C5 now one retry then 15 s cool-off, C15 1.0 s, C22 0.8 s, each noting
  the C30 change; Summary says 1.0 s
- Fix 3 (C17 + ai-agents.md interruption wording): claim corrected — both now describe `interruption` as the code does
  (≥ 3 own words → talk; else any stop word → stop; else 2 own words or any own word of ≥ 3 letters → talk; else null).
  Note: the stop-word check comes before the 2-word / ≥ 3-letter rule, so "stop" alone gives "stop"
- Fix 4 (undeclared files): claim corrected — added C36 for MapLanding.tsx, map.css, story.ts, guideSteps.ts, hud.css,
  written from their staged diffs. The guideSteps labels are for the Edit mode Builder's tools; the hud.css diff has no
  step-guide or Edit-mode rules (grep of its added lines for "step" and "edit" finds none), so C36 does not claim them
- C35 extended to list the C30 values in the KB and the decision amendments
- Round 2: FAIL (endpoint/tool docs, stale recognition text, post_arrive from_session access check, undeclared compass/queue, lint line)

## Fix round 2
- Fix 1 (commands.md endpoint table): implemented — `docs/guides/commands.md`: `/health` lists `"tts"`, `"stt"`
  (`backend/app.py:242`); `/chat` body adds `"heard"?` (false = tapped text: spoken, not rewritten; `agent/guide.py:401`)
  and `"selected"?` (space or asset id → selection note); new rows `PUT /sessions/{id}/location` (`LocationRequest`
  `{"space_id"|null}` → `{"location"}`, unknown space → 422) and `POST /sessions/{id}/arrive` (`ArriveRequest`
  `{"entrance","destination","from_session"?}` → `{"route","location","events"}`, MapError/KeyError → 422,
  `from_session` only used if the viewer may see it). Every route added in `git diff --cached backend/app.py`
  (`/stt/token`, `/tts`, `/sessions/{id}/location`, `/sessions/{id}/arrive`) now has a row
- Fix 2 (ai-agents.md Guide tools): implemented — `docs/architecture/ai-agents.md` tool table: `show_on_map(space_ids?,
  asset_ids?)`, `set_my_location(place)` → `location`, `open_edit_mode(request?)` → `edit_mode`,
  `search_nearby_buildings(query)` / `route_to_building(start, building, destination)` only with located neighbours
  (`agent/tools.py:496-504` `tool_definitions`, `CAMPUS_TOOLS`); "Implemented" paragraph lists them and "here" as a place (`HERE`)
- Fix 3 (stale recognition text): implemented — `memory-bank/project-state.md` drops "recognition is still the
  browser's"; `docs/architecture/ai-agents.md` "What the app runs today" says Scribe when `/health` `stt` is true,
  browser SpeechRecognition as fallback
- Fix 4 (post_arrive from_session access check): implemented by the implementer before this round (`backend/app.py`
  `post_arrive` loads it via `conversation_or_404(body.from_session, authorization)`, ignored on HTTPException);
  C28 extended to say so; not changed here
- Fix 5 (PENDING declarations): claim corrected — C33 adds the compass / north-up easing (`CompassTracker`, `northUp`)
  and keeping the user's tilt on refit; C30 adds queued utterances while a turn is pending (`queued`,
  `BuildingScreen.tsx`); the step-1 lint line is scoped to step 1; current lint count and the new warnings in touched
  files listed under Known gaps

Checks (fix round 2):
- `npm run lint --prefix frontend/app` → exit 0, 26 warnings, 0 errors (list in Known gaps)
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- `GUIDE_PERSIST=off uv run pytest -q` → `810 passed, 2 skipped in 95.44s (0:01:35)`
- Round 3: FAIL (barge-in watcher timing vs docs; queuing not documented)

## Fix round 3
Option (b): code kept (watcher from the reply's first sound; utterances during a pending turn queued). No code changed.
- Fix 1 (barge-in watcher timing): claim corrected — PENDING.md C16 now describes `useVoice.ts` `stream`/`watch`/`unwatch`
  as written: `watch()` on `onStart` (first sound, preamble included, turn may be pending), restarted after 250 ms if
  the browser ends it while speaking, aborted by `unwatch` on new stream / `onEnd` / `stop()` / `listenWith` / after
  firing, auto-listen 200 ms after the reply ends. `memory-bank/decisions.md` D-018: existing 2026-10-25 amendment
  extended (original text untouched). `docs/architecture/ai-agents.md#voice-path`: "once its reply is complete" and
  "Barge-in waits for the complete reply because a question can't be sent while one is pending" replaced; 200 ms
  added. Known gap "Words said over the preamble … don't interrupt" rewritten to what `BuildingScreen.tsx` `queued` does.
- Fix 2 (C30 `queued` undocumented): implemented — `docs/architecture/ai-agents.md#voice-path` and the
  `memory-bank/project-state.md` voice bullet say an utterance spoken while a Guide turn is pending is sent once that
  turn is done (`BuildingScreen.tsx` `queued`).
- C19 and C35 extended to name these doc changes.

Checks (fix round 3):
- `python3 scripts/check_links.py` → `OK: all links resolve in 35 files`
- `GUIDE_PERSIST=off uv run pytest -q` → `810 passed, 2 skipped in 97.23s (0:01:37)`
- `grep -rn "once complete\|complete reply\|can't be sent while\|preamble.*don't interrupt" docs memory-bank .claude/worklog/PENDING.md`
  → only `decisions.md:269` (original D-018 text, superseded by the amendment), `decisions.md:284` (the amendment
  quoting it) and `log.md:170` (historical step-3 log entry; the later "Voice gaps" entry states the current behaviour)
- Round 4: PASS


## Verification report (final round)

VERDICT: PASS
TREE: f5e0e1d407db5a7a26c4da1124b1d1b45bd156e7

## Claims
C1–C36: all MET (evidence per claim in the verifier's report: code locations read, named tests passing; 78 passed across the claim test files).

## Standard checks
- pytest: `GUIDE_PERSIST=off uv run pytest -q` → 810 passed, 2 skipped (two runs, 100.27s and 92.50s)
- links: OK: all links resolve in 35 files
- secrets: none found; no .env staged; xi-api-key only as a header name reading os.environ
- score.py unchanged: yes
- hard-coding: none found
- frontend: npm run build ✓ built in 603ms (chunk-size warning only); tsc -p tsconfig.app.json --noEmit exit 0; lint warnings only (listed in Known gaps)
- live / Chrome checks not re-runnable by the verifier

## Undeclared changes
- None significant. .claude/worktrees/ untracked and not staged, as declared.
- Advisory: memory-bank/project-state.md still says "not committed yet" in the new bullets; drop in a later chunk.

## Required fixes
None.
