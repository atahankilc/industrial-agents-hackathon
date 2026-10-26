---
id: log
summary: Append-only dated session log, newest on top. The hackathon weekend's log is archived.
related: [project-state.md, ../archive/hackathon/log-2026-10-24-to-25.md]
---

# Log

[Memory bank](README.md) · Hackathon weekend (2026-10-24 – 2026-10-25):
[archive/hackathon/log-2026-10-24-to-25.md](../archive/hackathon/log-2026-10-24-to-25.md)

## 2026-10-26 — Location dot back after a reload inside a building

- `frontend/app/src/map/MapLanding.tsx`: the "show my location" step ran only on the map's first mount and skipped
  itself when a building was open, so a reload inside a building never showed the dot on the map. It now waits for
  the map to be shown (no open building) and runs once; a run undone before the browser answered (dev double mount)
  asks again. Checked with `npm run build`; not tried in a browser (extension not connected).

## 2026-10-26 — LLM parser, solver agent and decision cache archived

- Atahan: delete `llm_cache/` (done, it was untracked) and, on Claude's recommendation, archive what only the
  benchmark used. The app used just two small parts: the python sandbox of `agent/solver_agent.py` (now
  `agent/compute.py`, the Guide's `compute` tool; its 5 tests in `tests/test_compute.py`) and `LlmUsage` /
  `building_vocabulary` of `agent/llm_parser.py` (now in `agent/rewriter.py`). Archived to
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md): `agent/llm_parser.py`, `agent/solver_agent.py`, `agent/llm_cache.py`,
  `tests/test_llm_route_spec.py`, `tests/test_solver_agent.py`, `tests/fake_llm.py`, `tests/conftest.py`.
  `core/question_parser.py`, `core/basic_parser.py`, `core/formatter.py` (test oracles only) moved to
  `tests/kit_oracles/`. pytest 955 passed, 2 skipped (978 − 28 archived + 5 moved).

## 2026-10-26 — Benchmark code archived

- Atahan: move everything about the hackathon that the app does not use to the archive. Moved with `git mv` to
  [archive/hackathon/benchmark-code/](../archive/hackathon/benchmark-code/README.md): `agent/answer.py`, `agent/benchmark_agent.py`, `agent/parsing.py`,
  `agent/run_benchmark.py`, `agent/run_benchmark_v1.py`, `agent/guide_v1/`, `benchmark/evaluate.py`,
  `scripts/eval_llm_parser.py`, `scripts/eval_sunday_probe.py`, `tests/sunday_probe/` and their 10 tests; the
  benchmark sections of commands.md went into that README. `docs/challenge/` and `docs/kit/starter-agent.md` moved to
  `archive/hackathon/docs/`. Kept (test oracles for app code): `benchmark/score.py`, `core/formatter.py`,
  `core/basic_parser.py`. `tests/fake_llm.py` now holds the fake client `tests/test_llm_route_spec.py` needs;
  `pyproject.toml`: `testpaths = ["tests"]`, the `run_benchmark` script entry removed. pytest 978 passed, 2 skipped.
- Re-score by another session (scratchpad only, UNVERIFIED here): with the right answer format and the bay /
  forklift rules on, ~0.89 on the jury's 36 sample questions; our submitted answers scored 0.19–0.33.

## 2026-10-26 — Post-hackathon cleanup

- Git: `main` fast-forwarded into `dev` (same commit `25c79b5`); deleted the merged local branches
  `backup/dev-before-pull-1043` and `voice-improvements`; pruned the stale `.claude/worktrees/voice-improvements`
  worktree; saved the 4 stashes as branches `archive/stash-0` … `archive/stash-3` and cleared the stash list;
  `git gc` (131 MB → 102 MB). Not done (needs Atahan's permission): push `dev`, delete the merged remote branches
  `2-builder-edit`, `4-sunday-agent`, `7-buildings-from-plans`.
- Moved hackathon material to [archive/hackathon/](../archive/hackathon/README.md): `SUBMISSION/`, the organiser
  PDF, technical explanation, demo runbook, the superpowers specs and plans (from `docs/`), the weekend log and the last
  project state. Links rewritten; `check_links.py` OK.
- New short [project-state.md](project-state.md); CLAUDE.md, README.md and docs index rewritten for ongoing
  development; hackathon-only questions closed ([Q-001](open-questions.md#q-001),
  [Q-002](open-questions.md#q-002), [Q-014](open-questions.md#q-014), [Q-017](open-questions.md#q-017),
  [Q-018](open-questions.md#q-018), [Q-019](open-questions.md#q-019)).
- Removed the unused `frontend/app/src/ui/Chat.tsx`.
- Held: removing the benchmark-only code (another session was re-scoring with `agent/run_benchmark_v1.py`).
