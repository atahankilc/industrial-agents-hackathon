"""A building from floor plans: /imports/stream runs the Creator (backend/agents/creator.py) on uploaded plans and
opens its building as a draft on a private base `import/<id>`; the draft's place on the map (fit onto an OSM
footprint, set by hand) and the straightened plans it came from."""

import json
import queue
import threading

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from shapely.geometry import Point as ShapelyPoint, Polygon as ShapelyPolygon

from backend.agents.creator import Creator
from backend.agents.creator_tools import ImportSession
from backend.api import deps
from backend.api.deps import draft_or_404
from backend.core import osm_lookup
from backend.core.edits import EditError, apply_op
from backend.core.geoplace import Placement, distance_m, location_for, place as place_on_map, placement_ops
from backend.core.plan_import.ingest import load_sources, median_gps
from backend.core.plan_import.reference import reference_for

router = APIRouter()


MAX_IMPORT_FILES = 20
MAX_IMPORT_BYTES = 25 * 1024 * 1024  # per file


def make_creator(session: ImportSession) -> Creator:
    return Creator(session)


@router.post("/imports/stream")
def import_stream(files: list[UploadFile] = File(...), place: str | None = Form(None),
                  device: str | None = Form(None), draft: str | None = Form(None),
                  levels: str | None = Form(None)) -> StreamingResponse:
    """Floor plans (PDF / images) → the Creator → a draft on a private base `import/<id>`, as NDJSON:
    {"type": "warning", "detail"} per unreadable file, {"type": "step", …} while the Creator works, then one of
    {"type": "done", "draft_id", "base", "name", "issues", "notes"}, {"type": "no_plan", "reason"} or
    {"type": "error", "detail"}. `place` (JSON, optional): where on the map the building stands — {"ring": [[lon, lat],
    …]} (the tapped OSM footprint, fitted onto) or {"point": [lon, lat]}; the `done` line then carries `location`.
    Without a tap the building goes where the photos were taken (EXIF GPS; else `device`, the browser's {"lat",
    "lon"} at upload), fitted onto the OSM building there (backend/core/osm_lookup.py) when one is found; with a tap far from
    that position the `done` line adds `suggestion` ({"ring", "name"}: the building the photos point at).
    `located_by`: "tap" | "photos" | "device" | null. `levels` (JSON list, one int per file, all different): the floor
    each file is, as the user said — the Creator registers each file at that level. `draft` (an open draft's id, Edit
    mode's "Add a floor"): the new floors go into that draft as one undo step (edit op `add_floors`, laid onto the
    building, backend/core/plan_import/merge.py); a level the draft already has → 422; the `done` line names that draft."""
    where = place_or_422(place)
    target = draft_or_404(draft) if draft else None
    given = levels_or_422(levels, len(files))
    if target is not None and given is not None:
        have = {floor["level"] for floor in deps.drafts.building(target)["floors"]}
        if clash := sorted(have & set(given)):
            raise HTTPException(422, f"the building already has floor {', '.join(map(str, clash))}; pick another level")
    browser = device_or_none(device)
    if len(files) > MAX_IMPORT_FILES:
        raise HTTPException(413, f"at most {MAX_IMPORT_FILES} files per import")
    uploads = []
    for upload in files:
        data = upload.file.read(MAX_IMPORT_BYTES + 1)
        if len(data) > MAX_IMPORT_BYTES:
            raise HTTPException(413, f"{upload.filename}: larger than {MAX_IMPORT_BYTES // (1024 * 1024)} MB")
        uploads.append((upload.filename or "upload", data))
    lines: queue.Queue[dict | None] = queue.Queue()
    cancel = threading.Event()  # the client went away: the Creator stops and no draft is made

    def work() -> None:
        try:
            sources, warnings = load_sources(uploads, given)
            found = median_gps([data for _, data in uploads])
            gps = (found[0], found[1]) if found else None
            for warning in warnings:
                lines.put({"type": "warning", "detail": warning})
            if not sources:
                lines.put({"type": "error", "detail": "no readable PDF or image among the files"})
                return
            session = ImportSession(sources, warnings)
            creator = make_creator(session)
            creator.cancel = cancel
            creator.on_step = lambda step: lines.put({"type": "step", **step})
            result = creator.run()
            if cancel.is_set() or result.status == "cancelled":
                return
            if result.status == "no_plan":
                lines.put({"type": "no_plan", "reason": result.reason})
            elif result.status != "done" or result.building is None:
                lines.put({"type": "error", "detail": result.reason or "the import did not finish"})
            else:
                notes = result.building["building"]["source_ref"]["import"]["floors"]
                for level, floor in session.floors.items():  # the straightened plans, for Edit mode's reference panel
                    if str(level) in notes and floor.image is not None and floor.transform is not None:
                        notes[str(level)]["reference"] = reference_for(floor)
                if target is not None:  # new floors of the building being edited
                    deps.drafts.apply(target, [{"op": "add_floors", "building_with_floors": result.building}])
                    lines.put({"type": "done", "draft_id": target.id, "base": target.base, "name": target.name,
                               "issues": deps.drafts.issues(target), "notes": strip_import_images(
                                   result.building["building"]["source_ref"].get("import")),
                               "location": None, "located_by": None, "suggestion": None})
                    return
                building, located_by, suggestion = locate_import(result.building, where, gps or browser,
                                                                 "photos" if gps else "device" if browser else None)
                draft = deps.drafts.create_import(building)
                lines.put({"type": "done", "draft_id": draft.id, "base": draft.base, "name": draft.name,
                           "issues": deps.drafts.issues(draft),
                           "notes": strip_import_images(building["building"]["source_ref"].get("import")),
                           "location": building["building"].get("location"), "located_by": located_by,
                           "suggestion": suggestion})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put({"type": "error", "detail": f"{type(error).__name__}: {error}"[:300]})
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        try:
            while (line := lines.get()) is not None:
                yield json.dumps(line, ensure_ascii=False) + "\n"
        finally:  # also on GeneratorExit: the client disconnected or the screen was left
            cancel.set()

    return StreamingResponse(stream(), media_type="application/x-ndjson")


