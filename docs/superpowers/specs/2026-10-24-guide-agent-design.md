---
id: spec-guide-agent
summary: Phase 3 design — the Building Guide "brain" (text, terminal first): multi-turn Q&A and directions over core/ tools, clarifies only what changes the answer, never states a fact a tool did not return.
status: approved by Utku 2026-10-24
sources:
  - conversation with Utku, 2026-10-24 (branch 1-agentic-yarag)
  - docs/architecture/ai-agents.md (Building Guide behaviour contract, tool layer)
  - docs/challenge/brief.md (levels, personas, judging)
  - core/building_map.py, core/solvers.py, core/question_parser.py, agent/answer.py, agent/llm_parser.py
related: [../../architecture/ai-agents.md, ../../challenge/brief.md, ../../product/routing-profiles.md, ../../architecture/solver-plan.md]
---

# Building Guide agent — Phase 3 design (the brain, terminal first)

[Docs index](../../README.md) · Agent overview: [ai-agents.md](../../architecture/ai-agents.md)

## Intent and why

At the demo a jury member asks a building questions and asks for directions, by text and later by voice. The
agent behaves like a chatbot: it answers, and when something is unclear in a way that matters (two "3D
printers", an unknown room) it asks back, then continues. The Interaction score (25 pts) is a short scripted
conversation with tricky users judged on: *asks only what it needs, shows what it understood, directions a
person can follow* ([brief.md](../../challenge/brief.md#judging)).

**Utku's biggest worry: the agent hallucinating in front of the jury.** Every design choice below serves
"never say a room, number or route that the deterministic core did not return".

Today we have a single-shot pipeline (`agent/answer.py`: text → parser → solver → `Answer:` line). It has no
memory, cannot ask back, and silently picks the first match (e.g. `locate` returns the first of two
`3d_printer` assets with no mention of the second). Phase 3 adds the conversational brain on top of the same
core.

## Goals (v1, this branch)

1. **Multi-turn conversation in the terminal** against one building directory (`data/<split>/<building>`).
2. **Questions:** everything the core can answer — locate, count, largest room, floor area total, shared walls,
   room above/below, straight-line distance, errand, reachable/wide-delivery counts, what-if-door — plus
   general lookups ("what is in room X", "what floors are there").
3. **Directions:** A→B, step-free, multi-stop tour, across floors, and a one-off closure stated in the request
   ("the lift is out, route me around it") — kept for this session's routes, the building is not changed
   (see session state below).
4. **Clarify only what changes the answer** (contract in [ai-agents.md](../../architecture/ai-agents.md#building-guide--behaviour-contract), [D-010](../../../memory-bank/decisions.md#d-010)):
   several candidates → solve for each; same answer → just answer; different answers → one short question
   with ≤ 3 options told apart by ref, floor or neighbour.
5. **Session context:** pronouns and references ("there", "that room", "the one on floor 1"), the user's
   position once stated, and stated constraints (wheelchair → step-free for every later route without asking
   again, confirmed once in one line).
6. **Echo understanding in one line** (from → to, constraints, closures), then numbered steps with landmarks,
   explicit floor changes, rounded metres.
7. **No hallucination** — see [Grounding](#grounding-the-anti-hallucination-design).
8. **Structured output per turn** alongside the text so the Phase 4 UI can highlight things without
   re-parsing prose. Nothing depends on it yet; layout *(my call)*: `space_ids`, `asset_ids`,
   `connector_ids` (mentioned, split by kind), `routes` (each in the existing `core/solvers.route` shape:
   `optimal_length_m`, `space_path`, `element_path`, `legs`, `steps`), `options` (candidates offered in a
   clarifying question), `asked` (bool: did this turn end with a question), plus `tool_calls` and `usage`.

## Non-goals (v1)

- Changing the building (close a lift permanently, move a machine, add a door) — later phase.
- Chat UI, HTTP API, ElevenLabs voice — Phase 4. The brain must be callable as a plain Python object so those
  can wrap it later.
- Routing profiles with soft penalties ([routing-profiles.md](../../product/routing-profiles.md)) — v1 only
  has the hard filters the core already supports (step-free, closures).
- Several buildings in one session.

## Anti-goals (a failure even if it "works")

- Stating any room, ref, count, area, distance, metre value or route step that did not come from a tool
  result in this conversation.
- Inventing a room or asset that does not exist instead of saying "I can't find that" with nearest matches.
- Asking questions the answer doesn't depend on (where are you? — when the question doesn't need a start;
  which 3D printer? — when the user asked how many there are).
- Asking the same thing twice in a session (constraints, position).
- Touching the benchmark path: `agent/answer.py`, `run_benchmark`, solver outputs and the 138/138 dev score
  must not change.

## Constraints

- Anthropic SDK directly, no LangChain/LangGraph (decided in conversation 2026-10-24: one tool-use loop over
  our own functions does not need a framework; we keep control of caching and cost).
- Deterministic core is the only source of facts ([D-003](../../../memory-bank/decisions.md#d-003)). Solvers in
  `core/solvers.py` and `BuildingMap` in `core/building_map.py` are reused, not re-implemented.
- Python ≥ 3.12 via `uv`; key in `.env` (`ANTHROPIC_API_KEY`).
- Budget: $150 Claude credits total for the hackathon ([Q-012](../../../memory-bank/open-questions.md#q-012)).
  Cache the building overview and tool definitions in the system prompt; keep tool results compact.
- Must work on unseen buildings (Sunday); no hard-coding to train/dev/test buildings or names.
- Commits only via `/ship`.

## How it works (decided)

```
user text ─► Guide.turn(text)
               │  system prompt: rules + compact building overview (cached)
               │  history: previous turns (+ session facts: position, constraints)
               ▼
            Claude ── tool_use ──► tool layer (Python, core/) ──► compact JSON result
               ▲                                                     │
               └──────────────────── tool_result ◄───────────────────┘
               │ final text
               ▼
            grounding check (code) ── fail ──► one repair round with the offending tokens
               │ pass
               ▼
            TurnResult(text, mentioned_ids, routes, tool_calls, usage)
```

- **One brain object per session**: `Guide(building_dir)` with `turn(text) -> TurnResult`. A terminal REPL
  wraps it; later the HTTP/voice layer wraps the same object.
- **Tools wrap core**, never new geometry. Starting set (from [ai-agents.md](../../architecture/ai-agents.md#shared-tool-layer),
  trimmed to read-only for v1):
  - `find(query, floor?)` → ranked spaces/assets with id, name, ref, type, floor, containing room.
    Backed by `BuildingMap.search` + the `Resolver` type matching (plurals, "air compressor" → `compressor`).
  - `room_facts(space)` → name, ref, type, floor, area, assets inside, neighbours, above/below.
  - `route(from, to, via?, step_free?, avoid?)` → reachable, metres, steps, space/element paths.
  - One tool per remaining question kind, or a single `solve(kind, inputs)` tool — builder's call (below).
- **Names are resolved in code, and code runs every candidate.** Tools accept free text or ids. If nothing
  matches, the tool returns `{"status": "not_found", "nearest": [...]}`. If several places match, the tool
  itself runs the solver once per candidate (≤ 5) and returns either `{"status": "ok", "agree": true,
  "answer": …}` (all candidates give the same answer → just answer) or `{"status": "ambiguous", "options":
  [...]}` with each option's distinguishing facts (ref, floor, a neighbour or containing room) and its own
  result. The model only phrases the question; it never compares answers itself. *(my call — keeps the
  D-010 rule deterministic instead of trusting the model to loop)*
- **Session state lives in code, not in the model's memory** (`Guide.session`): position, `step_free`, and
  closures the user stated. *(my calls:)*
  - A stated constraint ("I'm in a wheelchair") is acknowledged as a **statement in the same reply**
    ("Noted — step-free routes from now on."), not a yes/no question, and the route comes in that same turn.
  - A stated closure ("the lift is out", "avoid stair B") lasts **for the rest of the session** until the
    user lifts it ("the lift works again"); it only affects this session's routes, never `building.json`.
  - If the closure names several elements (two lifts) and the routes differ depending on which is closed,
    ask which one, using the same `ambiguous` mechanism; if it doesn't matter, don't ask.
- **Model:** configurable by env var (`GUIDE_MODEL`), default `claude-opus-5-5` (same as `agent/llm_parser.py`; ai-agents.md suggested Sonnet, switch by env var after measuring cost/quality). *(my call)*
- **Language:** reply in the user's language (jury likely English; Turkish should work too). *(my call)*

## Grounding (the anti-hallucination design)

Three layers, cheapest first:

1. **No facts in the prompt that the model could recite instead of calling a tool.** The system prompt holds
   only a compact overview (floors, building name, counts of rooms/assets, list of asset types and room types
   so the model knows what exists). Room-level facts come only via tools.
2. **Tools refuse to guess** (`not_found` / `ambiguous` + candidates, see above). An empty result says so
   explicitly; it is never an empty list the model can paper over.
3. **Code checks the final text.** *(scope is my call — strict where hallucination hurts, loose where names
   change form)*
   - **Checked: numbers and refs.** Every number with a decimal point/comma or a unit (m, m², metres) and
     every count, plus every token that looks like a room ref of this building or an id, must appear in a
     tool result from this session.
   - **Not checked: free-text names** (room/asset names, often German, translated room types in a Turkish
     reply, landmark phrasing). Names cannot be invented anyway because only refs/ids get checked and tools
     refuse to guess.
   - **Ignored:** step numbering ("1.", "2."), floor numbers inside floor names, option counts ("2 options"
     equal to the number of options a tool returned are fine).
   - **Rounding:** "37,4" and "37.4" are the same; a value counts as grounded if it equals a tool value
     rounded to 0, 1 or 2 decimals (37.42 → 37, 37.4, 37.42; *not* "about 40").
   - **No arithmetic by the model** ("2 more than on floor 1", sum of legs): such a number fails the check;
     the prompt tells the model to call a tool or not to state it.
   - On failure the offending tokens are sent back once ("these values are not in any tool result: …");
     if the second answer still fails, return a safe fallback built in code from the tool results.

Out-of-scope questions (weather, jokes): one polite line that it helps with this building.

## Testing

- **Unit tests offline** with a fake Anthropic client (pattern already used in `tests/test_parsing_modes.py`):
  tools return the right shapes; ambiguity/not-found paths; grounding checker accepts rounded values and
  rejects invented ones; benchmark tests stay green.
- **Scripted conversations** (YAML/JSON: turns + expectations) run live on a few dev buildings, covering:
  ambiguous name (two 3D printers → asks only when routing, not when counting), unknown room ("room 9.99"),
  follow-up reference ("how do I get there?"), mid-conversation constraint ("I'm in a wheelchair" → later
  routes step-free without re-asking), one-off closure, cross-floor route, out-of-scope question.
  Expectations are checked in code: the ids/metres in `TurnResult` equal what the solver returns for the
  same inputs; whether the agent asked a question or answered.
- **Terminal REPL** for manual trial: `uv run --env-file .env python -m agent.guide data/dev/<building>`;
  shows tool calls (optional flag) and running cost.

## Left to the builder

- Exact module layout under `agent/` (e.g. `agent/guide/` package with `tools.py`, `prompt.py`, `grounding.py`,
  `repl.py`) and names.
- Tool granularity for the benchmark kinds (one tool each vs one `solve(kind, inputs)`), as long as tool
  descriptions are clear enough that the model picks the right one and tests cover each kind.
- Manual tool-use loop vs the SDK tool runner; prompt-caching layout.
- How landmarks are phrased in steps (reuse `BuildingMap.directions` and enrich with assets in rooms passed).
- Format of the scripted-conversation files and how many dev buildings they run on (keep live cost of one
  full run under ~$2).
- Whether `locate` in the core should return all matches (it already returns `others`) — no change to
  benchmark output allowed.

## Open (UNVERIFIED)

- Exact phrasing and contents of the jury's scripted conversation — unknown; tests above are our guess at it.
