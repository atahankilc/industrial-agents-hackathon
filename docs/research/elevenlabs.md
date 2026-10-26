---
id: research-elevenlabs
summary: What ElevenLabs offers for our voice-first building guide (Agents platform, Scribe STT, TTS, extras), and a recommended integration architecture.
status: research (2026-10-24) — facts cite official docs; third-party or unconfirmed items are marked UNVERIFIED
sources:
  - https://elevenlabs.io/docs/agents-platform/customization/llm
  - https://elevenlabs.io/docs/eleven-agents/customization/llm/custom-llm
  - https://elevenlabs.io/docs/agents-platform/customization/tools/client-tools
  - https://elevenlabs.io/docs/agents-platform/customization/tools/server-tools
  - https://elevenlabs.io/docs/agents-platform/customization/tools/mcp
  - https://elevenlabs.io/docs/agents-platform/customization/tools/system-tools
  - https://elevenlabs.io/docs/agents-platform/customization/authentication
  - https://elevenlabs.io/docs/eleven-agents/api-reference/conversations/get-webrtc-token
  - https://elevenlabs.io/docs/agents-platform/libraries/react
  - https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow
  - https://elevenlabs.io/docs/eleven-agents/overview
  - https://elevenlabs.io/docs/eleven-agents/customization/voice/pronunciation-dictionary
  - https://elevenlabs.io/docs/capabilities/speech-to-text
  - https://elevenlabs.io/docs/eleven-api/resources/libraries/scribe-stt/react-scribe
  - https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/client-side-streaming
  - https://elevenlabs.io/docs/api-reference/tokens/create
  - https://elevenlabs.io/docs/models
  - https://elevenlabs.io/docs/eleven-api/guides/how-to/best-practices/latency-optimization
  - https://elevenlabs.io/docs/developers/guides/cookbooks/multi-context-web-socket
  - https://elevenlabs.io/docs/overview/capabilities/voice-isolator
  - https://elevenlabs.io/docs/api-reference/audio-isolation/stream
  - https://www.getmacha.com/blog/elevenlabs-agents-pricing-explained (third-party pricing)
  - https://www.cloudzero.com/blog/elevenlabs-pricing/ (third-party pricing)
related: [../architecture/overview.md, ../product/personas.md]
---

# ElevenLabs for "Talk to Your Building"

[Docs index](../README.md) · Architecture: [overview.md](../architecture/overview.md) · Personas:
[personas.md](../product/personas.md)

