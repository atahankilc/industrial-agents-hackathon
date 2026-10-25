---
id: challenge-brief
summary: What the organisers ask us to build, the five levels, add-ins, personas, judging weights and rules.
sources:
  - "Hackathon Challenge - Talk to Your Building.pdf (3 pages, Synera)"
  - archive/initial-repo/README-cb51a6f.md §1 (story, judging, submission process; dropped from 1.1.0, Q-017)
  - archive/initial-repo/README.md §1, §7 (kit 1.1.0)
related: [scoring.md, ../kit/questions.md, ../architecture/overview.md]
---

# Challenge brief

[Docs index](../README.md) · Next: [scoring.md](scoring.md)

Track 01 of the **Industrial Agents Hackathon 2026** (Synera, with UVC Partners and Anthropic).
Final pitch at Tacto. Kit repo upstream: `Synera-GmbH/industrial-agents-hackathon-2026` (local copy archived in
`archive/initial-repo/`; data + scorer at repo root).

## Mission

> Give any building its own map you can talk to. Feed your system a floor plan and it learns the building.
> Then anyone can just talk to it.

- **Agent** = interaction layer (you say what you want, the system does it).
- **Core** = mostly deterministic: a graph of rooms, doors, corridors, stairs, lifts + a shortest-path search.
  Exact model the answers use: [route-model.md](../kit/route-model.md).
- **App** shows 2D or 3D views of buildings/floors, animated routes, and the things inside (rooms, desks,
  machines, equipment). Works for an existing building and can set up a new one from floor plans quickly.

## The four canonical questions

| Verb | Example | Where it is covered |
|---|---|---|
| FIND | "Where is the 3D printer?" | `locate` warm-up ([questions.md](../kit/questions.md#warm-up-questions)) |
| ROUTE | "Lobby → CNC mill on floor 2 without stairs?" | `route`, `route_step_free`, `tour` |
| EDIT | "Add a door between rooms 2.03 and 2.04." | starter `add_door`; benchmark `what_if_door` |
| REACT | "The east lift is closed for maintenance. What changes?" | `route_with_closure`, `step_free_reachable_count` |

Industrial personas from the README: service technician ("which of the three presses is line 4?"),
forklift driver ("aisle 4 is blocked, fastest route to dock B?"), logistics ("where is the steel drum
delivered yesterday?").

## Levels

Each level earns points and builds on the previous one — stopping early still leaves something working.

1. **Locate** — one floor; talk to the agent, find things, see them on a view.
2. **Route** — A→B on one floor, with step-free routes, closed areas, multi-stop tours.
3. **Scale** — several floors, then several buildings; stairs, lifts, walkways between buildings.
4. **Build** — create/update a building from floor plans *by conversation*. Minutes, not days.
5. **Extend** — pick **one** add-in and do it well (or surprise us):
   - Make things move (barcode / RFID / "this is now here") so the map stays current
   - Several users: colleagues edit while others ask
   - Industrial logistics: forklifts/materials through a hall with blocked aisles and delivery points
   - Capture on site: build a building by walking it with a phone
   - Accessibility: wider doors, step-free and quiet routes
   - Presentation: isometric stacked floors, animated routes, voice in/out
   - AR: route overlay on phone (hard part: localisation — QR at doors, WiFi, …)

## Personas ("put yourself in their shoes")

| Who | Needs |
|---|---|
| First day at work | Knows no room names. "Where do I get coffee?" |
| Wheelchair user | Step-free routes and wide doors, every time, without asking twice |
| Service technician | Hands full; wants voice and "turn left at the press" |
| Facility manager | Moves a machine, closes a lift, adds a door — the map must keep up |

These drive the **Interaction** score — see [judging](#judging).

## Directions from the organisers

- **Think in a graph** — rooms/junctions = nodes, doors/corridors/stairs/lifts = edges; Dijkstra/A*. Agree on
  the data model in hour one → [route-model.md](../kit/route-model.md), [D-002](../../memory-bank/decisions.md#d-002).
- **One floor first** — one question end-to-end before 3D / pretty UI. Flat 2D plan + drawn route is fine;
  three.js for extruded floors later.
- **Spend time on decisions** — what should the agent ask when a request is vague? How does it show what it
  understood before changing a plan? Landmarks ("turn left at the printers") vs room numbers?

## Judging

Order of importance: *does it work → is it a pleasure to use → what did you add that we did not ask for.*

| Part | Points | What counts |
|---|---|---|
| Does it work | **55** | Sunday benchmark + automatic checks on unseen buildings/questions (levels 1–4): correct answers, valid routes, route length vs best, buildings built correctly from plans. Test-set submission is part of this. Details: [scoring.md](scoring.md) |
| Interaction | **25** | Short scripted conversation with tricky users, rubric: asks only what it needs, shows what it understood, directions a person can follow. **Voice counts.** |
| Creativity | **10** | Level 5 and add-ins |
| Submission demo | **10** | Demo video + technical explanation: clear, convincing, the real product. ⚠ Kit 1.1.0 README says "Pitch and demo: a 3–5 minute live demo that works without a restart" — [Q-017](../../memory-bank/open-questions.md#q-017) |

Credits for Claude, Lovable and ElevenLabs come via the organisers (voice-in/voice-out counts towards Interaction).

## Submission and finals

Online, by code freeze, via the organisers' platform — no pitch rooms:
1. Demo video of the app in action
2. Short technical explanation (architecture + tech stack)
3. Repository incl. `BENCHMARK.md` and our answers file ([format: scoring.md](scoring.md#submission-format))

Four finalists → final pitch at Tacto: **3 min + 1 min Q&A**.
Code-freeze time: **unknown** → [Q-002](../../memory-bank/open-questions.md#q-002).

## Rules

- **Generated answers only** — answers must come from our agent running on the data, not hand-labelling.
- **Sunday building arrives in the same format** — anything hard-coded to test buildings will fail.
- No company data / no NDA; data licences still apply: OSM-derived data is **ODbL** (share-alike, credit
  "© OpenStreetMap contributors"), Swiss Dwellings + ResPlan **CC BY 4.0**, procedural **CC0**
  (`ATTRIBUTION.md`).

## Related

- [scoring.md](scoring.md) — exact scoring mechanics
- [questions.md](../kit/questions.md) — what is actually asked
- [architecture/overview.md](../architecture/overview.md) — how we plan to cover the levels
