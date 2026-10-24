# Phase 3 Guide agent: approved design and implementation plan

- **Author:** Claude Code session (Utku) · **Date:** 2026-10-24
- **Related:** D-003, D-010, docs/architecture/ai-agents.md

## Summary
Docs only. Adds the approved Phase 3 design (Building Guide brain, terminal-first) and its task-by-task
implementation plan, links them from the docs index and ai-agents.md, and logs the session. No code changes.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Design doc exists with front matter (id, summary, sources, related), status approved, default model `claude-opus-5-5` via `GUIDE_MODEL` | `docs/superpowers/specs/2026-10-24-guide-agent-design.md` | read front matter + "How it works" |
| C2 | Plan exists with front matter, header, Global Constraints, Review Focus and 6 tasks | `docs/superpowers/plans/2026-10-24-guide-agent.md` | read |
| C3 | Both linked from docs index; design back-linked from ai-agents.md Related | `docs/README.md`, `docs/architecture/ai-agents.md` | grep `superpowers/` |
| C4 | Log entry for this session added (newest first) | `memory-bank/log.md` | read top entry |
| C5 | All doc links resolve | — | `uv run python scripts/check_links.py` → OK |
| C6 | No code files changed | — | `git diff --cached --stat` shows only docs/, memory-bank/, .claude/worklog/ |

## Checks I ran
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` — not needed yet: no capability changed; updated when Phase 3 code lands (plan Task 6)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none (conversation decisions are recorded in the design doc as "my call")
- [x] docs touched: docs/README.md, docs/architecture/ai-agents.md, new spec + plan

## Known gaps / not done
- No implementation yet; plan Tasks 1–6 follow in separate commits.

## Verification rounds
- Round 1: PASS (commit-verifier)

## Verification report (round 1)
VERDICT: PASS
TREE: 4d85246d5f900b9e45008659e6d7fbc1aad4c0a5
Claims C1–C6 MET (front matter + status + model line; plan sections + 6 tasks; links + back-link; log entry; check_links OK; docs-only files).
Standard checks: pytest 33 passed; links OK; no secrets; score.py unchanged; no hard-coding.
Undeclared changes: none. Required fixes: none.
