"""HTTP for the living building: GET /live (snapshot + route re-check), the demo controls, and real devices
(register, report)."""

import hashlib
import math
import secrets
import time
from typing import Callable

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from backend.core.building_map import BuildingMap, outline
from backend.core.fleet import space_at
from backend.core.live import WALKER_CLEARANCE_M

from backend.api.live.hub import LiveHub
from backend.api.live.reroute import blocking_spot, live_check, take_shorter
from backend.api.live.world import Device, LiveWorld


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
