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
| `kit/` | Facts about the provided kit: data, route model, questions, starter code | Rarely (the kit is fixed) |
| `architecture/` | **Our** design: components, agents, solver plan | We make a decision (log it in [decisions.md](../memory-bank/decisions.md)) |
| `product/` | **Our** users: personas, routing profiles | We learn about users / demo script |
| `research/` | Dated external research (ElevenLabs, cloud stack, parsing experiment) | Re-research; facts may age |
| `guides/` | How-to: commands, glossary | Tooling changes |

`kit/` is **descriptive** (verified against sources). `architecture/` is **prescriptive**
(our proposals/decisions) — check status markers there.

## All docs

### Kit (provided by organisers; data + scorer extracted to root, rest in `archive/initial-repo/`)
- [kit/repo-layout.md](kit/repo-layout.md) — files, splits, sources, dataset statistics.
- [kit/data-format.md](kit/data-format.md) — `building.json`, `equipment.csv`, `manifest.csv` schemas.
- [kit/route-model.md](kit/route-model.md) — the exact graph + cost model behind expected route lengths.
- [kit/questions.md](kit/questions.md) — warm-up and benchmark question kinds, precise definitions, counts.

### Architecture (ours)
- [architecture/overview.md](architecture/overview.md) — what we need (frontend, backend, DB, realtime, voice, CI), topology, collaboration flow, build order.
- [architecture/ai-agents.md](architecture/ai-agents.md) — Building Guide, Builder, Creator; shared tools; voice path; the (archived) benchmark pipeline.
- [architecture/solver-plan.md](architecture/solver-plan.md) — one deterministic function per benchmark kind — all VERIFIED 655/655, with the rules the data settled.

### Product (ours)
- [product/personas.md](product/personas.md) — 18 ranked personas with needs, data feasibility, what to ask / never ask.
- [product/visualization.md](product/visualization.md) — app visuals: current vector plan view (`backend/core/floorplan.py`, `GET /sessions/{id}/plan`) and the superseded (removed) point-cloud scene; three.js vs react-three-fiber.
- [product/routing-profiles.md](product/routing-profiles.md) — deterministic profile model (hard filters + soft penalties) on top of the exact route model.
- [product/living-building.md](product/living-building.md) — connected things (forklifts, robots, tagged pallets) reporting positions; how they cut walks, reroute the route on the map, the plan layer and the demo simulation.
- [product/organizations.md](product/organizations.md) — organisations own buildings (roles, listed / unlisted / private), their own maps shared by link, sites shown as close islands; phase 1 and 2a/2b (maps, share links, organisations sheet) built, 2c–4 planned.

### Research (dated 2026-10-24)
- [research/elevenlabs.md](research/elevenlabs.md) — Agents Platform, Scribe STT, TTS, integration options.
- [research/stack-options.md](research/stack-options.md) — Lovable, Supabase, hosting, CI, day-one checklist.
- [research/question-parsing.md](research/question-parsing.md) — Q-008 experiment: templates, parser accuracy.

### Guides
- [guides/commands.md](guides/commands.md) — setup, chat, evaluate, score, produce submission.
- [guides/dev-workflow.md](guides/dev-workflow.md) — verified commits: worklog claims → verifier agent → fixer loop → hook-enforced stamp.
- [guides/glossary.md](guides/glossary.md) — shared vocabulary.

## Archived (hackathon, 2026-10-24 – 2026-10-25)

Moved to [archive/hackathon/](../archive/hackathon/README.md) on 2026-10-26; read-only history.

- [challenge/brief.md](../archive/hackathon/docs/challenge/brief.md) — mission, levels 1–5, add-ins, personas, judging weights, rules.
- [challenge/scoring.md](../archive/hackathon/docs/challenge/scoring.md) — `Answer:` line parsing, tolerances per kind, submission CSV,
  Sunday benchmark, format conflicts.
- [kit/starter-agent.md](../archive/hackathon/docs/kit/starter-agent.md) — how the starter agent works, its tools, what it lacks.
- [benchmark-code/README.md](../archive/hackathon/benchmark-code/README.md) — the benchmark runners, v1 Guide, kit evaluator and their commands.
- [technical-explanation.md](../archive/hackathon/technical-explanation.md) — the submission form's technical
  explanation (architecture + stack), built facts only.
