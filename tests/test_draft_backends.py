"""Edit-mode storage (backend/api/drafts.py, milestone 3): the backends' contract, and two serverless instances sharing one
database — two DraftStores (each with its own catalogue, caches and Builders) on one MemoryDraftBackend. A live
Postgres check runs only with PERSIST_LIVE_TEST=1 and SUPABASE_DB_URL."""

import json
import os
import threading
import uuid
from dataclasses import dataclass, field

import psycopg
import pytest
from fastapi.testclient import TestClient

import backend.api.app as backend_app

from backend.api import deps

from backend.api.routes import drafts as draft_routes
from backend.agents.builder import Builder
from backend.api.drafts import (SAVE_ATTEMPTS, Draft, DraftStore, FileDraftBackend, MemoryDraftBackend,
                            PostgresDraftBackend)
from backend.api.persistence import Conflict, StateError, db_url
from backend.api.sessions import load_catalogue
from backend.core.edits import EditError, apply_steps

BASE = "train/proc-campus-train-000"


def a_room(building: dict) -> dict:
    return next(space for space in building["spaces"] if space["type"] == "room")


def rename_op(building: dict, name: str) -> list[dict]:
    return [{"op": "set_space", "space_id": a_room(building)["id"], "name": name}]


# ---------- the backend contract ----------


@pytest.fixture(params=["file", "memory"])
def backend(request, tmp_path):
    return FileDraftBackend(tmp_path) if request.param == "file" else MemoryDraftBackend()


def test_draft_round_trip_and_stale_save_conflicts(backend):
    draft = Draft(uuid.uuid4().hex, BASE, "Campus")
    backend.insert_draft(draft)
    assert backend.load_draft(draft.id) == draft and backend.draft_version(draft.id) == 0
    backend.save_draft(Draft(draft.id, BASE, "Campus", [[{"op": "x"}]], 1), loaded_version=0)
    assert backend.load_draft(draft.id).steps == [[{"op": "x"}]] and backend.draft_version(draft.id) == 1
    with pytest.raises(Conflict):
        backend.save_draft(Draft(draft.id, BASE, "Campus", [], 1), loaded_version=0)
    assert backend.load_draft("0" * 32) is None and backend.draft_version("0" * 32) is None


def test_builder_round_trip_and_stale_save_conflicts(backend):
    draft = Draft(uuid.uuid4().hex, BASE, "Campus")
    backend.insert_draft(draft)
    assert backend.load_builder(draft.id) == (None, 0) and backend.builder_version(draft.id) == 0
    assert backend.save_builder(draft.id, {"a": 1}, 0) == 1
    assert backend.load_builder(draft.id) == ({"a": 1}, 1)
    with pytest.raises(Conflict):
        backend.save_builder(draft.id, {"a": 2}, 0)


def test_saved_building_slug_is_claimed_once(backend):
    assert backend.insert_building("foo", "Foo", BASE, {"building": {"name": "Foo"}}, [])
    assert not backend.insert_building("foo", "Other", BASE, {"building": {"name": "Other"}}, [])
    assert backend.saved_buildings() == [{"slug": "foo", "name": "Foo"}]
    assert backend.load_building("foo") == {"building": {"name": "Foo"}} and backend.load_building("bar") is None


# ---------- two instances on one database ----------


def instance(shared: MemoryDraftBackend) -> DraftStore:
    return DraftStore(shared, load_catalogue())


