"""Live obstacles on routes (backend/core/live.py): a pallet in the campus ground-floor corridor (Corridor 0.01, 51.8 m × 2.4 m,
x from 0 to -51.8, y from -6.0 to -8.4; Main lobby door at x ≈ -1.7)."""

import math
from pathlib import Path

import pytest

from backend.core import navigation
from backend.core.building_map import BuildingMap
from backend.core.live import WALKER_CLEARANCE_M, Hazard, LiveEffects, Obstacle

ROOT = Path(__file__).resolve().parent.parent
CAMPUS = ROOT / "data" / "train" / "proc-campus-train-000"
LOBBY, FAR, NEAR = "Main lobby", "Office 0.10", "Canteen 0.20"  # Office 0.10 at x ≈ -44.9, Canteen at x ≈ -24.8


@pytest.fixture(scope="module")
def campus() -> BuildingMap:
    return BuildingMap.load(CAMPUS)


def pallets(across_m: float, moving: bool = False, x: float = -28.0) -> Obstacle:
    """Pallets standing in the middle of the corridor at x, `across_m` wide across it."""
    return Obstacle(id="p1", name="Pallets", kind="pallet", floor_id="proc-campus-train-000-F0", x=x, y=-7.2,
                    length_m=1.2, width_m=across_m, heading_deg=0.0, moving=moving,
                    state="moving" if moving else "left behind")


def route(building: BuildingMap, start: str, end: str, live: LiveEffects | None = None, **kwargs) -> dict:
    return navigation.find_route(building, start, end, include_steps=False, live=live, **kwargs).to_dict()


def test_no_live_state_changes_nothing(campus):
    plain = route(campus, LOBBY, FAR)
    assert route(campus, LOBBY, FAR, LiveEffects(campus, [])) == plain
    assert "live" not in plain


def test_a_blocked_corridor_sends_the_route_round(campus):
    plain = route(campus, LOBBY, FAR)
    live = LiveEffects(campus, [pallets(1.6)])  # 0.4 m free on each side: not enough to walk past
    detour = route(campus, LOBBY, FAR, live)
    assert detour["reachable"] and detour["length_m"] > plain["length_m"]
    assert detour["space_path"] != plain["space_path"]
    assert detour["live"]["avoided"][0]["id"] == "p1"
    assert detour["live"]["detour_m"] == pytest.approx(detour["length_m"] - plain["length_m"], abs=0.01)
    assert detour["live"]["without_live_m"] == plain["length_m"]


def test_a_room_before_the_blockage_is_entered_as_usual(campus):
    live = LiveEffects(campus, [pallets(1.6)])
    assert route(campus, LOBBY, NEAR, live) == route(campus, LOBBY, NEAR)


def test_a_room_just_past_the_blockage_on_its_near_side_is_reachable(campus):
    # pallets right beside the canteen door (x ≈ -24.8), on the far side of it: the canteen is still entered as usual
    live = LiveEffects(campus, [pallets(1.6, x=-26.5)])
    assert route(campus, LOBBY, NEAR, live) == route(campus, LOBBY, NEAR)


def test_a_narrow_gap_lets_a_walker_squeeze_past_but_not_a_wheelchair(campus):
    item = pallets(0.8)  # 0.8 m free on each side
    walker = route(campus, LOBBY, FAR, LiveEffects(campus, [item], clearance_m=WALKER_CLEARANCE_M))
    plain = route(campus, LOBBY, FAR)
    assert walker["space_path"] == plain["space_path"] and walker["length_m"] == plain["length_m"]
    assert walker["live"]["passing"][0]["effect"] == "squeeze"
    wheelchair = route(campus, LOBBY, FAR, LiveEffects(campus, [item], clearance_m=0.9), step_free=True)
    assert wheelchair["space_path"] != plain["space_path"]  # round by the lifts
    assert wheelchair["live"]["avoided"][0]["id"] == "p1"