Voice counts towards the **Interaction** score (25 pts), per [brief.md](../../archive/hackathon/docs/challenge/brief.md#judging). The
team has an ElevenLabs subscription: **Creator** tier, 131,000 characters per month (`GET /v1/user/subscription`,
2026-10-25); agent minutes and concurrency are still UNVERIFIED.

**Built so far (2026-10-25) — Architecture B, not the Agent:** TTS via `POST /tts` → Flash v2.5, voice "River"
([D-016](../../memory-bank/decisions.md#d-016)); Scribe Realtime from the browser with a single-use token and the
building's keyterms ([D-019](../../memory-bank/decisions.md#d-019)); our own turn-taking and barge-in
([D-018](../../memory-bank/decisions.md#d-018)); browser speech as fallback for both. Details:
[ai-agents.md](../architecture/ai-agents.md#voice-path). The Custom LLM endpoint exists but no agent uses it.
Checked live for Scribe Realtime: `keyterms` are repeated query parameters, max 50 terms of max 20 characters
(longer → `invalid_request`), so the realtime limits in the table below hold.

## TL;DR recommendation

**Keep one agent brain in our backend. Use ElevenLabs Agents for the voice loop, with a *Custom LLM* pointing
at that backend.** Push map updates to the UI over our own realtime channel. If the Custom LLM integration
fights us, fall back to Architecture B: Scribe Realtime → our agent → TTS WebSocket. Details are in
[Integration architectures](#integration-architectures).

## 1. Agents Platform (ElevenAgents, formerly Conversational AI)

An agent is configured in the dashboard, CLI or API with these parts: system prompt, first message, LLM,
voice, tools, knowledge base, conversation-flow settings, and auth/security.

### LLM options
- **Built-in Claude models:** Claude Opus 5.5, Opus 5, Opus 4.8/4.7/4.6, Sonnet 5.5, Sonnet 5, Sonnet 4.6/4.5,
  and Haiku 4.5. The list also has Gemini, GPT and ElevenLabs-hosted open models. Some models are unavailable
  with EU data residency.
- **Custom LLM:** ElevenLabs calls *our* endpoint, which must be OpenAI-compatible:
  - `/v1/chat/completions` or `/v1/responses`, **streamed as SSE** (`text/event-stream`, ending with
    `data: [DONE]`).
  - Configured system tools are passed in the OpenAI `tools` param, so the endpoint must handle function
    calling to use them.
  - Optional reasoning goes in `reasoning` / `reasoning_content`.
  - **Slow-LLM trick:** stream an early `"... "` chunk (ellipsis **plus space**) so speech keeps flowing while
    our tools run.
  - A Custom LLM can't be combined with the bundled Realtime models.
- **Realtime models** bundle STT, turn-taking, LLM and voice: `eleven_realtime_v1_mini` and
  `eleven_realtime_v1_max` (the Max model is tuned for tool calling). They can't run our own LLM.

### Tools
| Type | Runs where | Use for us |
|---|---|---|
| **Webhook ("server") tools** | ElevenLabs calls our HTTP API. Method, URL, path/query/body params generated by the LLM; auth via secret headers or OAuth2/Basic workspace connections; responses can set dynamic variables | `find_route`, `search` (only if the LLM lives at ElevenLabs) |
| **Client tools** | Browser. Registered in `clientTools` on `startSession` / `useConversation`; names case-sensitive; enable "Wait for response" to send the return value back to the agent | `highlight_route`, `focus_room`, `switch_floor` on the map |
| **MCP servers** | SSE or streamable-HTTP MCP. Workspace opt-in (`can_use_mcp_servers`); approval policies: always ask, fine-grained, none; not available with Zero Retention / HIPAA | Expose our building tools once to both Claude and ElevenLabs |
| **System tools** | Built in | `end_call`, `language_detection` (switch language), `transfer_to_agent`, `skip_turn` ("give me a moment"), `update_state` (set dynamic variables); phone-only tools such as `transfer_to_number`, keypad and voicemail |

### Other agent features
- **Knowledge base / RAG:** a small knowledge base is injected into context; a large one is searched by
  chunks, with a configurable chunk count. We don't need it, because building facts must come from
  deterministic tools.
- **Dynamic variables:** values like `{{building_id}}` and `{{user_profile}}` per session, also settable
  from tool responses and `update_state`. The exact React prop name is UNVERIFIED; the React page doesn't
  document it.
- **Conversation flow:** a proprietary turn-taking model, interruptions on/off, turn eagerness, silence
  timeouts.
- **Languages:** agents speak 90+ languages and can switch mid-conversation (an older page says 31+). That
  helps the German/English Munich audience.
- **Transport:** WebRTC is the default for voice; WebSocket is the default for text-only. There is a
  `textOnly` mode with no mic, and a `serverLocation` option (`us`, `eu-residency`, …).
- **Transcripts and events:** callbacks `onMessage` (user transcripts plus agent replies), `onModeChange`
  (speaking/listening), `onAgentChatResponsePart`, `onAudioAlignment`, `onVadScore`,
  `onUnhandledClientToolCall`. Conversation history is visible in the dashboard.
- **Text input on the same session:** `sendUserMessage` (typed message), `sendContextualUpdate` (silent
  context such as "user clicked Room 2.03" or "lift closed by facility manager"), `sendUserActivity`
  (pauses agent speech for about 2 s while the user types).
- **Overrides per session:** prompt, first message, language, voice ID.
- **Widget:** a one-line HTML embed, with a fuller JS embed that can pass client tools. It's fine for a demo,
  but we'll want our own UI.

### Auth (keep the API key server-side)
- WebSocket: `GET https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=…` with the
  `xi-api-key` header returns `signed_url`. It is valid for **15 min** to *start* a session; sessions can run
  longer.
- WebRTC: `GET /v1/convai/conversation/token?agent_id=…` returns `{token, conversation_id}`. Validity is
  **10 min** per the Kotlin SDK docs.
- Alternative: a hostname allowlist of up to 10 hosts, with exact matching. It is either the allowlist or
  signed URLs, not both.

### SDKs
`@elevenlabs/react` (`ConversationProvider`, `useConversation` plus granular hooks), `@elevenlabs/client`
(vanilla JS), and a Python SDK (`ClientTools().register`, `conversations.get_signed_url`). There are also
Swift and Kotlin SDKs.

### Pricing (UNVERIFIED, third-party sources from 2026)
- About **$0.08/min** for voice-agent minutes on every plan. LLM cost is billed separately per minute.
  Burst minutes above the concurrency limit cost about $0.16/min; text messages about $0.003 each.
- Starter (~$6) includes about 75 min; Pro (~$99) about 1,238 min.
- Check the live pricing page and our actual tier before the demo.

## 2. Speech-to-text: Scribe

| | `scribe_v2` (batch) | `scribe_v2_realtime` |
|---|---|---|
| Latency | – | **~150 ms**, partial transcripts plus committed segments |
| Languages | 90+ | 90+ |
| Diarization | up to 32 speakers | not listed |
| **Keyterm prompting** | up to 1,000 terms × 50 chars | **up to 50 terms × 20 chars** |
| Extras | word timestamps, audio-event tags, entity detection (65 types) | word timestamps, entity detection, transcript editing |

- **Keyterms** are how we get room names right ("CNC mill", "Seminar room 0.32", "Büro", "Lift 1"). We can
  build them per building from `spaces[].name` and asset types. The realtime cap of 50 means we pick the
  most relevant ones per floor or session. Keyterms cost extra.
- **Browser streaming:**
  - Our server mints a single-use token via `single-use-token/realtime_scribe`. It expires in 15 min and is
    consumed on use.
  - `useScribe({ modelId: "scribe_v2_realtime" })` exposes `connect(token, mic)`, `partialTranscript` and
    `committedTranscripts`.
  - Commit strategy is `manual` (default) or `vad`.

## 3. Text-to-speech

| Model | ID | Latency* | Languages | Notes |
|---|---|---|---|---|
| Flash v2.5 | `eleven_flash_v2_5` | ~75 ms | 32 | default choice for live turn-by-turn |
| Flash v2 | `eleven_flash_v2` | ~75 ms | English | supports phoneme rules |
| Eleven v4 Turbo | `eleven_v4_turbo` | ~100 ms | 90+ | Text to Dialogue WebSocket |
| Eleven v4 | `eleven_v4` | – | 90+ | highest quality; phoneme rules |
| Eleven v3 / v3 Conversational | `eleven_v3`, `eleven_v3_conversational` | – / ~280 ms | 70+ | expressive |
| Multilingual v2 | `eleven_multilingual_v2` | higher | 29 | |

\*Model inference only; excludes network and application time. Turbo v2/v2.5 are deprecated in favour of
Flash.

- **Streaming:** use the WebSocket endpoint `…/text-to-speech/{voice_id}/stream-input`.
  - `auto_mode` disables chunk buffering and is best for whole sentences.
  - Send `flush: true` at sentence or turn ends.
  - The multi-context WebSocket allows one connection per user session.
- **Pronunciation dictionaries** (PLS files) take alias or phoneme rules and attach to agents or TTS
  requests:
  - Phoneme rules only work on `eleven_v4`, `eleven_flash_v2` and `eleven_v3`. Other models need alias
    rules, e.g. `"2.03"` → "two oh three", `"N0110"` → "N one-ten", `"OG"` → "Obergeschoss".
  - Docs conflict on which models support phonemes, so test it (UNVERIFIED).
- **Voice design** (`eleven_ttv_v3`) can create a custom "building concierge" voice from a prompt.

## 4. Other products with a plausible use

- **Voice Isolator / audio isolation:** `POST /v1/audio-isolation` and `/stream`; PCM 16 kHz input gives lower
  latency. Useful for the **service technician in a noisy factory hall** persona: clean the mic audio before
  STT. Whether it can be chained in real time before Scribe Realtime is UNVERIFIED; it may only suit batch or
  push-to-talk.
- **Sound effects** (`eleven_text_to_sound_v2`): generate earcons once at build time, for "turn now",
  "arrived", "floor change" and "route recalculated (lift closed)" cues. These matter for hands-busy and
  low-vision users.
- **Tool-call sounds** in Agents: a short sound while a webhook runs, so the user isn't left in silence.
- **Music:** demo-video background at most. Dubbing and voice changer: no real use for us.

## Integration architectures

### A — ElevenLabs Agent owns the voice loop
**A1: LLM = Claude hosted by ElevenLabs, with webhook tools pointing at our backend.**
- ✅ Quickest voice demo; turn-taking and interruptions come for free.
- ❌ It's a **second agent brain**: its prompt and tool definitions live in the ElevenLabs dashboard and
  drift from our text/benchmark agent.
- ❌ Webhooks must reach a public URL.
- ❌ Every route-highlight needs a client tool or a side channel.

**A2: LLM = Custom LLM pointing at our backend's `/v1/chat/completions`.**
- How it works:
  - Our backend runs the same Claude agent loop (Anthropic API plus deterministic tools) and streams only
    the final spoken text back as SSE.
  - Tool calls happen inside our backend.
  - The backend publishes `route_updated` / `focus_room` events to the session's realtime channel, the same
    one text chat and collaborators use.
- ✅ **One agent brain** for voice, text chat and benchmark.
- ✅ ElevenLabs still handles VAD, turn-taking, interruptions and TTS.
- ✅ Map updates go through our own channel.
- ❌ We must map ElevenLabs' OpenAI-format messages to our session (pass `session_id` via dynamic
  variables / custom LLM extra body — exact mechanism UNVERIFIED).
- ❌ Must be publicly deployed — fine, since we deploy to the cloud from day one.
- ❌ Latency of our tool loop is handled with the `"... "` trick.

### B — Our own loop
Browser `useScribe` (realtime STT, keyterms) → our backend agent → ElevenLabs TTS WebSocket (Flash v2.5) →
browser audio.
- ✅ Full control and one brain; no dependency on agent-platform features; STT/TTS billed per use.
- ❌ We build turn-taking, barge-in (stop TTS when the user speaks), echo handling and audio playback
  ourselves. That's a lot for 2 days.

### Decision guidance
| Criterion | A1 | A2 | B |
|---|---|---|---|
| Single source of agent logic | ❌ | ✅ | ✅ |
| Benchmark answers from deterministic code | ✅ (via webhooks) | ✅ | ✅ |
| Same agent for text chat | ❌ duplicate | ✅ | ✅ |
| Natural turn-taking / interruptions | ✅ | ✅ | ❌ build it |
| Push map updates to UI | client tools | our realtime channel (+ client tools) | our channel |
| Build effort | low | medium | high |

**Recommendation: A2.** Prototype A1 for one hour only if the Custom LLM adapter blocks us. Keep B as the
fallback: Scribe for STT plus TTS gives a working push-to-talk mode even if the Agents platform misbehaves.
This feeds into [overview.md](../architecture/overview.md); the decision belongs in
[decisions.md](../../memory-bank/decisions.md) once the team agrees.

## Open points to check hands-on
- Our subscription tier: included agent minutes, concurrency, and whether MCP / Custom LLM are allowed.
- How a session id reaches the Custom LLM request (dynamic variables in the system prompt vs extra body).
- Whether Flash v2.5 needs alias rules for room refs like "0.21" (likely; test).