def test_interleaved_applies_on_two_instances_lose_nothing():
    """Review focus 1: each instance holds its own (soon stale) copy. An op either lands exactly once or its request
    gets Conflict (409, the UI reloads) — never lost silently, never duplicated."""
    shared = MemoryDraftBackend()
    a, b = instance(shared), instance(shared)
    draft_a = a.create(BASE)
    draft_b = b.get(draft_a.id)
    room = a_room(a.building(draft_a))["id"]
    barrier = threading.Barrier(2)
    landed: list[str] = []

    def worker(store: DraftStore, draft: Draft, tag: str) -> None:
        barrier.wait()
        for i in range(15):
            try:
                store.apply(draft, [{"op": "set_space", "space_id": room, "name": f"{tag}{i}"}])
                landed.append(f"{tag}{i}")
            except Conflict:
                pass

    threads = [threading.Thread(target=worker, args=args) for args in ((a, draft_a, "a"), (b, draft_b, "b"))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stored = shared.load_draft(draft_a.id)
    assert sorted(step[0]["name"] for step in stored.steps) == sorted(landed)
    assert len(landed) >= 15 and stored.version == len(landed)
    assert a.get(draft_a.id).version == b.get(draft_a.id).version == len(landed)
    assert a.building(draft_a) == apply_steps(a.base_building(BASE), stored.steps)


def test_lost_race_is_retried_then_conflicts():
    shared = MemoryDraftBackend()
    store = instance(shared)
    draft = store.create(BASE)
    ops = rename_op(store.building(draft), "x")
    real_save = shared.save_draft
    calls = []

    def always_beaten(changed: Draft, loaded_version: int) -> None:
        calls.append(loaded_version)
        raise Conflict(changed.id)

    shared.save_draft = always_beaten
    with pytest.raises(Conflict):
        store.apply(draft, ops)
    assert len(calls) == SAVE_ATTEMPTS and draft.version == 0 and not draft.steps
    shared.save_draft = real_save
    store.apply(draft, ops)
    assert draft.version == 1


def test_proposal_version_is_checked_against_the_stored_draft():
    shared = MemoryDraftBackend()
    a, b = instance(shared), instance(shared)
    draft_a = a.create(BASE)
    draft_b = b.get(draft_a.id)
    b.apply(draft_b, rename_op(b.building(draft_b), "elsewhere"))
    with pytest.raises(EditError, match="changed since"):
        a.apply(draft_a, rename_op(a.building(draft_a), "mine"), expected_version=0)


def test_same_name_saved_on_two_instances_gets_two_slugs():
    """Review focus 3: neither instance knows the other's save; the database hands out the slugs."""
    shared = MemoryDraftBackend()
    a, b = instance(shared), instance(shared)
    first = a.save(a.create(BASE), "Foo")
    second = b.save(b.create(BASE), "Foo")
    assert (first, second) == ("user/foo", "user/foo-2")
    assert {item["slug"] for item in shared.saved_buildings()} == {"foo", "foo-2"}


def test_building_saved_on_one_instance_opens_on_another():
    """Review focus 4: listed in the catalogue after a refresh, loadable as a session and as a draft base."""
    shared = MemoryDraftBackend()
    a, b = instance(shared), instance(shared)
    draft = a.create(BASE)
    a.apply(draft, rename_op(a.building(draft), "Edited on A"))
    saved = a.save(draft, "Shared")
    assert saved not in b.catalogue and "path" not in a.catalogue[saved]
    assert b.known(saved)
    data = b.base_building(saved)
    assert data["building"]["name"] == "Shared" and a_room(data)["name"] == "Edited on A"
    again = b.create(saved)
    assert again.base == saved


@dataclass
class Instance:
    """What one serverless instance has in memory: its catalogue, DraftStore and Builders."""

    store: DraftStore
    builders: dict = field(default_factory=dict)
    locks: dict = field(default_factory=dict)


@pytest.fixture
def two_instances(monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    shared = MemoryDraftBackend()
    pair = [Instance(instance(shared)), Instance(instance(shared))]

    def use(which: Instance) -> TestClient:
        monkeypatch.setattr(deps, "drafts", which.store)
        monkeypatch.setattr(deps.store, "catalogue", which.store.catalogue)
        monkeypatch.setattr(deps.store, "user_buildings", which.store)
        monkeypatch.setattr(draft_routes, "builders", which.builders)
        monkeypatch.setattr(draft_routes, "builder_locks", which.locks)
        return TestClient(backend_app.app)

    return pair, use


def builder_reply(client: TestClient, draft_id: str, text: str) -> dict:
    response = client.post(f"/drafts/{draft_id}/chat/stream", json={"message": text})
    return [json.loads(line) for line in response.text.splitlines() if line.strip()][-1]


def side_prompt(store: DraftStore, draft: Draft) -> str:
    from backend.agents.builder_tools import BuilderTools

    tools = BuilderTools(store, draft)
    for space in store.building(draft)["spaces"]:
        if space["room_type"] == "office" and len(space["polygon"]) == 4:
            info = tools.call("space_info", {"space": space["id"]})
            sides = [n["side"] for n in info["neighbours"] if n["side"] in ("east", "west") and n["shared_m"] >= 2]
            if sides:
                return f"make {space['ref']} 1 m wider to the {sides[0]}"
    raise AssertionError("no office with a side neighbour")


def test_proposal_made_on_one_instance_applies_on_another(two_instances):
    """Review focus 2: the Builder is restored from the draft row on the instance that gets the Apply."""
    (a, b), use = two_instances
    client = use(a)
    draft_id = client.post("/drafts", json={"base": BASE}).json()["draft"]["id"]
    proposal = builder_reply(client, draft_id, side_prompt(a.store, a.store.get(draft_id)))["proposal"]
    assert proposal is not None
    client = use(b)
    assert not b.builders
    response = client.post(f"/drafts/{draft_id}/proposals/{proposal['id']}/apply")
    assert response.status_code == 200 and response.json()["draft"]["steps"] == 1
    restored = b.builders[draft_id]
    assert restored.messages and restored.notes[-1].startswith("[note, not from the user] The user applied")
    # A applies the same proposal again with its stale Builder: restored from the row, where it is no longer open.
    client = use(a)
    assert client.post(f"/drafts/{draft_id}/proposals/{proposal['id']}/apply").status_code == 409


def test_yes_on_another_instance_applies_and_hand_edit_note_travels(two_instances):
    (a, b), use = two_instances
    client = use(a)
    created = client.post("/drafts", json={"base": BASE}).json()
    draft_id = created["draft"]["id"]
    builder_reply(client, draft_id, side_prompt(a.store, a.store.get(draft_id)))
    client = use(b)
    reply = builder_reply(client, draft_id, "yes")
    assert reply["applied"] and reply["state"]["draft"]["steps"] == 1
    # a hand edit on A is noted in the stored conversation, so B's next turn sees it
    client = use(a)
    building = client.get(f"/drafts/{draft_id}").json()["building"]
    assert client.post(f"/drafts/{draft_id}/ops", json={"ops": rename_op(building, "by hand")}).status_code == 200
    state, _ = a.store.backend.load_builder(draft_id)
    assert "changed the draft by hand" in state["notes"][-1]


def test_builder_turn_that_lost_a_race_asks_to_resend(two_instances):
    (a, b), use = two_instances
    client = use(a)
    draft_id = client.post("/drafts", json={"base": BASE}).json()["draft"]["id"]
    builder_reply(client, draft_id, "hello")
    stored_version = a.store.backend.builder_version(draft_id)
    a.store.backend.save_builder(draft_id, a.builders[draft_id].dump(), stored_version)  # "B" stored meanwhile
    a.builders[draft_id].version = stored_version  # A still thinks it has the latest; force a stale save
    original = draft_routes.load_builder
    draft_routes.load_builder = lambda draft: a.builders[draft.id]
    try:
        reply = builder_reply(client, draft_id, "hello again")
    finally:
        draft_routes.load_builder = original
    assert reply["type"] == "error" and "send the message again" in reply["detail"]


def test_draft_change_that_keeps_losing_is_409(two_instances, monkeypatch):
    (a, _), use = two_instances
    client = use(a)
    created = client.post("/drafts", json={"base": BASE}).json()

    def beaten(changed, loaded_version):
        raise Conflict(changed.id)

    monkeypatch.setattr(a.store.backend, "save_draft", beaten)
    response = client.post(f"/drafts/{created['draft']['id']}/ops", json={"ops": rename_op(created["building"], "x")})
    assert response.status_code == 409 and "updated elsewhere" in response.text


def test_database_down_is_503_and_dataset_buildings_keep_working(two_instances, monkeypatch):
    """Review focus 5."""
    (a, _), use = two_instances
    client = use(a)

    def down(*args, **kwargs):
        raise psycopg.OperationalError("connection refused")

    for name in ("load_draft", "draft_version", "insert_draft", "saved_buildings"):
        monkeypatch.setattr(a.store.backend, name, down)
    a.store.refreshed = float("-inf")
    assert client.post("/drafts", json={"base": BASE}).status_code == 503
    assert client.get(f"/drafts/{'0' * 32}").status_code == 503
    listed = client.get("/buildings")
    assert listed.status_code == 200 and BASE in [item["id"] for item in listed.json()]
    assert client.post("/sessions", json={"building": BASE}).status_code == 200


# ---------- the Builder's conversation as JSON ----------


def test_builder_dump_restore_round_trip(monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    store = instance(MemoryDraftBackend())
    draft = store.create(BASE)
    builder = Builder(store, draft)
    first = builder.reply(side_prompt(store, draft))
    assert first.proposal is not None
    state = builder.dump()
    assert json.loads(json.dumps(state)) == state and state["pending"][0]["preview"] is None
    restored = Builder.restore(store, draft, state)
    assert restored.dump() == state
    assert restored.tools.next_id == builder.tools.next_id
    restored.apply(first.proposal.id)
    assert draft.version == 1
    with pytest.raises(StateError):
        Builder.restore(store, draft, {"format": 999})


# ---------- live Postgres ----------


@pytest.mark.skipif(os.environ.get("PERSIST_LIVE_TEST") != "1" or not db_url(),
                    reason="live Postgres: PERSIST_LIVE_TEST=1 and SUPABASE_DB_URL")
def test_live_postgres_round_trip():
    shared = PostgresDraftBackend(db_url())
    a, b = DraftStore(shared, load_catalogue()), DraftStore(shared, load_catalogue())
    draft = a.create(BASE)
    slug = f"test-{uuid.uuid4().hex[:12]}"
    try:
        a.apply(draft, rename_op(a.building(draft), "live"))
        assert b.get(draft.id).steps == draft.steps
        assert shared.save_builder(draft.id, {"format": 1}, 0) == 1
        assert shared.load_builder(draft.id) == ({"format": 1}, 1)
        saved = a.save(draft, slug)
        assert saved == f"user/{slug}" and b.known(saved)
        assert a_room(b.base_building(saved))["name"] == "live"
    finally:
        shared.execute("delete from builder_drafts where id = %s", (draft.id,))
        shared.execute("delete from saved_buildings where slug like %s", (f"{slug}%",))