def test_a_moving_object_costs_a_wait_not_a_detour(campus):
    plain = route(campus, LOBBY, FAR)
    moving = route(campus, LOBBY, FAR, LiveEffects(campus, [pallets(1.6, moving=True)]))
    # the wait (10 m) is cheaper than the way round, so the route stays and says it may wait
    assert moving["space_path"] == plain["space_path"]
    assert moving["live"]["passing"][0]["effect"] == "wait"


def test_with_no_way_round_the_reason_names_the_blocker(campus):
    corridor = "proc-campus-train-000-F0-S001"
    others = [c["id"] for c in campus.connectors.values()]  # no stairs, no lifts: the corridor is the only way
    answer = route(campus, LOBBY, FAR, LiveEffects(campus, [pallets(1.6)]), closed=others)
    assert not answer["reachable"]
    assert "Pallets" in answer["reason"] and answer["live"]["blocked_by"][0]["id"] == "p1"
    assert corridor in campus.spaces


def test_a_wet_floor_is_avoided_when_it_is_cheap(campus):
    wet = Hazard(id="w1", name="Wet floor", kind="wet_floor", floor_id="proc-campus-train-000-F0",
                 polygon=((-30.0, -6.0), (-26.0, -6.0), (-26.0, -8.4), (-30.0, -8.4)))
    answer = route(campus, LOBBY, FAR, LiveEffects(campus, [], [wet]))
    assert answer["reachable"]
    assert answer["live"]["passing"][0]["effect"] == "wet_floor"  # no way round worth 6 m here


# ---------- backend: the live world, its endpoints and the route on the map (backend/api/live.py) ----------

from fastapi.testclient import TestClient  # noqa: E402

from backend.api.app import app

from backend.api.deps import live as hub, store  # noqa: E402
from backend.api.live import LiveWorld, route_walks  # noqa: E402

BUILDING = "train/proc-campus-train-000"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GUIDE_LLM", "offline")
    yield TestClient(app)
    with hub.lock:  # no live world left behind for other tests' routes
        hub.worlds.clear()


def quiet_world(building_id: str) -> LiveWorld:
    """The building's live world with its simulated things removed and the clock stopped."""
    with hub.lock:
        hub.worlds.pop(building_id, None)
    world = hub.world(building_id)
    with world.lock:
        world.devices.clear()
        world.paused = True
    return world


def test_route_walks_follow_the_drawn_route(campus):
    plain = route(campus, LOBBY, FAR)
    walks = route_walks(campus, plain["space_path"], plain["element_path"])
    assert [space for space, _, _ in walks] == plain["space_path"]
    assert walks[0][1] == plain["space_path"][0] and walks[-1][2] == plain["space_path"][-1]


def test_a_world_fills_with_things_that_report(campus):
    world = LiveWorld("test/campus", campus)
    kinds = {device.kind for device in world.devices.values()}
    assert "cleaning_robot" in kinds and "delivery_robot" in kinds
    for _ in range(100):
        world.step(0.5)
    snapshot = world.snapshot()
    moved = [item for item in snapshot["devices"] if item["trail"]]
    assert moved and snapshot["simulated"]
    for item in moved:  # the trail is the last 50 m at most
        trail = item["trail"]
        length = sum(math.dist(a[:2], b[:2]) for a, b in zip(trail, trail[1:]) if a[2] == b[2])
        assert length <= 50.0 + 2.0  # + one report's step


def test_the_route_on_the_map_is_moved_round_pallets(client):
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    quiet_world(BUILDING)
    assert client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()["devices"] == []
    session = store.get(session_id).session
    first = session.tool_find_route(LOBBY, FAR)
    assert first["reachable"] and "live" not in first
    blocked = client.post("/live/control", json={"building": BUILDING, "action": "block_route", "session_id": session_id})
    assert blocked.status_code == 200, blocked.text
    snapshot = client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()
    assert any(item["blocking"] for item in snapshot["devices"])
    reroute = snapshot["reroute"]
    assert reroute["type"] == "route" and reroute["line"] and reroute["length_m"] > first["length_m"]
    assert reroute["reroute"]["by"][0]["kind"] == "pallet" and "new route" in reroute["message"]
    # the new route goes round, so the next poll has nothing more to say; the Guide hears about it once
    assert "reroute" not in client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()
    assert store.get(session_id).guide.live_note.startswith("[live note")
    # the Guide's own routes now go round too, and say so
    again = session.tool_find_route(LOBBY, FAR)
    assert again["live"]["avoided"][0]["kind"] == "pallet"
    # picked up: the shorter way is offered back
    client.post("/live/control", json={"building": BUILDING, "action": "clear"})
    session.live_suggest_at = 0.0  # the check runs at most every SUGGEST_EVERY_S
    suggestion = client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()["suggestion"]
    assert suggestion["save_m"] > 0
    taken = client.post("/live/shorter", json={"session_id": session_id}).json()["events"][0]
    assert taken["length_m"] == first["length_m"]


