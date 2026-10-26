# Post-hackathon cleanup: archive hackathon material, fresh project state, docs for ongoing development

- **Author:** Claude session industrial-agents-hackathon-48 (for Atahan) · **Date:** 2026-10-26
- **Related:** Q-001, Q-002, Q-014, Q-017, Q-018, Q-019 (closed); D-004, D-008

## Summary
The hackathon is over (submitted 2026-10-25). This moves the hackathon-only material into `archive/hackathon/`,
rewrites CLAUDE.md / README.md / docs index / project state for ongoing development, starts a fresh log, closes the
hackathon-only questions and deletes one unused frontend component. No Python code changes.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Moved with `git mv` (history kept): `SUBMISSION/`, the organiser PDF, `docs/challenge/technical-explanation.md`, `docs/guides/demo-runbook.md`, `docs/superpowers/`, `memory-bank/log.md` → `archive/hackathon/log-2026-10-24-to-25.md`, `memory-bank/project-state.md` → `archive/hackathon/project-state-2026-10-25.md`. The two memory-bank files were moved with `git mv` and then new files were created at the old paths, so git shows them as copies, not renames: `git diff --cached -C -C --find-copies-harder --name-status` → `C096 memory-bank/log.md → archive/hackathon/log-2026-10-24-to-25.md`, `C080 memory-bank/project-state.md → archive/hackathon/project-state-2026-10-25.md` (with plain `-M` they show as `M` + `A`) | `archive/hackathon/` | `git diff --cached -M --name-status` shows R entries for the rest; copy detection command for the two memory-bank files |
| C2 | Relative markdown links into/out of moved files were rewritten; all docs + memory-bank links resolve, and links inside `archive/hackathon/*.md` resolve too. Non-link references to the moved paths that state a current location were also updated (fix round 2): front matter `sources:`/`related:` (brief, scoring, personas, visualization), NOTICE.md licensing row (PDF path), docs/architecture/overview.md (benchmark CLI row, repo tree no longer shows `SUBMISSION/` at root), link labels in docs/README.md and commands.md. Historical narrative left as is: scoring.md organiser announcement, decisions.md D-entry text, resolved Q-019/Q-0xx text in open-questions.md, log entries | many `.md`, `NOTICE.md` | `python3 scripts/check_links.py` → OK; archive check below; `grep -rnE "SUBMISSION/|demo-runbook|technical-explanation|Hackathon Challenge - Talk" --exclude-dir=archive --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.claude --exclude-dir=.venv .` → only links/labels already pointing into archive/hackathon/ or historical narrative |
| C10 | Comment/docstring-only edits: `docs/superpowers/` → `archive/hackathon/superpowers/` in .env.example, core/{access,edits,fleet,geoplace,osm_lookup,preferences,validate}.py, core/plan_import/{__init__,reference}.py, agent/{builder,builder_tools,creator,creator_tools,tools}.py, backend/{access,drafts}.py, scripts/eval_import.py, tests/test_{edits,geoplace,placement}.py, frontend/app/src {access/auth.ts, edit/useDraft.ts, edit/ReferencePanel.tsx, map/Placement.tsx, import/ImportScreen.tsx}, supabase/migrations/20261025180000_builder_imports.sql and 20261025200000_access.sql (SQL comment line 1 only); plus `SUBMISSION/BENCHMARK.md` → `archive/hackathon/SUBMISSION/BENCHMARK.md` in the agent/run_benchmark_v1.py docstring and agent/benchmark_agent.py usage comment. No code behaviour change | listed files | `grep -rn "docs/superpowers" --exclude-dir=archive --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.claude --exclude-dir=.venv .` → nothing; `git diff --cached --diff-filter=M -- '*.py' '*.ts' '*.tsx' '*.sql' .env.example \| grep '^[-+][^-+]' \| grep -v 'superpowers\|SUBMISSION'` → nothing |
| C3 | New `archive/hackathon/README.md` lists the archived files; `archive/README.md` points to it | `archive/` | read |
| C4 | New short `memory-bank/project-state.md` (phase, what exists, verified status, next incl. held benchmark-code decision and `through: false` finding) and fresh `memory-bank/log.md` with a 2026-10-26 entry | `memory-bank/` | read |
| C5 | Q-001, Q-002, Q-014, Q-017, Q-018, Q-019 moved from Open to Resolved with status "closed (hackathon over)" and a closing note, text otherwise kept; next free id corrected Q-020 → Q-021 (Q-020 already existed) | `memory-bank/open-questions.md` | `grep -n "^## \|^### Q" memory-bank/open-questions.md` |
| C6 | CLAUDE.md, README.md rewritten for ongoing development (archive pointers, run app / tests / benchmark commands taken from commands.md); docs/README.md: archived entries in their own section, new reading order | `CLAUDE.md`, `README.md`, `docs/README.md` | read |
| C7 | commands.md: re-score outputs go to `agent_output/` instead of the archived `SUBMISSION/`; Sunday section marked archived | `docs/guides/commands.md` | read |
| C8 | Deleted unused `frontend/app/src/ui/Chat.tsx` (no importer); docs/product/visualization.md "App and data path" bullet rewritten to list the current `frontend/app/src` folders (entry `src/Root.tsx`) and label `src/scene/` / old `App.tsx` as removed, so no doc names Chat.tsx | frontend, `docs/product/visualization.md` | `grep -rn "ui/Chat\|/Chat'" frontend/app/src` → nothing; `grep -rn "Chat.tsx" docs` → nothing; `npm run build` OK |
| C9 | `llm_cache/decisions.json` (written by another session's benchmark run) is NOT part of this commit | — | `git diff --cached --name-only` has no llm_cache |

## Checks I ran
- `uv run pytest -q` → 1088 passed, 2 skipped in 130.22s
- `python3 scripts/check_links.py` → OK: all links resolve in 27 files
- links inside `archive/hackathon/**/*.md` → broken in archive: 0
- `cd frontend/app && npm run build` → ✓ built (chunk-size warning only, pre-existing)
- Fix round 1: `grep -rn "Chat.tsx" docs` → no output (exit 1)
- Fix round 1: `python3 scripts/check_links.py` → OK: all links resolve in 27 files
- Fix round 1: `git diff --cached -C -C --find-copies-harder --name-status` → `C096 memory-bank/log.md archive/hackathon/log-2026-10-24-to-25.md`, `C080 memory-bank/project-state.md archive/hackathon/project-state-2026-10-25.md`
- Fix round 1: `uv run pytest -q` → 1088 passed, 2 skipped in 120.98s

- Fix round 2: `grep -rn "docs/superpowers" --exclude-dir=archive --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.claude --exclude-dir=.venv .` → no output (exit 1)
- Fix round 2: `git diff --cached --diff-filter=M -- '*.py' '*.ts' '*.tsx' '*.sql' .env.example | grep '^[-+][^-+]' | grep -v "superpowers\|SUBMISSION"` → no output (only comment lines changed)
- Fix round 2: `python3 scripts/check_links.py` → OK: all links resolve in 27 files
- Fix round 2: `uv run pytest -q` → 1088 passed, 2 skipped in 132.04s
- Fix round 2: `npm run build` on the staged tree only (`git checkout-index -a` into the scratchpad, node_modules symlinked, so an unrelated unstaged MapLanding.tsx edit is excluded) → ✓ built in 564ms (chunk-size warning only); also in the working tree → ✓ built in 867ms

## Knowledge base updates
- [x] `memory-bank/project-state.md` rewritten
- [x] `memory-bank/log.md` entry added (fresh log)
- [x] open questions: 6 closed
- [x] docs touched: README index, commands.md, link rewrites in ai-agents, brief, scoring, routing-profiles, visualization (plus App-path bullet, fix round 1), decisions

## Known gaps / not done
- Git housekeeping already done outside this commit (branches, worktree prune, stashes → `archive/stash-*`, `main` fast-forward, gc). Push of `dev` and deletion of merged remote branches were denied by permissions — left to Atahan.
- Benchmark-only code (agent/answer.py, run_benchmark*, guide_v1, core/formatter.py, core/basic_parser.py, related scripts/tests) not removed: waiting for Atahan's decision.
- `data/` not slimmed; `collab-edits` branch untouched.
- `frontend/app/src/map/MapLanding.tsx` has unstaged edits from another session (geolocation prompt); not part of this commit, left unstaged, like `llm_cache/`.

## Verification rounds
- Round 1: FAIL — visualization.md still listed Chat.tsx / src/scene; C1 wording
- Round 2: FAIL — plain-text/front-matter/comment references to moved paths

## Fix round 1
- visualization.md App path still named `src/ui/Chat.tsx` and `src/scene/`: implemented — bullet rewritten to the current `frontend/app/src` folders (checked with `ls`), entry `src/Root.tsx`, removed point-cloud files labelled as removed (`docs/product/visualization.md`); added to C8.
- C1 wording for memory-bank/log.md and project-state.md: claim corrected — C1 now says they were `git mv`'d then recreated, so git shows copies C096/C080, not renames (`.claude/worklog/PENDING.md`).

## Fix round 2
- NOTICE.md PDF path: implemented — licensing row now names `archive/hackathon/Hackathon Challenge - Talk to Your Building.pdf` (`NOTICE.md`).
- overview.md `SUBMISSION/`: implemented — benchmark CLI row points to `archive/hackathon/SUBMISSION/BENCHMARK.md` (archived 2026-10-26); `SUBMISSION/` line removed from the repo tree, note added on the `archive/` line (`docs/architecture/overview.md`).
- Front matter: implemented — `related:` in visualization.md and brief.md point to `../../archive/hackathon/…`; `sources:` naming the PDF in brief.md, scoring.md, personas.md use `archive/hackathon/Hackathon Challenge - Talk to Your Building.pdf`. No other front matter in docs/ or memory-bank/ names the old paths (grep). Also link labels: docs/README.md (`technical-explanation.md`, `demo-runbook.md`), commands.md (`archive/hackathon/SUBMISSION/BENCHMARK.md`).
- Comments/docstrings citing `docs/superpowers/`: implemented — rewritten in the 28 files listed in C10 (more than the report listed: also agent/, backend/, scripts/eval_import.py and two supabase migration comments). Comment-only, verified by the diff grep. memory-bank/log.md 2026-10-26 entry reworded ("the superpowers specs and plans (from `docs/`)") so the grep is empty.
- Other plain mentions: agent/run_benchmark_v1.py docstring and agent/benchmark_agent.py comment updated to the archive path (my choice). Left as historical narrative: scoring.md organiser announcement (its link already points into the archive), decisions.md D-entry, resolved questions in open-questions.md, log entries.
- C2 extended and C10 added in this file; checks above.

## Verification rounds (final)
- Round 1: FAIL — visualization.md still listed Chat.tsx / src/scene; C1 wording
- Round 2: FAIL — plain-text/front-matter/comment references to moved paths
- Round 3: PASS

## Verifier report (round 3)

VERDICT: PASS
TREE: fbfc70c6704eee5bb29b74751637580f69e608e7

Claims C1–C10: MET. pytest 1088 passed, 2 skipped; check_links OK (27 files); archive links 0 broken; secrets none;
score.py unchanged; hard-coding none; npm run build on staged tree ✓. Undeclared: memory-bank/README.md and
decisions.md link-only rewrites; CLAUDE.md rule rewording under C6. Not in commit: unstaged
frontend/app/src/map/MapLanding.tsx (other session), untracked llm_cache/. Minor: front matter inside archived files
still names old paths (read-only history).
