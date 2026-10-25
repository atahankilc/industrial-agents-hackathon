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

`MapView` derives what the map UI draws from a session: the vector floor plan of the session's *current* building
(cached until the session's BuildingMap object is replaced, e.g. by apply_change or a building switch) and outgoing
events enriched with route `legs` and `line` and change `space_ids` (copies; session.events is untouched)."""

import copy
import csv
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agent.guide import Guide, make_client, system_blocks
from backend import persistence
from agent.tools import BuildingSession
from core.access import filter_building, restricted_names, restricted_polygons
from core.building_map import OUTSIDE, BuildingMap
from core.directions import guidance, route_legs
from core.floorplan import export_plan
from core.routeline import route_line

DATA_DIR = Path(os.environ.get("GUIDE_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
SPLITS = ("train", "dev", "test")
DEFAULT_SESSION = "default"
DEMO_BUILDING = "train/proc-campus-train-000"  # the offline client's example phrasings match this building
LOCATIONS = Path(__file__).resolve().parent / "locations.json"  # real positions of the OSM buildings (see its "about")


def load_catalogue(data_dir: Path = DATA_DIR) -> dict[str, dict]:
    """building id → {"id", "split", "name", "path", "location"} for every split directory that holds a
    building.json; `location` is {"lat", "lon", "address"} plus optional "origin", "outline", "height_m" (see the "about" field
    of backend/locations.json) for a building with a known real position, else None."""
    names: dict[str, str] = {}
    manifest = data_dir / "manifest.csv"
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as handle:
            names = {row["path"]: row["name"] for row in csv.DictReader(handle)}
    located = json.loads(LOCATIONS.read_text(encoding="utf-8"))["buildings"] if LOCATIONS.exists() else {}
    catalogue = {}
    for split in SPLITS:
        for file in sorted((data_dir / split).glob("*/building.json")):
            building_id = f"{split}/{file.parent.name}"
            catalogue[building_id] = {"id": building_id, "split": split, "name": names.get(building_id),
                                      "path": file.parent, "location": located.get(file.parent.name)}
    return catalogue


class MapView:
    """Per-conversation cache of the vector floor plan of the session's current building."""

    def __init__(self) -> None:
        self.lock = threading.Lock()  # own lock: /events and /plan read while a Guide turn holds the turn lock
        self.building: BuildingMap | None = None  # the object the plan was built from (identity, not equality)
        self.floor_plan: dict | None = None

    def plan(self, session: BuildingSession) -> dict:
        """Vector floor plan (core/floorplan.py), rebuilt whenever the session's BuildingMap object changes."""
        with self.lock:
            if session.building is not self.building or self.floor_plan is None:
                self.building, self.floor_plan = session.building, export_plan(session.building)
            return self.floor_plan

    def enrich(self, session: BuildingSession, events: list[dict]) -> list[dict]:
        """Copies of `events` (a slice of session.events) with route legs and change space ids, computed on
        the session's building as it is now (changes only add doors or closures, so earlier paths still resolve)."""
        building = session.building
        enriched = []
        for event in events:
            if event.get("type") == "route":
                event = {**event, "legs": safe_legs(building, event), "steps": safe_steps(building, event),
                         "line": safe_line(building, event)}
            elif event.get("type") == "change":
                event = {**event, "space_ids": affected_spaces(building, event.get("targets") or [])}
            enriched.append(event)
        return enriched


def safe_legs(building: BuildingMap, event: dict) -> list[dict]:
    try:
        return route_legs(building, event.get("space_path") or [], event.get("element_path") or [])
    except (KeyError, StopIteration):  # path no longer valid on this building
        return []


def safe_steps(building: BuildingMap, event: dict) -> list[dict]:
    """The Guide's followable steps (core/directions.guidance: turns where a person makes them, landmarks, rounded
    metres) as data, for the app's next-move card; the same steps the Guide says."""
    try:
        return guidance(building, event.get("space_path") or [], event.get("element_path") or [])
    except (KeyError, StopIteration):  # path no longer valid on this building
        return []


def safe_line(building: BuildingMap, event: dict) -> list[list[float]]:
    """The route as a plan polyline [[x, y, floor_index], …] (core/routeline.py), for drawing it on the map."""
    try:
        return route_line(building, event.get("space_path") or [], event.get("element_path") or [])
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
    # Access mode (backend/access.py): space ids the current viewer may not enter; the session runs on a building
    # copy without them, `restricted_shapes` are their outlines for the plan (darkened, nothing else).
    restricted: frozenset[str] = frozenset()
    restricted_shapes: list[dict] = field(default_factory=list)


class UnknownBuilding(ValueError):
    pass


class SessionStore:
    def __init__(self, catalogue: dict[str, dict] | None = None, backend: object | None = None) -> None:
        self.catalogue = catalogue if catalogue is not None else load_catalogue()
        self.backend = backend if backend is not None else persistence.from_env()
        self.conversations: dict[str, Conversation] = {}
        self.guard = threading.Lock()  # protects the dict, not the conversations
        self.user_buildings: object | None = None  # the DraftStore: saved buildings (`known`, `base_building`)
        self.base_cache: dict[str, dict] = {}  # dataset building id → building.json data (access mode)

    def known(self, building: str) -> bool:
        """In the catalogue, or saved by another instance since this one last looked."""
        if building in self.catalogue:
            return True
        return self.user_buildings is not None and self.user_buildings.known(building)

    def load_session(self, building: str, restricted: frozenset[str] = frozenset()) -> BuildingSession:
        if restricted:
            data = self.base_data(building)
            session = BuildingSession(BuildingMap(filter_building(data, restricted)))
            session.restricted_names = restricted_names(data, restricted)
            return session
        entry = self.catalogue.get(building, {})  # not listed: a draft's private base (an import, `import/<id>`)
        if "path" in entry:
            return BuildingSession.load(entry["path"])
        return BuildingSession(BuildingMap(copy.deepcopy(self.user_buildings.base_building(building))))

    def base_data(self, building: str) -> dict:
        """building.json data of a catalogue or saved building, as stored (cached per dataset building; callers
        must not mutate it)."""
        entry = self.catalogue.get(building, {})
        if "path" not in entry:
            return self.user_buildings.base_building(building)
        with self.guard:
            cached = self.base_cache.get(building)
        if cached is None:
            cached = json.loads((Path(entry["path"]) / "building.json").read_text(encoding="utf-8"))
            with self.guard:
                self.base_cache[building] = cached
        return cached

    def ensure_access(self, conversation: Conversation, restricted: frozenset[str]) -> Conversation:
        """Put the conversation on the building copy for this restricted set (access mode). Same set → nothing.
        Otherwise its state is replayed onto the new copy; if a change no longer applies there (it touched a space
        that is now restricted) the conversation starts fresh on that building. The Guide's system prompt is
        rebuilt from the copy, so its overview never names a restricted space."""
        if conversation.restricted == restricted:
            return conversation
        with conversation.lock:
            if conversation.restricted == restricted:
                return conversation
            state = persistence.dump(conversation.session, conversation.guide)
            try:
                session, guide = persistence.restore(state, self.load_session(conversation.building, restricted),
                                                     make_client())
            except (KeyError, ValueError, persistence.StateError):
                session = self.load_session(conversation.building, restricted)
                guide = Guide(session, client=make_client())
            session.preferences_enabled = conversation.session.preferences_enabled
            guide.system = system_blocks(session)
            conversation.session, conversation.guide = session, guide
            conversation.restricted = restricted
            data = self.base_data(conversation.building)
            conversation.restricted_shapes = restricted_polygons(data, restricted)
        return conversation

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
            conversation.restricted, conversation.restricted_shapes = frozenset(), []  # ensure_access sets them
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
