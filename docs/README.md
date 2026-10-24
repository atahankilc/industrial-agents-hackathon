---
id: docs-index
summary: Index and reading order for the knowledge base. Every doc is reachable from here.
sources: [CLAUDE.md]
related: [../CLAUDE.md, ../memory-bank/README.md]
---

# Docs index

Back to [CLAUDE.md](../CLAUDE.md) · Live state lives in [memory-bank/](../memory-bank/README.md), not here.

## How the docs are organised

| Folder | Holds | Changes when |
|---|---|---|
| `challenge/` | What the organisers require and how we are judged | Organisers announce something new |
| `kit/` | Facts about the provided kit: data, route model, questions, starter code | Rarely (the kit is fixed) |
| `architecture/` | **Our** design: components, agents, solver plan | We make a decision (log it in [decisions.md](../memory-bank/decisions.md)) |
| `product/` | **Our** users: personas, routing profiles | We learn about users / demo script |
| `research/` | Dated external research (ElevenLabs, cloud stack, parsing experiment) | Re-research; facts may age |
| `guides/` | How-to: commands, glossary | Tooling changes |

`challenge/` and `kit/` are **descriptive** (verified against sources). `architecture/` is **prescriptive**
(our proposals/decisions) — check status markers there.

## All docs

### Challenge
- [challenge/brief.md](challenge/brief.md) — mission, levels 1–5, add-ins, personas, judging weights, rules.
- [challenge/scoring.md](challenge/scoring.md) — `Answer:` line parsing, tolerances per kind, submission CSV,
  Sunday benchmark, format conflicts.

### Kit (provided by organisers; data + scorer extracted to root, rest in `archive/initial-repo/`)
- [kit/repo-layout.md](kit/repo-layout.md) — files, splits, sources, dataset statistics.
- [kit/data-format.md](kit/data-format.md) — `building.json`, `equipment.csv`, `manifest.csv` schemas.
- [kit/route-model.md](kit/route-model.md) — the exact graph + cost model behind expected route lengths.
- [kit/questions.md](kit/questions.md) — warm-up and benchmark question kinds, precise definitions, counts.
- [kit/starter-agent.md](kit/starter-agent.md) — how the starter agent works, its tools, what it lacks.

### Architecture (ours)
- [architecture/overview.md](architecture/overview.md) — what we need (frontend, backend, DB, realtime, voice, CI), topology, collaboration flow, build order.
- [architecture/ai-agents.md](architecture/ai-agents.md) — Building Guide, benchmark pipeline, Builder; shared tools; voice path.
- [superpowers/specs/2026-10-24-guide-agent-design.md](superpowers/specs/2026-10-24-guide-agent-design.md) — design of the v1 Guide (`agent/guide_v1/`, branch `1-agentic-yarag`): terminal, multi-turn, grounded, clarifies only what matters.
- [superpowers/plans/2026-10-24-guide-agent.md](superpowers/plans/2026-10-24-guide-agent.md) — v1 Guide implementation plan (6 tasks).
- [architecture/solver-plan.md](architecture/solver-plan.md) — one deterministic function per benchmark kind — all VERIFIED 655/655, with the rules the data settled.

### Product (ours)
- [product/personas.md](product/personas.md) — 18 ranked personas with needs, data feasibility, what to ask / never ask.
- [product/visualization.md](product/visualization.md) — app visuals: current vector plan view (`core/floorplan.py`, `GET /sessions/{id}/plan`) and the superseded point-cloud scene; three.js vs react-three-fiber.
- [product/routing-profiles.md](product/routing-profiles.md) — deterministic profile model (hard filters + soft penalties) on top of the exact route model.

### Research (dated 2026-10-24)
- [research/elevenlabs.md](research/elevenlabs.md) — Agents Platform, Scribe STT, TTS, integration options.
- [research/stack-options.md](research/stack-options.md) — Lovable, Supabase, hosting, CI, day-one checklist.
- [research/question-parsing.md](research/question-parsing.md) — Q-008 experiment: templates, parser accuracy.

### Guides
- [guides/commands.md](guides/commands.md) — setup, chat, evaluate, score, produce submission.
- [guides/dev-workflow.md](guides/dev-workflow.md) — verified commits: worklog claims → verifier agent → fixer loop → hook-enforced stamp.
- [guides/glossary.md](guides/glossary.md) — shared vocabulary.

## Suggested reading order for a new agent

1. [brief](challenge/brief.md) → 2. [scoring](challenge/scoring.md) → 3. [data-format](kit/data-format.md) →
4. [route-model](kit/route-model.md) → 5. [questions](kit/questions.md) → 6. [overview](architecture/overview.md) →
7. [solver-plan](architecture/solver-plan.md) → 8. [personas](product/personas.md)

## Linking conventions

- Relative links only, with heading anchors (`file.md#heading-slug`, GitHub-style: lowercase, spaces → `-`,
  punctuation dropped). Keep headings stable; if you rename one, grep for its slug and fix links.
- Memory-bank items are referenced by ID: `D-###` (decision), `Q-###` (open question), e.g.
  [Q-001](../memory-bank/open-questions.md#q-001).
- Source code is cited as repo-root-relative `path/file.py:line` (e.g. `core/building_map.py:179`).
