"""Conversation persistence (backend/api/persistence.py): two SessionStores sharing one backend act like two serverless
instances sharing one database. Offline client; a live Postgres check runs only with PERSIST_LIVE_TEST=1."""

import os
import uuid

import pytest

from backend.api import persistence
from backend.api.sessions import SessionStore, summary

BUILDING = "train/proc-campus-train-000"
ROUTE = "from Main lobby to Meeting room 3.07"


@pytest.fixture
def instances(monkeypatch) -> tuple[SessionStore, SessionStore]:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    backend = persistence.MemoryConversations()
    first = SessionStore(backend=backend)
    return first, SessionStore(catalogue=first.catalogue, backend=backend)


def say(store: SessionStore, conversation_id: str, text: str) -> object:
    conversation = store.get(conversation_id)
    assert conversation is not None
    with conversation.lock:
        turn = conversation.guide.reply(text)
        store.save(conversation)
    return turn


def test_profile_said_on_one_instance_is_used_on_another(instances):
    a, b = instances
    conversation_id = a.create(BUILDING).id
    say(a, conversation_id, "I use a wheelchair")
    turn = say(b, conversation_id, ROUTE)
    route = next(call for call in turn.tool_calls if call["name"] == "find_route")
    assert route["result"]["profile"].startswith("step-free")
    assert summary(b.get(conversation_id))["profile"]["step_free"] is True


def test_change_confirmed_on_another_instance_replays_identically(instances):
    a, b = instances
    conversation_id = a.create(BUILDING).id
    say(a, conversation_id, ROUTE)
    say(a, conversation_id, "Lift 1 is broken")
    say(b, conversation_id, "yes")  # proposed on a, confirmed on b
    on_b = b.get(conversation_id)
    on_a = a.get(conversation_id)  # a's cached copy is stale: it must restore b's save
    assert on_a is not None and on_a.version == on_b.version == 4
    assert summary(on_a) == summary(on_b)
    assert [change["summary"] for change in summary(on_a)["applied"]] == ["close Lift 1"]
    assert on_a.session.building.closed == on_b.session.building.closed != set()
    assert on_a.session.events == on_b.session.events
    assert persistence.dump(on_a.session, on_a.guide) == persistence.dump(on_b.session, on_b.guide)


def test_change_ids_continue_after_restore(instances):
    a, b = instances
    conversation_id = a.create(BUILDING).id
    say(a, conversation_id, ROUTE)
    say(a, conversation_id, "Lift 1 is broken")
    assert list(b.get(conversation_id).session.pending) == ["C1"]
    proposal = b.get(conversation_id).session.call("propose_change", {"action": "reopen", "targets": ["Lift 1"]})
    assert proposal["change_id"] == "C2"


def test_concurrent_save_conflicts_and_drops_stale_copy(instances):
    a, b = instances
    conversation_id = a.create(BUILDING).id
    stale = a.get(conversation_id)
    say(b, conversation_id, "Where is the printer?")
    stale.guide.reply("I use a wheelchair")
    with pytest.raises(persistence.Conflict):
        a.save(stale)
    assert a.get(conversation_id) is not stale  # next lookup restores b's version
    assert summary(a.get(conversation_id))["profile"]["step_free"] is False


def test_get_or_create_on_two_instances_shares_one_conversation(instances):
    a, b = instances
    first, second = a.get_or_create("voice-1"), b.get_or_create("voice-1")
    assert first.building == second.building and first.version == second.version == 1
    assert a.get("missing") is None


def test_without_backend_store_stays_in_memory(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("GUIDE_LLM", "offline")
    store = SessionStore()
    assert store.backend is None
    conversation = store.create(BUILDING)
    store.save(conversation)
    assert store.get(conversation.id) is conversation and conversation.version == 0


def test_unknown_state_format_is_rejected(instances):
    a, _ = instances
    conversation = a.create(BUILDING)
    with pytest.raises(persistence.StateError):
        persistence.restore({"format": 999}, conversation.session, conversation.guide.client)


@pytest.mark.skipif(os.environ.get("PERSIST_LIVE_TEST") != "1" or not os.environ.get("SUPABASE_DB_URL"),
                    reason="live Postgres: PERSIST_LIVE_TEST=1 and SUPABASE_DB_URL")
def test_live_postgres_round_trip(monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    backend = persistence.from_env()
    a = SessionStore(backend=backend)
    b = SessionStore(catalogue=a.catalogue, backend=backend)
    conversation_id = f"test-{uuid.uuid4().hex}"
    a.create(BUILDING, conversation_id)
    try:
        say(a, conversation_id, "I use a wheelchair")
        assert summary(b.get(conversation_id))["profile"]["step_free"] is True
    finally:
        backend.execute("delete from conversations where id = %s", (conversation_id,))