def test_a_tapped_pallet_and_a_real_device(client):
    world = quiet_world(BUILDING)
    dropped = client.post("/live/control", json={"building": BUILDING, "action": "drop", "floor": 0, "x": -28.0, "y": -7.2})
    assert dropped.status_code == 200
    assert [item["kind"] for item in client.get("/live", params={"building": BUILDING}).json()["devices"]] == ["pallet"]
    device = client.post("/live/devices", json={"building": BUILDING, "name": "Scissor lift SL-1", "length_m": 2.5,
                                                "width_m": 1.2}).json()
    floor_id = next(iter(world.floor_index))
    report = {"floor_id": floor_id, "x": -10.0, "y": -7.2, "state": "parked"}
    assert client.post(f"/live/devices/{device['id']}/report", params={"building": BUILDING}, json=report,
                       headers={"X-Device-Token": "wrong"}).status_code == 403
    assert client.post(f"/live/devices/{device['id']}/report", params={"building": BUILDING}, json=report,
                       headers={"X-Device-Token": device["token"]}).status_code == 200
    items = {item["name"]: item for item in client.get("/live", params={"building": BUILDING}).json()["devices"]}
    assert items["Scissor lift SL-1"]["source"] == "device" and items["Scissor lift SL-1"]["state"] == "parked"


def test_a_door_beside_the_blockage_is_no_way_through_it(campus):
    # pallets right at the canteen door (x ≈ -24.8): the door's landing must not join both sides of them
    live = LiveEffects(campus, [pallets(1.6, x=-24.8)])
    answer = route(campus, LOBBY, FAR, live)
    plain = route(campus, LOBBY, FAR)
    assert answer["reachable"] and answer["length_m"] > plain["length_m"] + 10
    walks = route_walks(campus, answer["space_path"], answer["element_path"])  # the path is a well-formed walk
    assert walks


def test_a_door_only_touched_is_taken_out_of_the_path(campus):
    from backend.core.live import collapse_hops

    graph = campus.graph(step_free=False)
    prefix = "proc-campus-train-000-F0-"
    lobby, office = prefix + "S012", prefix + "S010"
    touched = [lobby, "door:" + prefix + "O0011", "door:" + prefix + "O0019", "door:" + prefix + "O0009", office]
    assert collapse_hops(graph, touched) == [touched[0], touched[1], touched[3], touched[4]]
    assert collapse_hops(graph, [lobby, touched[1], touched[3], office]) == [lobby, touched[1], touched[3], office]


# ---------- edge cases ----------

F0, F1 = "proc-campus-train-000-F0", "proc-campus-train-000-F1"


def thing(x: float, y: float, length: float = 1.2, width: float = 0.8, floor: str = F0, heading: float = 0.0,
          moving: bool = False, name: str = "Pallet", item_id: str = "e1") -> Obstacle:
    return Obstacle(id=item_id, name=name, kind="pallet", floor_id=floor, x=x, y=y, length_m=length, width_m=width,
                    heading_deg=heading, moving=moving, state="moving" if moving else "left behind")


def test_something_inside_the_destination_room_doesnt_keep_you_out(campus):
    # a pallet right on Office 0.10's centre point (-44.91, -3.0)
    live = LiveEffects(campus, [thing(-44.91, -3.0, 2.0, 2.0)])
    assert route(campus, LOBBY, FAR, live) == {**route(campus, LOBBY, FAR), **{"live": route(campus, LOBBY, FAR, live).get("live")}}
    assert route(campus, LOBBY, FAR, live)["reachable"]


