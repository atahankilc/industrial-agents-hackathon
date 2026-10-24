"""Building catalogue and conversation sessions.

A building id is "<split>/<directory>" (e.g. "train/proc-campus-train-000"), the `path` column of
data/manifest.csv. Ids are only ever looked up in the catalogue, never joined into a path from user input. Saved
Edit-mode buildings (`user/<slug>`) join the catalogue through `SessionStore.user_buildings` (the DraftStore,
backend/drafts.py); on the deployed app they have no `path` and their data comes from the database.

One session = one conversation = one `BuildingSession` + one `Guide`, behind a per-session lock so the Guide's
history never sees two turns at once. `SessionStore` keeps conversations in a dict. With a persistence backend
(backend/persistence.py, Supabase when SUPABASE_DB_URL is set) that dict is only a cache: every lookup checks the
stored version and restores the conversation if another instance saved it since, and every turn is saved after it
ends. The lock only serialises turns within one process; across processes the version check does (Conflict).

`MapView` derives what the map UI draws from a session: the point-cloud export of the session's *current*
building (cached until the session's BuildingMap object is replaced, e.g. by apply_change or a building switch)
and outgoing events enriched with route `vertices` and change `space_ids` (copies; session.events is untouched)."""

import copy
import csv
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agent.guide import Guide, make_client
from backend import persistence
from agent.tools import BuildingSession
from core.building_map import OUTSIDE, BuildingMap
from core.directions import route_legs
from core.floorplan import export_plan
from core.pointcloud import export_points, route_vertices

