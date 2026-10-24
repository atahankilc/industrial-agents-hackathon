# Commit hook checks the repository the commit runs in (git worktrees)

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-24 22:40
- **Related:** D-008, docs/guides/dev-workflow.md

## Summary
settings.json runs the main checkout's copy of require-verification.py, which compared the stamp with the main
checkout's index, so every verified commit in a git worktree was blocked as "stale". The hook now resolves the
repository the commit runs in and checks that repository's stamp and staged tree.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | The hook resolves the commit's directory from the payload `cwd`, then the last `cd <dir>` before the commit, then `git -C <dir>` (quoted paths with spaces work), takes `git rev-parse --show-toplevel` there, and compares that repo's `.claude/worklog/.verified` with that repo's `git write-tree`; unknown dirs fall back to the hook's own repository | `.claude/hooks/require-verification.py:commit_dir/repo_root/main` | read; `uv run pytest -q tests/test_commit_hook.py` |
| C2 | Existing behaviour kept: non-commit commands pass, `--amend` / `-a` / add-and-commit one-liners / missing or stale stamp block | same | the existing tests in `tests/test_commit_hook.py` still pass |
| C3 | New tests: a temp repository with its own stamp — allowed via cwd, `cd '<dir>' &&` and `git -C "<dir>"`; blocked when its stamp is stale or missing; this repo's stale stamp still blocks | `tests/test_commit_hook.py:test_commit_in_another_repo_*` | `uv run pytest -q tests/test_commit_hook.py` → 12 passed |
| C4 | Docs: dev-workflow.md hook row explains the repository resolution and the heredoc false positive; log entry | `docs/guides/dev-workflow.md`, `memory-bank/log.md` | read; `python3 scripts/check_links.py` |

## Checks I ran

- `env -u SUPABASE_DB_URL -u VIRTUAL_ENV uv run pytest -q tests/test_commit_hook.py` → `12 passed`
- The fixed hook (copied into the main checkout, which Claude Code runs) let the verified M3 commit `be669fd` through
  from the worktree, after the old one had blocked it as stale.

## Knowledge base updates
- [x] `memory-bank/project-state.md` — not needed (tooling fix; recorded in log)
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none
- [x] docs touched: docs/guides/dev-workflow.md

## Known gaps / not done
- The same fix sits uncommitted in the main checkout (branch `1-agentic-yarag`); it needs committing there or arrives
  by merge.
- Commit-like text inside a heredoc or quoted string still triggers the hook (pre-existing, documented).

## Verification rounds
- Round 1: VERDICT PASS (tree daecf161)

---

# Verification report

VERDICT: PASS
TREE: daecf16134087f4ab204391e93aaa9bbb26f7e64

## Claims
| # | Status | Evidence |
|---|---|---|
| C1 | MET | commit_dir: payload cwd (else HOOK_ROOT) → each `cd` before the match (quoted via shlex) → `git -C` group (quoted/unquoted); repo_root via rev-parse with HOOK_ROOT fallback; OSError → HOOK_ROOT; compares root stamp with root write-tree. Manual check with a temp repo path containing a space: cd "<dir>" && → 0, cd parent; cd 'sp ace'; → 0, -C '<dir>' → 0, plain from the worktree (no fresh stamp) → 2 |
| C2 | MET | Existing tests unchanged and passing (other commands, unverified/amend/-am/add one-liner blocked, fresh stamp allows, stale blocks); amend/add checks run before repo resolution |
| C3 | MET | other_repo fixture + two new tests; tests/test_commit_hook.py → 12 passed in 1.62s |
| C4 | MET | dev-workflow.md line 37 covers resolution + heredoc false positive; log entry 22:40; check_links OK in 32 files |

## Standard checks
- pytest full suite: 748 passed, 2 skipped in 97.39s
- links: OK, all links resolve in 32 files
- secrets: none found; no .env staged
- score.py unchanged: yes
- hard-coding: none found
- Checks re-run: hook tests 12 passed; be669fd exists on the branch, consistent with the claim
- Working tree / index unchanged by the checks (write-tree still daecf161…, stamp restored by the fixture)

## Undeclared changes
- `.claude/worklog/PENDING.md` (worklog; trivial). Nothing else.

## Knowledge base
- project-state.md not updated — acceptable for a tooling-only fix recorded in log.md; dev-workflow.md updated.

## Known gaps
- Both listed gaps are accurate; no unlisted TODOs, stubs or shortcuts.