def test_a_pallet_in_front_of_the_only_door_makes_the_room_unreachable(campus):
    # Office 0.10 has one door (-44.91, -6.0); the pallet stands on its corridor-side landing
    answer = route(campus, LOBBY, FAR, LiveEffects(campus, [thing(-44.91, -6.6, 1.6, 1.2)]))
    assert not answer["reachable"]
    assert "Pallet" in answer["reason"] and answer["live"]["blocked_by"][0]["id"] == "e1"


def test_a_corridor_narrower_than_the_clearance_is_judged_by_the_walk_line(campus):
    # 3 m needed in a 2.4 m corridor: even empty, its free area falls apart, so what stands across the walk decides
    plain = route(campus, LOBBY, FAR)
    assert route(campus, LOBBY, FAR, LiveEffects(campus, [], clearance_m=3.0))["length_m"] == plain["length_m"]
    blocked = route(campus, LOBBY, FAR, LiveEffects(campus, [pallets(1.6)], clearance_m=3.0))
    assert blocked["length_m"] > plain["length_m"] and blocked["live"]["avoided"][0]["id"] == "p1"
    # ... and a pallet far from the walk changes nothing
    aside = LiveEffects(campus, [thing(-50.5, -7.2, 0.6, 0.6)], clearance_m=3.0)
    assert route(campus, LOBBY, NEAR, aside)["length_m"] == route(campus, LOBBY, NEAR)["length_m"]


def test_things_on_another_floor_or_outside_the_building_change_nothing(campus):
    live = LiveEffects(campus, [thing(-28.0, -7.2, 1.2, 1.6, floor=F1, item_id="up"), thing(500.0, 500.0, item_id="far")])
    assert not live.in_space.get("proc-campus-train-000-F0-S001")
    assert route(campus, LOBBY, FAR, live)["length_m"] == route(campus, LOBBY, FAR)["length_m"]


def test_degenerate_things_do_not_crash(campus):
    live = LiveEffects(campus, [thing(-28.0, -7.2, 0.0, 0.0, item_id="dot")],
                       [Hazard(id="h", name="Wet floor", kind="wet_floor", floor_id=F0, polygon=((-28.0, -7.0), (-27.0, -7.0)))])
    assert route(campus, LOBBY, FAR, live)["reachable"]


def test_routes_from_outside_tours_and_stops_take_the_live_state(campus):
    live = LiveEffects(campus, [pallets(1.6)])
    outside = route(campus, "outside", FAR, live)
    assert outside["reachable"] and outside["live"]["avoided"][0]["id"] == "p1"
    via = navigation.find_route(campus, LOBBY, FAR, via=[NEAR], include_steps=False, live=live).to_dict()
    assert via["reachable"] and via["live"]["avoided"][0]["id"] == "p1" and via["live"]["detour_m"] > 0
    tour = navigation.tour(campus, [LOBBY, NEAR, FAR], live=live).to_dict()
    assert tour["reachable"] and tour["legs"][1]["live"]["avoided"][0]["id"] == "p1"
    assert "live" not in tour["legs"][0]  # lobby → canteen is before the pallets


def test_preferences_and_the_live_state_together_report_true_metres(campus):
    from backend.core.preferences import Penalties

    live = LiveEffects(campus, [pallets(1.6)])
    answer = route(campus, LOBBY, FAR, live, penalties=Penalties(stairs_per_flight_m=20.0))
    assert answer["reachable"]
    measured = navigation.path_length(campus, answer["space_path"], answer["element_path"])
    assert answer["length_m"] == pytest.approx(measured, abs=0.02)


