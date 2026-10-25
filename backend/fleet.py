"""Moving objects over HTTP (access mode only; core/fleet.py does the routing and the mission steps).

  admin:   POST /objects {building, name, kind, attributes, position?} → the object + its device token (shown once)
           PUT /objects/{id}, DELETE /objects/{id}, POST /objects/import-forklifts {building}
           POST /objects/{id}/mission {destination} (dispatch), DELETE /objects/{id}/mission (cancel)
  device:  POST /objects/{id}/position {floor_id, x, y, heading_deg?}, GET /objects/{id}/mission,
           POST /objects/{id}/mission/done — header `X-Object-Token`
  viewers: GET /objects?building=… — positions, trails and remaining mission lines for the plan view (polled);
           objects standing in a space the viewer may not enter are left out.

Objects live in `fleet_objects` (supabase/migrations/20261025200000_access.sql) or in memory. Multi-object path
conflicts are not handled (design "Later")."""

import copy
import hashlib
import secrets
import threading
import time
import uuid
from typing import Callable

from fastapi import APIRouter, Header, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from backend.persistence import PostgresConnection, db_url
from core.building_map import BuildingMap, MapError
from core.fleet import KINDS, Attributes, mission, space_at
from core.routeline import route_line

TRAIL_POINTS = 120  # last positions kept per object (≈ 2 min at one post per second)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class MemoryFleet:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.lock = threading.Lock()

    def get(self, object_id: str) -> dict | None:
        with self.lock:
            row = self.rows.get(object_id)
            return copy.deepcopy(row) if row else None

    def list(self, building: str) -> list[dict]:
        with self.lock:
            return [copy.deepcopy(row) for row in self.rows.values() if row["building"] == building]

    def put(self, row: dict) -> None:
        with self.lock:
            self.rows[row["id"]] = copy.deepcopy(row)

    def delete(self, object_id: str) -> None:
        with self.lock:
            self.rows.pop(object_id, None)


class PostgresFleet(PostgresConnection):
    COLUMNS = ("id", "building", "name", "kind", "attributes", "token_hash", "position", "trail", "mission")

    def row(self, values: tuple) -> dict:
        return dict(zip(self.COLUMNS, values))

    def get(self, object_id: str) -> dict | None:
        rows = self.execute(f"select {', '.join(self.COLUMNS)} from fleet_objects where id = %s", (object_id,))
        return self.row(rows[0]) if rows else None

    def list(self, building: str) -> list[dict]:
        rows = self.execute(f"select {', '.join(self.COLUMNS)} from fleet_objects where building = %s order by name",
                            (building,))
        return [self.row(values) for values in rows]

    def put(self, row: dict) -> None:
        json_columns = ("attributes", "position", "trail", "mission")
        values = [Jsonb(row[column]) if column in json_columns else row[column] for column in self.COLUMNS]
        self.execute(
            f"insert into fleet_objects ({', '.join(self.COLUMNS)}) values ({', '.join(['%s'] * len(self.COLUMNS))}) "
            "on conflict (id) do update set name = excluded.name, kind = excluded.kind, attributes = "
            "excluded.attributes, position = excluded.position, trail = excluded.trail, mission = excluded.mission, "
            "updated_at = now()", tuple(values))

    def delete(self, object_id: str) -> None:
        self.execute("delete from fleet_objects where id = %s", (object_id,))


def fleet_from_env() -> MemoryFleet | PostgresFleet:
    url = db_url()
    return PostgresFleet(url) if url else MemoryFleet()


class NewObject(BaseModel):
    building: str
    name: str
    kind: str = "robot"
    attributes: dict
    position: dict | None = None  # {floor_id, x, y, heading_deg?}


class ObjectUpdate(BaseModel):
    name: str | None = None
    attributes: dict | None = None


class Position(BaseModel):
    floor_id: str
    x: float
    y: float
    heading_deg: float | None = None


class Dispatch(BaseModel):
    destination: str


class BuildingRef(BaseModel):
    building: str


