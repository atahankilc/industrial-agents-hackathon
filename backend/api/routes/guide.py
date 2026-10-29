"""The Building Guide over HTTP: buildings, sessions, chat (plain and streamed), location, route end, arrival from a
nearby building, the events cursor for the map and the session's floor plan.

Guide turns are blocking (tool loop + LLM calls), so these endpoints are plain `def` and run in FastAPI's
threadpool; each conversation's lock serialises its turns. With persistence on (backend/api/persistence.py) every turn
is saved when it ends; a turn that lost a save race to another instance answers 409 and must be resent."""

import copy
import queue
import threading

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.campus import arrive
from backend.agents.guide import PHOTO_TYPES
from backend.api import deps, persistence, service_errors
from backend.api.deps import conversation_or_404, ndjson_with_pings, save_or_409, viewer_or_401, visible_or_422, with_access
from backend.api.sessions import Conversation, UnknownBuilding, summary
from backend.core.building_map import MapError

router = APIRouter()


class NewSession(BaseModel):
    building: str | None = None


class SwitchBuilding(BaseModel):
    building: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    channel: str = "text"  # "voice": spoken-style reply, also returned as `spoken` (backend/agents/speech.py)
    photo: str | None = None  # data URL (jpeg/png/webp) from the camera walk mode, shown to the Guide for one turn
    heard: bool = True  # voice channel: the message is a speech transcript; false for a tapped button read aloud
    selected: str | None = None  # the space or asset id tapped on the plan while asking ("how do I get there?")
    route_step: int | None = None  # the step card's step (0-based) while a route is on the map


class LocationRequest(BaseModel):
    space_id: str | None = None  # the room the "you are here" figure stands in; None = taken away
    point: list[float] | None = None  # where in that room (plan metres): the drawn route line starts there


class ArriveRequest(BaseModel):
    entrance: str  # opening id of this building the user comes in through
    destination: str  # space id here
    from_session: str | None = None  # the conversation in the building they came from: its routing profile carries over


PHOTO_MAX_CHARS = 1_500_000  # base64 of a ~1.1 MB image; the app sends ~1280 px JPEGs well below this


def turn_payload(conversation: Conversation, turn: object) -> dict:
    return {
        "reply": turn.text,
        "tool_calls": [{"name": call["name"], "input": call["input"]} for call in turn.tool_calls],
        "events": conversation.view.enrich(conversation.session, turn.events),
        "ungrounded": turn.ungrounded,
        "spoken": turn.spoken,
    }


@router.get("/buildings")
def buildings(authorization: str | None = Header(None)) -> list[dict]:
    deps.drafts.refresh(quiet=True)  # buildings saved on other instances; dataset buildings even if the database is down
    hidden = deps.access.hidden_buildings(viewer_or_401(authorization))
    owners = ({building: access.org for building, access in deps.access.store.all_buildings().items() if access.org}
              if deps.access.enabled else {})  # the owning organisation (docs/product/organizations.md)
    return [listing_item(item, owners.get(item["id"])) for item in deps.store.catalogue.values()
            if item["id"] not in hidden]


def listing_item(item: dict, org: str | None) -> dict:
    """A catalogue entry as GET /buildings (and GET /maps/{slug}) lists it."""
    return {"id": item["id"], "split": item["split"], "name": item["name"], "kind": item.get("kind"),
            "location": None if item.get("superseded") else item.get("location"),  # a newer save stands there
            "org": org}


@router.post("/sessions")
def create_session(body: NewSession, authorization: str | None = Header(None)) -> dict:
    viewer = viewer_or_401(authorization)
    visible_or_422(viewer, body.building)
    try:
        conversation = with_access(deps.store.create(body.building), viewer)
    except UnknownBuilding as error:
        raise HTTPException(422, f"unknown building {error}; see GET /buildings") from None
    return {"session_id": conversation.id, "building": conversation.building,
            "overview": conversation.session.building.overview()}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, authorization: str | None = Header(None)) -> dict:
    return summary(conversation_or_404(session_id, authorization))


@router.put("/sessions/{session_id}/building")
def switch_building(session_id: str, body: SwitchBuilding, authorization: str | None = Header(None)) -> dict:
    conversation = conversation_or_404(session_id, authorization)
    viewer = viewer_or_401(authorization)
    visible_or_422(viewer, body.building)
    try:
        deps.store.switch_building(conversation, body.building)
    except UnknownBuilding as error:
        raise HTTPException(422, f"unknown building {error}; see GET /buildings") from None
    except persistence.Conflict:
        raise HTTPException(409, "this conversation was updated elsewhere meanwhile; try again") from None
    with_access(conversation, viewer)
    return {**summary(conversation), "overview": conversation.session.building.overview()}


@router.post("/chat")
def chat(body: ChatRequest, authorization: str | None = Header(None)) -> dict:
    conversation = conversation_or_404(body.session_id, authorization)
    with conversation.lock:
        turn = conversation.guide.reply(body.message, channel=channel_or_422(body.channel),
                                        photo=photo_or_422(body.photo), heard=body.heard,
                                        selected=body.selected, route_step=body.route_step)
        save_or_409(conversation)
        return turn_payload(conversation, turn)


def photo_or_422(photo: str | None) -> dict | None:
    if photo is None:
        return None
    header, _, data = photo.partition(",")
    media_type = header.removeprefix("data:").removesuffix(";base64")
    if not header.startswith("data:") or not header.endswith(";base64") or media_type not in PHOTO_TYPES or not data:
        raise HTTPException(422, f"photo must be a base64 data URL of type {', '.join(PHOTO_TYPES)}")
    if len(data) > PHOTO_MAX_CHARS:
        raise HTTPException(413, "photo is too large; send a smaller image")
    return {"media_type": media_type, "data": data}


