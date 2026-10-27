# CLAUDE.md — Steward

Entry point for every agent session. Read this file fully, then follow the **Session protocol** below.

## What this repo is

**Steward** ([D-027](memory-bank/decisions.md#d-027), formerly "Talk to Your Building"): an app you can *talk to*
about a building: find things, get routed step by step, edit the building, create one from floor plans, react to
closures and moving machines. A deterministic geometry/graph core computes every answer; the LLM handles the
language. It started at the Industrial Agents Hackathon 2026 (Track 01, submitted
2026-10-25) and is now in ongoing development. Hackathon material is in
[archive/hackathon/](archive/hackathon/README.md).

```
/                                   ← git root (this file)
├── CLAUDE.md                       ← you are here
├── pyproject.toml                  ← uv project (Python ≥3.12)
├── frontend/                       ← React app: map, building search, plan view, Guide, Edit mode
├── backend/                        ← all Python (package `backend`): api → agents → core; core imports neither
│   ├── api/                        ← FastAPI: app.py assembles, routes/ per area, deps.py shared stores; sessions, persistence, voice, live/fleet
│   ├── agents/                     ← LLM layer: Guide, Builder, Creator, campus, compute sandbox, voice rewriter
│   └── core/                       ← deterministic engine: route model, geometry, solvers, edits, plan import
├── tests/                          ← pytest; tests/kit_oracles/ = official kit scorer (score.py, never edit) + parsers + formatter
├── data/                           ← kit dataset: train/ dev/ test/ + manifest.csv (committed, D-005)
├── docs/                           ← curated knowledge base — start at docs/README.md
├── memory-bank/                    ← live project state, decisions, open questions, log
├── scripts/                        ← repo tooling and eval scripts (check_links.py, …)
├── supabase/, vercel.json          ← deploy (D-006)
├── .claude/                        ← agents, /ship skill, commit hook, worklog (dev-workflow.md)
├── archive/initial-repo/           ← rest of the organiser kit, read-only reference (D-004)
├── archive/hackathon/              ← hackathon submission, brief, benchmark runners, weekend log and specs, read-only
└── LICENSE, NOTICE.md, ATTRIBUTION.md, data/README.md  ← licensing: MIT for our code only (D-009)
```

## Session protocol (do this every time)

1. Read [memory-bank/project-state.md](memory-bank/project-state.md) — what exists, what is next.
2. Skim [memory-bank/open-questions.md](memory-bank/open-questions.md) and
   [memory-bank/decisions.md](memory-bank/decisions.md) — never re-decide an `accepted` decision silently.
3. Use [docs/README.md](docs/README.md) to find the doc for your task. Follow links; do not guess.
4. At the end of a work chunk: update `project-state.md`, add an entry to
   [memory-bank/log.md](memory-bank/log.md) (newest on top), and record new decisions / questions.
   Rules for this: [memory-bank/README.md](memory-bank/README.md).

## Anti-hallucination rules

- **Source of truth order (kit facts):** `data/`, `tests/kit_oracles/score.py`, `archive/initial-repo/` code > kit README
  (`archive/initial-repo/README.md`) > the organiser PDF (`archive/hackathon/`) > `docs/`.
  `docs/` summarise; every doc lists its `sources:` in front matter. If a doc and the source disagree, the
  source wins — fix the doc and log it.
- **Never state a number, field name, tolerance or file path you have not seen** in a source or doc. If unsure,
  open the cited source. If still unknown, add it to `open-questions.md` instead of inventing it.
- Mark anything not yet verified as `UNVERIFIED` in docs.
- Don't hard-code to specific buildings or question ids; the core must work on any kit-schema building.

## Doc map (quick links)

| Need | Go to |
|---|---|
| System architecture (frontend, backend, DB, voice, deploy) | [docs/architecture/overview.md](docs/architecture/overview.md) |
| AI agents (Guide, Builder, Creator, solver agent) | [docs/architecture/ai-agents.md](docs/architecture/ai-agents.md) |
| App visuals (vector plan view, map) | [docs/product/visualization.md](docs/product/visualization.md) |
| Living building (live obstacles, fleet) | [docs/product/living-building.md](docs/product/living-building.md) |
| Personas / routing profiles | [docs/product/personas.md](docs/product/personas.md), [docs/product/routing-profiles.md](docs/product/routing-profiles.md) |
| `building.json` / `equipment.csv` / `manifest.csv` schema | [docs/kit/data-format.md](docs/kit/data-format.md) |
| Exact route graph + costs | [docs/kit/route-model.md](docs/kit/route-model.md) |
| Benchmark question kinds and solvers | [docs/kit/questions.md](docs/kit/questions.md), [docs/architecture/solver-plan.md](docs/architecture/solver-plan.md) |
| Original challenge brief, scoring, benchmark code (archived) | [brief](archive/hackathon/docs/challenge/brief.md), [scoring](archive/hackathon/docs/challenge/scoring.md), [benchmark code](archive/hackathon/benchmark-code/README.md) |
| Commands (run app, tests, evaluate, deploy) | [docs/guides/commands.md](docs/guides/commands.md) |
| How to commit (verified workflow) | [docs/guides/dev-workflow.md](docs/guides/dev-workflow.md) |
| Terms (anchor, opening, connector, …) | [docs/guides/glossary.md](docs/guides/glossary.md) |
| ElevenLabs, cloud stack, parsing research | [docs/research/](docs/README.md#research-dated-2026-10-24) |

## Commit workflow (mandatory)

Work on `dev`, never on `main`. Never run `git commit` directly — a hook blocks it. While working, keep
`.claude/worklog/PENDING.md` (from `.claude/worklog/TEMPLATE.md`) listing every claim and the checks you ran;
then use the **`/ship`** skill: an independent `commit-verifier` agent checks the claims against the staged diff,
`commit-fixer` repairs failures, and only a PASS is committed. Details:
[docs/guides/dev-workflow.md](docs/guides/dev-workflow.md), [D-008](memory-bank/decisions.md#d-008).

## Working conventions

- Python ≥ 3.12 via `uv` from the repo root: `uv sync`, `uv run python …` (system `python3` is 3.9). See
  [docs/guides/commands.md](docs/guides/commands.md).
- Secrets live in `.env` (from `.env.example`); never commit `.env`.
- Keep tool results compact and cache the building context.
- When you add or change a doc: give it front matter (`id`, `summary`, `sources`, `related`), link it from
  [docs/README.md](docs/README.md), and add backlinks in the docs it relates to.
- After editing any doc or memory-bank file run `python3 scripts/check_links.py` — it fails on any broken
  file link or `#anchor`.