def levels_or_422(levels: str | None, files: int) -> list[int] | None:
    """The floor of each uploaded file (JSON list of ints, one per file, all different), or None when not given."""
    if not levels:
        return None
    try:
        given = json.loads(levels)
        if not isinstance(given, list) or not all(isinstance(level, int) and not isinstance(level, bool) for level in given):
            raise ValueError("a list of whole numbers")
    except ValueError as error:
        raise HTTPException(422, f"levels must be a JSON list of floor numbers ({error})") from None
    if len(given) != files:
        raise HTTPException(422, f"levels: {len(given)} given for {files} files — one floor number per file")
    if len(set(given)) != len(given):
        raise HTTPException(422, "levels: each file must be a different floor")
    return given


def place_or_422(place: str | None) -> dict | None:
    """{"ring": [[lon, lat], ≥ 3 points]} or {"point": [lon, lat]} → keyword arguments of backend.core.geoplace.place."""
    if not place:
        return None
    try:
        data = json.loads(place)
        if "ring" in data:
            ring = [[float(lon), float(lat)] for lon, lat in data["ring"]]
            if len({tuple(point) for point in ring}) < 3:
                raise ValueError("a ring needs at least 3 points")
            return {"ring": ring}
        lon, lat = data["point"]
        return {"point": [float(lon), float(lat)]}
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, f"place must be {{'ring': [[lon, lat], …]}} or {{'point': [lon, lat]}} ({error})") from None


def device_or_none(device: str | None) -> tuple[float, float] | None:
    """The browser's position sent with an import ({"lat", "lon"}); None when absent or malformed (it is optional)."""
    try:
        data = json.loads(device) if device else None
        return (float(data["lat"]), float(data["lon"])) if data else None
    except (ValueError, TypeError, KeyError):
        return None


