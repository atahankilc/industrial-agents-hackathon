"""Building catalogue and conversation sessions.

A building id is "<split>/<directory>" (e.g. "train/proc-campus-train-000"), the `path` column of
data/manifest.csv. Ids are only ever looked up in the catalogue, never joined into a path from user input.

One session = one conversation = one `BuildingSession` + one `Guide`, behind a per-session lock so the Guide's
history never sees two turns at once. `SessionStore` is an in-memory dict; it is the seam where a persistent
store (Supabase) goes later.

`MapView` derives what the map UI draws from a session: the point-cloud export of the session's *current*
building (cached until the session's BuildingMap object is replaced, e.g. by apply_change or a building switch)
and outgoing events enriched with route `vertices` and change `space_ids` (copies; session.events is untouched)."""

import csv
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agent.guide import Guide, make_client
from agent.tools import BuildingSession
from core.building_map import OUTSIDE, BuildingMap
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
    """Per-conversation cache of the point-cloud export and of route polylines (by event index)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()  # own lock: /events and /points read while a Guide turn holds the turn lock
        self.building: BuildingMap | None = None  # the object the caches were built from (identity, not equality)
        self.export: dict | None = None
        self.routes: dict[int, list[list[float]]] = {}

    def refresh(self, building: BuildingMap) -> dict:
        if building is not self.building:
            self.building, self.export, self.routes = building, export_points(building), {}
        return self.export  # type: ignore[return-value]

    def points(self, session: BuildingSession) -> dict:
        with self.lock:
            return self.refresh(session.building)

    def enrich(self, session: BuildingSession, events: list[dict], first_index: int) -> list[dict]:
        """Copies of `events` (session.events[first_index:...]) with route vertices and change space ids.

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
                    event = {**event, "vertices": self.routes[index]}
                elif event.get("type") == "change":
                    event = {**event, "space_ids": affected_spaces(building, event.get("targets") or [])}
                enriched.append(event)
            return enriched


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


class UnknownBuilding(ValueError):
    pass


class SessionStore:
    def __init__(self, catalogue: dict[str, dict] | None = None) -> None:
        self.catalogue = catalogue if catalogue is not None else load_catalogue()
        self.conversations: dict[str, Conversation] = {}
        self.guard = threading.Lock()  # protects the dict, not the conversations

    def default_building(self) -> str:
        for wanted in (os.environ.get("GUIDE_BUILDING"), DEMO_BUILDING):
            if wanted in self.catalogue:
                return wanted
        return next((key for key in self.catalogue if key.startswith("train/")), next(iter(self.catalogue)))

    def build(self, conversation_id: str, building: str | None) -> Conversation:
        building = building or self.default_building()
        if building not in self.catalogue:
            raise UnknownBuilding(building)
        session = BuildingSession.load(self.catalogue[building]["path"])
        # make_client() per conversation, so GUIDE_LLM / ANTHROPIC_API_KEY are read at creation, not import.
        return Conversation(conversation_id, building, session, Guide(session, client=make_client()))

    def create(self, building: str | None = None, conversation_id: str | None = None) -> Conversation:
        conversation = self.build(conversation_id or uuid.uuid4().hex, building)
        with self.guard:
            self.conversations[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    def get_or_create(self, conversation_id: str) -> Conversation:
        if existing := self.conversations.get(conversation_id):
            return existing
        conversation = self.build(conversation_id, None)
        with self.guard:  # two first requests for one id race: keep whichever landed first
            return self.conversations.setdefault(conversation_id, conversation)

    def switch_building(self, conversation: Conversation, building: str) -> Conversation:
        """Fresh BuildingSession + Guide on another building; the session id (and its lock) stay."""
        fresh = self.build(conversation.id, building)
        with conversation.lock:
            conversation.building, conversation.session, conversation.guide = building, fresh.session, fresh.guide
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
