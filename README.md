# Steward

Talk to your building. Agent-first indoor navigation and building management. Ask a building where things are, how to get there, and what changes when a lift
closes or a forklift blocks an aisle; edit the building or create one from floor plans. A deterministic
geometry/graph core computes every answer and the LLM handles the language.

Started at the Industrial Agents Hackathon 2026, Track 01 (Synera); submitted 2026-10-25, now in ongoing
development. The submission and the weekend's history are in [archive/hackathon/](archive/hackathon/README.md).

Project knowledge base: [CLAUDE.md](CLAUDE.md) → [docs/README.md](docs/README.md). All commands:
[docs/guides/commands.md](docs/guides/commands.md).

Live: https://steward-io.vercel.app

## Features

### 1. Find a building on the map

The landing page is a city map (MapLibre on OpenFreeMap tiles, light and dark) with a pin for every building that
has a real position (the 17 OSM buildings in `backend/api/locations.json`, plus buildings created from plans). A search pill on the map opens the full list: all 280 kit
buildings (Swiss Dwellings, ResPlan, procedural campuses / factories / offices, OSM indoor maps) plus buildings users
have created, grouped by kind. Code: `frontend/src/map/`.

### 2. A plan view of the building

Each building opens as a calm 2D vector plan (`frontend/src/plan/`, data from `backend/core/floorplan.py`): rooms,
walls with door gaps, a strip per doorway (closed doors in red), stairs and lifts, furniture and equipment drawn to
their real footprints, labels only where they fit. Tap a room for its card. Only what the data holds is drawn (no
door swings, no stair direction: the kit has neither).
[visualization.md](docs/product/visualization.md)

### 3. The Guide: ask the building in plain words