def test_live_routes_have_well_formed_paths_everywhere_in_a_busy_building(campus):
    """Many things at once (standing, moving, wet): every reachable route is one the map can draw and measure."""
    from backend.core.routeline import route_line

    rng = __import__("random").Random(7)
    corridor = campus.spaces["proc-campus-train-000-F0-S001"]["polygon"]
    items = [thing(rng.uniform(-50, -2), rng.uniform(-8.0, -6.4), 1.2, rng.choice([0.6, 0.8, 1.6]),
                   heading=rng.choice([0, 90]), moving=rng.random() < 0.3, item_id=f"t{i}") for i in range(6)]
    wet = [Hazard(id="w", name="Wet floor", kind="wet_floor", floor_id=F0,
                  polygon=((-40.0, -6.0), (-36.0, -6.0), (-36.0, -7.0), (-40.0, -7.0)))]
    for clearance in (0.7, 0.9):
        live = LiveEffects(campus, items, wet, clearance_m=clearance)
        spaces = [s for s in campus.spaces if campus.spaces[s]["floor_id"] == F0]
        for start, end in [(a, b) for a in spaces[:8] for b in spaces[8:16]]:
            answer = route(campus, start, end, live)
            if answer["reachable"]:
                assert route_line(campus, answer["space_path"], answer["element_path"])
                measured = navigation.path_length(campus, answer["space_path"], answer["element_path"])
                assert answer["length_m"] == pytest.approx(measured, abs=0.05)
    assert corridor


def test_a_route_answer_with_live_notes_is_plain_json(campus):
    import json

    live = LiveEffects(campus, [pallets(1.6)], [Hazard(id="w", name="Wet floor", kind="wet_floor", floor_id=F0,
                                                        polygon=((-6.0, -6.0), (-4.0, -6.0), (-4.0, -8.4), (-6.0, -8.4)))])
    json.dumps(route(campus, LOBBY, FAR, live))


# ---------- the world (backend/api/live.py) ----------


def test_the_trail_is_the_last_50_metres_and_splits_by_floor():
    from backend.api.live import trimmed

    trail = [[float(x), 0.0, F0, float(x)] for x in range(0, 100)]  # 1 m apart, 1 s apart
    kept = trimmed(trail, 100.0)
    assert kept[-1][0] == 99.0 and 49.0 <= kept[-1][0] - kept[0][0] <= 50.0
    old = trimmed([[0.0, 0.0, F0, 0.0], [1.0, 0.0, F0, 1.0]], 1000.0)
    assert old == []  # older than TRAIL_MAX_S: gone


def test_a_ble_tag_reports_a_steady_position(campus):
    world = LiveWorld("test/ble", campus)
    world.devices.clear()
    item = world.leave_something((F0, -28.0, -7.2, 0.0), name="Pallet", length_m=1.2, width_m=0.8)
    reports = []
    for _ in range(12):
        world.report(item, force=True)
        reports.append((item.reported["x"], item.reported["y"]))
    spread = max(math.dist(a, b) for a in reports[-6:] for b in reports[-6:])
    assert spread < 0.3 and all(math.dist(r, (-28.0, -7.2)) < 0.3 for r in reports[-6:])


def test_wet_zones_follow_the_cleaning_robot_and_dry_up(campus):
    from backend.api.live import WET_S, wet_zones

    world = LiveWorld("test/wet", campus)
    robot = next(d for d in world.devices.values() if d.kind == "cleaning_robot")
    robot.wet = [[-30.0 + i * 0.3, -7.2, F0, 10.0 + i] for i in range(20)]
    zones = wet_zones(robot, 30.0)
    assert zones and all(len(zone.polygon) > 3 for zone in zones)
    assert not wet_zones(robot, 10.0 + 20 + WET_S)  # standing still, the floor dries all the same
    world.time, robot.path, robot.pause_s, robot.floor_id = 10.0 + WET_S + 30, [[-20.0, -7.2, F0]], 0.0, F0
    world.advance(robot, 0.1)
    assert all(world.time - point[3] < WET_S for point in robot.wet)


def test_an_idle_world_stops_and_its_things_vanish(campus):
    with hub.lock:
        hub.worlds.clear()
    world = hub.world(BUILDING)
    hub.tick(0.2, world.last_view + 10)
    assert BUILDING in hub.worlds
    hub.tick(0.2, world.last_view + 10_000)
    assert BUILDING not in hub.worlds and hub.state(BUILDING) == ([], [])


