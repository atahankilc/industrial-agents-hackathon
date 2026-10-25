---
id: technical-explanation
summary: The short technical explanation for the submission form (architecture + tech stack), in English, only what is built and verified.
sources:
  - docs/architecture/ai-agents.md (agents, voice path, Sunday layers)
  - docs/superpowers/specs/2026-10-25-access-profiles-design.md (access mode)
  - docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md (Edit mode)
  - agent/guide.py, agent/builder.py, agent/creator.py (DEFAULT_MODEL), agent/tools.py (25 Guide tools)
  - frontend/app/package.json (frontend stack)
  - "runs 2026-10-25: test 145/145 answered (hybrid), dev 138/138, tests/test_routes.py 1,338/1,338"
related: [brief.md, scoring.md, ../guides/demo-runbook.md, ../architecture/overview.md, ../architecture/ai-agents.md]
---

# Technical explanation (submission)

[Docs index](../README.md) · Brief: [brief.md](brief.md) · Demo: [demo-runbook.md](../guides/demo-runbook.md)

Text for the Hack and More form. Keep it to what is built; the Sunday and Level 4 facts are linked below.

---

**Talk to Your Building — team jaRAG**

**Idea.** Every building gets a map you can talk to. You ask in plain words, typed or spoken: where something is,
how to get there *for you* (wheelchair, no stairs, a forklift), or what changes when a lift is closed. The answer
comes first; the plan is shown to prove it.

**Architecture: the model talks, the code counts.**

- **Deterministic core (`core/`, Python, shapely + networkx).** Each `building.json` becomes a graph of rooms,
  doors (with widths), stairs and lifts. Routes are shortest paths door to door under the person's profile
  (step-free, minimum door width, avoid lifts, forklift rules) and the current closures. Areas, shared walls,
  reachability and the other benchmark questions are solved in code. All 1,338 reference routes in the kit match
  to the centimetre (length, rooms and doors).
- **Guide agent (Claude Opus 5.5).** Understands the person, asks only what it needs and calls 25 tools on the core
  (find, find nearest, route, tour, reachable rooms, propose / apply a change, show on map, …). It never invents a
  room or a number: every place, route and figure in a reply comes from a tool. A change is always proposed with
  its effect first (who loses access, how much longer routes get) and applied only after a yes.
- **Builder and Creator (Claude Opus 5.5).** Edit mode changes a copy of the building by hand (drag corners,
  doors, equipment) or by prompt ("make Office 0361 one metre wider to the east"): the Builder proposes, the plan
  shows it dashed with its area change and new problems, Apply applies. "Create from floor plans" turns PDFs, scans
  or photos into a building draft (rooms, doors, floors) that opens in Edit mode.
- **Access mode.** Supabase Auth accounts: visitor, invited member (groups per building), admin. Restricted rooms
  are darkened on the plan and removed from every answer and route in the tool layer, before the model sees
  anything. Preferences (wheelchair, avoid stairs, …) are remembered per user.
- **Voice.** ElevenLabs Scribe for speech-to-text (with the building's room names as keyterms) and ElevenLabs TTS
  for the spoken reply; a small Claude Haiku pass maps "lab two seventeen" to "Lab 2.17" before the Guide sees it.
  The browser's speech APIs are the fallback.
- **Benchmark pipeline.** Question → templates → solver → reply with an `Answer:` line written by code. Unseen
  wording goes to an LLM that only fills slots from the building's own vocabulary; every number still comes from
  code. One command, no manual steps: `SUBMISSION/BENCHMARK.md`. Dev set 138/138; test set 145/145 answered.

**Stack.** Python 3.12 (uv), FastAPI, shapely, networkx · Anthropic API (Claude Opus 5.5, Haiku 5.5) · React 19 +
TypeScript + Vite, three.js (react-three-fiber), MapLibre GL · ElevenLabs (Scribe, TTS) · Supabase (Postgres, Auth)
· Vercel.

**Data.** The kit's 280 buildings (OpenStreetMap indoor © OpenStreetMap contributors, ODbL; Swiss Dwellings and
ResPlan, CC BY 4.0; procedural, CC0). 17 OSM buildings are placed on a real map.
