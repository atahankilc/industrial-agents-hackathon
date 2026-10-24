# Live Guide check: live_guide script, complete change impact in proposals, prompt fixes

- **Author:** Claude (Guide session) · **Date:** 2026-10-24
- **Related:** Q-012, D-003, D-010; docs/architecture/ai-agents.md#implementation--agentguidepy-2026-10-24

## Summary
First runs of the Building Guide against the real Claude API (key now set). Adds a reusable live script and fixes
what the runs exposed: the lost-room list was capped, a parallel compare_routes call guessed a change id, and one
reply made a general claim no tool had shown.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `scripts/live_guide.py` runs the 7-turn tricky-user conversation live and prints tools, replies, ungrounded, per-turn seconds/tokens/cache/$; saves JSON under git-ignored `agent_output/live_guide/`; `--model`, `--effort`, `--building`, `--out` | `scripts/live_guide.py` | read; (live run costs money — the verifier need not run it) |
| C2 | `compare_routes` returns every lost room grouped by floor with code-computed counts (`lost_access_by_floor: {floor: {count, rooms}}`), no 15-item cap; capped `lost_access` list removed | `agent/tools.py:names_by_floor`, `comparison` | `uv run pytest -q tests/test_agent_tools.py` |
| C3 | `propose_change` effect includes the impact (from, reachable before/after, lost_access_count, lost_access_by_floor, longer_routes_count, max_extra_m) without emitting events; falls back to route-only prediction if there is no start to compare from | `agent/tools.py:tool_propose_change`, `IMPACT_KEYS`, `comparison` | `test_proposal_reports_who_loses_access` |
| C4 | `compare_routes` still emits the lost_access highlight event; its logic is split into `comparison()` returning (result, lost ids) | `agent/tools.py:tool_compare_routes` | `test_compare_routes_pending_and_applied` |
| C5 | Unknown change id errors list the valid ids (apply_change: pending; compare_routes: pending + applied) | `agent/tools.py` | `test_proposal_reports_who_loses_access` (`"C2" in error`) |
| C6 | Guide instructions: general claims only when a tool shows them; propose_change reports the impact; change ids only after a tool returned them | `agent/guide.py:INSTRUCTIONS` | read |
| C7 | Live results recorded accurately: Opus 5.5 medium (~5.9–7.3 s/turn: 7.3 pre-fix/$0.157, 5.9 post-fix/$0.129), Opus 5.5 low ($0.118, ~6.8 s/turn, one pre-fix run), Sonnet 5.5 low (~3.3–3.9 s/turn: 3.3 pre-fix/$0.055, 3.9 post-fix/$0.061); first Opus medium run had one failed find_route (via id ...-V04) the model recovered from; 0 ungrounded on all runs; total ≈ $0.52 | `docs/architecture/ai-agents.md` (live table), `memory-bank/open-questions.md` Q-012, `memory-bank/log.md` | read; transcripts in agent_output/live_guide/*.json (local, git-ignored) |
| C8 | Tests and benchmark unaffected | — | `uv run pytest -q` → 87 passed; dev benchmark 138/138 |
| C9 | Docs/memory bank: ai-agents.md (impact in proposals, live table), commands.md (live script), Q-012 evidence, project-state (phase 3 ✅, next = frontend/voice), log entry | `docs/`, `memory-bank/` | read; `python3 scripts/check_links.py` |

## Checks I ran
- `uv run pytest -q` → `87 passed in 10.55s`
- `PARSER_MODE=regex uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer --name dev` → `all 138 / 138 (100%)`
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`
- Live: `uv run --env-file .env python scripts/live_guide.py` → `TOTAL 51.2s · 21 requests · $0.157` (before fixes); after fixes `TOTAL 41.4s · 17 requests · $0.129`
- Live: `--model claude-sonnet-5-5 --effort low` → `TOTAL 23.3s · 14 requests · $0.055` (before fixes, one failed compare_routes with id "pending"); after fixes `TOTAL 27.0s · 14 requests · $0.061`, no failed calls
- Live: `--model claude-opus-5-5 --effort low` → `TOTAL 47.6s · 20 requests · $0.118`
- No `UNGROUNDED` flag in any live run; every turn `stop end_turn`.

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added (spend ≈ $0.52)
- [x] decisions / open questions touched: Q-012 live evidence + proposal (model per channel, Atahan decides)
- [x] docs touched: docs/architecture/ai-agents.md, docs/guides/commands.md

## Known gaps / not done
- Default model unchanged (Opus 5.5 medium); per-channel choice left to Atahan (Q-012).
- Replies use markdown and step text contains bracketed ids — not yet voice-friendly.
- Live check covers one building and one scripted conversation; the grounding check doesn't catch qualitative over-claims, only numbers/ids (mitigated by the prompt sentence).
- Live runs were after/before fixes as listed; the post-fix Opus low run was not repeated.

## Verification rounds
- Round 1: FAIL — latency figures cited only the faster runs (Opus medium given as ~5.9 s/turn only; Sonnet low as ~3.9 in table/Q-012 vs ~3.3–3.9 in C7; "Opus low gives no speed gain" overstated; failed find_route in first Opus medium run not mentioned).

## Fix round 1
- Opus 5.5 medium range: implemented — now "~5.9–7.3 s/turn (7.3 pre-fix, 5.9 post-fix)" in `docs/architecture/ai-agents.md` live table, `memory-bank/open-questions.md` Q-012, C7 above (and `memory-bank/project-state.md`, which said ~6).
- Sonnet 5.5 low consistent: implemented — "~3.3–3.9 s/turn (3.3 pre-fix, 3.9 post-fix)" in table, Q-012, C7 (and project-state, which said ~4).
- Opus low claim: claim corrected — "no clear speed gain (6.8 s/turn, one pre-fix run; not directly comparable)" in ai-agents.md table and `memory-bank/log.md`; log speed ratio now "~1.5–2.2× faster (3.3–3.9 vs 5.9–7.3 s/turn)".
- Failed find_route: implemented — log entry notes the first Opus medium run had one failed `find_route` (invalid via id `proc-campus-train-000-V04`, "No place matches") that the model recovered from.
- Re-checks: `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`; `uv run pytest -q` → `87 passed in 10.47s`. Live script not re-run (paid API); figures taken from local transcripts in agent_output/live_guide/*.json.

- Round 2: VERDICT: PASS (TREE c62eba28e65cfb6768e7cae0ea55555b08b9400b)

## Verification report (round 2)

VERDICT: PASS
TREE: c62eba28e65cfb6768e7cae0ea55555b08b9400b

Claims C1–C9: all MET.
- C1 live_guide.py: 7 turns, per-turn stats, args, saves to git-ignored agent_output/live_guide/ (not run: paid API).
- C2 lost_access_by_floor with counts, uncapped; old capped list removed; tests pass.
- C3 propose_change merges IMPACT_KEYS, catches MapError, emits no events.
- C4 compare_routes emits lost_access highlight only when rooms are lost.
- C5 id errors list pending / known ids.
- C6 two prompt sentences added.
- C7 all 5 transcripts read: opus-medium 7.31 s/turn $0.1571 (one recovered failed find_route) and 5.91 s/turn $0.1289; opus-low 6.8 s/turn $0.1176; sonnet-low 3.33 s/turn $0.0551 (failed compare_routes "pending") and 3.85 s/turn $0.0608; 0 ungrounded, all end_turn; total $0.5195; figures match docs.
- C8 pytest 87 passed; dev 138/138.
- C9 docs and memory bank updated; check_links OK.
Standard checks: no secrets, score.py unchanged, no hard-coding.
Undeclared (trivial): propose_change tool description; prompt "re-run the affected route" wording.
Doc nit (not blocking): only the post-fix Sonnet run applied the 0.8 m wheelchair default.
Required fixes: none.
