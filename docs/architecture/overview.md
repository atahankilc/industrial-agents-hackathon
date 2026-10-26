---
id: arch-overview
summary: System architecture (stack accepted in D-006, zero-cost revision; repo layout and build order proposed) — what we need (frontend, backend, DB/realtime, voice, agents, CI, hosting), topology, collaboration flow, repo layout and build order.
status: accepted (D-006, zero-cost revision, 2026-10-24) — repo layout and build order remain proposals
sources: [../research/stack-options.md, ../research/elevenlabs.md, ../../archive/hackathon/docs/challenge/brief.md, ../../archive/hackathon/docs/challenge/scoring.md]
related: [ai-agents.md, solver-plan.md, ../product/personas.md, ../product/routing-profiles.md, ../../memory-bank/decisions.md]
---

# Architecture overview

[Docs index](../README.md) · Agents: [ai-agents.md](ai-agents.md) · Research: [stack](../research/stack-options.md),
[voice](../research/elevenlabs.md) · Decision: [D-006](../../memory-bank/decisions.md#d-006)

## Principle

**LLM for language, code for facts** ([D-003](../../memory-bank/decisions.md#d-003)). Routing is deterministic and
explainable; personas change *parameters* of the same router, never the algorithm
([routing-profiles.md](../product/routing-profiles.md)).

## What we need

| # | Component | Choice (accepted, D-006) | Why | Details |
|---|---|---|---|---|
| 1 | **Deterministic core** | Python package `core/` (shapely, networkx) | exact route model, geometry, solvers, profiles; shared by API + CLI | [solver-plan.md](solver-plan.md) |
| 2 | **Backend API** | FastAPI on **Vercel's Python runtime** (zero cost; Render Free / Modal fallback) — was Railway | Python needed for core + Claude SDK; same project as the frontend; streaming OK, no WebSockets (Supabase does push) | [stack §9](../research/stack-options.md#9-zero-cost-variant-added-2026-10-24) |
| 3 | **AI agents** | Claude (Anthropic API) in the backend: Guide, Builder; benchmark pipeline | one brain for text + voice | [ai-agents.md](ai-agents.md) |
| 4 | **Voice** | ElevenLabs Agents with **Custom LLM** → our backend; client tools drive the map | turn-taking/interruptions/TTS for free, logic stays ours | [elevenlabs.md](../research/elevenlabs.md#tldr-recommendation) |
| 5 | **Database** | **Supabase Postgres**: buildings (original JSON), `building_edits` event log, conversations, profiles | JSON + event log = undo, audit, replay | [stack data model](../research/stack-options.md#data-model-sketch-postgres) |
| 6 | **Realtime collaboration** | Supabase Realtime: broadcast on `building:<id>` + Presence | instant edits for all clients, who's online | [stack §2](../research/stack-options.md#2-realtime--database) |
| 7 | **Auth** | Supabase Auth (anon / magic link); roles visitor vs facility manager | only editors may apply changes | — |
| 8 | **File storage** | Supabase Storage | floor-plan uploads for the Builder (L4) | — |
| 9 | **Frontend** | Vite + React + TS + Tailwind + shadcn/ui in `frontend/`; 2D SVG plan + react-three-fiber stacked floors | Lovable can't sync a monorepo subfolder → own app; Lovable only for mock-ups | [stack §1](../research/stack-options.md#1-lovable) |
| 10 | **Frontend hosting** | Vercel Hobby, same project as the backend (Services), preview per PR | zero-config, previews, free | [stack](../research/stack-options.md#frontend-hosting) |
| 11 | **CI** | GitHub Actions: tests, link check, oracle + solver eval on dev (no API keys) | regressions on the 55-point part caught per push | [stack §4](../research/stack-options.md#4-ci-github-actions) |
| 12 | **Benchmark CLI** | `run_benchmark_v1 <building_dir> <questions> <answers>` + `archive/hackathon/SUBMISSION/BENCHMARK.md` (archived 2026-10-26) | Sunday requirement; no cloud needed | [scoring.md](../../archive/hackathon/docs/challenge/scoring.md#sunday-benchmark) |

## Topology

```
      Browser (team, judges, phone)  ── React app on Vercel ─────────────────────────────
        │ chat (REST + SSE)        │ edits & presence (WS)          │ voice (WebRTC)
        ▼                          ▼                                ▼
  ┌───────────────────────┐   ┌─────────────────────────┐   ┌────────────────────────────┐
  │ FastAPI  (Vercel fn)  │──►│ Supabase                │   │ ElevenLabs Agent           │
  │  core/ router+solvers │   │  Postgres: buildings,   │   │  STT · turn-taking · TTS   │
  │  Guide agent (Claude) │◄──┤  building_edits, convos │   │  Custom LLM ───────────────┼─► FastAPI
  │  /v1/chat/completions │   │  Realtime broadcast +   │   │  client tools ─► browser   │   /v1/chat/completions
  │  ElevenLabs token mint│   │  presence · Storage     │   └────────────────────────────┘
  │  only writer of edits │   │  Auth                   │
  └──────────┬────────────┘   └─────────────────────────┘
             │ same package, offline
             ▼
   run_benchmark <building_dir> <questions.json> <answers.json>   (archived 2026-10-26)
```

(The stack research sketched ElevenLabs calling us via webhook tools; the voice research recommends Custom LLM
instead so there is one agent brain. Webhooks remain the fallback.)

## Collaboration flow (instant updates)

1. Facility manager: "Close the east lift." → Guide calls `propose_change` → UI shows an effect card.
2. Confirm → backend `apply_change`: validates, appends a row to `building_edits` (who, when, kind, payload).
3. Backend broadcasts on `building:<id>` → every open client applies the edit and re-renders; active routes that
   used the lift are recomputed and flagged ("your route changed: +40 m via stairs core B").
4. Backend's in-memory `BuildingMap` per building = original JSON + replayed edits.
5. Presence shows who is viewing / editing which floor.

The backend is the **only writer**: no conflicting edits, one place for validation.

## Repo layout (target)

```
/
├── core/            deterministic: building_map, geometry, profiles, question_parser, solvers, formatter
├── api/             FastAPI app: chat/SSE, OpenAI-compatible endpoint for ElevenLabs, edits, tokens
├── agent/           Claude Guide + Builder: prompts, tool wiring
├── benchmark/       official kit scorer/evaluator (unchanged)
├── frontend/        Vite React app
├── supabase/        migrations (SQL), seed script
├── tests/           pytest: solvers vs train/dev, parser, router profiles
├── data/ docs/ memory-bank/ scripts/ archive/   (hackathon SUBMISSION/ now in archive/hackathon/)
└── .github/workflows/ci.yml
```

## Build order (each step leaves something demoable)

1. **Core + solvers + parser** verified on train/dev → test CSV (55 pts, no cloud needed).
2. **API + minimal frontend** (2D plan, search, route drawn) deployed — Level 1–2 online.
3. **Supabase** edits + realtime + presence — collaboration.
4. **Guide agent** with profiles + clarification → **voice** via ElevenLabs.
5. **3D stacked floors**, animated route; **Builder** (L4); one add-in (L5, [Q-010](../../memory-bank/open-questions.md#q-010)).

Day-one cloud checklist (accounts, secrets): [stack-options.md](../research/stack-options.md#7-day-one-setup-checklist-human-actions--ask-before-creating-anything).

## Related
- [ai-agents.md](ai-agents.md) · [solver-plan.md](solver-plan.md) · [stack-options.md](../research/stack-options.md) ·
  [elevenlabs.md](../research/elevenlabs.md) · [personas.md](../product/personas.md)
