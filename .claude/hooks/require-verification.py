"""PreToolUse hook (Bash): block `git commit` unless the staged tree was verified by the commit-verifier.

The /ship skill writes .claude/worklog/.verified (via stamp-verified.py) after a PASS; it holds the
`git write-tree` hash of the staged index. Exit 2 blocks the tool call and shows stderr to Claude.

The repository checked is the one the commit runs in — the tool call's `cwd`, then a `cd <dir>` or `git -C <dir>` in
the command — not the one this file lives in: settings.json runs the main checkout's copy even when the commit
happens in a git worktree (.claude/worktrees/…), which has its own index and its own stamp."""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

COMMIT = re.compile(r"(^|[;&|(\s])git(\s+-C\s+(?P<dir>\"[^\"]+\"|'[^']+'|\S+))?(\s+-c\s+\S+)*\s+commit\b")
CD = re.compile(r"(?:^|[;&|(]\s*)cd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|)]+)")
HOOK_ROOT = Path(__file__).resolve().parents[2]


def unquote(word: str) -> str:
    try:
        return shlex.split(word)[0]
    except (ValueError, IndexError):
        return word


def commit_dir(command: str, cwd: str | None, commit: re.Match) -> Path:
    """Where the commit runs: cwd, then the last `cd` before it, then its `git -C`."""
    where = Path(cwd) if cwd else HOOK_ROOT
    for match in CD.finditer(command[:commit.start() + 1]):
        where = where / os.path.expanduser(unquote(match.group(1)))
    if commit.group("dir"):
        where = where / os.path.expanduser(unquote(commit.group("dir")))
    return where


def repo_root(where: Path) -> Path:
    found = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=where, capture_output=True, text=True)
    return Path(found.stdout.strip()) if found.returncode == 0 and found.stdout.strip() else HOOK_ROOT


def staged_tree(root: Path) -> str:
    return subprocess.run(
        ["git", "write-tree"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def block(reason: str) -> None:
    sys.stderr.write(
        f"Commit blocked: {reason}\n"
        "Use the /ship skill: write .claude/worklog/PENDING.md, stage, run the commit-verifier agent, and "
        "commit only after a PASS stamp (python3 .claude/hooks/stamp-verified.py <report>).\n"
    )
    sys.exit(2)


def main() -> None:
    payload = json.load(sys.stdin)
    command = payload.get("tool_input", {}).get("command", "")
    commit = COMMIT.search(command)
    if not commit:
        return
    if "--amend" in command:
        block("amending is not allowed in the verified workflow; make a new verified commit.")
    if re.search(r"git\s+add\b", command) or re.search(r"\s-a[a-zA-Z]*\b|\s--all\b", command):
        block("stage files in a separate command before committing (the stamp covers the staged tree only).")
    try:
        root = repo_root(commit_dir(command, payload.get("cwd"), commit))
    except OSError:  # the directory doesn't exist: check the hook's own repository
        root = HOOK_ROOT
    stamp = root / ".claude" / "worklog" / ".verified"
    if not stamp.exists():
        block(f"no verification stamp found in {root}.")
    stamped = stamp.read_text(encoding="utf-8").split()[0]
    if stamped != staged_tree(root):
        block("the staged tree changed since verification (stamp is stale).")


if __name__ == "__main__":
    main()
