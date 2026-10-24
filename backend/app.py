"""FastAPI app: the Building Guide over HTTP.

  GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765

Endpoints: /health, /buildings, /sessions (create, inspect, switch building), /sessions/{id}/points (point-cloud
export of the session's current building, gzipped), /chat, /chat/stream (the same turn as NDJSON: live tool steps,
then the reply), /events (polling cursor for the map UI; route events
carry `vertices`, change events `space_ids`), the OpenAI-compatible /v1/chat/completions for ElevenLabs
(backend/openai_compat.py), and the Edit mode's /drafts (create, get, points, plan, ops, undo, save — backend/drafts.py;
saved buildings appear in /buildings as `user/<slug>`, stored under GUIDE_USER_DIR, default data/user/).
Guide turns are blocking (tool loop + LLM calls), so those endpoints are plain `def` and run in FastAPI's
threadpool; each conversation's lock serialises its turns. With persistence on (backend/persistence.py) every turn
is saved when it ends; a turn that lost a save race to another instance answers 409 and must be resent.

On Vercel (vercel.json) the app is the `api` service behind the rewrite `/api/(.*)`, which passes the original path
through, so every route is also reachable under `/api` (StripPrefix). CORS_ORIGINS (comma-separated) restricts
cross-origin callers; the default `*` is for local development, the deployed frontend is same-origin."""

import json
import os
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.guide import PHOTO_TYPES, llm_mode
from backend import openai_compat, persistence
from backend.drafts import Draft, DraftStore
from backend.sessions import DATA_DIR, DEFAULT_SESSION, Conversation, SessionStore, UnknownBuilding, summary
from core.building_map import BuildingMap
from core.edits import EditError
from core.pointcloud import export_points

API_PREFIX = "/api"


class StripPrefix:
    """ASGI middleware: serve `/api/x` as `/x`, so the same routes work behind the Vercel rewrite and locally."""

    def __init__(self, app: object, prefix: str = API_PREFIX) -> None:
        self.app, self.prefix = app, prefix

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        path = scope.get("path", "")
        if scope["type"] in ("http", "websocket") and (path == self.prefix or path.startswith(self.prefix + "/")):
            scope = {**scope, "path": path[len(self.prefix):] or "/",
                     "raw_path": scope.get("raw_path", b"")[len(self.prefix):] or b"/"}
        await self.app(scope, receive, send)


origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()]
app = FastAPI(title="Talk to Your Building")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)  # the point-cloud export is ~4 MB of JSON
app.add_middleware(StripPrefix)  # added last = outermost: routes see the path without /api
store = SessionStore()
drafts = DraftStore(Path(os.environ.get("GUIDE_USER_DIR", DATA_DIR / "user")), store.catalogue)


class NewSession(BaseModel):
    building: str | None = None


class SwitchBuilding(BaseModel):
    building: str


class NewDraft(BaseModel):
    base: str


class DraftOps(BaseModel):
    ops: list[dict]


class SaveDraft(BaseModel):
    name: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    channel: str = "text"  # "voice": spoken-style reply, also returned as `spoken` (agent/speech.py)
    photo: str | None = None  # data URL (jpeg/png/webp) from the camera walk mode, shown to the Guide for one turn


PHOTO_MAX_CHARS = 1_500_000  # base64 of a ~1.1 MB image; the app sends ~1280 px JPEGs well below this


def conversation_or_404(session_id: str) -> Conversation:
    conversation = store.get(session_id)
    if conversation is None:
        raise HTTPException(404, f"unknown session {session_id!r}")
    return conversation


def save_or_409(conversation: Conversation) -> None:
    try:
        store.save(conversation)
    except persistence.Conflict:
        raise HTTPException(409, "this conversation was updated elsewhere meanwhile; send the message again") from None


def turn_payload(conversation: Conversation, turn: object) -> dict:
    # turn.events is the tail of session.events, so its first index is len(log) - len(turn.events).
    first_index = len(conversation.session.events) - len(turn.events)
    return {
        "reply": turn.text,
        "tool_calls": [{"name": call["name"], "input": call["input"]} for call in turn.tool_calls],
        "events": conversation.view.enrich(conversation.session, turn.events, first_index),
        "ungrounded": turn.ungrounded,
        "spoken": turn.spoken,
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True, "llm": llm_mode()}


@app.get("/buildings")
def buildings() -> list[dict]:
    return [{"id": item["id"], "split": item["split"], "name": item["name"]} for item in store.catalogue.values()]


@app.post("/sessions")
def create_session(body: NewSession) -> dict:
    try:
        conversation = store.create(body.building)
    except UnknownBuilding as error:
        raise HTTPException(422, f"unknown building {error}; see GET /buildings") from None
    return {"session_id": conversation.id, "building": conversation.building,
            "overview": conversation.session.building.overview()}


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    return summary(conversation_or_404(session_id))


