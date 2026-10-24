---
id: arch-agents
summary: PROPOSED design of every AI agent in the system — Building Guide (chat + voice), benchmark pipeline, Builder (plan → building), and how they share one deterministic tool layer.
status: proposed
sources: [../research/elevenlabs.md, ../kit/starter-agent.md, ../challenge/brief.md, ../challenge/scoring.md]
related: [overview.md, solver-plan.md, ../product/routing-profiles.md, ../product/personas.md, ../research/question-parsing.md]
---

# AI agents — PROPOSED

[Docs index](../README.md) · System view: [overview.md](overview.md)

**One rule for every agent:** the LLM understands and explains; tools compute. No agent ever states a room,
distance, count or route that did not come from a tool result ([D-003](../../memory-bank/decisions.md#d-003)).

## The agents

| Agent | Job | Model (start) | Channel | Points |
|---|---|---|---|---|
| **Building Guide** | conversation: find, route, react, edit; clarifies; remembers user profile. **v1 implemented** (terminal, `agent/guide/`: 6 tools, grounding check, session; live scripted run 16/16 turns, 9 conversations, [spec](../superpowers/specs/2026-10-24-guide-agent-design.md), [plan](../superpowers/plans/2026-10-24-guide-agent.md)); edit tools, UI and voice not yet | Opus 5.5 default (`GUIDE_MODEL`), medium effort | terminal REPL; text chat + voice (via ElevenLabs) planned | Interaction 25, L1–L3 |
| **Benchmark pipeline** | question text → parse → solver → `Answer:` line; no free-form LLM | none; Haiku/Sonnet only as parse fallback | CLI `run_benchmark`, `benchmark.evaluate --agent` | Does it work 55 |
| **Builder** | floor-plan image → draft `building.json` → validate → user confirms | Opus 5.5 (vision) | UI upload + chat | L4 |
| (dev) **Claude Code subagents** | build the product: research, solvers, tests | — | this repo | — |

Model ids: [claude-api skill / docs]; switch by env var, compare cost/quality with `benchmark.evaluate`.

## Shared tool layer

Every agent calls the same Python functions in `core/` (exposed as Anthropic tools, as HTTP for ElevenLabs
webhooks if ever needed, and optionally as one MCP server). Proposed tool set for the Guide:

| Tool | Returns | Mutates shared building? |
|---|---|---|
| `building_overview` | floors, cores, entrances, closures | no |
| `search(query, floor?)` | ranked spaces/assets with ids | no |
| `room_facts(space)` | area, centre, floor, neighbours (shared walls), above/below, doors + widths | no |
| `find_route(from, to, via?, profile)` | node path, metres, steps with landmarks, profile used | no |
| `compare_routes(before/after change)` | diff: rooms that lost access, extra metres | no |
| `set_profile(...)` | the active [routing profile](../product/routing-profiles.md) for this user | user state only |
| `propose_change(kind, …)` | a **pending** change (close lift, add door, move asset) + its predicted effect | no — needs confirm |
| `apply_change(change_id)` | committed edit event, broadcast to all clients | **yes** |
| `show_on_map(ids, route?)` | UI event (highlight / fly to / switch floor) | no |

`propose_change` → user sees an "I understood: close *Office lift*; 3 routes get 40 m longer. Apply?" card →
`apply_change`. That is the brief's "show what it understood before it changes a plan"
([brief.md](../challenge/brief.md#directions-from-the-organisers)).

## Building Guide — behaviour contract

- **Ask only what changes the answer.** If a search returns several candidates and the words don't settle it,
  run the solver for each; if the answers agree, just answer. If they differ, ask one short question listing
  ≤ 3 options by what tells them apart — ref first, else floor, size, a neighbour or position (duplicate names
  usually share the floor) — or highlight them on the plan ([D-010](../../memory-bank/decisions.md#d-010)). Never ask where the user is if the question doesn't
  need it; once known, remember it for the session.
- **Profile once, remember always.** Infer constraints (wheelchair, trolley width, no lifts, quiet) from the
  conversation, confirm once in one line, store in the session/user profile → used by every later route
  without asking twice ([routing-profiles.md](../product/routing-profiles.md)).
- **Echo understanding in one line** (from → to, constraints, closures), then numbered steps.
- **Directions a person can follow:** landmarks from assets/room names ("past the printers", "through the
  double door into Hall 0.02"), floor changes explicit, metres rounded. Voice gets shorter steps than text.
- **Robust to tricky users:** vague ("the printer"), wrong ("room 9.99" → nearest matches), mid-course
  changes ("actually avoid the lift"), multilingual (ElevenLabs language detection).

## Voice path

Per [elevenlabs.md](../research/elevenlabs.md#tldr-recommendation): ElevenLabs Agent handles STT, turn-taking,
interruptions and TTS; its **Custom LLM** points at our backend's OpenAI-compatible streaming endpoint, which
wraps the same Building Guide (one brain for text and voice). Map actions reach the browser as ElevenLabs
**client tools** and/or our own realtime channel. Fallback: Scribe Realtime → Guide → TTS WebSocket.
Per-building **keyterms** (room names, machine names) go to Scribe for accurate recognition.
A **transcript rewriter** normalises each STT transcript to the building's vocabulary before the Guide sees it
(original transcript passed along too); typed chat has no rewriter ([D-011](../../memory-bank/decisions.md#d-011)).

## Benchmark pipeline

```
question text ─► template parser ──ok──► solver(kind, params) ─► formatter ─► reply + "Answer: …"
                     │ fail                        ▲
                     └► LLM extractor (strict schema) ┘  (resolved + validated in code)
```

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
