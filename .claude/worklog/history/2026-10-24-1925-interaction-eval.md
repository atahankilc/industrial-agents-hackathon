# Interaction eval: simulated tricky users + LLM judge for the Guide

- **Author:** Claude session (Utku) · **Date:** 2026-10-24
- **Related:** docs/challenge/brief.md#judging (Interaction 25 pts rubric), docs/product/personas.md, Q-014/Q-015

## Summary
New `scripts/interaction_eval.py`: Claude plays a scenario's tricky user against the canonical Guide (text or voice),
then a Claude judge scores the transcript with the brief's Interaction rubric. 6 scenarios, offline tests, docs and
memory bank with the live numbers.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Scenario files have keys building/channel/persona/goal/knows/max_turns; unknown or missing required keys raise; channel text\|voice; defaults knows=[] max_turns=6 | `load_scenario`; `tests/interaction_scenarios/*.json` (6, one voice) | `test_scenario_files_are_valid`, `test_unknown_or_missing_scenario_keys_are_rejected` |
| C2 | Simulated user: Anthropic `messages.create` with `output_config.format` json_schema `{message, done, goal_reached}`, roles flipped (guide replies are its user turns), facts shared only when asked (prompt) | `SimulatedUser`, `USER_RULES`, `USER_SCHEMA`, `structured` | `test_simulated_user_flips_roles_and_keeps_its_own_replies`; read |
| C3 | Judge: json_schema with 4 criteria (score enum 1–5 + evidence), goal_reached, issues; rubric text from the brief; sees each tool call with its compact result (space/element paths dropped, cut at 1,500 chars) and UNGROUNDED values; voice shows the spoken text | `judge`, `JUDGE_RULES`, `JUDGE_SCHEMA`, `tool_line`, `transcript_text` | `test_tool_line_shows_the_result_and_cuts_long_ones`, `test_transcript_marks_spoken_replies_and_ungrounded_values` |
| C4 | A refusal / cut-off / bad JSON / API error becomes `Run.error`, not a score; exit 1 if any run errored | `structured`, `run_scenario`, `main` | `test_refusal_is_reported_as_an_error_not_a_score` |
| C5 | End-to-end with the offline Guide and a fake client: stops when the user says done, judge gets the transcript | `run_scenario` | `test_full_run_with_offline_guide_scores_and_stops_when_done` |
| C6 | CLI: files, `--repeat`, `--model/--effort` (Guide), `--user-model/--judge-model` (default claude-opus-5-5), `--judge-effort`, `--out`; per-run line + averages + costs; JSON saved under git-ignored `agent_output/interaction_eval/` | `main`, `summary_line` | read; live output below |
| C7 | Docs: commands.md section; project-state + log entry with live numbers and the factory no-route finding | docs/guides/commands.md, memory-bank/* | read; `uv run python scripts/check_links.py` |

## Checks I ran
- `uv run pytest tests/test_interaction_eval.py -q` → `7 passed`
- `uv run pytest -q` → `311 passed, 1 skipped in 63.70s`
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files`
- Live run 1 (all Opus 5.5, short tool summaries): `AVERAGE asks_only_needed=4.33 shows_understanding=4.17 followable_directions=3.50 remembers_context=5.00  goal 6/6  errors 0  cost guide $0.37 + eval $0.28`
- Live run 2 (full tool results, current code): `AVERAGE asks_only_needed=4.17 shows_understanding=4.17 followable_directions=3.33 remembers_context=4.83  goal 5/6  errors 0  cost guide $0.31 + eval $0.31`
- Factory finding: `BuildingSession.call("find_route", {"start": "Locker room 0.30", "destination": "Production zone H-A2"})` → `reachable False … production bays are destinations only`; `navigation.find_route` without rules → `True 61.56` via Assembly zone H-A1.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none new (factory finding linked to existing Q-014/Q-015 in the log)
- [x] docs touched: `docs/guides/commands.md`

## Known gaps / not done
- Single live runs only; judge/user variance not measured (`--repeat` exists, not run).
- The judge is the same model family as the Guide (possible self-preference); not calibrated against human scores.
- No Guide fixes for the judge's issues (directions landmarks/rounding, ids in voice, factory bay rule) — logged as next steps.
- Cost per full run ~$0.62 (6 scenarios, all Opus 5.5).

## Verification rounds
- Round 1: VERDICT: PASS (TREE 23fdac5f9a6405bb854aa1c6e1e5c276c51ca0fc)

## Verification report (round 1)

VERDICT: PASS
TREE: 23fdac5f9a6405bb854aa1c6e1e5c276c51ca0fc

| # | Status | Evidence |
|---|---|---|
| C1 | MET | load_scenario rejects unknown keys, requires building/persona/goal, channel text/voice, defaults knows/max_turns; 6 scenarios, 1 voice; tests pass |
| C2 | MET | structured() uses output_config json_schema; USER_SCHEMA message/done/goal_reached; roles flipped; test passes |
| C3 | MET | JUDGE_SCHEMA 4 criteria (enum 1..5 + evidence), goal_reached, issues; tool_line drops paths, cuts at 1500; spoken/UNGROUNDED lines; tests pass |
| C4 | MET | refusal/bad JSON → RuntimeError → run.error; exit 1 on errors; test passes |
| C5 | MET | stops on done; offline Guide end-to-end test passes |
| C6 | MET | CLI options as claimed; agent_output/ git-ignored; interfaces checked against agent/guide.py and scripts/live_guide.py; live numbers not re-run (paid) |
| C7 | MET | commands.md section; project-state + log entries; links OK |

Standard checks: pytest 311 passed / 1 skipped; links OK under uv; no secrets; score.py unchanged; no hard-coding; factory finding re-checked (reachable False with rules, 61.56 m without). Undeclared changes: none.
