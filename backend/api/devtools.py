"""Dev tool endpoints (the app's dev panel, frontend/src/dev/): run the Guide's tools directly, without a
language model, so every map state (place found, route, profile, closure, lost access) can be produced and
inspected by hand.

  GET  /dev/tools                      the Guide's tool definitions (name, description, input schema)
  POST /dev/sessions/{id}/tool         {name, arguments} → {result, events}: one BuildingSession.call, the events it
                                       emitted enriched like /events (legs, space_ids, route line)
  GET  /dev/sessions/{id}/state        profile, pending/applied changes, closed elements, the elements the profile
                                       treats as closed, the entrance room, rooms unreachable from it
  POST /dev/sessions/{id}/reset        a fresh session on the same building (profile, changes and events cleared)

The tools are the same ones the Guide calls in a conversation; a tool call is saved like a Guide turn.
`router(...)` takes the app's store and helpers so this module does not import backend.api.deps. Session endpoints
pass the request's Authorization header to `lookup`, so in access mode the dev panel sees the same building copy
as the signed-in viewer (`/dev/tools` has no session and lists TOOL_DEFINITIONS)."""

from collections.abc import Callable

from fastapi import APIRouter, Header
from pydantic import BaseModel

from backend.agents.tools import TOOL_DEFINITIONS
from backend.api.sessions import Conversation, SessionStore, summary
from backend.core.building_map import MapError
from backend.core.solvers.reachability import is_room


class ToolCall(BaseModel):
    name: str
    arguments: dict = {}


def router(store: SessionStore, lookup: Callable[[str, str | None], Conversation], save: Callable[[Conversation], None]) -> APIRouter:
    routes = APIRouter(prefix="/dev")

    @routes.get("/tools")
    def tools() -> list[dict]:
        return TOOL_DEFINITIONS

    @routes.post("/sessions/{session_id}/tool")
    def call_tool(session_id: str, body: ToolCall, authorization: str | None = Header(None)) -> dict:
        conversation = lookup(session_id, authorization)
        with conversation.lock:
            session = conversation.session
            first = len(session.events)
            result = session.call(body.name, body.arguments)
            events = conversation.view.enrich(session, session.events[first:])
            save(conversation)
        return {"result": result, "events": events}

    @routes.get("/sessions/{session_id}/state")
    def state(session_id: str, authorization: str | None = Header(None)) -> dict:
        conversation = lookup(session_id, authorization)
        with conversation.lock:
            session = conversation.session
            building = session.building
            unreachable: list[str] | None
            try:
                start = session.main_entrance_space()
                reached = set(session.space_distances(building, start))
                unreachable = sorted(space_id for space_id, space in building.spaces.items()
                                     if is_room(space) and space_id not in reached)
            except MapError:
                start, unreachable = None, None
            return {
                **summary(conversation),
                "profile_fields": {name: getattr(session.profile, name)
                                   for name in ("step_free", "min_door_width_m", "avoid_lifts", "forklift", "preset")},
                "closed": sorted(building.closed),
                "profile_closed": session.profile_closures(),
                "entrance_space": start,
                "unreachable": unreachable,
            }

    @routes.post("/sessions/{session_id}/reset")
    def reset(session_id: str, authorization: str | None = Header(None)) -> dict:
        conversation = lookup(session_id, authorization)
        return summary(store.switch_building(conversation, conversation.building))

    return routes
