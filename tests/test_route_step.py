"""The step card and the Guide stay in step: the app sends the card's step (`route_step` → a route note with the
card's numbering), and the Guide moves the card when it talks about another step (show_route_step → `route_step`)."""

from pathlib import Path

import pytest

from agent.guide import Guide
from agent.tools import BuildingSession
from tests.test_guide import ScriptedClient, say

DATA = Path(__file__).resolve().parent.parent / "data" / "train" / "proc-campus-train-000"


@pytest.fixture
def session() -> BuildingSession:
    return BuildingSession.load(DATA)


def routed(session: BuildingSession) -> list[dict]:
    assert session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})["reachable"]
    steps = session.route_card()
    assert len(steps) >= 2
    return steps


def test_show_route_step_moves_the_card(session):
    assert session.call("show_route_step", {"step": 1}).get("error")  # no route on the map yet
    steps = routed(session)
    result = session.call("show_route_step", {"step": 2})
    assert result == {"shown": 2, "of": len(steps), "text": steps[1]["text"]}
    assert session.events[-1] == {"type": "route_step", "index": 1}
    assert session.call("show_route_step", {"step": len(steps) + 1}).get("error")


def test_route_note_tells_the_guide_the_cards_step(session):
    steps = routed(session)
    guide = Guide(session, client=ScriptedClient([say("Go on."), say("Fine.")]))
    guide.reply("What now?", route_step=1)
    sent = guide.messages[0]["content"]
    assert "[route note" in sent and f"step 2 of {len(steps)}" in sent and steps[1]["text"] in sent
    guide.reply("And then?", route_step=99)  # out of range: no note
    assert "[route note" not in guide.messages[-2]["content"]
