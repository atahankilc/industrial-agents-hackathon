"""POST /imports/stream (backend/api/routes/imports.py): upload → Creator → private draft, as NDJSON progress lines."""

import json

import pytest
from fastapi.testclient import TestClient

import backend.api.app as backend_app

from backend.api import deps

from backend.api.routes import imports as import_routes
from backend.agents.creator import CreatorResult
from backend.api.drafts import DraftStore
from backend.core.plan_import.assemble import assemble, autofix
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
    catalogue = dict(deps.store.catalogue)
    monkeypatch.setattr(deps.store, "catalogue", catalogue)
    drafts = DraftStore(tmp_path, catalogue)
    monkeypatch.setattr(deps, "drafts", drafts)
    monkeypatch.setattr(deps.store, "user_buildings", drafts)

    def use(outcome: str = "done") -> TestClient:
        monkeypatch.setattr(import_routes, "make_creator", lambda session: FakeCreator(session, outcome))
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
    monkeypatch.setattr(import_routes, "MAX_IMPORT_BYTES", len(PLAN) - 1)
    assert client().post("/imports/stream", files=[("files", ("plan.png", PLAN))]).status_code == 413


def test_an_import_opens_in_the_building_screen(client):
    api = client()
    done = post_files(api, [("plan.png", PLAN)])[-1]
    session = api.post("/sessions", json={"building": done["base"]})
    assert session.status_code == 200, session.text
    plan = api.get(f"/sessions/{session.json()['session_id']}/plan")
    assert plan.status_code == 200 and len(plan.json()["spaces"]) == 3


def test_closing_the_stream_cancels_the_creator(client, monkeypatch):
    import threading
    import time

    started, made = threading.Event(), []

    class SlowCreator:
        def __init__(self, session):
            self.cancel, self.on_step = threading.Event(), None
            made.append(self)

        def run(self):
            self.on_step({"kind": "say", "text": "working"})
            started.set()
            self.cancel.wait(10)
            return CreatorResult("cancelled", reason="cancelled")

    api = client()
    monkeypatch.setattr(import_routes, "make_creator", SlowCreator)
    with api.stream("POST", "/imports/stream", files=[("files", ("plan.png", PLAN))]) as response:
        next(response.iter_lines())
        assert started.wait(5)
    deadline = time.monotonic() + 5
    while not made[0].cancel.is_set() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert made[0].cancel.is_set()
