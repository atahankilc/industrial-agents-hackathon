"""Claude API failures reach the user as a short, readable sentence (backend/service_errors.py), not as a raw
`BadRequestError: Error code: 400 - {...}`: in the Guide and Builder streams, and as a status code on plain requests."""

import json

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from agent.builder import Builder
from backend import app as backend_app
from backend.drafts import DraftStore
from backend.service_errors import friendly

BUILDING = "train/proc-campus-train-000"
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
CREDIT = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to "
          "access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."}}


def status_error(cls, status: int, body: dict | None = None) -> anthropic.APIStatusError:
    return cls(f"Error code: {status} - {body}", response=httpx2.Response(status, request=REQUEST, json=body), body=body)


@pytest.mark.parametrize(("error", "code"), [
    (status_error(anthropic.BadRequestError, 400, CREDIT), "credits"),
    (status_error(anthropic.AuthenticationError, 401, {"error": {"message": "invalid x-api-key"}}), "auth"),
    (status_error(anthropic.PermissionDeniedError, 403, {"error": {"message": "not allowed"}}), "auth"),
    (status_error(anthropic.RateLimitError, 429, {"error": {"message": "rate limited"}}), "busy"),
    (status_error(anthropic.APIStatusError, 529, {"error": {"type": "overloaded_error"}}), "unavailable"),
    (status_error(anthropic.InternalServerError, 500, {"error": {"message": "oops"}}), "unavailable"),
    (anthropic.APIConnectionError(request=REQUEST), "offline"),
    (anthropic.APITimeoutError(request=REQUEST), "offline"),
    (status_error(anthropic.BadRequestError, 400, {"error": {"message": "messages: field required"}}), "internal"),
    (RuntimeError("index out of range"), "internal"),
])
def test_each_failure_gets_a_code_and_a_sentence_without_the_raw_error(error: Exception, code: str) -> None:
    result = friendly(error)
    assert result["code"] == code
    assert result["message"].endswith(".") and "Error code" not in result["message"] and "{" not in result["message"]


@pytest.fixture
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    catalogue = dict(backend_app.store.catalogue)
    monkeypatch.setattr(backend_app.store, "catalogue", catalogue)
    monkeypatch.setattr(backend_app, "drafts", DraftStore(tmp_path, catalogue))
    return TestClient(backend_app.app)


def out_of_credit(*_, **__):
    raise status_error(anthropic.BadRequestError, 400, CREDIT)


def session_with_failing_guide(client: TestClient, monkeypatch) -> str:
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    monkeypatch.setattr(backend_app.store.get(session_id).guide, "reply", out_of_credit)
    return session_id


def test_guide_stream_reports_a_readable_error(client: TestClient, monkeypatch) -> None:
    session_id = session_with_failing_guide(client, monkeypatch)
    lines = [json.loads(line) for line in
             client.post("/chat/stream", json={"session_id": session_id, "message": "hi"}).text.splitlines() if line]
    assert lines[-1]["type"] == "error" and lines[-1]["code"] == "credits"
    assert "credit" in lines[-1]["message"] and "Error code" not in lines[-1]["message"]


def test_plain_chat_answers_503_with_the_sentence(client: TestClient, monkeypatch) -> None:
    session_id = session_with_failing_guide(client, monkeypatch)
    response = client.post("/chat", json={"session_id": session_id, "message": "hi"})
    assert response.status_code == 503
    assert response.json()["code"] == "credits" and "credit" in response.json()["detail"]


def test_builder_stream_reports_a_readable_error(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(Builder, "reply", out_of_credit)
    draft_id = client.post("/drafts", json={"base": BUILDING}).json()["draft"]["id"]
    lines = [json.loads(line) for line in
             client.post(f"/drafts/{draft_id}/chat/stream", json={"message": "hi"}).text.splitlines() if line]
    assert lines[-1]["type"] == "error" and lines[-1]["code"] == "credits" and "credit" in lines[-1]["message"]