@app.put("/sessions/{session_id}/building")
def switch_building(session_id: str, body: SwitchBuilding) -> dict:
    conversation = conversation_or_404(session_id)
    try:
        store.switch_building(conversation, body.building)
    except UnknownBuilding as error:
        raise HTTPException(422, f"unknown building {error}; see GET /buildings") from None
    except persistence.Conflict:
        raise HTTPException(409, "this conversation was updated elsewhere meanwhile; try again") from None
    return {**summary(conversation), "overview": conversation.session.building.overview()}


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    conversation = conversation_or_404(body.session_id)
    with conversation.lock:
        turn = conversation.guide.reply(body.message, channel=channel_or_422(body.channel),
                                        photo=photo_or_422(body.photo))
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


@app.post("/chat/stream")
def chat_stream(body: ChatRequest) -> StreamingResponse:
    """One turn as NDJSON lines: {"type": "step", …} per tool call or check while the Guide works (the map can
    poll /events on each `tool_done`), then {"type": "reply", …the /chat payload} or {"type": "error", "detail"}."""
    conversation = conversation_or_404(body.session_id)
    channel, photo = channel_or_422(body.channel), photo_or_422(body.photo)
    lines: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            with conversation.lock:
                conversation.guide.on_step = lambda step: lines.put({"type": "step", **step})
                try:
                    turn = conversation.guide.reply(body.message, channel=channel, photo=photo)
                finally:
                    conversation.guide.on_step = None
                try:
                    store.save(conversation)
                except persistence.Conflict:
                    lines.put({"type": "error", "detail": "this conversation was updated elsewhere meanwhile; "
                                                          "send the message again"})
                    return
                lines.put({"type": "reply", **turn_payload(conversation, turn)})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put({"type": "error", "detail": f"{type(error).__name__}: {error}"[:300]})
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        while (line := lines.get()) is not None:
            yield json.dumps(line, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.get("/events")
def events(session_id: str, after: int = Query(0, ge=0)) -> dict:
    # Read without the lock so the map can update while a turn's tools run.
    conversation = conversation_or_404(session_id)
    log = conversation.session.events
    end = len(log)  # snapshot: a running turn may append meanwhile
    return {"events": conversation.view.enrich(conversation.session, log[after:end], after), "next": end}


@app.get("/sessions/{session_id}/points")
def points(session_id: str) -> dict:
    conversation = conversation_or_404(session_id)
    return conversation.view.points(conversation.session)


@app.get("/sessions/{session_id}/plan")
def plan(session_id: str) -> dict:
    conversation = conversation_or_404(session_id)
    return conversation.view.plan(conversation.session)


# ---------- Edit mode: drafts (backend/drafts.py) ----------


def draft_or_404(draft_id: str) -> Draft:
    draft = drafts.get(draft_id)
    if draft is None:
        raise HTTPException(404, f"unknown draft {draft_id!r}")
    return draft


@app.post("/drafts")
def create_draft(body: NewDraft) -> dict:
    try:
        draft = drafts.create(body.base)
    except KeyError:
        raise HTTPException(422, f"unknown building {body.base!r}; see GET /buildings") from None
    return drafts.state(draft)


@app.get("/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    return drafts.state(draft_or_404(draft_id))


@app.get("/drafts/{draft_id}/points")
def draft_points(draft_id: str) -> dict:
    return export_points(BuildingMap(drafts.building(draft_or_404(draft_id))))


@app.get("/drafts/{draft_id}/plan")
def draft_plan(draft_id: str) -> dict:
    return drafts.plan(draft_or_404(draft_id))


@app.post("/drafts/{draft_id}/ops")
def draft_ops(draft_id: str, body: DraftOps) -> dict:
    draft = draft_or_404(draft_id)
    try:
        drafts.apply(draft, body.ops)
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    return drafts.state(draft)


@app.post("/drafts/{draft_id}/undo")
def draft_undo(draft_id: str) -> dict:
    draft = draft_or_404(draft_id)
    try:
        drafts.undo(draft)
    except EditError as error:
        raise HTTPException(409, str(error)) from None
    return drafts.state(draft)


@app.post("/drafts/{draft_id}/save")
def draft_save(draft_id: str, body: SaveDraft) -> dict:
    draft = draft_or_404(draft_id)
    issues = drafts.issues(draft)
    return {"building": drafts.save(draft, body.name), "issues": issues}


@app.post("/v1/chat/completions", response_model=None)
def chat_completions(body: dict, x_session_id: str | None = Header(None)) -> dict | StreamingResponse:
    # The request's `tools` (ElevenLabs system tools) are ignored: UNVERIFIED, not handled yet.
    conversation = store.get_or_create(openai_compat.session_key(body, x_session_id) or DEFAULT_SESSION)
    text = openai_compat.last_user_text(body.get("messages") or [])
    model = str(body.get("model") or os.environ.get("GUIDE_MODEL", "building-guide"))

    def reply() -> str:
        if not text:
            return "Sorry, I didn't catch that."
        with conversation.lock:
            turn = conversation.guide.reply(text, channel="voice")  # spoken style for ElevenLabs
            try:
                store.save(conversation)
            except persistence.Conflict:  # mid-stream there is no status code left to send: say it instead
                return "Sorry, I lost track of that. Could you say it again?"
            return turn.spoken or turn.text

    if body.get("stream"):
        return StreamingResponse(openai_compat.stream(reply, model), media_type="text/event-stream")
    return openai_compat.completion(reply(), model)
