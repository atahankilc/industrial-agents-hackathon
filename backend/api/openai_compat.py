"""OpenAI-compatible `/v1/chat/completions` for an ElevenLabs Custom LLM (docs/research/elevenlabs.md).

Only the last user message is used: the Guide keeps its own history, so earlier OpenAI messages are ignored.
Streaming sends an early "... " chunk (ellipsis plus space) before the Guide runs, so speech keeps flowing
while tools execute, then the reply in sentence chunks, a finish chunk and `data: [DONE]`.

Not handled: request `tools` (ElevenLabs system tools such as end_call arrive there — UNVERIFIED, ignored).
How ElevenLabs passes our session id is UNVERIFIED; `session_key` accepts the plausible places."""

import json
import re
import time
import uuid
from collections.abc import Callable, Iterator

SENTENCE_END = re.compile(r"(?<=[.!?:])\s+")
THINKING = "... "


def message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
    return ""


def last_user_text(messages: list[dict]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return message_text(item.get("content")).strip()
    return ""


def session_key(body: dict, header: str | None) -> str | None:
    """First match wins: body session_id, elevenlabs_extra_body.session_id, X-Session-Id header, body user."""
    extra = body.get("elevenlabs_extra_body")
    candidates = [body.get("session_id"), extra.get("session_id") if isinstance(extra, dict) else None,
                  header, body.get("user")]
    return next((str(value) for value in candidates if value), None)


def completion(text: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion", "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def chunks(text: str) -> list[str]:
    parts = [part for part in SENTENCE_END.split(text.strip()) if part]
    return [part + " " for part in parts[:-1]] + parts[-1:]


def stream(reply: Callable[[], str], model: str) -> Iterator[str]:
    """SSE lines; `reply()` runs only after the thinking chunk has been yielded (and flushed)."""
    base = {"id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion.chunk", "created": int(time.time()),
            "model": model}

    def event(delta: dict, finish: str | None = None) -> str:
        payload = {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    yield event({"role": "assistant", "content": THINKING})
    try:
        text = reply()
    except Exception:  # the stream has started, so an HTTP error is no longer possible: say it instead
        text = "Sorry, something went wrong on my side. Please try again."
    for part in chunks(text):
        yield event({"content": part})
    yield event({}, "stop")
    yield "data: [DONE]\n\n"
