"""FastAPI app: the Building Guide over HTTP.

  GUIDE_LLM=offline uv run uvicorn backend.app:app --port 8765

Endpoints: /health, /buildings, /sessions (create, inspect, switch building), /sessions/{id}/points (point-cloud
export of the session's current building, gzipped), /chat, /events (polling cursor for the map UI; route events
carry `vertices`, change events `space_ids`) and the OpenAI-compatible /v1/chat/completions for ElevenLabs
(backend/openai_compat.py).
Guide turns are blocking (tool loop + LLM calls), so those endpoints are plain `def` and run in FastAPI's
threadpool; each conversation's lock serialises its turns."""

import os

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.guide import llm_mode
from backend import openai_compat
from backend.sessions import DEFAULT_SESSION, Conversation, SessionStore, UnknownBuilding, summary

app = FastAPI(title="Talk to Your Building")
# Local dev only: restrict allow_origins to the deployed frontend before deploying.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)  # the point-cloud export is ~4 MB of JSON
store = SessionStore()


class NewSession(BaseModel):
    building: str | None = None


class SwitchBuilding(BaseModel):
    building: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


def conversation_or_404(session_id: str) -> Conversation:
    conversation = store.get(session_id)
    if conversation is None:
        raise HTTPException(404, f"unknown session {session_id!r}")
    return conversation


def turn_payload(conversation: Conversation, turn: object) -> dict:
    # turn.events is the tail of session.events, so its first index is len(log) - len(turn.events).
    first_index = len(conversation.session.events) - len(turn.events)
    return {
        "reply": turn.text,
        "tool_calls": [{"name": call["name"], "input": call["input"]} for call in turn.tool_calls],
        "events": conversation.view.enrich(conversation.session, turn.events, first_index),
        "ungrounded": turn.ungrounded,
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
    return {**summary(conversation), "overview": conversation.session.building.overview()}


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    conversation = conversation_or_404(body.session_id)
    with conversation.lock:
        return turn_payload(conversation, conversation.guide.reply(body.message))


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
            return conversation.guide.reply(text).text

    if body.get("stream"):
        return StreamingResponse(openai_compat.stream(reply, model), media_type="text/event-stream")
    return openai_compat.completion(reply(), model)
