"""POST /stt/token and keyterms: Scribe Realtime for the user's words (backend/api/stt.py), ElevenLabs faked."""

import io
import json
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agents.tools import BuildingSession
from backend.api import stt
from backend.api.app import app

client = TestClient(app)
FACTORY = Path("data/buildings/proc-factory-dev-003")


@pytest.fixture
def scribe(monkeypatch):
    """ElevenLabs answers the token request; the requests it got are recorded."""
    sent = []

    def urlopen(request, timeout):
        sent.append(request)
        return io.BytesIO(json.dumps({"token": "sutkn_test"}).encode())

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.delenv("STT_MODE", raising=False)
    monkeypatch.setattr(stt.urllib.request, "urlopen", urlopen)
    return sent


def test_health_reports_scribe_and_stt_mode_browser_turns_it_off(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.delenv("STT_MODE", raising=False)
    assert client.get("/health").json()["stt"] is True
    monkeypatch.setenv("STT_MODE", "browser")
    assert client.get("/health").json()["stt"] is False
    assert client.post("/stt/token", json={}).status_code == 503
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    monkeypatch.delenv("STT_MODE")
    assert client.get("/health").json()["stt"] is False


def test_token_with_the_session_buildings_keyterms(scribe):
    session_id = client.post("/sessions", json={"building": "proc-factory-dev-003"}).json()["session_id"]
    body = client.post("/stt/token", json={"session_id": session_id}).json()
    assert body["token"] == "sutkn_test"
    assert "CNC mill" in body["keyterms"] and len(body["keyterms"]) == stt.MAX_KEYTERMS
    (request,) = scribe
    assert request.full_url == stt.TOKEN_URL and request.get_method() == "POST"
    assert request.get_header("Xi-api-key") == "test-key"
    assert client.post("/stt/token", json={}).json()["keyterms"] == []  # no session: no keyterms
    assert client.post("/stt/token", json={"session_id": "nope"}).status_code == 404


def test_a_refused_token_is_a_502(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"bad key"}'))

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.delenv("STT_MODE", raising=False)
    monkeypatch.setattr(stt.urllib.request, "urlopen", urlopen)
    response = client.post("/stt/token", json={})
    assert response.status_code == 502 and "401" in response.json()["detail"]


def test_keyterms_fit_the_api_limits_and_put_places_first():
    terms = stt.keyterms(BuildingSession.load(FACTORY).building)
    assert len(terms) <= stt.MAX_KEYTERMS and all(0 < len(term) <= stt.KEYTERM_CHARS for term in terms)
    assert not any(char.isdigit() for term in terms for char in term)  # numbers are dropped from names
    assert len({term.lower() for term in terms}) == len(terms)
    assert terms.index("Meeting room") < terms.index("Chair")  # rooms people ask for before furniture
    assert {"Staircase", "Lift", "CNC mill"} <= set(terms)
