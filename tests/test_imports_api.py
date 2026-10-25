"""POST /imports/stream (backend/app.py): upload → Creator → private draft, as NDJSON progress lines."""

import json

import pytest
from fastapi.testclient import TestClient

import backend.app as backend_app
from agent.creator import CreatorResult
from backend.drafts import DraftStore
from core.plan_import.assemble import assemble, autofix
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan, labelled_floor, to_png

PLAN = to_png(draw_plan(*TWO_ROOMS_AND_CORRIDOR))


class FakeCreator:
    def __init__(self, session, outcome: str) -> None:
        self.session, self.outcome = session, outcome
        self.on_step = None

    def run(self) -> CreatorResult:
        self.on_step({"kind": "say", "text": f"{len(self.session.sources)} sources."})
        if self.outcome == "no_plan":
            return CreatorResult("no_plan", reason="only text")
        if self.outcome == "failed":
            return CreatorResult("failed", reason="model unavailable")
        building = autofix(assemble("import-abc", "Fake house", [labelled_floor()], ["plan.png"]))
        return CreatorResult("done", building, [])


@pytest.fixture
def client(monkeypatch, tmp_path):
    catalogue = dict(backend_app.store.catalogue)
    monkeypatch.setattr(backend_app.store, "catalogue", catalogue)
    monkeypatch.setattr(backend_app, "drafts", DraftStore(tmp_path, catalogue))

    def use(outcome: str = "done") -> TestClient:
        monkeypatch.setattr(backend_app, "make_creator", lambda session: FakeCreator(session, outcome))
        return TestClient(backend_app.app)

    return use


def post_files(client: TestClient, files: list[tuple[str, bytes]]) -> list[dict]:
    response = client.post("/imports/stream", files=[("files", (name, data)) for name, data in files])
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_import_stream_creates_private_draft(client):
    api = client()
    lines = post_files(api, [("plan.png", PLAN)])
    assert lines[0] == {"type": "step", "kind": "say", "text": "1 sources."}
    done = lines[-1]
    assert done["type"] == "done" and done["base"].startswith("import/")
    assert api.get(f"/drafts/{done['draft_id']}").status_code == 200
    assert done["base"] not in [b["id"] for b in api.get("/buildings").json()]
    assert done["notes"]["floors"]["0"]["scale_method"] == "doors"


def test_bad_file_is_a_warning(client):  # Review Focus 4
    lines = post_files(client(), [("x.heic", b"zz"), ("plan.png", PLAN)])
    assert lines[0]["type"] == "warning" and lines[0]["detail"].startswith("x.heic:")
    assert lines[-1]["type"] == "done"


def test_no_plan_line(client):
    assert post_files(client("no_plan"), [("plan.png", PLAN)])[-1] == {"type": "no_plan", "reason": "only text"}


def test_failed_run_is_an_error_line(client):
    assert post_files(client("failed"), [("plan.png", PLAN)])[-1] == {"type": "error", "detail": "model unavailable"}


def test_nothing_readable_is_an_error_line(client):
    lines = post_files(client(), [("x.heic", b"zz")])
    assert lines[-1]["type"] == "error" and "no readable" in lines[-1]["detail"]


def test_too_many_files_is_413(client):
    response = client().post("/imports/stream", files=[("files", (f"p{i}.png", PLAN)) for i in range(21)])
    assert response.status_code == 413


def test_too_large_file_is_413(client, monkeypatch):
    monkeypatch.setattr(backend_app, "MAX_IMPORT_BYTES", len(PLAN) - 1)
    assert client().post("/imports/stream", files=[("files", ("plan.png", PLAN))]).status_code == 413
