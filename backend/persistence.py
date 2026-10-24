"""Conversation persistence: a Guide conversation as JSON, and the Postgres table it lives in (Supabase).

Serverless instances (Vercel) share no memory, so any request may land on an instance that has never seen the
conversation. `dump` turns a BuildingSession + Guide into JSON; `restore` rebuilds them on a fresh BuildingSession
of the same building by replaying the applied changes in order. Replay is deterministic, so new door ids and the
before/after snapshots come out as they were. Assistant content blocks are stored as plain dicts, which the
Messages API accepts as input. The system blocks are stored too, so a resumed conversation keeps its exact
prompt (and prompt-cache prefix); prompt changes in a deploy reach new conversations only.

Saves are optimistic: `save` writes only if the row still has the version we loaded, otherwise it raises
`Conflict` and the caller reloads. Schema: supabase/migrations/. Enabled when SUPABASE_DB_URL is set (the
Transaction pooler URI, which doesn't support prepared statements); GUIDE_PERSIST=off disables it."""

import itertools
import json
import os
import threading
from dataclasses import asdict, dataclass

import psycopg
from psycopg.types.json import Jsonb

from agent.guide import Guide, Usage
from agent.tools import BuildingSession, Change, RoutingProfile

STATE_FORMAT = 1


class Conflict(RuntimeError):
    """The conversation was saved by someone else since we loaded it."""


class StateError(ValueError):
    """A stored state this code can't restore (other format)."""


@dataclass
class Stored:
    building: str
    state: dict
    version: int


# ---------- conversation ⇄ JSON ----------


def plain(block: object) -> object:
    return block.model_dump(mode="json", exclude_none=True) if hasattr(block, "model_dump") else block


def plain_messages(messages: list[dict]) -> list[dict]:
    return [{**message, "content": [plain(block) for block in message["content"]]}
            if isinstance(message["content"], list) else dict(message) for message in messages]


def dump(session: BuildingSession, guide: Guide) -> dict:
    state = {
        "format": STATE_FORMAT,
        "session": {
            "profile": asdict(session.profile),
            "applied": [asdict(change) for change in session.applied],
            "pending": [asdict(change) for change in session.pending.values()],
            "events": session.events,
            "last_route": session.last_route,
        },
        "guide": {
            "system": guide.system,
            "messages": plain_messages(guide.messages),
            "corpus": guide.corpus,
            "turn": guide.turn,
            "proposed_in_turn": guide.proposed_in_turn,
            "usage": asdict(guide.usage),
            "profile_note": guide.profile_note,
        },
    }
    return json.loads(json.dumps(state, ensure_ascii=False))  # tuples → lists, fails early on anything non-JSON


def restore(state: dict, session: BuildingSession, client: object) -> tuple[BuildingSession, Guide]:
    """Bring a fresh BuildingSession (base building, no changes) to the stored state; build its Guide."""
    if state.get("format") != STATE_FORMAT:
        raise StateError(f"stored state format {state.get('format')!r}, expected {STATE_FORMAT}")
    saved = state["session"]
    session.profile = RoutingProfile(**saved["profile"])
    for item in saved["applied"]:  # same steps as tool_apply_change, without re-emitting its UI event
        change = Change(**item)
        before = session.building
        session.building = session.changed_building(change)
        session.snapshots[change.id] = (before, session.building)
        session.applied.append(change)
    session.pending = {item["id"]: Change(**item) for item in saved["pending"]}
    session.events = saved["events"]
    session.last_route = saved["last_route"]
    numbers = [int(change.id[1:]) for change in [*session.applied, *session.pending.values()]
               if change.id[1:].isdigit()]
    session._ids = itertools.count(max(numbers, default=0) + 1)

    guide = Guide(session, client=client)
    saved = state["guide"]
    guide.system = saved["system"]
    guide.messages = saved["messages"]
    guide.corpus = saved["corpus"]
    guide.turn = saved["turn"]
    guide.proposed_in_turn = saved["proposed_in_turn"]
    guide.usage = Usage(**saved["usage"])
    guide.profile_note = saved["profile_note"]
    return session, guide


# ---------- where states live ----------


class MemoryConversations:
    """Same contract as PostgresConversations, in one process. States go through JSON like they would in the DB.
    Several SessionStores sharing one instance behave like serverless instances sharing one database."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, str, int]] = {}
        self.lock = threading.Lock()

    def version(self, conversation_id: str) -> int | None:
        row = self.rows.get(conversation_id)
        return None if row is None else row[2]

    def load(self, conversation_id: str) -> Stored | None:
        row = self.rows.get(conversation_id)
        return None if row is None else Stored(row[0], json.loads(row[1]), row[2])

    def insert(self, conversation_id: str, building: str, state: dict) -> bool:
        with self.lock:
            if conversation_id in self.rows:
                return False
            self.rows[conversation_id] = (building, json.dumps(state), 1)
            return True

    def save(self, conversation_id: str, building: str, state: dict, version: int) -> int:
        with self.lock:
            if self.version(conversation_id) != version:
                raise Conflict(conversation_id)
            self.rows[conversation_id] = (building, json.dumps(state), version + 1)
            return version + 1


class PostgresConnection:
    """One reused connection to SUPABASE_DB_URL (reopened if it drops); shared by the stores in this module and
    backend/drafts.py."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.connection: psycopg.Connection | None = None
        self.lock = threading.Lock()

    def execute(self, sql: str, params: tuple) -> list[tuple]:
        with self.lock:
            for attempt in range(2):
                if self.connection is None or self.connection.closed:
                    self.connection = psycopg.connect(self.dsn, autocommit=True, prepare_threshold=None,
                                                      connect_timeout=10)
                try:
                    with self.connection.cursor() as cursor:
                        cursor.execute(sql, params)
                        return cursor.fetchall() if cursor.description else []
                except psycopg.OperationalError:
                    self.connection = None
                    if attempt:
                        raise
        raise AssertionError("unreachable")


class PostgresConversations(PostgresConnection):
    """The `conversations` table."""

    def version(self, conversation_id: str) -> int | None:
        rows = self.execute("select version from conversations where id = %s", (conversation_id,))
        return rows[0][0] if rows else None

    def load(self, conversation_id: str) -> Stored | None:
        rows = self.execute("select building, state, version from conversations where id = %s", (conversation_id,))
        return Stored(*rows[0]) if rows else None

    def insert(self, conversation_id: str, building: str, state: dict) -> bool:
        rows = self.execute(
            "insert into conversations (id, building, state) values (%s, %s, %s) on conflict (id) do nothing "
            "returning version", (conversation_id, building, Jsonb(state)))
        return bool(rows)

    def save(self, conversation_id: str, building: str, state: dict, version: int) -> int:
        rows = self.execute(
            "update conversations set building = %s, state = %s, version = version + 1, updated_at = now() "
            "where id = %s and version = %s returning version",
            (building, Jsonb(state), conversation_id, version))
        if not rows:
            raise Conflict(conversation_id)
        return rows[0][0]


def db_url() -> str | None:
    """SUPABASE_DB_URL unless GUIDE_PERSIST=off: the database the deployed backend keeps its state in."""
    url = os.environ.get("SUPABASE_DB_URL")
    if not url or os.environ.get("GUIDE_PERSIST", "on") == "off":
        return None
    return url


def from_env() -> PostgresConversations | None:
    url = db_url()
    return PostgresConversations(url) if url else None
