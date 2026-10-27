"""The OpenAI-compatible /v1/chat/completions for ElevenLabs' Custom LLM (backend/api/openai_compat.py): a voice
caller talks to the Guide as an anonymous viewer."""

import os

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from backend.api import deps, openai_compat, persistence
from backend.api.deps import viewer_or_401, with_access
from backend.api.sessions import DEFAULT_SESSION

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
def chat_completions(body: dict, x_session_id: str | None = Header(None)) -> dict | StreamingResponse:
    # The request's `tools` (ElevenLabs system tools) are ignored: UNVERIFIED, not handled yet.
    conversation = deps.store.get_or_create(openai_compat.session_key(body, x_session_id) or DEFAULT_SESSION)
    conversation = with_access(conversation, viewer_or_401(None))  # voice callers are anonymous viewers
    text = openai_compat.last_user_text(body.get("messages") or [])
    model = str(body.get("model") or os.environ.get("GUIDE_MODEL", "building-guide"))

    def reply() -> str:
        if not text:
            return "Sorry, I didn't catch that."
        with conversation.lock:
            turn = conversation.guide.reply(text, channel="voice")  # spoken style for ElevenLabs
            try:
                deps.store.save(conversation)
            except persistence.Conflict:  # mid-stream there is no status code left to send: say it instead
                return "Sorry, I lost track of that. Could you say it again?"
            return turn.spoken or turn.text

    if body.get("stream"):
        return StreamingResponse(openai_compat.stream(reply, model), media_type="text/event-stream")
    return openai_compat.completion(reply(), model)
