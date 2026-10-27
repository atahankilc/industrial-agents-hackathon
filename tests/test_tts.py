"""POST /tts: ElevenLabs audio for the Guide's voice (backend/api/tts.py), with ElevenLabs faked — no network, no cost."""

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from backend.api import tts
from backend.api.app import app

client = TestClient(app)


class FakeAudio(io.BytesIO):
    def read1(self, size: int = -1) -> bytes:
        return super().read1(size)


@pytest.fixture
def upstream(monkeypatch):
    """Captures the ElevenLabs request and answers with fake MP3 bytes."""
    sent = []

    def urlopen(request, timeout):
        sent.append(request)
        return FakeAudio(b"ID3fake-mp3" * 4000)

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.delenv("TTS_VOICE_ID", raising=False)
    monkeypatch.delenv("TTS_MODEL", raising=False)
    monkeypatch.setattr(tts.urllib.request, "urlopen", urlopen)
    return sent


def test_health_reports_whether_the_voice_is_configured(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert client.get("/health").json()["tts"] is False
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    assert client.get("/health").json()["tts"] is True


def test_without_a_key_the_app_is_told_to_use_the_browser_voice(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert client.post("/tts", json={"text": "Hello."}).status_code == 503


def test_streams_mp3_from_flash_with_the_default_voice_and_language(upstream):
    response = client.post("/tts", json={"text": "Take **Lift 1** → Floor 3, about 12 m.", "lang": "de-DE"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3fake-mp3" * 4000
    (request,) = upstream
    assert request.full_url == f"{tts.API}/{tts.DEFAULT_VOICE}/stream?output_format={tts.OUTPUT_FORMAT}"
    assert request.get_header("Xi-api-key") == "test-key"
    body = json.loads(request.data)
    # the text is made speakable first (backend/agents/speech.py): no markdown or arrows read out
    assert body == {"text": "Take Lift 1 to Floor 3, about 12 metres.", "model_id": "eleven_flash_v2_5",
                    "language_code": "de"}


def test_voice_and_model_come_from_the_environment(upstream, monkeypatch):
    monkeypatch.setenv("TTS_VOICE_ID", "voice123")
    monkeypatch.setenv("TTS_MODEL", "eleven_v3")
    assert client.post("/tts", json={"text": "Hi."}).status_code == 200
    (request,) = upstream
    assert "/voice123/stream" in request.full_url
    assert json.loads(request.data) == {"text": "Hi.", "model_id": "eleven_v3"}  # no lang: no language_code


@pytest.mark.parametrize("text, status", [("", 422), ("**  **", 422), ("word " * 300, 413)])
def test_rejects_empty_and_overlong_text(upstream, text, status):
    assert client.post("/tts", json={"text": text}).status_code == status
    assert upstream == []


def test_an_elevenlabs_refusal_is_a_502(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"quota"}'))

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(tts.urllib.request, "urlopen", urlopen)
    response = client.post("/tts", json={"text": "Hello."})
    assert response.status_code == 502
    assert "401" in response.json()["detail"]


def test_an_unreachable_elevenlabs_is_a_502(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(tts.urllib.request, "urlopen", urlopen)
    response = client.post("/tts", json={"text": "Hello."})
    assert response.status_code == 502
    assert "network" in response.json()["detail"]