A floating chat on the building screen. Ask "where is the nearest printer?", "how do I get to Lab 2.20?", "how many
meeting rooms are on floor 3?" and the Guide (Claude, `backend/agents/guide.py`) answers by calling tools on the
deterministic core: search, room facts, routes, nearest item, counts, reachability, tours, every benchmark question
kind, and a sandboxed Python `compute` over a copy of the building for anything else. Every number in a reply must come
from a tool: a grounding check catches invented numbers and has the model repair them
([D-010](memory-bank/decisions.md#d-010)). Names that fit several rooms make it ask which one
([D-012](memory-bank/decisions.md#d-012)). Without an API key a rule-based offline Guide handles simple phrasings.
[ai-agents.md](docs/architecture/ai-agents.md)

### 4. Routes: an overview first, then step by step

A route reply is a short summary (total metres, floors crossed, a landmark or two); the plan frames the whole
route, floors stacked when it changes floor. "Start" begins the step guide: each step is framed and read aloud, and
"I'm there" / "next" (button, typed or spoken) moves on ([D-020](memory-bank/decisions.md#d-020)). The route line
follows the walk the route model measures, door to door inside each space. "You are here": tell the Guide where you
are, or tap one of the rooms it suggests.

### 5. Routes that fit the person

The same router with different parameters ([routing-profiles.md](docs/product/routing-profiles.md)): presets for
wheelchair, pram, trolley, no lifts and forklift (step-free, minimum door width, avoid lifts, forklift aisles), set
by the Guide when you mention them. In access mode soft preferences add to these: prefer lifts, fewer doors, quiet
routes, avoid halls, simple routes, avoid room types. Personas behind them: [personas.md](docs/product/personas.md).

### 6. Voice

Speak instead of typing ([D-016](memory-bank/decisions.md#d-016)–[D-019](memory-bank/decisions.md#d-019)):

- your words go to ElevenLabs Scribe Realtime, primed with the building's room and asset names (browser recognition
  as fallback);
- the reply is spoken with ElevenLabs TTS through our backend, sentence by sentence while the Guide still works,
  and only sentences that pass the grounding check (browser voice as fallback);
- a spoken question starts a hands-free conversation: the Guide listens again after it answers, and you can
  interrupt it (barge-in).

`/v1/chat/completions` is an OpenAI-compatible endpoint for an ElevenLabs Custom LLM agent (not connected yet).

### 7. Nearby buildings

In a building with located neighbours (≤ 600 m) the Guide can search them and route there: inside here, a
straight-line outdoor leg, inside there. "Continue" opens the next building with you at its entrance and the rest of
the route drawn ([D-021](memory-bank/decisions.md#d-021)).

### 8. Edit mode and the Builder

Change the building by hand or by asking (`frontend/src/edit/`, `backend/core/edits.py`, `backend/agents/builder.py`):
drag corners (shared walls stay shared), move doors along walls, move equipment, undo. The validator marks problems
(overlaps, doors off a shared wall, unreachable rooms) in red. In the Edit mode chat the Builder proposes edits
("add a door between the lab and the corridor"), shown as a ghost on the plan with Apply / Cancel; nothing changes
without a confirmation. Saved buildings get their own id and the Guide routes in them. In the Guide, changes like
closing a lift are also proposed first and applied on confirmation, and the reply says which rooms lost access.

### 9. Create a building from floor plans

Right-click a building on the map → "Create a building here", then upload PDFs, photos or scans (HEIC too), one
floor number per file. The Creator (`backend/agents/creator.py` over `backend/core/plan_import/`) builds the whole
building: code does the geometry (walls, rooms, doors, scale, stacking floors), the model reads the drawings (which
page is which floor, room names from legends). The result opens in Edit mode with the straightened plan beside it
to trace over. It is then fitted onto the OSM footprint and you place it by hand (drag, turn, size)
([D-023](memory-bank/decisions.md#d-023)).

### 10. The living building

Connected things move through the building and change routes ([living-building.md](docs/product/living-building.md)):
forklifts and AGVs in factories, delivery and cleaning robots, pallets and carts left in walkways. A standing thing
cuts the walk past it (a wider clearance for a wheelchair or a forklift), a moving one adds a wait, a cleaned floor
is wet for a while. A route on the map is rerouted when it gets blocked, with a notice (spoken while guiding), and a
shorter way is offered once it clears. **These things are simulated** and labelled so; real devices can register
and report positions through `POST /live/devices`.

### 11. Access mode (optional)

Behind `ACCESS_MODE=on`, off by default ([D-015](memory-bank/decisions.md#d-015)): Supabase accounts, one admin over
every building, members invited per building in groups, restricted rooms that people without access never see (not
on the plan, not in any answer or route), and preferences remembered per user. The admin manages them in Building
settings (Access / People / Objects).

### Not built yet

Camera walk mode (`frontend/src/ui/CameraGuide.tsx` exists but is not wired into the app), sign-in-based shared
editing (branch `collab-edits`), handling of bays marked `through: false`, a checked phone layout. Current list:
[memory-bank/project-state.md](memory-bank/project-state.md#next).

## Repository layout

```
frontend/          React + Vite app: map, building search, plan view, Guide, Edit mode
backend/           all Python, one package `backend`
  api/             FastAPI server: HTTP endpoints, sessions, Supabase persistence, voice, live building
  agents/          LLM layer: the Guide, Builder and Creator agents and their tools
  core/            deterministic engine: route graph, geometry, solvers, edits, plan import (no LLM, no HTTP)
tests/             pytest; tests/kit_oracles/ holds the official kit scorer and question parsers used as oracles
data/              the kit's buildings, one folder each (data/buildings/<id>/) + manifest.csv
scripts/           repo tooling and eval scripts
docs/ memory-bank/ knowledge base and project state; archive/ is read-only history
```

A request goes `frontend → backend/api → backend/agents → backend/core`: the agents choose what to compute, the
core computes it. `core` never imports `agents` or `api`; the only upward imports are the Builder
(`builder.py`, `builder_tools.py`) using `backend/api/drafts.py` and `backend/api/persistence.py`.

## Setup

You need Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node.js for the app, and an Anthropic API key. The
organiser kit's dataset is committed in `data/`, so one clone is enough.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # if uv is missing
git clone https://github.com/atahankilc/steward.git
cd steward
uv sync
cp .env.example .env                                  # put ANTHROPIC_API_KEY in .env (never commit it)
```

## Running the app

```bash
npm run dev                                           # backend + app; open http://localhost:5390
```

`npm run dev` (repo root, `scripts/dev.sh`) starts the backend on **8390** and the app on **5390**, ports picked to
stay clear of other local projects; Ctrl-C stops both. Move them with `BACKEND_PORT=… FRONTEND_PORT=… npm run dev`.
Without a `.env` the Guide runs offline (no key needed). Each side on its own:

```bash
uv run --env-file .env uvicorn backend.api.app:app --port 8390  # backend
cd frontend && npm install && npm run dev                      # app on http://localhost:5390 (vite.config.ts)
```

## Tests

```bash
uv run pytest -q                                      # offline tests
python3 scripts/check_links.py                        # docs and memory-bank links
cd frontend && npm run build                          # type-check + production bundle
```

## Benchmark (archived)

The hackathon benchmark runners, the kit evaluator and the v1 Guide are in
[archive/hackathon/benchmark-code/](archive/hackathon/benchmark-code/README.md), with how to restore and run them.
`tests/kit_oracles/score.py` (the organisers' official scorer, never edit it) stays: the solver tests use it. The rest of the
organiser kit (starter agent) is in `archive/initial-repo/`.

## Licences

Our code is MIT ([LICENSE](LICENSE)). Kit code and data keep their own terms: see [NOTICE.md](NOTICE.md),
[ATTRIBUTION.md](ATTRIBUTION.md) and [data/README.md](data/README.md). Anything derived from the OpenStreetMap
buildings stays under the ODbL and credits © OpenStreetMap contributors.
