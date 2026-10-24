"""PreToolUse hook (Bash): block `git commit` unless the staged tree was verified by the commit-verifier.

The /ship skill writes .claude/worklog/.verified (via stamp-verified.py) after a PASS; it holds the
`git write-tree` hash of the staged index. Exit 2 blocks the tool call and shows stderr to Claude."""

import json
import re
import subprocess
import sys
from pathlib import Path

COMMIT = re.compile(r"(^|[;&|(\s])git(\s+-C\s+\S+)?(\s+-c\s+\S+)*\s+commit\b")
ROOT = Path(__file__).resolve().parents[2]
STAMP = ROOT / ".claude" / "worklog" / ".verified"


def staged_tree() -> str:
    return subprocess.run(
        ["git", "write-tree"], cwd=ROOT, capture_output=True, text=True, check=True
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
    if not COMMIT.search(command):
        return
    if "--amend" in command:
        block("amending is not allowed in the verified workflow; make a new verified commit.")
    if re.search(r"git\s+add\b", command) or re.search(r"\s-a[a-zA-Z]*\b|\s--all\b", command):
        block("stage files in a separate command before committing (the stamp covers the staged tree only).")
    if not STAMP.exists():
        block("no verification stamp found.")
    stamped = STAMP.read_text(encoding="utf-8").split()[0]
    if stamped != staged_tree():
        block("the staged tree changed since verification (stamp is stale).")


if __name__ == "__main__":
    main()
