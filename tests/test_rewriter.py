"""Voice transcript rewriter (D-013): normalises names and numbers to the building's vocabulary before the Guide
sees a voice turn; the original transcript is passed along; any doubt falls back to the transcript as heard."""

import json
from pathlib import Path

import anthropic
import httpx2
import pytest

from backend.agents.guide import Guide
from backend.agents.offline_llm import message, text_block
from backend.agents.rewriter import TranscriptRewriter, invented_numbers
from backend.agents.tools import BuildingSession
from tests.test_guide import ScriptedClient, say

BUILDING = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"


class FakeRewriteClient:
    """Answers every rewrite request with a fixed JSON reply (or raises), and records the requests."""

    def __init__(self, rewritten: str | None = None, error: Exception | None = None) -> None:
        self.rewritten, self.error = rewritten, error
        self.requests: list[dict] = []
        self.messages = self

    def create(self, **request: object) -> object:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return message(text_block(json.dumps({"rewritten": self.rewritten})))


@pytest.fixture
def session() -> BuildingSession:
    return BuildingSession.load(BUILDING)


def rewriter_for(session: BuildingSession, client: FakeRewriteClient) -> TranscriptRewriter:
    return TranscriptRewriter(session.building, client=client)


def test_rewrite_normalises_to_the_vocabulary(session):
    client = FakeRewriteClient("How do I get to Lab 2.17?")
    rewriter = rewriter_for(session, client)
    assert rewriter.rewrite("how do I get to lab two seventeen") == "How do I get to Lab 2.17?"
    request = client.requests[0]
    assert request["model"] == "claude-haiku-5-5"
    assert "Lab 2.17" in json.dumps(request["system"])  # the building's names are the vocabulary
    assert request["messages"][-1]["content"].endswith("how do I get to lab two seventeen")


def test_a_number_neither_heard_nor_in_the_building_rejects_the_rewrite(session):
    rewriter = rewriter_for(session, FakeRewriteClient("How do I get to Lab 9.99?"))
    assert rewriter.rewrite("how do I get to lab nine") == "how do I get to lab nine"


def test_api_errors_and_empty_answers_fall_back_to_the_transcript(session):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    failing = FakeRewriteClient(error=anthropic.APIConnectionError(request=request))
    assert rewriter_for(session, failing).rewrite("lab two seventeen") == "lab two seventeen"
    assert rewriter_for(session, FakeRewriteClient("  ")).rewrite("lab two seventeen") == "lab two seventeen"


def test_invented_numbers_allows_heard_and_building_numbers(session):
    vocabulary = "Lab 2.17; Office 0.02"
    assert invented_numbers("Lab 2.17 and Office 0.02", "lab two seventeen", vocabulary) == []
    assert invented_numbers("take 3 steps", "take 3 steps", vocabulary) == []
    assert invented_numbers("Lab 9.99", "lab nine", vocabulary) == ["9.99"]


def test_voice_turn_shows_the_guide_both_transcripts(session):
    guide = Guide(session, client=ScriptedClient([say("Lab 2.17 is on Floor 2.")]))
    guide.rewriter = rewriter_for(session, FakeRewriteClient("Where is Lab 2.17?"))
    turn = guide.reply("where is lab two seventeen", channel="voice")
    sent = guide.messages[0]["content"]
    assert "Where is Lab 2.17?" in sent and "where is lab two seventeen" in sent
    assert turn.rewritten == "Where is Lab 2.17?"
    assert "Where is Lab 2.17?" in guide.corpus and "where is lab two seventeen" in guide.corpus


def test_text_turns_and_unchanged_transcripts_are_left_alone(session):
    rewrite_client = FakeRewriteClient("Where is Lab 2.17?")
    guide = Guide(session, client=ScriptedClient([say("Which lab do you mean?"), say("It is on Floor 2.")]))
    guide.rewriter = rewriter_for(session, rewrite_client)
    typed = guide.reply("where is lab two seventeen")
    assert typed.rewritten is None and not rewrite_client.requests  # typed chat has no rewriter
    rewrite_client.rewritten = "Where is Lab 2.17?"
    same = guide.reply("Where is Lab 2.17?", channel="voice")
    assert same.rewritten is None and "as heard" not in json.dumps(guide.messages[-2]["content"])


def test_tapped_voice_turn_is_spoken_but_not_rewritten(session):
    rewrite_client = FakeRewriteClient("Where is Lab 2.17?")
    guide = Guide(session, client=ScriptedClient([say("Lab 2.17 is on Floor 2.")]))
    guide.rewriter = rewriter_for(session, rewrite_client)
    turn = guide.reply("How do I get to Lab 2.17?", channel="voice", heard=False)  # the room card's Directions
    assert turn.rewritten is None and not rewrite_client.requests
    assert turn.spoken


def test_offline_guide_has_no_rewriter(session, monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    assert Guide(session).rewriter is None
