# Sunday hardening: parser paraphrase check, Swiss frame check, no above/below on unaligned buildings

- **Author:** Claude (Guide session) · **Date:** 2026-10-24
- **Related:** Q-008, D-007, Q-006; docs/architecture/solver-plan.md#straight_line_3d, docs/research/question-parsing.md#risks

## Summary
Measured the parser on reworded questions (the main Sunday risk) and settled the Swiss `straight_line_3d` frame
risk with data. One code change: the Guide's `room_facts` no longer reports rooms above/below on Swiss Dwellings
buildings, whose floors are not aligned.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Live paraphrase eval: regex 0/31, llm 31/31, hybrid 31/31 across 9 kinds (4 per kind, step_free_reachable_count 1, what_if_door 2); parser tokens 4,970 in / 7,820 out / 328,984 cache read / 69,620 cache write | — | output saved at /private/tmp/claude-501/-Users-atahankilic-Documents-industrial-agents-hackathon/be12c591-7eb6-4e67-96c4-e06bb82e9cfb/scratchpad/paraphrase.txt (tail); do not re-run (paid) |
| C2 | All 30 train+dev and all 15 test `straight_line_3d` questions are on procedural/OSM buildings; 84 of 108 multi-floor Swiss buildings have every floor's space-bbox centre within 2 m of the origin on each axis (per-axis; 82 with a Euclidean 2 m radius) | data/ | re-count with a short script over `data/*/*/questions*.jsonl`, `data/test/questions.csv` and `data/*/swiss-*/building.json` |
| C3 | `room_facts` on a `swiss_dwellings` building returns `stacked = {"note": …}` instead of above/below; other sources unchanged | `agent/tools.py` (`UNALIGNED_SOURCES`, `tool_room_facts`) | `uv run pytest -q tests/test_agent_tools.py` (`test_room_facts_skips_stacking_on_unaligned_buildings`) |
| C4 | Benchmark unaffected: train 515/517 (the 2 known Q-006 identical-text cases), dev 138/138 | — | `PARSER_MODE=regex uv run python -m benchmark.evaluate data/train --agent agent.benchmark_agent:answer --name train` and `… data/dev …` |
| C5 | Docs: ai-agents tool table `room_facts` row (above/below omitted on Swiss), solver-plan straight_line_3d section (risk checked, evidence), question-parsing Risks (measured), Q-008 live evidence, project-state priority 5, log | `docs/`, `memory-bank/` | `python3 scripts/check_links.py` |
| C6 | Tests | — | `uv run pytest -q` → 147 passed |

## Checks I ran
- `uv run --env-file .env python scripts/eval_llm_parser.py --per-kind 4 --paraphrase` → table above (C1)
- `PARSER_MODE=regex uv run python -m benchmark.evaluate data/train …` → `all 515 / 517 (100%)`
- dev (earlier this session, no solver/parser change since) → `all 138 / 138 (100%)`
- Swiss/straight_line counts via inline Python (C2): `straight_line_3d by source (train+dev): {'proc': 20, 'osm': 10}`, `swiss multi-floor buildings: 108 | every floor centred at ~origin: 84`; test: straight_line_3d proc 11, osm 4
- Real-Claude turns through the Vite proxy `/api/chat` (Opus 5.5): wheelchair route (15 vertices), "lift broken" → propose, "yes" → change event `space_ids` = 4 lift shafts + route via Lift 2; ungrounded [] on all 3 (not part of the diff; evidence for the log entry)
- `uv run pytest -q` → `147 passed in 17.53s`; `python3 scripts/check_links.py` → OK (26 files)
- After fix round 1: `uv run pytest -q` → `147 passed in 18.46s`; `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (priority 5)
- [x] `memory-bank/log.md` entry added (spend estimate ≈ $1.4 total; the paraphrasing calls are not metered by the script, so this is an estimate)
- [x] decisions / open questions touched: Q-008 live evidence
- [x] docs touched: solver-plan.md, question-parsing.md

## Known gaps / not done
- Browser re-check of the app with real Claude not possible (Chrome extension disconnected); covered by the API-level run above.
- Phone layout still unchecked in a browser.
- Swiss suppression is per source, not per building (24 Swiss multi-floor buildings may be aligned) — conservative.
- Sunday output format (Q-001) and new question kinds remain open.

## Verification rounds
- Round 1: FAIL — room_facts doc row missed; Swiss count wording imprecise

## Fix round 1
- room_facts doc row: implemented — `docs/architecture/ai-agents.md` tool table now says above/below is omitted on
  Swiss Dwellings buildings (floors not aligned), linking to solver-plan.md#straight_line_3d.
- Swiss count wording: implemented — "84 of 108 multi-floor Swiss buildings have every floor's space-bbox centre
  within 2 m of the origin on each axis (82 with a Euclidean 2 m radius)" in `agent/tools.py` (comment above
  `UNALIGNED_SOURCES`), `docs/architecture/solver-plan.md` (straight_line_3d), `memory-bank/log.md` (newest entry),
  and C2 above.
- room_facts tool description: implemented — `TOOL_DEFINITIONS` entry in `agent/tools.py` now says
  "rooms above/below (omitted where floors aren't aligned)"; lines kept ≤ 120 chars.
- Round 2: VERDICT: PASS (TREE e8a237dbf2c32c15f03f81f58008c3509d285279)

## Verification report (round 2)

VERDICT: PASS
TREE: e8a237dbf2c32c15f03f81f58008c3509d285279

C1–C6 MET. C1 from saved paraphrase output (31 questions, regex 0, llm/hybrid all, token line matches). C2 recount:
train+dev proc 20 / osm 10, test osm 4 / proc 11, swiss multi 108, per-axis 84, Euclidean 82; backed by kit
README:166,270. C3 room_facts note on swiss_dwellings, test passes, tool description updated. C4 train 515/517,
dev 138/138. C5 docs + links OK. C6 147 on the staged set (working tree 154 + 1 skipped only because of the
user's untracked tests/test_persistence.py). No secrets, score.py unchanged, no hard-coding. Unstaged deployment
work (.env.example, pyproject.toml, uv.lock, backend/*, supabase/, tests/test_persistence.py) ignored.