- [superpowers/specs/2026-10-24-builder-edit-mode-design.md](../archive/hackathon/superpowers/specs/2026-10-24-builder-edit-mode-design.md) — PROPOSED design of the app's Edit mode (L4 step 1): edit a copy of a building by prompt and drag on a 2D plan with 3D preview; validator; drafts; Builder agent.
- [superpowers/plans/2026-10-25-plan-import.md](../archive/hackathon/superpowers/plans/2026-10-25-plan-import.md) — implementation plan (14 tasks) for the Creator / plan import.
- [superpowers/plans/2026-10-25-plan-reference-and-location.md](../archive/hackathon/superpowers/plans/2026-10-25-plan-reference-and-location.md) — implementation plan (8 tasks, 3 milestones) for the plan reference in Edit mode and buildings created at a place on the map.
- [superpowers/specs/2026-10-25-plan-import-design.md](../archive/hackathon/superpowers/specs/2026-10-25-plan-import-design.md) — PROPOSED design of Builder project 2 (L4): the Creator agent turns PDFs / photos of floor plans into a building.json draft (code segments rooms, Claude vision labels them, scale, stacking, validate) and hands it to Edit mode.
- [superpowers/specs/2026-10-25-plan-reference-and-location-design.md](../archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md) — IMPLEMENTED 2026-10-25: the straightened source plan beside the editor in Edit mode (with a trace underneath), and creating a building at a place on the map, fitted onto its OSM footprint (position with bearing), GPS check, supersede on re-save.
- [superpowers/specs/2026-10-24-guide-agent-design.md](../archive/hackathon/superpowers/specs/2026-10-24-guide-agent-design.md) — design of the v1 Guide (`agent/guide_v1/`, archived 2026-10-26 to `archive/hackathon/benchmark-code/`, branch `1-agentic-yarag`): terminal, multi-turn, grounded, clarifies only what matters.
- [superpowers/plans/2026-10-24-builder-edit-mode-m3.md](../archive/hackathon/superpowers/plans/2026-10-24-builder-edit-mode-m3.md) — Builder Edit mode milestone-3 plan: drafts, saved buildings and Builder history in Supabase for the deployed app (6 tasks; Tasks 1–5 done 2026-10-24, deploy pending).
- [superpowers/plans/2026-10-24-builder-edit-mode-m2.md](../archive/hackathon/superpowers/plans/2026-10-24-builder-edit-mode-m2.md) — Builder Edit mode milestone-2 plan: prompt edits by a Builder agent (5 tasks).
- [superpowers/plans/2026-10-24-builder-edit-mode-m1.md](../archive/hackathon/superpowers/plans/2026-10-24-builder-edit-mode-m1.md) — Builder Edit mode milestone-1 implementation plan (7 tasks).
- [superpowers/plans/2026-10-24-guide-agent.md](../archive/hackathon/superpowers/plans/2026-10-24-guide-agent.md) — v1 Guide implementation plan (6 tasks).
- [superpowers/plans/2026-10-25-access-profiles.md](../archive/hackathon/superpowers/plans/2026-10-25-access-profiles.md) — implementation plan for access mode: phase 1 tasks (switch, accounts, restricted spaces), phases 2–4 outlined.
- [superpowers/specs/2026-10-25-access-profiles-design.md](../archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md) — ACCEPTED demo feature behind `ACCESS_MODE` (off by default): accounts (one admin, invited members), restricted spaces darkened and hidden from answers, remembered user preferences, moving objects with live positions and machine-readable missions; replaces parts of the access-roles design.
- [superpowers/specs/2026-10-24-access-roles-design.md](../archive/hackathon/superpowers/specs/2026-10-24-access-roles-design.md) — demo feature design (not built): roles with room access + physical limits set by the facility manager in conversation, building-wide rules and changes, manager-only edits; benchmark untouched.
- [demo-runbook.md](../archive/hackathon/demo-runbook.md) — demo video (2 min) and final pitch: building, exact lines, expected answers, checklist.

## Suggested reading order for a new agent

1. [overview](architecture/overview.md) → 2. [ai-agents](architecture/ai-agents.md) →
3. [visualization](product/visualization.md) → 4. [data-format](kit/data-format.md) →
5. [route-model](kit/route-model.md) → 6. [personas](product/personas.md) → 7. [commands](guides/commands.md).
For the benchmark: [brief](../archive/hackathon/docs/challenge/brief.md), [scoring](../archive/hackathon/docs/challenge/scoring.md), [questions](kit/questions.md),
[solver-plan](architecture/solver-plan.md).

## Linking conventions

- Relative links only, with heading anchors (`file.md#heading-slug`, GitHub-style: lowercase, spaces → `-`,
  punctuation dropped). Keep headings stable; if you rename one, grep for its slug and fix links.
- Memory-bank items are referenced by ID: `D-###` (decision), `Q-###` (open question), e.g.
  [Q-001](../memory-bank/open-questions.md#q-001).
- Source code is cited as repo-root-relative `path/file.py:line` (e.g. `backend/core/building_map.py:179`).
