---
id: log
summary: Append-only session log, newest first. One entry per session/work chunk.
related: [project-state.md, decisions.md, open-questions.md]
---

# Log

[Memory bank](README.md)

Template: `## YYYY-MM-DD HH:MM — title` then *Did / Learned / Changed docs / Opened-closed Q / Next*.

## 2026-10-24 — Licensing, configurable parsing, point-cloud prototype

- **Did:** Checked licences: data CC BY 4.0 / ODbL / CC0 (redistributable with attribution; ODbL share-alike);
  upstream kit repo has no licence → kit code flagged (Q-013). Added `LICENSE` (MIT; Atahan confirmed MIT), `NOTICE.md`,
  `data/README.md`. Added parser modes (`agent/parsing.py`) + LLM parser (`agent/llm_parser.py`) + offline tests
  + live eval script. Point-cloud 3D prototype (three.js) built and verified in Chrome by a background agent;
  viewer shows building attribution (ODbL credit for OSM).
- **Learned:** Opus 5.5 rejects forced `tool_choice` → structured outputs (`output_config.format`) for extraction.
- **Decisions:** D-007 accepted (configurable, hybrid default); D-009 accepted (MIT, Atahan confirmed).

## 2026-10-24 — Verified-commit workflow (.claude/)

- **Did:** Added `commit-verifier` + `commit-fixer` agents, `/ship` skill, worklog template/history, commit-gate
  hook + stamp script, `.claude/settings.json`; documented in [dev-workflow.md](../docs/guides/dev-workflow.md).
- **Learned:** the hook went live immediately and blocked a test command containing a `git commit --amend` string —
  test hook inputs via a script file, not inline.
- **Decisions:** D-008 accepted.
- **Next:** first commit via `/ship` once the GitHub repo question is answered.

## 2026-10-24 — Restructure, setup, research (4 parallel agents)

- **Did:** `uv sync` + oracle on dev (369/369). Moved data + scorer to root, copied `building_map.py` to `core/`,
  archived the kit, root `pyproject.toml`. Research agents wrote ElevenLabs, cloud-stack, question-parsing docs and
  personas + routing profiles; I wrote [overview.md](../docs/architecture/overview.md) and
  [ai-agents.md](../docs/architecture/ai-agents.md) (renamed from agents.md: macOS case-insensitivity made it match
  `AGENTS.md`).
- **Learned:** one template per benchmark kind → regex parser 100%; Lovable can't sync a monorepo subfolder;
  ElevenLabs Custom LLM lets one Claude brain serve voice + text; only 30/23,748 openings have steps (all
  entrances) — lifts and door widths are the real accessibility constraints; 77 multi-floor buildings have no lift.
- **Decisions:** D-004, D-005 accepted (Atahan); D-006, D-007 proposed.
- **Budget:** $150 Claude credits announced (Q-012). Spend so far: $0 API (all deterministic).
- **Next:** [project-state.md](project-state.md#next-priorities).

## 2026-10-24 — Foundation: docs + memory bank

- **Did:** Read the PDF brief, kit README, ATTRIBUTION, starter agent and benchmark code; scanned all 280
  buildings and all question files for schemas and counts. Created `CLAUDE.md`, `docs/` (challenge, kit,
  architecture, guides) and `memory-bank/`.
- **Learned:**
  - Test set = 145 questions in 8 kinds; floor_area_total + shared_walls_count = 41%.
  - Route model fully specified and implemented in `starter_agent/building_map.py`.
  - Scorer: units like `m2` are safe; room refs / extra numbers on a number answer line are fatal.
  - PDF and README disagree on Sunday output format (Q-001).
  - System `python3` is 3.9; the kit needs ≥3.12 → use `uv`.
- **Decisions:** D-001 accepted; D-002, D-003 proposed.
- **Questions opened:** Q-001 … Q-012.
- **Next:** see [project-state.md](project-state.md#next-priorities).
