"""Buildings next to each other (backend/agents/campus.py), the "you are here" figure (BuildingSession.user_location) and
the clearer highlights (items as well as rooms), through the tools and the HTTP backend in offline mode."""

import pytest
from fastapi.testclient import TestClient

from backend.agents.campus import Campus, arrive, distance_m, heading
from backend.agents.tools import BuildingSession
from backend.api.app import app
from backend.api.sessions import load_catalogue
from backend.core.building_map import MapError

HAUPT = "train/osm-way10053349"  # Hauptgebäude, Arcisstraße 21: TUM's main campus, several modelled neighbours
MENSA = "train/osm-way19183732"  # Mensa Arcisstraße, a canteen in it
LONELY = "train/proc-campus-train-000"  # procedural: no real position, no neighbours


@pytest.fixture(scope="module")
def catalogue() -> dict:
    return load_catalogue()


@pytest.fixture
def haupt(catalogue) -> BuildingSession:
    session = BuildingSession.load(catalogue[HAUPT]["path"])
    session.campus = Campus(HAUPT, catalogue)
    return session


def test_distance_and_heading():
    assert round(distance_m((11.0, 48.0), (11.0, 48.001))) == 111
    assert heading((11.0, 48.0), (11.0, 48.001)) == "north"
    assert heading((11.0, 48.0), (10.999, 48.0)) == "west"


def test_neighbours_nearest_first_and_only_located_buildings(catalogue, haupt):
    nearby = haupt.campus.neighbours()
    assert MENSA in [item["building_id"] for item in nearby]
    assert [item["distance_m"] for item in nearby] == sorted(item["distance_m"] for item in nearby)
    assert Campus(LONELY, catalogue).neighbours() == []
    lonely = BuildingSession.load(catalogue[LONELY]["path"])
    lonely.campus = Campus(LONELY, catalogue)
    assert "search_nearby_buildings" not in [tool["name"] for tool in lonely.tool_definitions()]
    assert "search_nearby_buildings" in [tool["name"] for tool in haupt.tool_definitions()]


def test_search_nearby_finds_rooms_and_the_building_by_name(haupt):
    canteens = haupt.call("search_nearby_buildings", {"query": "canteen"})
    assert MENSA in [item["building_id"] for item in canteens["buildings"]]
    by_name = haupt.call("search_nearby_buildings", {"query": "the Mensa"})
    assert by_name["buildings"][0]["building_id"] == MENSA and by_name["buildings"][0]["building_match"]
    assert haupt.events[-1]["type"] == "elsewhere" and haupt.events[-1]["buildings"][0]["building"] == MENSA


def test_a_miss_here_hints_at_the_neighbours(haupt):
    assert "search_nearby_buildings" in haupt.call("search", {"query": "zzzz-nothing"})["hint"]


def test_route_to_building_three_parts_and_a_continue_event(haupt):
    start = haupt.main_entrance_space()
    result = haupt.call("route_to_building", {"start": start, "building": "Mensa Arcisstraße", "destination": "canteen"})
    assert result["reachable"] and result["to_building"] == "Mensa Arcisstraße"
    assert result["outside"]["about_m"] > 0 and result["inside_here"]["steps"] and result["inside_there"]["steps"]
    event = haupt.events[-1]
    assert event["type"] == "route" and event["space_path"][-1] == "outside"
    follow = event["next_building"]
    assert follow["building"] == MENSA and follow["destination"] == result["destination"]["id"]
    assert len(follow["from"]) == 2 and len(follow["to"]) == 2


def test_route_to_the_building_itself_and_unknown_buildings(haupt):
    start = haupt.main_entrance_space()
    result = haupt.call("route_to_building", {"start": start, "building": MENSA, "destination": "entrance"})
    assert result["reachable"] and result["inside_there"]["about_m"] >= 1
    assert "No single nearby building" in haupt.call("route_to_building", {
        "start": start, "building": LONELY, "destination": "x"})["error"]
    assert "No single nearby building" in haupt.call("route_to_building", {
        "start": start, "building": "Elbphilharmonie", "destination": "x"})["error"]


