"""The Guide's voice: ElevenLabs speech for its replies (/tts, backend/api/tts.py) and a Scribe Realtime token for
the user's words (/stt/token, backend/api/stt.py)."""

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.speech import speakable
from backend.api import stt, tts
from backend.api.deps import conversation_or_404

router = APIRouter()


class SpeechRequest(BaseModel):
    text: str
    lang: str | None = None  # BCP 47 like "de-DE"; its first two letters keep the voice to that language


class SttTokenRequest(BaseModel):
    session_id: str | None = None  # keyterms come from this session's building


@router.post("/stt/token")
def speech_to_text_token(body: SttTokenRequest, authorization: str | None = Header(None)) -> dict:
    """A single-use ElevenLabs Scribe Realtime token (15 minutes, one connection) and the session building's keyterms
    (backend/api/stt.py) — from the building copy this viewer may see, so restricted names never reach the browser in
    access mode. 503 when Scribe is off, 502 when ElevenLabs refuses: the app then uses browser recognition."""
    if not stt.enabled():
        raise HTTPException(503, "Scribe speech recognition is not configured (ELEVENLABS_API_KEY, STT_MODE)")
    conversation = conversation_or_404(body.session_id, authorization) if body.session_id else None
    try:
        token = stt.single_use_token()
    except stt.SttError as error:
        raise HTTPException(502, f"ElevenLabs Scribe failed ({error})") from None
    return {"token": token, "keyterms": stt.keyterms(conversation.session.building) if conversation else []}


@router.post("/tts", response_model=None)
def text_to_speech(body: SpeechRequest) -> StreamingResponse:
    """One piece of a spoken reply as ElevenLabs MP3 (backend/api/tts.py). 503 without a key, 502 when ElevenLabs
    refuses: the app then speaks with the browser's own voice."""
    if not tts.enabled():
        raise HTTPException(503, "the ElevenLabs voice is not configured (ELEVENLABS_API_KEY)")
    text = speakable(body.text)  # the voice replies' safety net: no markup, ids or symbols read out
    if not text:
        raise HTTPException(422, "nothing to say")
    if len(text) > tts.MAX_CHARS:
        raise HTTPException(413, f"text is too long to speak at once (max {tts.MAX_CHARS} characters)")
    try:
        audio = tts.open_stream(text, body.lang)
    except tts.TtsError as error:
        raise HTTPException(502, f"ElevenLabs voice failed ({error})") from None
    return StreamingResponse(audio, media_type="audio/mpeg", headers={"cache-control": "no-store"})