def test_every_simulated_kind_moves_and_stays_inside_the_building(campus):
    from backend.core.fleet import space_at

    world = LiveWorld("test/inside", campus)
    seen = set()
    for _ in range(400):
        world.step(0.5)
        for device in world.devices.values():
            if device.reported and device.state not in ("riding",):
                at = device.reported
                assert space_at(campus, at["floor_id"], at["x"], at["y"]) is not None or device.kind in ("pallet", "cart"), device.name
            seen.add((device.kind, device.state))
    assert {"delivery_robot", "cleaning_robot"} <= {kind for kind, state in seen if state in ("moving", "cleaning")}


# ---------- endpoints ----------


def test_control_rejects_what_it_cannot_do(client):
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    quiet_world(BUILDING)
    post = lambda body: client.post("/live/control", json={"building": BUILDING, **body})  # noqa: E731
    assert post({"action": "dance"}).status_code == 422
    assert post({"action": "drop", "floor": 0, "x": 999.0, "y": 999.0}).status_code == 422
    assert post({"action": "drop", "floor": 42, "x": -28.0, "y": -7.2}).status_code == 422
    assert post({"action": "drop", "floor": 0}).status_code == 422
    assert post({"action": "block_route", "session_id": session_id}).status_code == 422  # no route on the map
    assert post({"action": "speed", "value": 1000}).json()["speed"] == 8.0
    assert post({"action": "speed", "value": 0.01}).json()["speed"] == 0.25
    assert client.get("/live", params={"building": "train/nope"}).status_code == 422
    assert client.post("/live/shorter", json={"session_id": session_id}).status_code == 409
    forklift = post({"action": "drop", "floor": 0, "x": -28.0, "y": -7.2, "kind": "forklift"})
    assert forklift.status_code == 200
    items = client.get("/live", params={"building": BUILDING}).json()["devices"]
    assert items[0]["kind"] == "forklift" and items[0]["state"] == "loading" and items[0]["blocking"]["space"] == "Corridor 0.01"  # 1.2 m across a 2.4 m corridor: 0.6 m a side
    assert post({"action": "reset"}).status_code == 200


def test_a_real_device_on_an_unknown_floor_is_refused(client):
    quiet_world(BUILDING)
    device = client.post("/live/devices", json={"building": BUILDING, "name": "Tag"}).json()
    report = client.post(f"/live/devices/{device['id']}/report", params={"building": BUILDING},
                         json={"floor_id": "nowhere", "x": 0, "y": 0}, headers={"X-Device-Token": device["token"]})
    assert report.status_code == 422
    assert client.post("/live/devices/dev-nope/report", params={"building": BUILDING},
                       json={"floor_id": F0, "x": 0, "y": 0}, headers={"X-Device-Token": "x"}).status_code == 404


def test_in_access_mode_only_the_admin_uses_the_controls_and_registers_devices(client, monkeypatch):
    from backend.api import deps
    from backend.api.access import Access, MemoryAccess
    from tests.test_access import FakeAuth, auth

    monkeypatch.setattr(deps, "access", Access(store=MemoryAccess(), auth=FakeAuth(), enabled=True))
    quiet_world(BUILDING)
    pause = {"building": BUILDING, "action": "pause"}
    device = {"building": BUILDING, "name": "Tag"}
    for headers in ({}, auth("staff")):  # anonymous, a signed-in non-admin
        assert client.post("/live/control", json=pause, headers=headers).status_code == 403
        assert client.post("/live/devices", json=device, headers=headers).status_code == 403
    assert client.post("/live/control", json=pause, headers=auth("admin")).status_code == 200
    assert client.post("/live/devices", json=device, headers=auth("admin")).status_code == 200


