---
name: ship
description: Verified commit workflow for this repo. Use whenever work is ready to commit (or the user says "commit", "ship", "/ship"). Ensures .claude/worklog/PENDING.md lists the claims, runs the commit-verifier agent on the staged diff, loops commit-fixer on FAIL (max 3 rounds), and commits only after a PASS. Direct `git commit` is blocked by a hook without a fresh PASS stamp.
---

# /ship — verified commit

A commit is allowed only after an **independent** `commit-verifier` agent confirms that what
`.claude/worklog/PENDING.md` promises is actually in the staged change. A PreToolUse hook
(`.claude/hooks/require-verification.py`) blocks `git commit` unless `.claude/worklog/.verified` holds the
hash of the exact staged tree.

Optional argument: `push` → also `git push` after a successful commit (only if a remote exists).

## Steps

### 1. Worklog
- If `.claude/worklog/PENDING.md` does not exist, the implementer (you) writes it now from
  `.claude/worklog/TEMPLATE.md`: every promise as a checkable claim, the checks you actually ran with real
  output, knowledge-base updates, known gaps. Do this honestly — the verifier will check it.
- Make sure the session protocol from `CLAUDE.md` was followed (project-state, log, decisions/questions).

### 2. Stage
- `git status --short`, then `git add` the intended paths (never `.env`, never secrets). Include PENDING.md.
- Nothing staged → stop and tell the user.

### 3. Verify (fresh agent, every round)
Spawn the agent with `subagent_type: "commit-verifier"`, prompt:
> Verify the currently staged change against .claude/worklog/PENDING.md. Follow your procedure exactly and
> return your report in the required format.

Save its full report to `.claude/worklog/VERIFICATION.md` (overwrite per round; keep previous rounds' verdict
lines in PENDING.md under "## Verification rounds").

### 4. On FAIL → fix → re-verify
- Spawn `subagent_type: "commit-fixer"` with the full verifier report in the prompt.
- After it returns, go back to step 3 with a **new** verifier agent (never reuse the old one: no anchoring).
- Max **3** fix rounds. Still FAIL → stop, do not commit, show the user the remaining required fixes.

### 5. On PASS → archive, stamp, commit
Run these as **separate** Bash commands (the hook checks the index at the moment of `git commit`):
1. Archive: `mkdir -p .claude/worklog/history` then move PENDING.md to
   `.claude/worklog/history/<YYYY-MM-DD-HHMM>-<slug>.md` and append the VERIFICATION.md report to that file;
   delete VERIFICATION.md. `git add .claude/worklog/`.
2. Stamp: `python3 .claude/hooks/stamp-verified.py .claude/worklog/history/<file>.md` — it refuses unless the
   report says `VERDICT: PASS` and the file is staged; writes the staged-tree hash to `.claude/worklog/.verified`.
3. Commit: `git commit -m "<title from worklog>" -m "<summary + claim ids>" -m "Verified-by: commit-verifier (<n> round(s)), log: <history file>"`
   plus the attribution trailer required for this session.
4. `git log -1 --stat | head -20` and report to the user: commit hash, rounds, any warnings.
5. If the argument was `push`: `git push`.

## Notes
- Anything staged after stamping changes the tree hash → the hook blocks; re-run from step 3.
- Humans committing from their own terminal are not blocked (the hook only guards Claude's Bash tool), but should
  still run `/ship`.
- Parallel sessions: only one PENDING.md at a time — finish or ship before starting another chunk.
