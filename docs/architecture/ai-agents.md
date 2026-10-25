---
id: arch-agents
summary: PROPOSED design of every AI agent in the system — Building Guide (chat + voice), benchmark pipeline, Builder (plan → building), and how they share one deterministic tool layer.
status: proposed
sources: [../research/elevenlabs.md, ../kit/starter-agent.md, ../challenge/brief.md, ../challenge/scoring.md, ../../agent/tools.py, ../../agent/guide.py, ../../agent/offline_llm.py]
related: [overview.md, solver-plan.md, ../product/routing-profiles.md, ../product/personas.md, ../research/question-parsing.md]
---

# AI agents — PROPOSED

[Docs index](../README.md) · System view: [overview.md](overview.md)

**One rule for every agent:** the LLM understands and explains; tools compute. No agent ever states a room,
distance, count or route that did not come from a tool result ([D-003](../../memory-bank/decisions.md#d-003)).

## The agents

| Agent | Job | Model (start) | Channel | Points |
|---|---|---|---|---|
| **Building Guide** | conversation: find, route, react, edit; clarifies; remembers user profile. **v1 implemented** (terminal, `agent/guide_v1/`: 6 tools, grounding check, session; live scripted run 16/16 turns, 9 conversations, [spec](../superpowers/specs/2026-10-24-guide-agent-design.md), [plan](../superpowers/plans/2026-10-24-guide-agent.md)); the v1 Guide has no edit tools, UI or voice — those are in the canonical `agent/guide.py` (below) | Opus 5.5 default (`GUIDE_MODEL`), medium effort | terminal REPL; text chat + voice (via ElevenLabs) planned | Interaction 25, L1–L3 |
| **Benchmark pipeline** | question text → parse → solver → `Answer:` line; no free-form LLM | none; Haiku/Sonnet only as parse fallback | CLI `run_benchmark`, `benchmark.evaluate --agent` | Does it work 55 |
| **Builder** | floor-plan image → draft `building.json` → validate → user confirms; drafting from plans is the **Creator** ([design](../superpowers/specs/2026-10-25-plan-import-design.md), [plan](../superpowers/plans/2026-10-25-plan-import.md), in progress) | Opus 5.5 (vision) | UI upload + chat | L4 |
| (dev) **Claude Code subagents** | build the product: research, solvers, tests | — | this repo | — |

Model ids: [claude-api skill / docs]; switch by env var, compare cost/quality with `benchmark.evaluate`.

## Shared tool layer

Every agent calls the same Python functions in `core/` (exposed as Anthropic tools, as HTTP for ElevenLabs
webhooks if ever needed, and optionally as one MCP server). Proposed tool set for the Guide:

| Tool | Returns | Mutates shared building? |
|---|---|---|
| `building_overview` | floors, cores, entrances, closures | no |
| `search(query, floor?)` | ranked spaces/assets with ids | no |
| `room_facts(space)` | area, centre, floor, neighbours (shared walls), above/below (omitted on Swiss Dwellings buildings, floors not aligned — [solver-plan](solver-plan.md#straight_line_3d)), doors + widths | no |
| `find_route(from, to, via?, profile)` | node path, metres, steps with landmarks, profile used | no |
| `compare_routes(before/after change)` | diff: rooms that lost access, extra metres | no |
| `set_profile(...)` | the active [routing profile](../product/routing-profiles.md) for this user | user state only |
| `propose_change(kind, …)` | a **pending** change (close lift, add door, move asset) + its predicted effect | no — needs confirm |
| `apply_change(change_id)` | committed edit event, broadcast to all clients | **yes** |
| `show_on_map(ids, route?)` | UI event (highlight / fly to / switch floor) | no |

**Implemented (2026-10-24):** `agent/tools.py` — `BuildingSession` (private building copy, routing profile,
pending/applied changes, UI events) + `TOOL_DEFINITIONS` (Anthropic tool schemas) for building_overview, search,
locate, count_assets, room_facts, find_route, tour, reachable_rooms, solve (every benchmark kind), set_profile,
propose_change, apply_change, compare_routes, show_on_map. Errors come back as `{"error": …}` so the model can
search or ask. Profile → constraints: `min_door_width_m` and `avoid_lifts` act as closures of narrow openings /
lifts. Built on `core/navigation.py` (locate, count, find_route, tour; gold path format) and `core/solvers/`.
Tests: `tests/test_agent_tools.py`.

`compare_routes(change_id, start?)` works on a **pending** change (current building vs the building with the
change) or an **applied** one (snapshot before vs after `apply_change`). From `start` (default: the last route's
start, else the main step-free entrance) under the user's profile it returns rooms reachable before/after, the
rooms that **lost access** as `lost_access_by_floor` (`{floor: {count, rooms}}`, uncapped; also emitted as a
`highlight` event with `style: "lost_access"`), the routes that got longer with `before_m`/`after_m`/`extra_m`
(route-model metres, longest first) and the last route's before/after. `propose_change`'s effect carries the same
impact (lost access by floor, longer routes, `max_extra_m`) plus the last route's `extra_m`, without emitting
events — so one call answers "what happens if…", and the model never counts or subtracts itself.

`propose_change` → user sees an "I understood: close *Office lift*; 3 routes get 40 m longer. Apply?" card →
`apply_change`. That is the brief's "show what it understood before it changes a plan"
([brief.md](../challenge/brief.md#directions-from-the-organisers)).

## Building Guide — behaviour contract

- **Ask only what changes the answer.** If a search returns several candidates and the words don't settle it,
  run the solver for each; if the answers agree, just answer. If they differ, ask one short question listing
  ≤ 3 options by what tells them apart — ref first, else floor, size, a neighbour or position (duplicate names
  usually share the floor) — or highlight them on the plan ([D-012](../../memory-bank/decisions.md#d-012)). Never ask where the user is if the question doesn't
  need it; once known, remember it for the session.
- **Profile once, remember always.** Infer constraints (wheelchair, trolley width, no lifts, quiet) from the
  conversation, confirm once in one line, store in the session/user profile → used by every later route
  without asking twice ([routing-profiles.md](../product/routing-profiles.md)).
- **Echo understanding in one line** (from → to, constraints, closures), then numbered steps.
- **Directions a person can follow:** landmarks from assets/room names ("past the printers", "through the
  double door into Hall 0.02"), floor changes explicit, metres rounded. Voice gets shorter steps than text.
- **Robust to tricky users:** vague ("the printer"), wrong ("room 9.99" → nearest matches), mid-course
  changes ("actually avoid the lift"), multilingual (ElevenLabs language detection).

### Implementation — `agent/guide.py` (2026-10-24)

`Guide(session, client=None)` is one conversation: `guide.reply(text) → GuideTurn(text, tool_calls, events,
ungrounded, stop_reason)`. A manual tool-use loop over `client.beta.messages.create` (≤ 12 tool rounds per turn):
every `tool_use` block goes to `BuildingSession.call`, all results return in one user message (`is_error` on
`{"error": …}`), text written before tool calls is kept in the reply.

| Aspect | How |
|---|---|
| Model | `GUIDE_MODEL` (default `claude-opus-5-5`), `GUIDE_EFFORT` (default `medium`); thinking left at the model default (adaptive); `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`, as in `agent/llm_parser.py` |
| Caching | system = fixed instructions + building overview (static `BuildingMap.overview()`, no profile/closures) with `cache_control`; tools render before it, so both are cached; top-level `cache_control` also caches the growing history |
| History | append-only (assistant `response.content` stored unchanged), so the cached prefix and thinking blocks stay valid |
| Confirm before edit | `apply_change` for a change proposed in the **same user turn** is refused with an error telling the model to show the summary and wait — enforced in code, not only in the prompt |
| Profile safety net | a deterministic cue detector reads every user message (wheelchair, pram, no lifts, trolley width, reset…); if the model's turn left the cue unhonoured the Guide calls `set_profile` itself, appends a one-line confirmation and, if the turn already routed, asks once for a redo. `set_profile` takes persona presets ([routing-profiles.md](../product/routing-profiles.md#implemented-presets)); tests `tests/test_profiles.py` |
| D-003 grounding | after each turn, every number and id in the reply must appear in a tool result, the overview or the user's own messages (a number counts if a known number rounds half-up to it at the same precision, or if it is the length of a list in a tool result; numbers glued to a unit like "120m" are checked; numbered-list markers and clock times ignored — ported from the v1 Guide 2026-10-24). Fails → one repair round ("[grounding check] … appear in no tool result"); anything still ungrounded is returned in `GuideTurn.ungrounded` |
| Place names | `BuildingSession.resolve` → `agent/places.py` (ported from the v1 Guide): id, asset id, exact ref/name after dropping "the / a / room", asset name, exact asset type ("the 3D printer" → the room holding it), then word search. One candidate → its id; several → `MapError` listing each as `id (name, ref, type, floor)` and telling the model to ask what tells them apart ([D-012](../../memory-bank/decisions.md#d-012)); none → near-miss names ("Did you mean …"). `find_route` / `tour` resolve their stops this way; a destination that fits 2–8 spaces returns every option with its route length, shortest first, and draws no route. Tests `tests/test_places.py` |
| No key | `make_client()` → `agent/offline_llm.py` `OfflineClient`: keyword rules choose tools, replies are composed only from tool results (demo + backend tests). `GUIDE_LLM=offline|anthropic` forces either |

Tests: `tests/test_guide.py` — a scripted fake client plays the tricky user (vague printer → ≤ 3 options;
ambiguous "the meeting room" → search → ≤ 3 options with floors; "I use a wheelchair" → `set_profile`, remembered
on the next route; "the lift is broken" → propose, same-turn apply refused, apply after "yes"; route after the
closure 124.24 m → 132.2 m via Lift 2, `compare_routes` +7.96 m), plus request shape (cached system, env model,
append-only history, every tool_use answered), the repair round, and the offline client.

**Live check (2026-10-24, `scripts/live_guide.py`, same 7 turns, train campus 000):**

| Model · effort | s / turn | $ / 7 turns | Behaviour |
|---|---|---|---|
| Opus 5.5 · medium (default) | ~5.9–7.3 (7.3 pre-fix, 5.9 post-fix) | 0.13–0.16 | all turns correct; inferred "the lift" = Lift 1 on the route; most thorough, longest replies |
| Opus 5.5 · low | ~6.8 (one pre-fix run) | 0.12 | same quality, no clear speed gain (one pre-fix run; not directly comparable) |
| Sonnet 5.5 · low | ~3.3–3.9 (3.3 pre-fix, 3.9 post-fix) | 0.06 | correct and shortest (best for voice); applied the routing-profiles wheelchair default 0.8 m door width and said so |

All runs: 0 ungrounded replies, no same-turn apply, cache reads on every request after the first. Fixed from
the first runs: lost-room list was capped at 15; a parallel `compare_routes` guessed a change id; an
unsupported "nothing upstairs" claim → impact moved into `propose_change`, two prompt sentences added. Model
choice stays open ([Q-012](../../memory-bank/open-questions.md#q-012)).

## Voice path

Per [elevenlabs.md](../research/elevenlabs.md#tldr-recommendation): ElevenLabs Agent handles STT, turn-taking,
interruptions and TTS; its **Custom LLM** points at our backend's OpenAI-compatible streaming endpoint, which
wraps the same Building Guide (one brain for text and voice) — skeleton in `backend/` (see
[commands.md](../guides/commands.md#backend-guide-api)). Map actions reach the browser as ElevenLabs
**client tools** and/or our own realtime channel. Fallback: Scribe Realtime → Guide → TTS WebSocket.
Per-building **keyterms** (room names, machine names) go to Scribe for accurate recognition.
A **transcript rewriter** normalises each STT transcript to the building's vocabulary before the Guide sees it
(original transcript passed along too); typed chat has no rewriter ([D-013](../../memory-bank/decisions.md#d-013)).
Implemented in `agent/rewriter.py`: one `claude-haiku-5-5` call (effort low, JSON schema `{rewritten}`) with the
building vocabulary as cached system prompt; `Guide.reply(..., channel="voice")` sends the model
`<rewritten>\n\n[speech transcript as heard: <original>]`, adds both to the grounding corpus and returns
`GuideTurn.rewritten`. Only with the real API client; `GUIDE_REWRITER=off` disables it, `GUIDE_REWRITER_MODEL`
overrides the model. Any doubt (API error, refusal, empty, a number in neither the transcript nor the building)
keeps the transcript as heard. Live (train campus 000): "lab two seventeen" → "Lab 2.17", "office zero oh two"
→ "Office 0.02", "the kitchen" and "the second floor" unchanged; ~1–2 s per call. Tests `tests/test_rewriter.py`.

**Implemented (2026-10-24):** `Guide.reply(text, channel="voice")` — used by `/v1/chat/completions` — adds the
`VOICE_STYLE` instruction (plain spoken sentences, ≤ ~3 sentences, first 2–3 steps then offer to continue) as a
mid-conversation **system message** after the user turn on models that support it (Opus 5/5.5, Opus 4.8, Fable,
Sonnet 5.5, Haiku 5.5 — keeps the cached prefix), else as a note in the user turn; then `agent/speech.py`
`speakable()` deterministically strips markdown, list markers, ids and symbols and spells out units (it never adds
a number, so grounding holds). `GuideTurn.spoken` carries the result; the chat panel keeps the text channel.
Live (Sonnet 5.5 low, `scripts/live_guide.py --channel voice`): 7 turns, ~3 s/turn, $0.054, 0 ungrounded, no ids
or markdown in speech. Tests: `tests/test_speech.py`. Still open: ElevenLabs account wiring (session id, system
tools) — needs the public deploy.

## Benchmark pipeline

```
question text ─► template parser ──ok──► solver(kind, params) ─► formatter ─► reply + "Answer: …"
                     │ fail                        ▲
                     └► LLM extractor (strict schema) ┘  (resolved + validated in code)
```

Implemented: `agent/benchmark_agent.py` (`answer()` for `benchmark.evaluate --agent`) and `agent/run_benchmark.py`
(second test CLI; the submission uses `agent/run_benchmark_v1.py`, [BENCHMARK.md](../../SUBMISSION/BENCHMARK.md)). Dev 138/138 end to end. Warm-up kinds (locate, count,
route, step-free, closure, tour) parse via `core/basic_parser.py` → `core/navigation.py`: 2120/2130 train+dev
from text, 100% with gold ids (`scripts/validate_warmup.py`).

Parser evidence and accuracy: [question-parsing.md](../research/question-parsing.md) ([Q-008](../../memory-bank/open-questions.md#q-008)).
Solvers: [solver-plan.md](solver-plan.md). The same solvers back the Guide's `room_facts` / `find_route` tools,
so benchmark work directly improves the product.

### Parser modes

Set with `PARSER_MODE` ([D-007](../../memory-bank/decisions.md#d-007)).

| Mode | Behaviour | Use for |
|---|---|---|
| `hybrid` (default) | regex template first; LLM (`agent/llm_parser.py`) only if no template matches or a slot doesn't resolve | benchmark + Sunday |
| `regex` | deterministic only; unknown wording → `ParseError` | reproducibility checks |
| `llm` | LLM only | robustness experiments, conversational input |
| `crosscheck` | both; keep regex result, note `agree` / `disagree` | measuring the LLM parser |

Why regex stays first even though credits don't matter: on template wording it is **provably** 100% (655/655),
**reproducible** (judges may re-run our command and get identical output), and instant. The LLM can at best
tie there, and is non-deterministic. Where the LLM wins is wording the templates don't cover — so it is the
fallback, not the default. Both paths share one `Resolver`: the LLM returns raw slot text chosen from the
building's vocabulary (never ids or numbers), code resolves it, and a resolution error is sent back once for
correction. Measure live with `scripts/eval_llm_parser.py [--paraphrase]`.

## Deterministic vs adaptive — the split

The brief asks for a "mostly deterministic" core. Our rule for which side does what:

| Deterministic (code, `core/`) | Adaptive (Claude) |
|---|---|
| every number, id, route, count, area, distance | understanding the request (parsing, intent, references like "the printer", "it", "there") |
| graph, costs, profiles, closures, edits applied | deciding what to ask when the request is ambiguous or a constraint is missing |
| the final `Answer:` line | explaining *why* (route choice, what a closure changes) in plain words |
| validation of every edit before it is applied | choosing landmarks / phrasing for directions; language; voice brevity |
| benchmark output (reproducible) | Builder: proposing rooms/doors from a plan image (then validated by code) |

So the answer is always correct-by-construction, and the agent's job is to get the *right question* into the
solver and the *answer* back to the person in a form they can use. When the agent and a tool disagree, the
tool wins.

## Builder (Level 4)

Edit mode design (step 1 of the Builder): [builder-edit-mode-design](../superpowers/specs/2026-10-24-builder-edit-mode-design.md).
**Milestone 1 implemented (2026-10-24, branch `2-builder-edit`):** Edit button on the building screen (Atahan's
new UI, merged from `dev`); drag corners (shared walls stay shared), doors along walls and assets on a 2D plan with
the 3D `PlanView` of the draft as a live inset; undo; validator issues
in red (pre-existing issues of the original are warnings); save as `user/<slug>`, then the Guide routes in it.
Code: `core/edits.py`, `core/validate.py`, `backend/drafts.py` + `/drafts`, `frontend/app/src/edit/`. **Milestone 2 implemented (2026-10-24):** prompt edits — the Builder agent (`agent/builder.py`,
`agent/builder_tools.py`, offline `agent/builder_offline.py`; `BUILDER_MODEL` default `claude-opus-5-5`) proposes
op lists with `propose_edit` (dry run, area effect, new problems), never applies; the Edit mode's chat shows the
proposal as a ghost on the plan with Apply / Cancel, a plain "yes" also applies; hand edits drop an open proposal
(stale ones are refused server-side). Live (Opus 5.5 medium, `scripts/live_builder.py`): move a machine 7.6 s, add a
door 13.1 s, an ambiguous "widen the lab into the next room" asked which side (5.4 s), then proposed `move_edge` and
flagged the sink left outside (6.9 s); 0 ungrounded; ~$0.02–0.04 per turn. A proposal is open for one exchange
only (the next message or Apply); another turn, Cancel or a hand edit closes it, and only a bare "yes"/"ok" applies
without the model. **Milestone 3 built (2026-10-24, deploy pending):** with `SUPABASE_DB_URL` drafts, saved buildings
and the Builder's conversation live in Postgres (`builder_drafts`, `saved_buildings`), so any serverless instance
serves any request — a proposal made on one instance can be applied on another; each person edits their own draft,
concurrent writes are version-checked (409); saved buildings are shared with everyone
([milestone 3 plan](../superpowers/plans/2026-10-24-builder-edit-mode-m3.md)). Plan images (project 2): the Creator agent, [design](../superpowers/specs/2026-10-25-plan-import-design.md) and [plan](../superpowers/plans/2026-10-25-plan-import.md) (in progress, 2026-10-25).

1. Upload plan image (PNG/PDF page) or describe changes by conversation.
2. Claude vision drafts `floors`/`spaces`/`openings` in our schema (scale from a known dimension the user gives
   or a scale bar).
3. **Validator in code:** valid polygons, no overlaps, every opening lies on a shared wall, every room reachable
   from an entrance, connectors link existing spaces. Errors go back to the model (loop ≤ N times).
4. Render the draft over the image; user confirms or corrects by chat ("the door is on the north wall").
5. Measure on our own data: rebuild train buildings from `floor_*_plain.png` and compare to `building.json`
   (room count, area error, connectivity) — a measurable L4 score.

## Budget

$150 Claude credits ([Q-012](../../memory-bank/open-questions.md#q-012)). Benchmark runs are ~free once the
parser + solvers are deterministic; spend goes to Guide conversations, Builder vision calls and dev agents.
Cache the building overview in the system prompt; keep tool results compact.

## Related
- [overview.md](overview.md) · [solver-plan.md](solver-plan.md) · [routing-profiles.md](../product/routing-profiles.md) · [Phase 3 Guide design](../superpowers/specs/2026-10-24-guide-agent-design.md)