class Fleet:
    """Object rows + what the endpoints and the Guide's send_object tool share."""

    def __init__(self, store: MemoryFleet | PostgresFleet, building_data: Callable[[str], dict]) -> None:
        self.store = store
        self.building_data = building_data
        self.maps: dict[str, BuildingMap] = {}
        self.lock = threading.Lock()

    def building(self, building: str) -> BuildingMap:
        with self.lock:
            if building not in self.maps:
                self.maps[building] = BuildingMap(copy.deepcopy(self.building_data(building)))
            return self.maps[building]

    def floor_index(self, building: str) -> dict[str, int]:
        floors = sorted(self.building(building).floors.values(), key=lambda floor: floor["level"])
        return {floor["id"]: index for index, floor in enumerate(floors)}

    def create(self, body: NewObject) -> tuple[dict, str]:
        if body.kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        attributes = Attributes.from_dict(body.attributes)
        token = secrets.token_urlsafe(24)
        row = {"id": "obj-" + uuid.uuid4().hex[:10], "building": body.building, "name": body.name.strip()[:80] or
               body.kind, "kind": body.kind, "attributes": attributes.to_dict(), "token_hash": token_hash(token),
               "position": None, "trail": [], "mission": None}
        if body.position:
            self.move(row, Position(**body.position))
        self.store.put(row)
        return row, token

    def move(self, row: dict, position: Position) -> None:
        building = self.building(row["building"])
        if position.floor_id not in building.floors:
            raise ValueError(f"unknown floor {position.floor_id}")
        row["position"] = {"floor_id": position.floor_id, "x": round(position.x, 3), "y": round(position.y, 3),
                           "heading_deg": position.heading_deg, "t": time.time(),
                           "space_id": space_at(building, position.floor_id, position.x, position.y)}
        row["trail"] = (row.get("trail") or [])[-(TRAIL_POINTS - 1):] + [
            [round(position.x, 3), round(position.y, 3), position.floor_id]]

    def dispatch(self, row: dict, destination: str) -> dict:
        """Plan and store a mission from the object's current space; the result says why when there is none."""
        building = self.building(row["building"])
        start = (row.get("position") or {}).get("space_id")
        if not start:
            raise ValueError(f"{row['name']} has no known position inside the building yet")
        target = building.resolve_space(destination)
        planned = mission(building, row["kind"], Attributes.from_dict(row["attributes"]), start, target)
        if not planned["reachable"]:
            return {"reachable": False, "object": row["name"], "reason": planned["reason"]}
        version = ((row.get("mission") or {}).get("version") or 0) + 1
        row["mission"] = {
            "mission_id": "m-" + uuid.uuid4().hex[:8], "version": version, "object_id": row["id"], "status": "active",
            "to": {"space_id": target, "name": building.spaces[target]["name"]}, "length_m": planned["length_m"],
            "steps": planned["steps"],
            "line": route_line(building, planned["space_path"], planned["element_path"]),
        }
        self.store.put(row)
        return {"reachable": True, "object": row["name"], "to": row["mission"]["to"]["name"],
                "length_m": planned["length_m"], "steps": len(planned["steps"])}

    def public(self, row: dict, with_token: str | None = None) -> dict:
        index = self.floor_index(row["building"])
        position = row.get("position")
        item = {key: row[key] for key in ("id", "building", "name", "kind", "attributes")}
        item["position"] = {**position, "floor": index.get(position["floor_id"])} if position else None
        item["trail"] = [[x, y, index.get(floor_id)] for x, y, floor_id in row.get("trail") or []]
        item["mission"] = row.get("mission")
        if with_token:
            item["token"] = with_token
        return item