DATA_DIR = Path(os.environ.get("GUIDE_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
SPLITS = ("train", "dev", "test")
DEFAULT_SESSION = "default"
DEMO_BUILDING = "train/proc-campus-train-000"  # the offline client's example phrasings match this building


def load_catalogue(data_dir: Path = DATA_DIR) -> dict[str, dict]:
    """building id → {"id", "split", "name", "path"} for every split directory that holds a building.json."""
    names: dict[str, str] = {}
    manifest = data_dir / "manifest.csv"
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as handle:
            names = {row["path"]: row["name"] for row in csv.DictReader(handle)}
    catalogue = {}
    for split in SPLITS:
        for file in sorted((data_dir / split).glob("*/building.json")):
            building_id = f"{split}/{file.parent.name}"
            catalogue[building_id] = {"id": building_id, "split": split, "name": names.get(building_id),
                                      "path": file.parent}
    return catalogue


class MapView:
    """Per-conversation cache of the point-cloud export, the vector floor plan and route polylines (by event index)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()  # own lock: /events and /points read while a Guide turn holds the turn lock
        self.building: BuildingMap | None = None  # the object the caches were built from (identity, not equality)
        self.export: dict | None = None
        self.routes: dict[int, list[list[float]]] = {}
        self.floor_plan: dict | None = None

    def refresh(self, building: BuildingMap) -> dict:
        if building is not self.building:
            self.building, self.export, self.routes, self.floor_plan = building, export_points(building), {}, None
        return self.export  # type: ignore[return-value]

    def points(self, session: BuildingSession) -> dict:
        with self.lock:
            return self.refresh(session.building)

    def plan(self, session: BuildingSession) -> dict:
        """Vector floor plan (core/floorplan.py) with the point-cloud export's centre, cached like the export."""
        with self.lock:
            export = self.refresh(session.building)
            if self.floor_plan is None:
                self.floor_plan = export_plan(session.building, export["center"])
            return self.floor_plan

    def enrich(self, session: BuildingSession, events: list[dict], first_index: int) -> list[dict]:
        """Copies of `events` (session.events[first_index:...]) with route vertices + legs and change space ids.

        Limitation: vertices are computed on the session's building as it is now, not the one current when the
        route was emitted (changes only add doors or closures, so earlier paths still resolve); the route cache is
        dropped together with the export whenever the building object changes."""
        with self.lock:
            building = session.building
            enriched = []
            for index, event in enumerate(events, start=first_index):
                if event.get("type") == "route":
                    export = self.refresh(building)
                    if index not in self.routes:
                        try:
                            self.routes[index] = route_vertices(export, building, event.get("space_path") or [],
                                                                event.get("element_path") or [])
                        except (KeyError, StopIteration):  # path no longer valid on this building
                            self.routes[index] = []
                    event = {**event, "vertices": self.routes[index],
                             "legs": safe_legs(building, event)}
                elif event.get("type") == "change":
                    event = {**event, "space_ids": affected_spaces(building, event.get("targets") or [])}
                enriched.append(event)
            return enriched


def safe_legs(building: BuildingMap, event: dict) -> list[dict]:
    try:
        return route_legs(building, event.get("space_path") or [], event.get("element_path") or [])
    except (KeyError, StopIteration):  # path no longer valid on this building
        return []


def affected_spaces(building: BuildingMap, targets: list[str]) -> list[str]:
    """Spaces a change touches: a connector's spaces, an opening's two sides (minus outside), a space itself."""
    spaces: list[str] = []
    for target in targets:
        if target in building.connectors:
            spaces += building.connectors[target]["space_ids"]
        elif target in building.openings:
            spaces += building.openings[target]["space_ids"]
        elif target in building.spaces:
            spaces.append(target)
    return list(dict.fromkeys(space for space in spaces if space != OUTSIDE))


@dataclass
class Conversation:
    id: str
    building: str
    session: BuildingSession
    guide: Guide
    lock: threading.Lock = field(default_factory=threading.Lock)
    view: MapView = field(default_factory=MapView)
    version: int = 0  # stored version this object reflects (0 = not persisted)


class UnknownBuilding(ValueError):
    pass


class SessionStore:
    def __init__(self, catalogue: dict[str, dict] | None = None, backend: object | None = None) -> None:
        self.catalogue = catalogue if catalogue is not None else load_catalogue()
        self.backend = backend if backend is not None else persistence.from_env()
        self.conversations: dict[str, Conversation] = {}
        self.guard = threading.Lock()  # protects the dict, not the conversations
        self.user_buildings: object | None = None  # the DraftStore: saved buildings (`known`, `base_building`)

    def known(self, building: str) -> bool:
        """In the catalogue, or saved by another instance since this one last looked."""
        if building in self.catalogue:
            return True
        return self.user_buildings is not None and self.user_buildings.known(building)

    def load_session(self, building: str) -> BuildingSession:
        entry = self.catalogue[building]
        if "path" in entry:
            return BuildingSession.load(entry["path"])
        return BuildingSession(BuildingMap(copy.deepcopy(self.user_buildings.base_building(building))))

    def default_building(self) -> str:
        for wanted in (os.environ.get("GUIDE_BUILDING"), DEMO_BUILDING):
            if wanted in self.catalogue:
                return wanted
        return next((key for key in self.catalogue if key.startswith("train/")), next(iter(self.catalogue)))

    def build(self, conversation_id: str, building: str | None) -> Conversation:
        building = building or self.default_building()
        if not self.known(building):
            raise UnknownBuilding(building)
        session = self.load_session(building)
        # make_client() per conversation, so GUIDE_LLM / ANTHROPIC_API_KEY are read at creation, not import.
        return Conversation(conversation_id, building, session, Guide(session, client=make_client()))

    def remember(self, conversation: Conversation) -> Conversation:
        with self.guard:
            self.conversations[conversation.id] = conversation
        return conversation

    def insert(self, conversation: Conversation) -> bool:
        """Store a new conversation; False if the id already exists in the backend."""
        if self.backend is None:
            return True
        state = persistence.dump(conversation.session, conversation.guide)
        if not self.backend.insert(conversation.id, conversation.building, state):
            return False
        conversation.version = 1
        return True

    def create(self, building: str | None = None, conversation_id: str | None = None) -> Conversation:
        conversation = self.build(conversation_id or uuid.uuid4().hex, building)
        self.insert(conversation)
        return self.remember(conversation)

    def get(self, conversation_id: str) -> Conversation | None:
        cached = self.conversations.get(conversation_id)
        if self.backend is None:
            return cached
        current = self.backend.version(conversation_id)
        if current is None:
            return None
        if cached is not None and cached.version == current:
            return cached
        stored = self.backend.load(conversation_id)
        if stored is None or not self.known(stored.building):
            return None
        fresh = self.load_session(stored.building)
        session, guide = persistence.restore(stored.state, fresh, make_client())
        return self.remember(Conversation(conversation_id, stored.building, session, guide, version=stored.version))

    def get_or_create(self, conversation_id: str) -> Conversation:
        if existing := self.get(conversation_id):
            return existing
        conversation = self.build(conversation_id, None)
        if not self.insert(conversation):  # another instance created it first
            return self.get(conversation_id) or conversation
        with self.guard:  # two first requests for one id race: keep whichever landed first
            return self.conversations.setdefault(conversation_id, conversation)

    def save(self, conversation: Conversation) -> None:
        """Persist after a turn or a building switch. Raises persistence.Conflict (and drops the cached copy) if
        another instance saved this conversation in between; the caller's turn is then lost."""
        if self.backend is None:
            return
        state = persistence.dump(conversation.session, conversation.guide)
        try:
            conversation.version = self.backend.save(conversation.id, conversation.building, state,
                                                     conversation.version)
        except persistence.Conflict:
            with self.guard:
                if self.conversations.get(conversation.id) is conversation:
                    del self.conversations[conversation.id]
            raise

    def switch_building(self, conversation: Conversation, building: str) -> Conversation:
        """Fresh BuildingSession + Guide on another building; the session id (and its lock) stay."""
        fresh = self.build(conversation.id, building)
        with conversation.lock:
            conversation.building, conversation.session, conversation.guide = building, fresh.session, fresh.guide
            self.save(conversation)
        return conversation


def summary(conversation: Conversation) -> dict:
    session = conversation.session
    return {
        "session_id": conversation.id,
        "building": conversation.building,
        "profile": {**vars(session.profile), "summary": session.profile.describe()},
        "applied": [{"id": change.id, "summary": change.summary} for change in session.applied],
        "pending": [{"id": change.id, "summary": change.summary} for change in session.pending.values()],
        "event_count": len(session.events),
    }
