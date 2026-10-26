"""The living building: connected things that move around or are left behind, reporting where they are now and then.

A `LiveWorld` per building holds its devices. Most are SIMULATED (source "sim", clearly labelled in the app): forklifts
and an AGV in factories, delivery and cleaning robots, and pallets / carts with BLE tags that people leave in corridors
for a few minutes. Real devices can join over HTTP (source "device"): register, then post positions. Every device has a
report interval (telematics 1 s, Wi-Fi robots 2 s, BLE tags 10 s); the app only ever sees the last REPORTED position
and the trail of reports (the last `TRAIL_M` metres), never the simulation's true position.

What is reported feeds routing (backend/core/live.py): parked things cut the walks they block, moving ones cost a wait, a
cleaning robot's wet floor costs a little. Sessions get `session.live` (backend/agents/tools.py), and `GET /live` re-checks the
route on a viewer's map: a route that just got blocked is replaced (event `route` with `reroute`), one whose detour is
no longer needed is offered back (`suggestion`).

A world runs while someone looks at it (GET /live polled) and stops `IDLE_S` after the last look; its things vanish
with it, so routes go back to the plain route model."""

import copy
import hashlib
import itertools
import math
import queue
import random
import secrets
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from shapely.geometry import LineString, Point

from backend.core import navigation
from backend.core.building_map import DOOR_PREFIX, LIFT, BuildingMap, MapError, door_landing, outline
from backend.core.fleet import space_at
from backend.core.floorplan import floor_indices
from backend.core.live import BIG_OUTLINE, WALKER_CLEARANCE_M, Hazard, LiveEffects, Obstacle
from backend.core.route_models import RouteRules
from backend.core.routeline import route_line, route_nodes, walk_corners

TICK_S = 0.2
IDLE_S = 90  # no viewer for this long: the world stops
TRAIL_M = 50.0  # the trail shown behind a device
TRAIL_MAX_S = 240
WET_S = 120  # a cleaned floor stays wet this long (simulated seconds)
WET_WIDTH_M = 0.9
DEVICE_TIMEOUT_S = 300  # a real device that stopped reporting is dropped
RIDE_S = 6.0  # a lift ride or a flight of stairs, simulated
BLE_FIXES = 6  # a BLE tag's reported position is the mean of its last fixes
REROUTE_GAIN_M = 4.0  # a cleared blockage is offered back when the plain route is at least this much shorter
SUGGEST_EVERY_S = 4.0  # how often a detour is checked for being no longer needed (it routes again)

FACTORY_ZONES = {"warehouse_zone", "logistics_zone", "production_zone", "assembly_zone", "additive_zone"}
ROBOT_ROOMS = {"office", "meeting_room", "lab", "kitchen", "print_room", "seminar_room", "library", "quality_lab",
               "server_room", "makerspace", "storage", "canteen", "lobby"}
WALKWAYS = {"corridor", "hall"}
STANDING = {"left behind", "parked", "loading", "unloading"}  # states that block like a wall


@dataclass(frozen=True)
class Kind:
    label: str
    length_m: float
    width_m: float
    speed: float  # m/s
    report_s: float
    link: str  # how it reports
    jitter_m: float = 0.0


KINDS = {
    "forklift": Kind("Forklift", 2.6, 1.2, 1.7, 1.0, "telematics"),
    "agv": Kind("AGV", 1.6, 0.9, 1.0, 1.0, "fleet manager"),
    "delivery_robot": Kind("Delivery robot", 0.8, 0.6, 1.0, 2.0, "Wi-Fi"),
    "cleaning_robot": Kind("Cleaning robot", 0.9, 0.7, 0.35, 2.0, "Wi-Fi"),
    "pallet": Kind("Pallet", 1.2, 0.8, 0.0, 10.0, "BLE tag", jitter_m=0.12),
    "cart": Kind("Cart", 1.1, 0.6, 0.0, 10.0, "BLE tag", jitter_m=0.12),
    "pallet_jack": Kind("Pallet jack", 1.6, 0.7, 0.0, 10.0, "BLE tag", jitter_m=0.12),
    "device": Kind("Device", 1.0, 0.8, 0.0, 1.0, "API"),
}
LEFT_BEHIND = {  # what people leave in walkways (name, kind, length × width across)
    "factory": [("Pallet", "pallet", 1.2, 0.8), ("Two pallets", "pallet", 1.2, 1.6), ("Pallet jack", "pallet_jack", 1.6, 0.7),
                ("Parts trolley", "cart", 1.2, 0.7)],
    "other": [("Cleaning cart", "cart", 1.0, 0.55), ("Delivery trolley", "cart", 1.2, 0.7), ("Mail cart", "cart", 0.9, 0.5),
              ("Pallet delivery", "pallet", 1.2, 0.8)],
}


@dataclass
class Device:
    id: str
    name: str
    kind: str
    source: str  # "sim" or "device"
    floor_id: str
    x: float
    y: float
    heading: float = 0.0
    length_m: float = 1.0
    width_m: float = 0.8
    state: str = "idle"  # idle, moving, loading, unloading, cleaning, riding, left behind, parked
    # the plan: points [x, y, floor_id] still to drive, and a pause before driving on
    path: list[list] = field(default_factory=list)
    pause_s: float = 0.0
    pause_state: str = "idle"
    stop_at: int | None = None  # index into path where the forklift stops to load in the aisle
    destination: str | None = None  # space id
    expires: float | None = None  # simulated time a left-behind thing is picked up
    report_s: float = 1.0
    next_report: float = 0.0
    reported: dict | None = None  # {x, y, floor_id, heading, t, state, moving}
    trail: list[list] = field(default_factory=list)  # [x, y, floor_id, t] of reports
    wet: list[list] = field(default_factory=list)  # cleaning robot: [x, y, floor_id, t]
    token_hash: str | None = None
    last_seen: float = 0.0  # real devices: wall clock of the last report
    dropped: bool = False  # put down from the app's demo controls
    fixes: list[tuple[float, float]] = field(default_factory=list)  # BLE tags: the last raw fixes
    planning: bool = False  # its next mission is being planned off the clock (LiveHub planner)

    @property
    def moving(self) -> bool:
        """Stops of a few seconds (idle, a lift ride) count as moving: people wait, they don't go round."""
        return self.state not in STANDING