def test_the_reroute_follows_the_route_on_the_map_not_an_older_question(client):
    """A route drawn by another tool (here: the arrival from a nearby building) is the one asked again."""
    from backend.agents.campus import arrive

    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    quiet_world(BUILDING)
    session = store.get(session_id).session
    session.tool_find_route(LOBBY, NEAR)  # an older question: to the canteen
    entrance = "proc-campus-train-000-F0-O0021"  # the corridor's outside door at x = 0
    arrived = arrive(session, entrance, FAR)
    assert arrived["reachable"] and session.shown_route()["request"]["destination"] == arrived["to_space_id"]
    assert client.post("/live/control", json={"building": BUILDING, "action": "block_route",
                                              "session_id": session_id}).status_code == 200
    reroute = client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()["reroute"]
    assert reroute["space_path"][-1] == arrived["to_space_id"]  # still to Office 0.10, not the canteen


def test_a_route_without_a_request_gets_an_alert_not_a_new_route(client):
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    quiet_world(BUILDING)
    session = store.get(session_id).session
    session.tool_find_route(LOBBY, FAR)
    session.events[-1].pop("request")  # e.g. a route event saved before routes carried their request
    client.post("/live/control", json={"building": BUILDING, "action": "block_route", "session_id": session_id})
    snapshot = client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()
    assert "reroute" not in snapshot and "block the way" in snapshot["alert"]["message"]
    again = client.get("/live", params={"building": BUILDING, "session_id": session_id}).json()
    assert "alert" not in again  # once per blocker set


def test_viewers_never_see_things_in_spaces_hidden_from_them(client, monkeypatch):
    from backend.api import deps
    corridor = "proc-campus-train-000-F0-S001"
    quiet_world(BUILDING)
    client.post("/live/control", json={"building": BUILDING, "action": "drop", "floor": 0, "x": -28.0, "y": -7.2})
    assert len(client.get("/live", params={"building": BUILDING}).json()["devices"]) == 1
    monkeypatch.setattr(deps, "live_hidden", lambda authorization, building: frozenset({corridor}))
    assert client.get("/live", params={"building": BUILDING}).json()["devices"] == []
    from backend.api.live import SessionLive

    assert SessionLive(hub, BUILDING).devices(spaces={"somewhere-else"}) == []
    assert len(SessionLive(hub, BUILDING).devices()) == 1


def test_the_guide_can_ask_what_is_live(client):
    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    quiet_world(BUILDING)
    client.post("/live/control", json={"building": BUILDING, "action": "drop", "floor": 0, "x": -28.0, "y": -7.2})
    client.get("/live", params={"building": BUILDING, "session_id": session_id})
    conversation = store.get(session_id)
    from backend.api.deps import with_live

    session = with_live(conversation).session
    assert "live_status" in [tool["name"] for tool in session.tool_definitions()]
    status = session.tool_live_status("pallet")
    assert status["simulated"] and status["devices"][0]["kind"] == "pallet"
    assert status["devices"][0]["space"] == "Corridor 0.01"
    with hub.lock:
        hub.worlds.clear()
    assert "live_status" not in [tool["name"] for tool in with_live(conversation).session.tool_definitions()]


def test_sessions_with_live_routes_still_save(client):
    import json

    from backend.api import persistence

    session_id = client.post("/sessions", json={"building": BUILDING}).json()["session_id"]
    quiet_world(BUILDING)
    conversation = store.get(session_id)
    conversation.session.tool_find_route(LOBBY, FAR)
    client.post("/live/control", json={"building": BUILDING, "action": "block_route", "session_id": session_id})
    client.get("/live", params={"building": BUILDING, "session_id": session_id})
    json.dumps(persistence.dump(conversation.session, conversation.guide))


def test_the_hub_plans_off_the_clock_and_things_move(client):
    import time as clock

    with hub.lock:
        hub.worlds.clear()
    world = hub.world(BUILDING)
    assert world.planner is not None
    world.speed = 8.0
    start = {item.id: (item.x, item.y) for item in world.devices.values() if item.kind == "delivery_robot"}
    deadline = clock.time() + 15
    while clock.time() < deadline:
        clock.sleep(0.3)
        with world.lock:
            moved = [item for item in world.devices.values() if item.id in start and (item.x, item.y) != start[item.id]]
        if moved:
            break
    assert moved, "no delivery robot moved within 15 s"