def router(fleet: Fleet, enabled: Callable[[], bool], admin_or_403: Callable, viewer_restricted: Callable,
           known_or_422: Callable) -> APIRouter:
    """`viewer_restricted(authorization, building)` → (viewer, restricted space ids) for listing."""
    api = APIRouter()

    def on() -> None:
        if not enabled():
            raise HTTPException(404, "access mode is off")

    def object_or_404(object_id: str) -> dict:
        row = fleet.store.get(object_id)
        if row is None:
            raise HTTPException(404, f"unknown object {object_id!r}")
        return row

    def device_or_403(object_id: str, token: str | None) -> dict:
        row = object_or_404(object_id)
        if not token or not secrets.compare_digest(token_hash(token), row["token_hash"]):
            raise HTTPException(403, "wrong object token")
        return row

    @api.get("/objects")
    def list_objects(building: str, authorization: str | None = Header(None)) -> list[dict]:
        on()
        viewer, restricted = viewer_restricted(authorization, building)
        rows = fleet.store.list(building)
        if not viewer.admin:
            rows = [row for row in rows if (row.get("position") or {}).get("space_id") not in restricted]
        return [fleet.public(row) for row in rows]

    @api.post("/objects")
    def create_object(body: NewObject, authorization: str | None = Header(None)) -> dict:
        on()
        admin_or_403(authorization)
        known_or_422(body.building)
        try:
            row, token = fleet.create(body)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from None
        return fleet.public(row, with_token=token)

    @api.post("/objects/import-forklifts")
    def import_forklifts(body: BuildingRef, authorization: str | None = Header(None)) -> list[dict]:
        """The building's forklift assets (equipment.csv) as objects at their asset position; vehicle width = the
        narrow side of the footprint (the forklift rule's 3 m openings apply on top)."""
        on()
        admin_or_403(authorization)
        known_or_422(body.building)
        existing = {row["name"] for row in fleet.store.list(body.building)}
        created = []
        for asset in fleet.building(body.building).assets.values():
            if asset.get("type") != "forklift" or asset["name"] in existing:
                continue
            footprint = asset.get("footprint") or {}
            width = min(footprint.get("width_m") or 1.2, footprint.get("depth_m") or 1.2)
            x, y = asset["position"]
            row, token = fleet.create(NewObject(
                building=body.building, name=asset["name"], kind="forklift", attributes={"width_m": width},
                position={"floor_id": asset["floor_id"], "x": x, "y": y,
                          "heading_deg": footprint.get("rotation_deg")}))
            created.append(fleet.public(row, with_token=token))
        return created

    @api.put("/objects/{object_id}")
    def update_object(object_id: str, body: ObjectUpdate, authorization: str | None = Header(None)) -> dict:
        on()
        admin_or_403(authorization)
        row = object_or_404(object_id)
        try:
            if body.attributes is not None:
                row["attributes"] = Attributes.from_dict(body.attributes).to_dict()
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from None
        if body.name:
            row["name"] = body.name.strip()[:80]
        fleet.store.put(row)
        return fleet.public(row)

    @api.delete("/objects/{object_id}")
    def delete_object(object_id: str, authorization: str | None = Header(None)) -> dict:
        on()
        admin_or_403(authorization)
        fleet.store.delete(object_or_404(object_id)["id"])
        return {"deleted": object_id}

    @api.post("/objects/{object_id}/mission")
    def dispatch(object_id: str, body: Dispatch, authorization: str | None = Header(None)) -> dict:
        on()
        admin_or_403(authorization)
        row = object_or_404(object_id)
        try:
            result = fleet.dispatch(row, body.destination)
        except (MapError, ValueError, KeyError) as error:
            raise HTTPException(422, str(error.args[0]) if error.args else "unknown place") from None
        return {**result, "object": fleet.public(fleet.store.get(object_id) or row)}

    @api.delete("/objects/{object_id}/mission")
    def cancel(object_id: str, authorization: str | None = Header(None)) -> dict:
        on()
        admin_or_403(authorization)
        row = object_or_404(object_id)
        if row.get("mission"):
            row["mission"] = {**row["mission"], "status": "cancelled",
                              "version": row["mission"]["version"] + 1, "steps": []}
            fleet.store.put(row)
        return fleet.public(row)

    @api.post("/objects/{object_id}/position")
    def post_position(object_id: str, body: Position, x_object_token: str | None = Header(None)) -> dict:
        on()
        row = device_or_403(object_id, x_object_token)
        try:
            fleet.move(row, body)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        fleet.store.put(row)
        return {"ok": True, "space_id": row["position"]["space_id"],
                "mission_version": (row.get("mission") or {}).get("version")}

    @api.get("/objects/{object_id}/mission")
    def get_mission(object_id: str, x_object_token: str | None = Header(None)) -> dict:
        on()
        mission_ = device_or_403(object_id, x_object_token).get("mission")
        if not mission_:
            return {"status": "idle"}
        return {key: value for key, value in mission_.items() if key != "line"}

    @api.post("/objects/{object_id}/mission/done")
    def mission_done(object_id: str, x_object_token: str | None = Header(None)) -> dict:
        on()
        row = device_or_403(object_id, x_object_token)
        if row.get("mission"):
            row["mission"] = {**row["mission"], "status": "done"}
            fleet.store.put(row)
        return {"status": "done"}

    return api
