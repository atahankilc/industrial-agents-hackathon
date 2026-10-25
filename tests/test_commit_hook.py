"""The commit gate hook blocks unverified commits and allows a commit whose staged tree matches the stamp."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "require-verification.py"
STAMP = ROOT / ".claude" / "worklog" / ".verified"
COMMIT = "git " + "commit"


def hook_exit(command: str, cwd: Path | None = None) -> int:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True).returncode


def staged_tree(root: Path = ROOT) -> str:
    return subprocess.run(["git", "write-tree"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


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


@pytest.fixture
def other_repo(tmp_path, stamp) -> Path:
    """Another repository with something staged (like a git worktree: own index, own stamp); this repo's stamp is
    stale, so only a hook that checks the commit's own repository lets its commits through."""
    stamp("0" * 40 + "\n")
    repo = tmp_path / "other repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "file.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True)
    (repo / ".claude" / "worklog").mkdir(parents=True)
    return repo


def test_commit_in_another_repo_checks_that_repos_stamp(other_repo):
    other_stamp = other_repo / ".claude" / "worklog" / ".verified"
    other_stamp.write_text(staged_tree(other_repo) + "\n", encoding="utf-8")
    assert hook_exit(f"{COMMIT} -m ok", cwd=other_repo) == 0
    assert hook_exit(f"cd '{other_repo}' && {COMMIT} -m ok", cwd=ROOT) == 0
    assert hook_exit(f'git -C "{other_repo}" commit -m ok', cwd=ROOT) == 0
    assert hook_exit(f"{COMMIT} -m stale-here", cwd=ROOT) == 2  # this repo's stamp is still stale
    other_stamp.write_text("0" * 40 + "\n", encoding="utf-8")
    assert hook_exit(f"{COMMIT} -m stale-there", cwd=other_repo) == 2


def test_commit_in_another_repo_without_stamp_is_blocked(other_repo):
    assert hook_exit(f"{COMMIT} -m x", cwd=other_repo) == 2
    assert hook_exit(f"{COMMIT} -m x", cwd=other_repo / "missing") == 2  # unknown dir: falls back to this repo