MISMATCH_M = 50  # the photos' position this far from the tapped building (and outside it) = another building


def locate_import(building: dict, where: dict | None, position: tuple[float, float] | None,
                  source: str | None) -> tuple[dict, str | None, dict | None]:
    """(placed building, how it was located, a suggestion when the tap and the photos disagree)."""
    if where:
        placed = place_on_map(building, **where)
        if position is None:
            return placed, "tap", None
        if "ring" in where:
            ring = ShapelyPolygon(where["ring"])
            near = ring.contains(ShapelyPoint(position[1], position[0])) or distance_m(
                position, (ring.centroid.y, ring.centroid.x)) <= MISMATCH_M
        else:
            near = distance_m(position, (where["point"][1], where["point"][0])) <= MISMATCH_M
        if near:
            return placed, "tap", None
        other = osm_lookup.building_at(*position)
        suggestion = {"ring": other["ring"], "name": other.get("name")} if other else {"point": [position[1], position[0]], "name": None}
        return placed, "tap", suggestion
    if position is None:
        return building, None, None
    found = osm_lookup.building_at(*position)
    if found:
        return place_on_map(building, ring=found["ring"], address=found.get("name")), source, None
    return place_on_map(building, point=[position[1], position[0]]), source, None


class DraftFit(BaseModel):
    ring: list[list[float]]
    name: str | None = None


@router.post("/drafts/{draft_id}/fit")
def draft_fit(draft_id: str, body: DraftFit) -> dict:
    """Fit the draft's building onto another OSM footprint (the "did you mean" building): one undo step."""
    draft = draft_or_404(draft_id)
    where = place_or_422(json.dumps({"ring": body.ring}))
    try:
        deps.drafts.apply(draft, placement_ops(deps.drafts.building(draft), ring=where["ring"], address=body.name))
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    return deps.drafts.state(draft)


def strip_import_images(notes: dict | None) -> dict | None:
    """The import notes without the reference images (they are served by /drafts/{id}/references)."""
    if not notes:
        return notes
    floors = {level: {key: value for key, value in floor.items() if key != "reference"}
              for level, floor in notes.get("floors", {}).items()}
    return {**notes, "floors": floors}


class DraftLocation(BaseModel):
    origin: dict
    bearing_deg: float
    scale: float = 1.0


@router.put("/drafts/{draft_id}/location")
def draft_location(draft_id: str, body: DraftLocation) -> dict:
    """Where the building stands on the map, set by hand (move / rotate / scale over the OSM footprint): one undo
    step of `scale_building` (when the scale changes) + `set_location`. Scale per call within 0.75–1.25."""
    draft = draft_or_404(draft_id)
    if not 0.75 <= body.scale <= 1.25:
        raise HTTPException(422, "scale must be within 0.75–1.25 (the map fit corrects the import's scale by ±25 % at most)")
    try:
        origin = {"lat": float(body.origin["lat"]), "lon": float(body.origin["lon"])}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "origin must be {lat, lon}") from None
    ops = [] if abs(body.scale - 1.0) < 1e-6 else [{"op": "scale_building", "factor": body.scale}]
    building = deps.drafts.building(draft)
    for operation in ops:
        building = apply_op(building, operation)
    previous = building["building"].get("location") or {}
    location = location_for(building, Placement(origin, body.bearing_deg % 360, 1.0, 0.0, False),
                            address=previous.get("address"))
    location["fit"] = {"scale": body.scale, "by_hand": True}
    if previous.get("supersedes"):
        location["supersedes"] = previous["supersedes"]
    try:
        deps.drafts.apply(draft, [*ops, {"op": "set_location", "location": location}])
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    return deps.drafts.state(draft)


@router.get("/drafts/{draft_id}/references")
def draft_references(draft_id: str) -> dict:
    """The import's straightened plan per floor (image data URL + 2×3 px → metres transform) for Edit mode's
    reference panel and trace; empty for buildings that did not come from an import."""
    return {"floors": deps.drafts.references(draft_or_404(draft_id))}
