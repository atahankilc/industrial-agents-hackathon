"""ElevenLabs text-to-speech for the Guide's voice (POST /tts in backend/api/app.py).

The browser asks for one piece of a spoken reply at a time and plays the MP3 (frontend/src/voice/tts.ts); without
ELEVENLABS_API_KEY, or when a request fails, it falls back to the browser's own voice. The key never leaves the
backend. TTS_MODEL and TTS_VOICE_ID override the defaults: Flash v2.5 (lowest latency, 32 languages) and the premade
voice "River" (calm, neutral, conversational) — docs/research/elevenlabs.md#3-text-to-speech."""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator

API = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE = "SAz9YHcvj6GT2YYXdXww"  # "River", premade (GET /v1/voices on the team account, 2026-10-25)
DEFAULT_MODEL = "eleven_flash_v2_5"
OUTPUT_FORMAT = "mp3_44100_128"
MAX_CHARS = 1000  # one piece of a reply; the app sends sentence groups well below this
TIMEOUT_S = 15
BLOCK = 16 * 1024


class TtsError(Exception):
    """ElevenLabs refused or could not be reached; `status` is its HTTP status (None: network)."""

    def __init__(self, status: int | None, detail: str):
        super().__init__(f"{status or 'network'}: {detail}")
        self.status = status


def enabled() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def upstream_request(text: str, lang: str | None) -> urllib.request.Request:
    voice = os.environ.get("TTS_VOICE_ID") or DEFAULT_VOICE
    body = {"text": text, "model_id": os.environ.get("TTS_MODEL") or DEFAULT_MODEL}
    language = (lang or "")[:2].lower()
    if language.isalpha() and len(language) == 2:  # "de-DE" → "de": Flash v2.5 then keeps to that language
        body["language_code"] = language
    return urllib.request.Request(
        f"{API}/{voice}/stream?output_format={OUTPUT_FORMAT}",
        data=json.dumps(body).encode(),
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "content-type": "application/json",
                 "accept": "audio/mpeg"},
        method="POST",
    )


def open_stream(text: str, lang: str | None = None) -> Iterator[bytes]:
    """Starts the request now, so a refusal surfaces before our response has begun; then yields MP3 bytes."""
    try:
        response = urllib.request.urlopen(upstream_request(text, lang), timeout=TIMEOUT_S)
    except urllib.error.HTTPError as error:
        raise TtsError(error.code, error.read().decode(errors="replace")[:200]) from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise TtsError(None, str(getattr(error, "reason", error))) from None

    def blocks() -> Iterator[bytes]:
        with response:
            while block := response.read1(BLOCK):
                yield block

    return blocks()