def channel_or_422(channel: str) -> str:
    if channel not in ("text", "voice"):
        raise HTTPException(422, "channel must be 'text' or 'voice'")
    return channel


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, authorization: str | None = Header(None)) -> StreamingResponse:
    """One turn as NDJSON lines: {"type": "step", …} per tool call or check while the Guide works (the map can
    poll /events on each `tool_done`), then {"type": "reply", …the /chat payload} or {"type": "error", "detail"}.
    Voice turns also send {"type": "say", "text"} per sentence as soon as it may be spoken (backend/agents/speech.py
    SpokenStream), all before the reply line; together they are the whole spoken reply."""
    conversation = conversation_or_404(body.session_id, authorization)
    channel, photo = channel_or_422(body.channel), photo_or_422(body.photo)
    lines: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            with conversation.lock:
                conversation.guide.on_step = lambda step: lines.put({"type": "step", **step})
                conversation.guide.on_say = lambda text: lines.put({"type": "say", "text": text})
                try:
                    turn = conversation.guide.reply(body.message, channel=channel, photo=photo, heard=body.heard,
                                                    selected=body.selected, route_step=body.route_step)
                finally:
                    conversation.guide.on_step = None
                    conversation.guide.on_say = None
                try:
                    deps.store.save(conversation)
                except persistence.Conflict:
                    lines.put({"type": "error", "code": "conflict",
                               "message": "This conversation was updated elsewhere meanwhile. Send the message again.",
                               "detail": "this conversation was updated elsewhere meanwhile; send the message again"})
                    return
                lines.put({"type": "reply", **turn_payload(conversation, turn)})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put(service_errors.error_line(error))
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        yield from ndjson_with_pings(lines)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.put("/sessions/{session_id}/location")
def put_location(session_id: str, body: LocationRequest, authorization: str | None = Header(None)) -> dict:
    """The app's "you are here" figure: the Guide routes from there and stops asking where the user is."""
    conversation = conversation_or_404(session_id, authorization)
    with conversation.lock:
        if body.space_id is not None and body.space_id not in conversation.session.building.spaces:
            raise HTTPException(422, f"unknown space {body.space_id!r}")
        location = conversation.guide.set_location(body.space_id, body.point)
        save_or_409(conversation)
    return {"location": location}


@router.delete("/sessions/{session_id}/route")
def delete_route(session_id: str, authorization: str | None = Header(None)) -> dict:
    """The user ended the route in the app (End directions, or the arrival): it is off the map, so the Guide gets
    no route note for it and show_route_step / end_route no longer see it."""
    conversation = conversation_or_404(session_id, authorization)
    with conversation.lock:
        session = conversation.session
        if session.shown_route() is None:
            return {"ended": False}
        session.events.append({"type": "route_end", "arrived": False, "by": "app"})
        save_or_409(conversation)
    return {"ended": True}


@router.post("/sessions/{session_id}/arrive")
def post_arrive(session_id: str, body: ArriveRequest, authorization: str | None = Header(None)) -> dict:
    """Coming over from a nearby building (route_to_building → Continue): the user stands at `entrance`; the
    route from there to `destination` comes back as events, like a Guide turn's."""
    conversation = conversation_or_404(session_id, authorization)
    previous = None
    if body.from_session:
        try:  # same access check as the target session; a session this viewer may not see is ignored
            previous = conversation_or_404(body.from_session, authorization)
        except HTTPException:
            previous = None
    with conversation.lock:
        session = conversation.session
        if previous is not None:
            session.profile = copy.deepcopy(previous.session.profile)
        first = len(session.events)
        try:
            route = arrive(session, body.entrance, body.destination)
        except (MapError, KeyError) as error:
            raise HTTPException(422, str(error)) from None
        conversation.guide.set_location(session.user_location["space_id"])
        conversation.guide.location_note += (" They just came over from a nearby building; the map shows the way "
                                             f"to {session.building.spaces[route['to_space_id']]['name']}."
                                             if route.get("reachable") else " They just came over from a nearby building.")
        save_or_409(conversation)
        events = conversation.view.enrich(session, session.events[first:])
    return {"route": {key: route.get(key) for key in ("reachable", "reason", "about_m", "length_m")},
            "location": session.user_location, "events": events}


@router.get("/events")
def events(session_id: str, after: int = Query(0, ge=0), authorization: str | None = Header(None)) -> dict:
    # Read without the lock so the map can update while a turn's tools run.
    conversation = conversation_or_404(session_id, authorization)
    log = conversation.session.events
    end = len(log)  # snapshot: a running turn may append meanwhile
    return {"events": conversation.view.enrich(conversation.session, log[after:end]), "next": end}


@router.get("/sessions/{session_id}/plan")
def plan(session_id: str, authorization: str | None = Header(None)) -> dict:
    conversation = conversation_or_404(session_id, authorization)
    floor_plan = conversation.view.plan(conversation.session)
    if not conversation.restricted_shapes:
        return floor_plan
    index = {floor["id"]: number for number, floor in enumerate(floor_plan["floors"])}
    return {**floor_plan, "restricted": [{"id": shape["id"], "floor": index[shape["floor_id"]],
                                          "polygon": shape["polygon"]}
                                         for shape in conversation.restricted_shapes if shape["floor_id"] in index]}
