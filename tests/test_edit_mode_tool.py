"""The Guide can switch the app to the Edit mode (backend/agents/tools.py open_edit_mode → an `edit_mode` UI event)."""

from pathlib import Path

from backend.agents.guide import Guide
from backend.agents.offline_llm import EDIT, OfflineClient
from backend.agents.tools import TOOL_DEFINITIONS, BuildingSession

BUILDING = Path(__file__).resolve().parents[1] / "data" / "train" / "proc-campus-train-000"


def test_tool_emits_edit_mode_event_and_changes_nothing():
    session = BuildingSession.load(BUILDING)
    spaces = dict(session.building.spaces)
    result = session.call("open_edit_mode", {"request": "  Rename 0.03 to Quiet room "})
    assert result["opened"] and result["request"] == "Rename 0.03 to Quiet room"
    assert session.events == [{"type": "edit_mode", "request": "Rename 0.03 to Quiet room"}]
    assert session.building.spaces.keys() == spaces.keys()
    session.events.clear()
    assert session.call("open_edit_mode", {})["request"] is None
    assert session.events == [{"type": "edit_mode", "request": None}]


def test_tool_is_offered():
    assert any(tool["name"] == "open_edit_mode" for tool in TOOL_DEFINITIONS)


def test_offline_intent():
    assert EDIT.search("I want to edit this building")
    assert EDIT.search("Rename 0.03 to Quiet room")
    assert not EDIT.search("where is the toilet")
    assert not EDIT.search("the lift is broken")
    assert not EDIT.search("add a door between 0.02 and 0.03")  # a routing change: propose_change


def test_offline_guide_switches_to_edit_mode():
    session = BuildingSession.load(BUILDING)
    guide = Guide(session, client=OfflineClient())
    reply = guide.reply("Please rename 0.03 to Quiet room")
    assert {"type": "edit_mode", "request": "Please rename 0.03 to Quiet room"} in reply.events
    assert "Edit mode" in reply.text