def test_arrive_places_the_user_at_the_entrance_and_routes_on(catalogue, haupt):
    haupt.call("route_to_building", {"start": haupt.main_entrance_space(), "building": MENSA, "destination": "canteen"})
    follow = haupt.events[-1]["next_building"]
    mensa = BuildingSession.load(catalogue[MENSA]["path"])
    route = arrive(mensa, follow["entrance"], follow["destination"])
    assert route["reachable"] and route["space_path"][0] == "outside"
    assert mensa.user_location["space_id"] == follow["entrance_space"]
    assert mensa.events[-1]["type"] == "route"
    with pytest.raises(MapError):
        arrive(mensa, "no-such-door", follow["destination"])


def test_here_means_the_figure(catalogue):
    session = BuildingSession.load(catalogue[LONELY]["path"])
    assert "not known" in session.call("find_route", {"start": "here", "destination": "outside"})["error"]
    lobby = session.resolve("Main lobby")
    session.set_location(lobby)
    route = session.call("find_route", {"start": "here", "destination": "Meeting room 3.07"})
    assert route["reachable"] and route["space_path"][0] == lobby


def test_highlights_carry_items_and_their_rooms(catalogue):
    session = BuildingSession.load(catalogue[LONELY]["path"])
    asset = next(iter(session.building.assets.values()))
    session.call("show_on_map", {"space_ids": [asset["name"]]})
    event = session.events[-1]
    if asset["id"] in event["asset_ids"]:  # the name is unique in this building
        assert asset["space_id"] in event["space_ids"]
    session.call("locate", {"query": asset["type"]})
    assert session.events[-1]["asset_ids"] and session.events[-1]["type"] == "highlight"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("GUIDE_LLM", "offline")
    return TestClient(app)


def test_location_endpoint_and_arrive_endpoint(client, catalogue):
    first = client.post("/sessions", json={"building": HAUPT}).json()["session_id"]
    entrance = BuildingSession.load(catalogue[HAUPT]["path"]).main_entrance_space()
    assert client.put(f"/sessions/{first}/location", json={"space_id": "nope"}).status_code == 422
    placed = client.put(f"/sessions/{first}/location", json={"space_id": entrance}).json()["location"]
    assert placed["space_id"] == entrance
    tool = client.post(f"/dev/sessions/{first}/tool", json={"name": "route_to_building", "arguments": {
        "start": "here", "building": MENSA, "destination": "canteen"}}).json()
    follow = tool["events"][-1]["next_building"]
    assert tool["events"][-1]["line"]  # enriched like any route: drawn on the plan
    second = client.post("/sessions", json={"building": MENSA}).json()["session_id"]
    arrived = client.post(f"/sessions/{second}/arrive", json={
        "entrance": follow["entrance"], "destination": follow["destination"], "from_session": first}).json()
    assert arrived["route"]["reachable"] and arrived["location"]["space_id"] == follow["entrance_space"]
    assert arrived["events"][-1]["type"] == "route" and arrived["events"][-1]["steps"]
    assert client.put(f"/sessions/{first}/location", json={"space_id": None}).json()["location"] is None


def test_the_guide_opens_a_nearby_building_itself(catalogue, haupt):
    assert "open_nearby_building" in [tool["name"] for tool in haupt.tool_definitions()]
    result = haupt.call("open_nearby_building", {"building": "Mensa Arcisstraße"})
    assert result["opened"] and haupt.events[-1] == {"type": "open_building", "building": MENSA,
                                                     "name": result["building"]}
    assert "No single nearby building" in haupt.call("open_nearby_building", {"building": "zzzz"})["error"]
    lonely = BuildingSession.load(catalogue[LONELY]["path"])
    lonely.campus = Campus(LONELY, catalogue)
    assert "open_nearby_building" not in [tool["name"] for tool in lonely.tool_definitions()]
