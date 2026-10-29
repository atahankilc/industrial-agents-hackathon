"""What every router shares: the process-wide stores and the request guards built on them.

Routers read the stores as `deps.store`, `deps.drafts`, … (not `from deps import store`), so a test that replaces one
with monkeypatch reaches every route. `live` (backend/api/live/) and `fleet` (backend/api/fleet.py) are created
here too, because the session guards attach them to conversations."""

import copy
import json
import os
import queue
from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException

from backend.agents.campus import Campus
from backend.api import persistence
from backend.api.access import Access, AuthError, AuthUnavailable, Viewer
from backend.api.drafts import Draft, DraftStore, backend_from_env
from backend.api.fleet import Fleet, fleet_from_env
from backend.api.live import LiveHub, SessionLive
from backend.api.sessions import DATA_DIR, Conversation, SessionStore
from backend.core.building_map import BuildingMap

store = SessionStore()
drafts = DraftStore(backend_from_env(Path(os.environ.get("GUIDE_USER_DIR", DATA_DIR / "user"))), store.catalogue)
store.user_buildings = drafts
access = Access()  # access mode (ACCESS_MODE=on): accounts, restricted spaces — backend/api/access.py
live = LiveHub(lambda building: BuildingMap(copy.deepcopy(store.base_data(building))))  # backend/api/live/
fleet = Fleet(fleet_from_env(), store.base_data)  # moving objects (access mode): backend/api/fleet.py


def viewer_or_401(authorization: str | None) -> Viewer:
    try:
        return access.viewer(authorization)
    except AuthError:
        raise HTTPException(401, "sign-in expired or invalid; sign in again") from None
    except AuthUnavailable as error:
        raise HTTPException(503, f"sign-in is unavailable right now ({error})") from None


def conversation_or_404(session_id: str, authorization: str | None = None) -> Conversation:
    """The conversation, on the building copy this request's viewer may see (access mode; a no-op when off)."""
    conversation = store.get(session_id)
    if conversation is None:
        raise HTTPException(404, f"unknown session {session_id!r}")
    viewer = viewer_or_401(authorization)
    return with_live(with_campus(with_access(conversation, viewer), access.hidden_buildings(viewer)))


def live_hidden(authorization: str | None, building: str) -> frozenset[str] | None:
    """Access mode: the spaces whose live things this viewer may not see (none for the admin)."""
    if not access.enabled:
        return None
    viewer = viewer_or_401(authorization)
    return None if access.can_admin(viewer, building) else access.restricted_for(viewer, building,
                                                                                store.base_data(building))


def with_live(conversation: Conversation) -> Conversation:
    """The building's live world (backend/api/live/) for the session's routes, while one runs; else no live state."""
    world = live.world(conversation.building, start=False)
    conversation.session.live = SessionLive(live, conversation.building) if world is not None else None
    return conversation


def with_campus(conversation: Conversation, hidden: set[str] = frozenset()) -> Conversation:
    """The session's buildings nearby (backend/agents/campus.py); sessions are rebuilt on restores and switches.
    `hidden`: buildings this viewer may not list (access mode), so the Guide neither names nor routes to them."""
    catalogue = {key: entry for key, entry in store.catalogue.items() if key not in hidden} if hidden else store.catalogue
    campus = conversation.session.campus
    if campus is None or campus.building_id != conversation.building:
        conversation.session.campus = Campus(conversation.building, catalogue)
    else:
        campus.catalogue = catalogue
    return conversation


def with_access(conversation: Conversation, viewer: Viewer) -> Conversation:
    if not access.enabled:
        return conversation
    conversation.session.preferences_enabled = True  # remembered preferences come with access mode
    if not access.visible(viewer, conversation.building):
        raise HTTPException(404, f"unknown session {conversation.id!r}")
    restricted = access.restricted_for(viewer, conversation.building, store.base_data(conversation.building))
    conversation = store.ensure_access(conversation, restricted)
    conversation.session.preferences_enabled = True
    building = conversation.building
    conversation.session.object_dispatch = (
        (lambda name, destination: dispatch_by_name(building, name, destination))
        if access.can_admin(viewer, building) else None)
    return conversation


def dispatch_by_name(building: str, name: str, destination: str) -> dict:
    """The Guide's send_object for the admin: an object of this building by name or id → fleet.dispatch."""
    rows = fleet.store.list(building)
    wanted = name.strip().lower()
    row = next((row for row in rows if wanted in (row["id"].lower(), row["name"].lower())), None)
    if row is None:
        matches = [row for row in rows if wanted in row["name"].lower()]
        row = matches[0] if len(matches) == 1 else None
    if row is None:
        return {"error": f"No object called '{name}'", "objects": [row["name"] for row in rows]}
    return fleet.dispatch(row, destination)


def visible_or_422(viewer: Viewer, building: str | None) -> None:
    if building is not None and access.enabled and not access.visible(viewer, building):
        raise HTTPException(422, f"unknown building {building}; see GET /buildings")


def save_or_409(conversation: Conversation) -> None:
    try:
        store.save(conversation)
    except persistence.Conflict:
        raise HTTPException(409, "this conversation was updated elsewhere meanwhile; send the message again") from None


def admin_or_403(authorization: str | None) -> Viewer:
    """An admin: rights over every building and org (ADMIN_EMAIL)."""
    if not access.enabled:
        raise HTTPException(404, "access mode is off")
    viewer = viewer_or_401(authorization)
    if not viewer.admin:
        raise HTTPException(403, "only the admin can do this")
    return viewer


def building_admin_or_403(authorization: str | None, building: str) -> Viewer:
    """Whoever administers this building: an admin, or an editor / owner of the org that owns it."""
    if not access.enabled:
        raise HTTPException(404, "access mode is off")
    viewer = viewer_or_401(authorization)
    if not access.can_admin(viewer, building):
        raise HTTPException(403, "only the building admin can do this")
    return viewer


def known_or_422(building: str) -> None:
    if not store.known(building):
        raise HTTPException(422, f"unknown building {building}; see GET /buildings")


def viewer_restricted(authorization: str | None, building: str) -> tuple[Viewer, frozenset[str]]:
    viewer = viewer_or_401(authorization)
    known_or_422(building)
    if not access.visible(viewer, building):
        raise HTTPException(422, f"unknown building {building}; see GET /buildings")
    return viewer, access.restricted_for(viewer, building, store.base_data(building))


def draft_or_404(draft_id: str) -> Draft:
    draft = drafts.get(draft_id)
    if draft is None:
        raise HTTPException(404, f"unknown draft {draft_id!r}")
    return draft


PING_S = 10  # a quiet turn (the model thinking) still sends a line this often; the app gives up after 45 s of silence


def ndjson_with_pings(lines: queue.Queue) -> Iterator[str]:
    """The queued lines as NDJSON until None, with {"type": "ping"} whenever PING_S pass without one, so a phone's
    connection is never idle long enough to be dropped and the app can tell a slow turn from a lost one."""
    while True:
        try:
            line = lines.get(timeout=PING_S)
        except queue.Empty:
            yield '{"type": "ping"}\n'
            continue
        if line is None:
            return
        yield json.dumps(line, ensure_ascii=False) + "\n"