def building_flavour(building: BuildingMap) -> str:
    rooms = {space.get("room_type") for space in building.spaces.values()}
    if rooms & FACTORY_ZONES or any(asset.get("type") == "forklift" for asset in building.assets.values()):
        return "factory"
    if len(building.spaces) < 25 and not any(space.get("type") == "corridor" and polygon_size(space) > 20
                                              for space in building.spaces.values()):
        return "home"
    return "other"


def polygon_size(space: dict) -> float:
    return outline(space["polygon"]).area


class LiveWorld:
    def __init__(self, building_id: str, building: BuildingMap) -> None:
        self.building_id = building_id
        self.building = building
        self.flavour = building_flavour(building)
        self.random = random.Random(building_id)
        self.lock = threading.RLock()
        self.time = 0.0  # simulated seconds
        self.speed = 1.0
        self.paused = False
        self.devices: dict[str, Device] = {}
        self.last_view = time.time()
        self.floor_index = floor_indices(building)
        self.floor_ids = {index: floor_id for floor_id, index in self.floor_index.items()}
        self.next_drop = 20.0
        self.planned = False
        self.planner: Callable[["LiveWorld", str], None] | None = None  # set by LiveHub: plan off the clock
        self._ids = itertools.count(1)
        self._snapshot_cache: tuple[float, list, list] | None = None
        self.walkways = [space_id for space_id, space in building.spaces.items()
                         if space.get("type") in WALKWAYS and self.door_count(space_id) >= 2]
        self.populate()

    # ---------- setup ----------

    def door_count(self, space_id: str) -> int:
        return sum(1 for opening in self.building.openings.values() if space_id in opening["space_ids"])

    def spaces(self, room_types: set[str] | None = None, types: set[str] | None = None,
               floor_id: str | None = None) -> list[str]:
        return [space_id for space_id, space in self.building.spaces.items()
                if (room_types is None or space.get("room_type") in room_types)
                and (types is None or space.get("type") in types)
                and (floor_id is None or space["floor_id"] == floor_id)
                and self.door_count(space_id) >= 1]

    def add(self, kind: str, name: str, space_id: str, **extra) -> Device:
        spec = KINDS[kind]
        space = self.building.spaces[space_id]
        x, y = self.building.anchor(space_id)
        device = Device(id=f"live-{kind}-{next(self._ids)}", name=name, kind=kind, source="sim",
                        floor_id=space["floor_id"], x=x, y=y, length_m=spec.length_m, width_m=spec.width_m,
                        report_s=spec.report_s, next_report=self.random.uniform(0, spec.report_s), **extra)
        self.devices[device.id] = device
        return device

    def populate(self) -> None:
        size = len(self.building.spaces)
        if self.flavour == "factory":
            zones = self.spaces(FACTORY_ZONES) or self.spaces(types={"hall"})
            forklifts = [asset for asset in self.building.assets.values() if asset.get("type") == "forklift"]
            for index in range(max(2, min(4, len(forklifts) or size // 25))):
                asset = forklifts[index] if index < len(forklifts) else None
                start = asset["space_id"] if asset else self.random.choice(zones)
                device = self.add("forklift", f"Forklift FL-{index + 1:02d}", start)
                if asset:
                    device.x, device.y = asset["position"]
            if zones:
                self.add("agv", "AGV T-1 (tugger)", self.random.choice(zones))
        else:
            rooms = self.spaces(ROBOT_ROOMS)
            if self.flavour != "home" and rooms:
                for index in range(1 if size < 60 else 2):
                    self.add("delivery_robot", f"Delivery robot DR-{index + 1}", self.random.choice(rooms))
        if self.walkways:
            self.add("cleaning_robot", "Cleaning robot CR-1", self.random.choice(self.walkways))
        for _ in range(1 if self.flavour == "home" else 2):
            self.leave_something()
        for device in self.devices.values():
            self.report(device, force=True)

    # ---------- simulation ----------

    def step(self, dt: float) -> None:
        with self.lock:
            if self.paused:
                return
            dt *= self.speed
            self.time += dt
            self.planned = False  # one new mission per tick at most: route planning is the slow part
            for device in list(self.devices.values()):
                if device.source == "sim":
                    self.advance(device, dt)
                    if device.expires is not None and self.time >= device.expires:
                        del self.devices[device.id]
                        continue
                    if self.time >= device.next_report:
                        self.report(device)
                elif time.time() - device.last_seen > DEVICE_TIMEOUT_S:
                    del self.devices[device.id]
            if self.time >= self.next_drop:
                self.next_drop = self.time + self.random.uniform(45, 110)
                left = [d for d in self.devices.values() if d.state == "left behind"]
                if len(left) < (2 if self.flavour == "home" else 4):
                    self.leave_something()
            self._snapshot_cache = None

    def advance(self, device: Device, dt: float) -> None:
        if device.state == "left behind":
            return
        if device.pause_s > 0:
            device.pause_s -= dt
            device.state = device.pause_state
            return
        if not device.path:
            if not self.planned and not device.planning:
                self.planned = True
                self.new_mission(device)
            return
        device.state = "cleaning" if device.kind == "cleaning_robot" else "moving"
        budget = KINDS[device.kind].speed * dt
        while budget > 0 and device.path:
            x, y, floor_id = device.path[0]
            if floor_id != device.floor_id:  # lift or stairs: ride, then appear on the other floor
                device.floor_id, device.x, device.y = floor_id, x, y
                device.path.pop(0)
                self.shift_stop(device)
                device.pause_s, device.pause_state = RIDE_S, "riding"
                return
            distance = math.dist((device.x, device.y), (x, y))
            if distance <= budget:
                device.x, device.y = x, y
                device.path.pop(0)
                budget -= distance
                if self.shift_stop(device):
                    device.pause_s = self.random.uniform(30, 55)
                    device.pause_state = "loading"
                    return
            else:
                device.heading = math.degrees(math.atan2(y - device.y, x - device.x))
                device.x += (x - device.x) / distance * budget
                device.y += (y - device.y) / distance * budget
                budget = 0
        if device.kind == "cleaning_robot":
            device.wet.append([device.x, device.y, device.floor_id, self.time])
            device.wet = [point for point in device.wet if self.time - point[3] < WET_S]
        if not device.path:  # arrived: unload / drop off, then the next mission
            device.pause_state = "unloading" if device.kind in ("forklift", "agv") else "idle"
            device.pause_s = self.random.uniform(8, 20) if device.kind in ("forklift", "agv", "delivery_robot") else 2.0

    def shift_stop(self, device: Device) -> bool:
        """One waypoint passed; True when it was the forklift's stop in the aisle."""
        if device.stop_at is None:
            return False
        device.stop_at -= 1
        if device.stop_at < 0:
            device.stop_at = None
            return True
        return False

    def new_mission(self, device: Device) -> None:
        """Plan the device's next mission: on the hub's planner thread when there is one (route planning can take a
        while in a big building, and must not hold up the clock), else right here."""
        if self.planner is None:
            self.plan_mission(device)
            return
        device.planning = True
        device.pause_s, device.pause_state = 0.0, "idle"
        self.planner(self, device.id)

    def plan_off_clock(self, device_id: str) -> None:
        """The planner thread's part: plan on a copy of the device outside the world's lock, then hand it over."""
        with self.lock:
            device = self.devices.get(device_id)
            if device is None:
                return
            draft = copy.copy(device)
        self.plan_mission(draft)
        with self.lock:
            device = self.devices.get(device_id)
            if device is None:
                return
            device.planning = False
            if (device.x, device.y, device.floor_id) != (draft.x, draft.y, draft.floor_id):
                return  # it was moved meanwhile (a real device, a reset): plan again next tick
            device.path, device.destination, device.stop_at = draft.path, draft.destination, draft.stop_at
            device.pause_s, device.pause_state = draft.pause_s, draft.pause_state

    def plan_mission(self, device: Device) -> None:
        start = space_at(self.building, device.floor_id, device.x, device.y) or self.nearest_space(device)
        if start is None:
            return
        if device.kind in ("forklift", "agv"):
            pool = [s for s in self.spaces(FACTORY_ZONES) if s != start] or [s for s in self.walkways if s != start]
        elif device.kind == "delivery_robot":
            pool = [s for s in self.spaces(ROBOT_ROOMS) if s != start]
        elif device.kind == "cleaning_robot":
            pool = [s for s in self.walkways if s != start and self.building.spaces[s]["floor_id"] == device.floor_id]
            if start in self.walkways and (not pool or self.random.random() < 0.6) and self.sweep(device, start):
                return
        else:
            return
        self.random.shuffle(pool)
        for destination in pool[:6]:
            line = self.plan_line(device, start, destination)
            if line and len(line) > 1:
                device.path = [[x, y, self.floor_ids[floor]] for x, y, floor in line[1:]]
                device.destination = destination
                device.stop_at = None
                if device.kind == "forklift" and self.random.random() < 0.6:
                    aisle = [index for index, (x, y, floor_id) in enumerate(device.path[:-1])
                             if (space_at(self.building, floor_id, x, y) or "") in self.walkways]
                    if aisle:
                        device.stop_at = self.random.choice(aisle)
                return
        device.pause_s, device.pause_state = 10.0, "idle"

    def sweep(self, device: Device, space_id: str) -> bool:
        """The cleaning robot cleans the walkway it is in: to its door farthest away, along the walk inside."""
        space = self.building.spaces[space_id]
        doors = [tuple(o["position"]) for o in self.building.openings.values() if space_id in o["space_ids"]]
        if not doors:
            return False
        far = max(doors, key=lambda door: math.dist(door, (device.x, device.y)))
        if math.dist(far, (device.x, device.y)) < 3:
            return False
        landing = door_landing(outline(space["polygon"]), far)
        points = [*corners_inside(space["polygon"], (device.x, device.y), far), landing]
        device.path = [[x, y, device.floor_id] for x, y in points]
        device.destination, device.stop_at = space_id, None
        return True

    def nearest_space(self, device: Device) -> str | None:
        options = [(math.dist((device.x, device.y), self.building.anchor(s)), s) for s, space in self.building.spaces.items()
                   if space["floor_id"] == device.floor_id]
        return min(options)[1] if options else None

    def plan_line(self, device: Device, start: str, destination: str) -> list[list[float]] | None:
        """The device's route as a drawn line; vehicles stay off stairs (and forklifts out of lifts), and every device
        goes round what blocks it."""
        building = self.building
        closed = [c["id"] for c in building.connectors.values()
                  if c["kind"] != LIFT or device.kind in ("forklift", "agv", "cleaning_robot")]
        obstacles, _ = self.obstacles(exclude=device.id)  # robots go round what stands, wait for what moves
        live = LiveEffects(building, [item for item in obstacles if not item.moving], [],
                           clearance_m=device.width_m + 0.2, notes=False)
        attempts = [RouteRules(forklift=True), RouteRules()] if device.kind == "forklift" else [RouteRules()]
        for rules in attempts:
            try:
                route = navigation.find_route(building, start, destination, step_free=True, closed=closed,
                                              include_steps=False, rules=rules, live=live).to_dict()
            except MapError:
                return None
            if route.get("reachable"):
                return route_line(building, route["space_path"], route["element_path"],
                                  start=(device.x, device.y))
        return None

    def leave_something(self, at: tuple[str, float, float, float] | None = None, name: str | None = None,
                        length_m: float | None = None, width_m: float | None = None, kind: str = "pallet",
                        dropped: bool = False) -> Device | None:
        """Someone leaves a pallet / cart in a walkway (somewhere random, or `at` = (floor_id, x, y, heading))."""
        if at is None:
            spot = self.random_spot()
            if spot is None:
                return None
            name, kind, length_m, width_m = self.random.choice(LEFT_BEHIND["factory" if self.flavour == "factory" else "other"])
            at = spot
        floor_id, x, y, heading = at
        space_id = space_at(self.building, floor_id, x, y)
        if space_id is None:
            return None
        device = self.add(kind, name or KINDS[kind].label, space_id, state="left behind", dropped=dropped)
        device.x, device.y, device.heading = x, y, heading
        device.length_m, device.width_m = length_m or device.length_m, width_m or device.width_m
        device.expires = self.time + self.random.uniform(150, 320)
        tag = f"{'P' if kind == 'pallet' else 'C'}-{self.random.randint(100, 999)}"
        device.name = f"{device.name} · BLE {tag}"
        self.report(device, force=True)
        return device

    def random_spot(self) -> tuple[str, float, float, float] | None:
        """A point on a door-to-door walk of a random walkway, shifted a little sideways."""
        for _ in range(8):
            if not self.walkways:
                return None
            space_id = self.random.choice(self.walkways)
            space = self.building.spaces[space_id]
            doors = [o for o in self.building.openings.values() if space_id in o["space_ids"]]
            first, second = self.random.sample(doors, 2)
            polygon = outline(space["polygon"])
            points = [door_landing(polygon, tuple(first["position"])),
                      *corners_inside(space["polygon"], tuple(first["position"]), tuple(second["position"])),
                      door_landing(polygon, tuple(second["position"]))]
            lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
            total = sum(lengths)
            if total < 6:
                continue
            target = self.random.uniform(0.3, 0.7) * total
            for (a, b), length in zip(zip(points, points[1:]), lengths):
                if target <= length and length > 0:
                    t = target / length
                    x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                    heading = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                    side = self.random.uniform(-0.45, 0.45)
                    x += -math.sin(math.radians(heading)) * side
                    y += math.cos(math.radians(heading)) * side
                    if polygon.buffer(-0.3).contains(Point(x, y)):
                        return space["floor_id"], round(x, 3), round(y, 3), round(heading, 1)
                    break
                target -= length
        return None

    # ---------- reports ----------

    def report(self, device: Device, force: bool = False, at: dict | None = None) -> None:
        """The device tells the system where it is (sim: its true position, BLE tags with a little jitter)."""
        jitter = KINDS.get(device.kind, KINDS["device"]).jitter_m
        if at is None:
            x = device.x + (self.random.gauss(0, jitter) if jitter else 0.0)
            y = device.y + (self.random.gauss(0, jitter) if jitter else 0.0)
            if jitter:  # a standing tag: the system keeps the mean of its last fixes, as indoor positioning does,
                # so the noise of single BLE fixes can't flip a corridor between blocked and free
                device.fixes = [*device.fixes[-(BLE_FIXES - 1):], (x, y)]
                x = sum(fix[0] for fix in device.fixes) / len(device.fixes)
                y = sum(fix[1] for fix in device.fixes) / len(device.fixes)
            at = {"x": round(x, 3), "y": round(y, 3), "floor_id": device.floor_id, "heading": round(device.heading, 1)}
        device.reported = {**at, "t": self.time, "state": device.state, "moving": device.moving}
        device.next_report = self.time + device.report_s
        if device.state != "left behind":
            device.trail.append([at["x"], at["y"], at["floor_id"], self.time])
            device.trail = trimmed(device.trail, self.time)
        self._snapshot_cache = None

    # ---------- what routing sees ----------

    def obstacles(self, exclude: str | None = None) -> tuple[list[Obstacle], list[Hazard]]:
        with self.lock:
            if exclude is None and self._snapshot_cache and self._snapshot_cache[0] == self.time:
                return self._snapshot_cache[1], self._snapshot_cache[2]
            items = []
            hazards = []
            for device in self.devices.values():
                if device.id == exclude or not device.reported:
                    continue
                at = device.reported
                state = at["state"]
                items.append(Obstacle(id=device.id, name=device.name, kind=device.kind, floor_id=at["floor_id"],
                                      x=at["x"], y=at["y"], length_m=device.length_m, width_m=device.width_m,
                                      heading_deg=at.get("heading") or 0.0, moving=bool(at["moving"]), state=state))
                if device.kind == "cleaning_robot":
                    hazards += wet_zones(device, self.time)
            if exclude is None:
                self._snapshot_cache = (self.time, items, hazards)
            return items, hazards

    # ---------- the app's view ----------

    def snapshot(self, clearance_m: float = WALKER_CLEARANCE_M) -> dict:
        with self.lock:
            obstacles, hazards = self.obstacles()
            live = LiveEffects(self.building, obstacles, hazards, clearance_m)
            blocking = blockers(self.building, live)
            devices = []
            for device in self.devices.values():
                if not device.reported:
                    continue
                at = device.reported
                space_id = space_at(self.building, at["floor_id"], at["x"], at["y"])
                spec = KINDS.get(device.kind, KINDS["device"])
                ahead = []
                if device.moving and device.path:
                    ahead = self.ahead(device)
                devices.append({
                    "id": device.id, "name": device.name, "kind": device.kind, "label": spec.label,
                    "source": device.source, "link": spec.link, "state": at["state"], "moving": at["moving"],
                    "position": {"x": at["x"], "y": at["y"], "floor": self.floor_index.get(at["floor_id"]),
                                 "floor_id": at["floor_id"], "heading_deg": at.get("heading"),
                                 "space_id": space_id,
                                 "space": self.building.spaces[space_id]["name"] if space_id else None},
                    "footprint": {"length_m": device.length_m, "width_m": device.width_m},
                    "report_every_s": device.report_s, "reported_ago_s": round(self.time - at["t"], 1),
                    "reported_at": at["t"],
                    "trail": [[x, y, self.floor_index.get(floor_id)] for x, y, floor_id, _ in device.trail],
                    "ahead": ahead,
                    "to": self.building.spaces[device.destination]["name"] if device.destination and device.moving else None,
                    "blocking": blocking.get(device.id),
                    "left_s": round(device.expires - self.time) if device.expires is not None else None,
                    "dropped": device.dropped,
                })
            devices.sort(key=lambda item: (item["source"] != "device", item["kind"], item["name"]))
            return {
                "building": self.building_id, "t": round(self.time, 2), "speed": self.speed, "paused": self.paused,
                "flavour": self.flavour, "simulated": any(d.source == "sim" for d in self.devices.values()),
                "devices": devices,
                "hazards": [{"id": hazard.id, "name": hazard.name, "kind": hazard.kind,
                             "floor": self.floor_index.get(hazard.floor_id),
                             "polygon": [[round(x, 2), round(y, 2)] for x, y in hazard.polygon]} for hazard in hazards],
            }

    def ahead(self, device: Device, metres: float = 12.0) -> list[list[float]]:
        """The next few metres the device will drive (same floor), for the app's heading line."""
        points = [[device.x, device.y, self.floor_index.get(device.floor_id)]]
        left = metres
        last = (device.x, device.y)
        for x, y, floor_id in device.path:
            if floor_id != device.floor_id:
                break
            step = math.dist(last, (x, y))
            if step >= left:
                t = left / step if step else 0
                points.append([last[0] + (x - last[0]) * t, last[1] + (y - last[1]) * t, self.floor_index.get(floor_id)])
                break
            points.append([x, y, self.floor_index.get(floor_id)])
            left -= step
            last = (x, y)
        return [[round(x, 2), round(y, 2), floor] for x, y, floor in points]


def corners_inside(polygon: list, first: tuple, last: tuple) -> list:
    """walk_corners, except in a huge outline (backend/core/live.py BIG_OUTLINE), where the walk is taken straight."""
    return walk_corners(polygon, first, last) if len(polygon) <= BIG_OUTLINE else []


def trimmed(trail: list[list], now: float) -> list[list]:
    """The newest reports covering at most TRAIL_M metres (and TRAIL_MAX_S seconds)."""
    kept = []
    distance = 0.0
    for point in reversed(trail):
        if now - point[3] > TRAIL_MAX_S:
            break
        if kept and kept[-1][2] == point[2]:
            distance += math.dist(kept[-1][:2], point[:2])
            if distance > TRAIL_M:
                break
        kept.append(point)
    return kept[::-1]


def wet_zones(device: Device, now: float) -> list[Hazard]:
    """The floor the cleaning robot wet in the last WET_S seconds: one zone per run on a floor."""
    zones = []
    runs: list[list] = []
    for point in (point for point in device.wet if now - point[3] < WET_S):  # dry again after WET_S
        if runs and runs[-1][-1][2] == point[2] and math.dist(runs[-1][-1][:2], point[:2]) < 3:
            runs[-1].append(point)
        else:
            runs.append([point])
    for index, run in enumerate(runs):
        if len(run) < 2:
            continue
        coarse = run[:: max(1, len(run) // 40)] + [run[-1]]
        shape = LineString([(x, y) for x, y, _, _ in coarse]).buffer(WET_WIDTH_M / 2, cap_style="round").simplify(0.05)
        if shape.is_empty or shape.geom_type != "Polygon":
            continue
        zones.append(Hazard(id=f"{device.id}-wet-{index}", name=f"Wet floor ({device.name})", kind="wet_floor",
                            floor_id=run[0][2],
                            polygon=tuple((round(x, 2), round(y, 2)) for x, y in shape.exterior.coords)))
    return zones


def blockers(building: BuildingMap, live: LiveEffects) -> dict[str, dict]:
    """Per obstacle that cuts at least one walk of its space for a walker: {"space", "cuts"} (walks cut)."""
    found: dict[str, dict] = {}
    for space_id, items in live.in_space.items():
        if all(item.moving for item in items):
            continue
        nodes = [space_id] + [DOOR_PREFIX + o["id"] for o in building.openings.values() if space_id in o["space_ids"]]
        cuts: dict[str, int] = {}
        for first, second in itertools.combinations(nodes, 2):
            for item in live.cut(space_id, first, second) or []:
                cuts[item] = cuts.get(item, 0) + 1
        for item_id, count in cuts.items():
            found[item_id] = {"space": building.spaces[space_id]["name"], "space_id": space_id, "cuts": count}
    return found


# ---------- the hub: worlds, the tick thread, sessions ----------


class LiveHub:
    def __init__(self, building_map: Callable[[str], BuildingMap]) -> None:
        self.building_map = building_map  # building id → BuildingMap (base data, read only)
        self.worlds: dict[str, LiveWorld] = {}
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.planner_thread: threading.Thread | None = None
        self.jobs: queue.Queue = queue.Queue()

    def world(self, building_id: str, start: bool = True) -> LiveWorld | None:
        with self.lock:
            world = self.worlds.get(building_id)
        if world is None and start:
            # built outside the hub's lock: a big building takes a while, and other buildings keep running
            built = LiveWorld(building_id, self.building_map(building_id))
            built.planner = self.plan
            with self.lock:
                world = self.worlds.setdefault(building_id, built)
            self.ensure_thread()
        if world is not None and start:
            world.last_view = time.time()
        return world

    def ensure_thread(self) -> None:
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, daemon=True, name="live-world")
                self.thread.start()
            if self.planner_thread is None or not self.planner_thread.is_alive():
                self.planner_thread = threading.Thread(target=self.plan_forever, daemon=True, name="live-planner")
                self.planner_thread.start()

    def plan(self, world: LiveWorld, device_id: str) -> None:
        self.jobs.put((world, device_id))

    def plan_forever(self) -> None:
        while True:
            world, device_id = self.jobs.get()
            try:
                world.plan_off_clock(device_id)
            except Exception:  # noqa: BLE001 — a failed plan leaves the device idle; it asks again
                traceback.print_exc()
                with world.lock:
                    device = world.devices.get(device_id)
                    if device is not None:
                        device.planning, device.pause_s, device.pause_state = False, 10.0, "idle"

    def run(self) -> None:
        last = time.time()
        while True:
            time.sleep(TICK_S)
            now = time.time()
            self.tick(min(now - last, 1.0), now)
            last = now

    def tick(self, dt: float, now: float) -> None:
        """Every world one step on; a world nobody looked at for IDLE_S stops (its things vanish with it)."""
        with self.lock:
            worlds = list(self.worlds.items())
        for building_id, world in worlds:
            if now - world.last_view > IDLE_S:
                with self.lock:
                    if self.worlds.get(building_id) is world:
                        del self.worlds[building_id]
                continue
            try:
                world.step(dt)
            except Exception:  # noqa: BLE001 — one broken world must not stop the others
                traceback.print_exc()

    def state(self, building_id: str) -> tuple[list[Obstacle], list[Hazard]]:
        world = self.world(building_id, start=False)
        return world.obstacles() if world else ([], [])


def route_walks(building: BuildingMap, space_path: list[str], element_path: list[str]) -> list[tuple[str, str, str]]:
    """The walks of a drawn route as (space, first node, second node) in route-graph node names: door to door through
    a space, anchor to door where a route starts (or leaves a lift / stairs), door to anchor where it ends."""
    nodes = route_nodes(building, space_path, element_path)
    walks = []
    for index, (kind, node) in enumerate(nodes):
        if kind != "space":
            continue
        before = nodes[index - 1] if index > 0 and nodes[index - 1][0] == "door" else None
        after = nodes[index + 1] if index + 1 < len(nodes) and nodes[index + 1][0] == "door" else None
        if before and after:
            walks.append((node, DOOR_PREFIX + before[1], DOOR_PREFIX + after[1]))
        elif before:
            walks.append((node, DOOR_PREFIX + before[1], node))
        elif after:
            walks.append((node, node, DOOR_PREFIX + after[1]))
    return walks


def route_blocked(building: BuildingMap, live: LiveEffects, event: dict) -> list[str]:
    """Obstacle ids that now cut a walk of the route on the map (endpoints count as reached from any free door)."""
    space_path = event.get("space_path") or []
    if not space_path:
        return []
    endpoints = {space_path[0], space_path[-1]}
    cut = []
    try:
        walks = route_walks(building, space_path, event.get("element_path") or [])
    except (KeyError, StopIteration):
        return []
    for space_id, first, second in walks:
        cut += live.cut(space_id, first, second, endpoints) or []
    return list(dict.fromkeys(cut))


class SessionLive:
    """What a session (backend/agents/tools.py `session.live`) asks of its building's live world."""

    def __init__(self, hub: "LiveHub", building_id: str) -> None:
        self.hub = hub
        self.building_id = building_id

    def state(self) -> tuple[list[Obstacle], list[Hazard]]:
        return self.hub.state(self.building_id)

    def devices(self, spaces: set[str] | None = None) -> list[dict]:
        """The things as the Guide's live_status gives them; with `spaces`, only those standing in one of them or
        in no space (access mode: never one in a space the viewer may not see)."""
        world = self.hub.world(self.building_id, start=False)
        if world is None:
            return []
        keys = ("name", "label", "kind", "source", "state", "to", "left_s")
        return [{**{key: item[key] for key in keys if item.get(key) is not None},
                 "space": item["position"]["space"], "space_id": item["position"]["space_id"],
                 "floor": world.building.floor_name(item["position"]["floor_id"]),
                 **({"blocking": item["blocking"]["space"]} if item.get("blocking") else {}),
                 "reported_ago_s": item["reported_ago_s"]}
                for item in visible(world.snapshot()["devices"], spaces)]


def blocks(items: list[dict]) -> str:
    """"… blocks" / "… block" for what `names` says."""
    plural = len(items) > 1 or items[0]["name"].split(" · ")[0].endswith("s")
    return "block" if plural else "blocks"


def visible(devices: list[dict], spaces: set[str] | None) -> list[dict]:
    """Devices outside every space or in one of `spaces` (None = all)."""
    if spaces is None:
        return devices
    return [item for item in devices if item["position"]["space_id"] in spaces or item["position"]["space_id"] is None]


def names(items: list[dict]) -> str:
    return ", ".join(f"{item['name'].split(' · ')[0].lower() if item['kind'] in ('pallet', 'cart', 'pallet_jack') else item['name']}"
                     f"{' in ' + item['space'] if item.get('space') else ''}" for item in items)


def live_check(conversation, world: LiveWorld, save) -> dict:
    """The route on this viewer's map against what is reported now: `reroute` (a new route event, already in the
    session's events, when the route on the map just got cut), `alert` (cut with no way round; once per blocker set)
    or `suggestion` (a detour that is no longer needed). Skipped while a Guide turn holds the conversation."""
    session = conversation.session
    route = session.shown_route()
    if route is None or session.live is None:
        return {}
    request = route.get("request")  # what was asked: the route can be asked again (backend/agents/tools.py reroute)
    if not conversation.lock.acquire(blocking=False):
        return {}
    try:
        live = session.live_effects()
        blocked = route_blocked(session.building, live, route) if live is not None else []
        end = (request or {}).get("destination") or (route.get("space_path") or [None])[-1]
        destination = session.building.spaces.get(end, {}).get("name", "the exit" if end == "outside" else "there")
        if blocked:
            who = live.describe(blocked)
            new = session.reroute(request) if request else None
            if new and new.get("reachable"):
                start = new["from_space_id"]
                event = {"type": "route", "space_path": new["space_path"], "element_path": new["element_path"],
                         "length_m": new["length_m"], "profile": session.profile.describe(),
                         **session.start_point(start), **({"live": new["live"]} if new.get("live") else {}),
                         "reroute": {"by": who, "was_m": route.get("length_m")}, "request": request,
                         **({"next_building": route["next_building"]} if route.get("next_building") else {})}
                longer = round(new["length_m"] - (route.get("length_m") or new["length_m"]))
                message = (f"{names(who)[:1].upper()}{names(who)[1:]} now {blocks(who)} the way — new route to {destination}"
                           + (f", about {longer} m longer." if longer > 0 else "."))
                enriched = conversation.view.enrich(session, [event])[0]
                if not enriched.get("line"):  # a path the map can't draw: keep the route shown, say what blocks
                    return {"alert": {"by": who, "message": message}}
                session.events.append(event)
                conversation.guide.live_note = (f"[live note, from the app] {message} The map shows the new route "
                                                f"(about {round(new['length_m'])} m); the step card starts again.")
                try:
                    save(conversation)
                except Exception:  # noqa: BLE001 — a conflict only loses the note, the route is still sent
                    pass
                return {"reroute": {**enriched, "message": message}}
            key = (route.get("length_m"), tuple(sorted(blocked)))
            if getattr(session, "live_alerted", None) != key:
                session.live_alerted = key
                return {"alert": {"by": who, "message": f"{names(who)[:1].upper()}{names(who)[1:]} {blocks(who)} the way to "
                                                        f"{destination} and there is no way round right now. It usually "
                                                        "moves on soon."}}
            return {}
        if request and (route.get("live") or {}).get("avoided"):
            if time.time() - getattr(session, "live_suggest_at", 0.0) < SUGGEST_EVERY_S:
                return {}
            session.live_suggest_at = time.time()
            new = session.reroute(request)
            if new and new.get("reachable") and new["length_m"] < (route.get("length_m") or 0) - REROUTE_GAIN_M:
                blocking = blockers(session.building, live) if live is not None else {}
                gone = [item for item in route["live"]["avoided"] if item["id"] not in blocking]
                if gone:
                    return {"suggestion": {"message": f"The way past {names(gone)} is clear again — about "
                                                      f"{round(route['length_m'] - new['length_m'])} m shorter.",
                                           "save_m": round(route["length_m"] - new["length_m"], 1)}}
        return {}
    finally:
        conversation.lock.release()


def take_shorter(conversation) -> dict | None:
    """The viewer took the suggestion: the route on the map asked again under what is reported now, as a new
    route event."""
    session = conversation.session
    route = session.shown_route()
    request = (route or {}).get("request")
    new = session.reroute(request) if request else None
    if not new or not new.get("reachable"):
        return None
    event = {"type": "route", "space_path": new["space_path"], "element_path": new["element_path"],
             "length_m": new["length_m"], "profile": session.profile.describe(),
             **session.start_point(new["from_space_id"]), **({"live": new["live"]} if new.get("live") else {}),
             "request": request, **({"next_building": route["next_building"]} if route.get("next_building") else {})}
    session.events.append(event)
    return event


# ---------- HTTP ----------


class Control(BaseModel):
    building: str
    action: str  # speed, pause, resume, drop, clear, block_route, reset
    value: float | None = None
    floor: int | None = None
    x: float | None = None
    y: float | None = None
    session_id: str | None = None
    kind: str | None = None  # drop: pallet (default) or forklift


class Register(BaseModel):
    building: str
    name: str
    kind: str = "device"
    length_m: float = 1.0
    width_m: float = 0.8
    report_every_s: float = 1.0


class Report(BaseModel):
    floor_id: str
    x: float
    y: float
    heading_deg: float | None = None
    state: str | None = None  # moving (default), parked, …


class Shorter(BaseModel):
    session_id: str


def router(hub: LiveHub, known_or_422, conversation_or_404, save_or_409, hidden_spaces=lambda authorization, building: None,
           enabled: Callable[[], bool] = lambda: False, admin_or_403: Callable = lambda authorization: None) -> APIRouter:
    """`hidden_spaces(authorization, building)`: space ids this viewer may not see (access mode), or None.
    `enabled()`: access mode is on; then the demo controls and device registration need `admin_or_403(authorization)`
    (the building admin). With access mode off they stay open (demo)."""
    api = APIRouter()

    def admin_in_access_mode(authorization: str | None) -> None:
        if enabled():
            admin_or_403(authorization)

    @api.get("/live")
    def get_live(building: str, session_id: str | None = Query(None), authorization: str | None = Header(None)) -> dict:
        known_or_422(building)
        world = hub.world(building)
        clearance = WALKER_CLEARANCE_M
        conversation = None
        if session_id:
            try:
                conversation = conversation_or_404(session_id, authorization)
            except HTTPException:
                conversation = None
        if conversation is not None and conversation.building == building:
            clearance = conversation.session.live_clearance()
        snapshot = {**world.snapshot(clearance), "clearance_m": clearance}
        hidden = hidden_spaces(authorization, building)
        if hidden:  # access mode: nothing standing in, or wetting, a space this viewer may not see
            snapshot["devices"] = [item for item in snapshot["devices"] if item["position"]["space_id"] not in hidden]
            snapshot["hazards"] = [item for item in snapshot["hazards"] if not hidden_hazard(world, item, hidden)]
        if conversation is not None and conversation.building == building:
            snapshot.update(live_check(conversation, world, save_or_409))
        return snapshot

    @api.post("/live/shorter")
    def shorter(body: Shorter, authorization: str | None = Header(None)) -> dict:
        """Take the shorter route a cleared blockage opened (GET /live `suggestion`)."""
        conversation = conversation_or_404(body.session_id, authorization)
        with conversation.lock:
            event = take_shorter(conversation)
            if event is None:
                raise HTTPException(409, "no route right now")
            save_or_409(conversation)
            return {"events": conversation.view.enrich(conversation.session, [event])}

    @api.post("/live/control")
    def control(body: Control, authorization: str | None = Header(None)) -> dict:
        admin_in_access_mode(authorization)
        known_or_422(body.building)
        world = hub.world(body.building)
        with world.lock:
            if body.action == "speed":
                world.speed = max(0.25, min(8.0, body.value or 1.0))
            elif body.action == "pause":
                world.paused = True
            elif body.action == "resume":
                world.paused = False
            elif body.action == "clear":
                for device in [d for d in world.devices.values() if d.state == "left behind"]:
                    del world.devices[device.id]
                world.next_drop = world.time + 90
            elif body.action == "reset":
                with hub.lock:
                    hub.worlds.pop(body.building, None)
                world = hub.world(body.building)
            elif body.action == "drop":
                if body.floor is None or body.x is None or body.y is None:
                    raise HTTPException(422, "drop needs floor, x, y")
                floor_id = world.floor_ids.get(body.floor)
                if floor_id is None:
                    raise HTTPException(422, "unknown floor")
                device = drop(world, floor_id, body.x, body.y, body.kind or "pallet")
                if device is None:
                    raise HTTPException(422, "that point is not inside a room or corridor")
            elif body.action == "block_route":
                if not body.session_id:
                    raise HTTPException(422, "block_route needs session_id")
                conversation = conversation_or_404(body.session_id, authorization)
                route = conversation.session.shown_route()
                if route is None:
                    raise HTTPException(422, "no route on the map")
                spot = blocking_spot(world, conversation.session.building, route)
                if spot is None:
                    raise HTTPException(422, "no walkway on this route to block")
                floor_id, x, y, heading, across = spot
                world.leave_something((floor_id, x, y, heading), name="Pallets", length_m=1.2, width_m=across,
                                      kind="pallet", dropped=True)
            else:
                raise HTTPException(422, f"unknown action {body.action!r}")
            world._snapshot_cache = None
        return {"ok": True, "speed": world.speed, "paused": world.paused}

    @api.post("/live/devices")
    def register(body: Register, authorization: str | None = Header(None)) -> dict:
        """A real connected device joins a building's live world; its token is shown once. Access mode: admin only."""
        admin_in_access_mode(authorization)
        known_or_422(body.building)
        world = hub.world(body.building)
        token = secrets.token_urlsafe(18)
        with world.lock:
            device = Device(id=f"dev-{secrets.token_hex(4)}", name=body.name.strip()[:60] or "Device", kind="device",
                            source="device", floor_id=next(iter(world.floor_index)), x=0.0, y=0.0,
                            length_m=max(0.2, min(6.0, body.length_m)), width_m=max(0.2, min(4.0, body.width_m)),
                            report_s=max(0.2, body.report_every_s), state="parked",
                            token_hash=hashlib.sha256(token.encode()).hexdigest(), last_seen=time.time())
            world.devices[device.id] = device
        return {"id": device.id, "token": token}

    @api.post("/live/devices/{device_id}/report")
    def device_report(device_id: str, body: Report, building: str, x_device_token: str | None = Header(None)) -> dict:
        known_or_422(building)
        world = hub.world(building)
        with world.lock:
            device = world.devices.get(device_id)
            if device is None or device.source != "device":
                raise HTTPException(404, "unknown device")
            if not x_device_token or not secrets.compare_digest(hashlib.sha256(x_device_token.encode()).hexdigest(),
                                                                device.token_hash or ""):
                raise HTTPException(403, "wrong device token")
            if body.floor_id not in world.floor_index:
                raise HTTPException(422, "unknown floor_id")
            device.floor_id, device.x, device.y = body.floor_id, body.x, body.y
            device.heading = body.heading_deg or 0.0
            device.state = body.state or "moving"
            device.last_seen = time.time()
            world.report(device, force=True, at={"x": round(body.x, 3), "y": round(body.y, 3), "floor_id": body.floor_id,
                                                 "heading": device.heading})
        return {"ok": True}

    return api


def hidden_hazard(world: LiveWorld, hazard: dict, hidden: set[str]) -> bool:
    centre = outline(hazard["polygon"]).representative_point()
    return space_at(world.building, world.floor_ids.get(hazard["floor"], ""), centre.x, centre.y) in hidden


def drop(world: LiveWorld, floor_id: str, x: float, y: float, kind: str) -> Device | None:
    """The demo controls put something down at a point: pallets across the walkway there, or a parked forklift."""
    space_id = space_at(world.building, floor_id, x, y)
    if space_id is None:
        return None
    heading = walkway_heading(world.building, space_id, x, y)
    if kind == "forklift":
        device = world.add("forklift", f"Forklift FL-{len([d for d in world.devices.values() if d.kind == 'forklift']) + 1:02d}",
                           space_id, dropped=True)
        device.x, device.y, device.heading = x, y, heading
        device.pause_s, device.pause_state, device.state = world.random.uniform(60, 90), "loading", "loading"
        world.report(device, force=True)
        return device
    return world.leave_something((floor_id, x, y, heading), name="Pallet", length_m=1.2, width_m=0.8, kind="pallet",
                                 dropped=True)


def walkway_heading(building: BuildingMap, space_id: str, x: float, y: float) -> float:
    """Along the space's longer side at that point (a corridor's direction)."""
    rectangle = outline(building.spaces[space_id]["polygon"]).minimum_rotated_rectangle
    corners = list(rectangle.exterior.coords)
    edges = [(math.dist(a, b), math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))) for a, b in zip(corners, corners[1:])]
    return round(max(edges)[1], 1) if edges else 0.0


def blocking_spot(world: LiveWorld, building: BuildingMap, route: dict) -> tuple[str, float, float, float, float] | None:
    """Where pallets would cut the route on the map: the middle of its longest walk through a walkway (not its start
    or end space), with the width across that walkway there."""
    space_path = route.get("space_path") or []
    try:
        walks = route_walks(building, space_path, route.get("element_path") or [])
    except (KeyError, StopIteration):
        return None
    best = None
    for space_id, first, second in walks:
        if space_id in (space_path[0], space_path[-1]) or not (first.startswith(DOOR_PREFIX) and second.startswith(DOOR_PREFIX)):
            continue
        a = tuple(building.openings[first.removeprefix(DOOR_PREFIX)]["position"])
        b = tuple(building.openings[second.removeprefix(DOOR_PREFIX)]["position"])
        polygon = outline(building.spaces[space_id]["polygon"])
        points = [door_landing(polygon, a), *corners_inside(building.spaces[space_id]["polygon"], a, b), door_landing(polygon, b)]
        for p, q in zip(points, points[1:]):
            length = math.dist(p, q)
            if best is None or length > best[0]:
                best = (length, space_id, p, q)
    if best is None or best[0] < 2.5:
        return None
    _, space_id, p, q = best
    x, y = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    heading = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
    polygon = outline(building.spaces[space_id]["polygon"])
    normal = (-math.sin(math.radians(heading)), math.cos(math.radians(heading)))
    cross = LineString([(x - normal[0] * 50, y - normal[1] * 50), (x + normal[0] * 50, y + normal[1] * 50)]).intersection(polygon)
    pieces = list(getattr(cross, "geoms", [cross]))
    here = Point(x, y)
    piece = min(pieces, key=lambda item: item.distance(here)) if pieces else None
    width = piece.length if piece is not None and not piece.is_empty else 2.4
    if width > 6:  # a hall: pallets can't cut it, a row of them still makes people go round
        width = 6
    centre = piece.centroid if piece is not None and not piece.is_empty else here
    return building.spaces[space_id]["floor_id"], round(centre.x, 3), round(centre.y, 3), round(heading, 1), round(max(0.8, width - 0.3), 2)
