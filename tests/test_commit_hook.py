"""The commit gate hook blocks unverified commits and allows a commit whose staged tree matches the stamp."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "require-verification.py"
STAMP = ROOT / ".claude" / "worklog" / ".verified"
COMMIT = "git " + "commit"


def hook_exit(command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(["python3", str(HOOK)], input=payload, capture_output=True, text=True).returncode


def staged_tree() -> str:
    return subprocess.run(["git", "write-tree"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def stamp():
    """Yield a writer for the stamp file; restore whatever was there before."""
    previous = STAMP.read_text(encoding="utf-8") if STAMP.exists() else None
    yield lambda text: STAMP.write_text(text, encoding="utf-8") if text is not None else STAMP.unlink(missing_ok=True)
    if previous is None:
        STAMP.unlink(missing_ok=True)
    else:
        STAMP.write_text(previous, encoding="utf-8")


@pytest.mark.parametrize("command", ["ls -la", "git status", "git log --grep commit", "uv run pytest -q"])
def test_other_commands_pass(command, stamp):
    stamp(None)
    assert hook_exit(command) == 0


@pytest.mark.parametrize(
    "command", [f"{COMMIT} -m x", f"git add -A && {COMMIT} -m x", f"{COMMIT} -am x", f"{COMMIT} --amend"]
)
def test_unverified_commits_blocked(command, stamp):
    stamp(None)
    assert hook_exit(command) == 2


def test_fresh_stamp_allows_commit(stamp):
    stamp(staged_tree() + "\n")
    assert hook_exit(f'{COMMIT} -m "ok"') == 0
    assert hook_exit(f"git -C . {COMMIT} -m ok") == 0


def test_stale_stamp_blocks_commit(stamp):
    stamp("0" * 40 + "\n")
    assert hook_exit(f"{COMMIT} -m stale") == 2
