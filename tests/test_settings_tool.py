"""The Guide can open the app's Building settings (backend/agents/tools/ open_building_settings → a `settings` UI event)."""

from pathlib import Path

from backend.agents.guide import Guide
from backend.agents.offline_llm import EDIT, SETTINGS, OfflineClient
from backend.agents.tools import TOOL_DEFINITIONS, BuildingSession

BUILDING = Path(__file__).resolve().parents[1] / "data" / "buildings" / "proc-campus-train-000"


def test_tool_emits_settings_event_and_changes_nothing():
    session = BuildingSession.load(BUILDING)
    spaces = dict(session.building.spaces)
    assert session.call("open_building_settings", {})["opened"]
    assert session.events == [{"type": "settings"}]
    assert session.building.spaces.keys() == spaces.keys()


def test_tool_is_offered():
    assert any(tool["name"] == "open_building_settings" for tool in TOOL_DEFINITIONS)


def test_offline_intent():
    assert SETTINGS.search("open the building settings")
    assert SETTINGS.search("who can enter the lab?")
    assert not SETTINGS.search("where is the toilet")
    assert not EDIT.search("open the building settings")


def test_offline_guide_opens_settings():
    session = BuildingSession.load(BUILDING)
    reply = Guide(session, client=OfflineClient()).reply("Open the building settings")
    assert {"type": "settings"} in reply.events
    assert "Building settings" in reply.text
