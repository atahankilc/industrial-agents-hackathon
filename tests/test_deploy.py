"""Deployment config: the /api prefix the Vercel rewrite keeps, and what vercel.json leaves in the function bundle."""

import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
API = CONFIG["services"]["api"]


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/health", "/api/health"])
def test_routes_answer_with_and_without_api_prefix(client, path):
    assert client.get(path).json()["ok"] is True


@pytest.mark.parametrize("path", ["/api", "/apiary", "/api-health"])
def test_only_a_whole_api_segment_is_stripped(client, path):
    assert client.get(path).status_code == 404


def test_rewrites_send_api_to_backend_and_the_rest_to_frontend():
    rewrites = [(rule["source"], rule["destination"]["service"]) for rule in CONFIG["rewrites"]]
    assert rewrites == [("/api/(.*)", "api"), ("/(.*)", "web")]
    assert set(CONFIG["services"]) == {"api", "web"}
    assert (ROOT / CONFIG["services"]["web"]["root"] / "package.json").exists()


def test_entrypoint_and_functions_key_name_the_same_app():
    module, variable = API["entrypoint"].split(":")
    assert (module, variable) == ("backend.app", "app")
    assert list(API["functions"]) == [module.replace(".", "/") + ".py"]


def glob_regex(pattern: str) -> re.Pattern:
    """Enough of node-glob for our patterns: `**/` any directories, `**` anything, `*` within one segment."""
    text = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.compile(text + "$")


def test_bundle_keeps_what_the_backend_reads_and_drops_the_rest():
    excludes = [glob_regex(item) for item in API["functions"]["backend/app.py"]["excludeFiles"].strip("{}").split(",")]
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True)
    files = [name for name in tracked.stdout.split("\0") if name]
    kept = {name for name in files if not any(pattern.match(name) for pattern in excludes)}
    buildings = {name for name in files if name.endswith("/building.json")}
    assert buildings and buildings <= kept and "data/manifest.csv" in kept
    assert {"backend/app.py", "backend/persistence.py", "core/building_map.py", "agent/guide.py"} <= kept
    assert not any(name.startswith(("archive/", "frontend/", "tests/", "docs/")) or name.endswith(".png")
                   for name in kept)
