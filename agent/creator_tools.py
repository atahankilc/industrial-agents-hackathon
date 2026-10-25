"""The Creator's tools (docs/superpowers/specs/2026-10-25-plan-import-design.md): every plan-import stage behind a
tool, so the agent decides *what* to do (which page, which segmentation, what each cell is) and code does the
geometry and checks every answer. Results are tool_result content blocks: one JSON text block, plus a PNG when there
is something to look at. Errors are a single text block `{"error": …}`.

Code keeps the skeleton: one plan per level (unless `replace`), `finish` refuses unlabelled floors and gives the
agent exactly one chance to repair validation errors before it accepts the building as it is; `no_plan` only while
no floor is registered."""

import base64
import json
import uuid
from dataclasses import dataclass, field

import cv2
import numpy as np

from core.plan_import.assemble import assemble, autofix, check
from core.plan_import.cells import carve, cells_from_boxes, render_cells, segment_colours, segment_walls
from core.plan_import.ingest import MODEL_MAX_SIDE, contact_sheet, grid_view, png
from core.plan_import.labels import apply_labels, kept, render_labels
from core.plan_import.model import FloorPlan, Source
from core.plan_import.prepare import crop, rectify, wall_mask
from core.plan_import.scale import ensure_scales, scale_from_bar, scale_from_doors, scale_prior
from core.plan_import.stack import align, connectors

SOURCE_TEXT = 600
VIEW_TEXT = 4000


@dataclass
class ImportSession:
    sources: list[Source]
    warnings: list[str] = field(default_factory=list)
    floors: dict[int, FloorPlan] = field(default_factory=dict)
    label_sources: dict[int, list[str]] = field(default_factory=dict)
    finished: dict | None = None  # {"building", "issues"}
    no_plan: str | None = None
    finish_attempts: int = 0


def text(payload: dict) -> dict:
    return {"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}


def image(data: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.b64encode(data).decode("ascii")}}


class ToolError(Exception):
    pass


BOX = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
       "description": "[x0, y0, x1, y1], normalised 0–1 (read off the grid)"}
POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
LEVEL = {"type": "integer", "description": "0 = ground, 1 = first upper floor, -1 = first basement"}

CREATOR_TOOLS = [
    {"name": "list_sources", "description": "Contact sheets of every uploaded page / image with its id, plus each "
     "source's size and the first lines of its text (PDFs). Start here.", "input_schema": {"type": "object",
                                                                                         "properties": {}}},
    {"name": "view_source", "description": "One source at full model resolution with a 0–1 grid (to read a plan's "
     "box, a legend, room names, a scale bar), plus its full text.",
     "input_schema": {"type": "object", "properties": {"source_id": {"type": "string"}}, "required": ["source_id"]}},
    {"name": "register_plan", "description": "Use the floor plan drawn in `bbox` of a source as the plan of `level`: "
     "flattens a photographed sheet (photo=true; give `corners` of the sheet if the automatic flattening is wrong), "
     "crops, splits it into numbered cells along the walls. Returns the cells drawn over the plan and the red door "
     "candidates d1, d2, … One plan per level; replace=true swaps it.",
     "input_schema": {"type": "object", "properties": {
         "source_id": {"type": "string"}, "level": LEVEL,
         "floor_name": {"type": "string", "description": "the floor's name as written on the plan"},
         "bbox": BOX, "photo": {"type": "boolean"},
         "corners": {"type": "array", "items": POINT, "minItems": 4, "maxItems": 4,
                     "description": "sheet corners TL, TR, BR, BL, normalised in the source"},
         "label_sources": {"type": "array", "items": {"type": "string"},
                           "description": "other sources that name this floor's rooms (legend, signs)"},
         "replace": {"type": "boolean"}},
         "required": ["source_id", "level", "floor_name", "bbox", "photo"]}},
    {"name": "segment", "description": "Split a registered floor again. method=walls (dark wall lines; gap_px = "
     "widest door gap to close, dark = wall darkness cut-off 0–255) or colours (rooms drawn as coloured fills split by "
     "thin lines). Clears the floor's labels.",
     "input_schema": {"type": "object", "properties": {
         "level": LEVEL, "method": {"type": "string", "enum": ["walls", "colours"]},
         "gap_px": {"type": "integer"}, "dark": {"type": "integer"}}, "required": ["level", "method"]}},
    {"name": "coarse_rooms", "description": "Last resort when neither segmentation works: give one box per room "
     "(normalised in the registered plan, read off its grid); they become the floor's cells, ids in box order. The "
     "floor is marked low confidence.",
     "input_schema": {"type": "object", "properties": {"level": LEVEL, "boxes": {"type": "array", "items": BOX}},
                      "required": ["level", "boxes"]}},
    {"name": "add_rooms", "description": "Cut rooms the segmentation merged out of one cell: one box per room "
     "(normalised in the registered plan). They become new cells; the rest stays the old cell. cell=0 adds rooms "
     "where there is no cell yet (open rooms the walls did not close, e.g. a foyer without a front wall).",
     "input_schema": {"type": "object", "properties": {"level": LEVEL, "cell": {"type": "integer"},
                                                       "boxes": {"type": "array", "items": BOX}},
                      "required": ["level", "cell", "boxes"]}},
    {"name": "label_cells", "description": "Say what each cell is. Every kept cell needs a label (or merge it, or mark "
     "it outside). Calls add up; send fixes only. doors: the full list of doors between cells as \"d<n>\" (a red "
     "candidate) or [cell, cell] — omit to keep the current doors (at first: all candidates). entrances: cells with a "
     "door to outside (omit to keep the candidates to outside). Returns the labelled plan and the problems left.",
     "input_schema": {"type": "object", "properties": {
         "level": LEVEL,
         "cells": {"type": "array", "items": {"type": "object", "properties": {
             "cell": {"type": "integer"}, "action": {"type": "string", "enum": ["room", "merge", "outside"]},
             "into": {"type": "integer"},
             "type": {"type": "string", "enum": ["room", "corridor", "stair", "lift", "hall", "outdoor"]},
             "room_type": {"type": "string"}, "name": {"type": "string"}, "ref": {"type": "string"}},
             "required": ["cell"]}},
         "doors": {"type": "array", "items": {}}, "entrances": {"type": "array", "items": {"type": "integer"}}},
         "required": ["level", "cells"]}},
    {"name": "set_scale", "description": "Metres per pixel of a floor. method=bar: p0, p1 = the ends of a scale bar or "
     "a dimension line (normalised in the registered plan) and its length_m. method=doors: from the door gaps. "
     "method=prior: typical room size. Floors without a scale get doors → same sheet → prior at stack/finish.",
     "input_schema": {"type": "object", "properties": {
         "level": LEVEL, "method": {"type": "string", "enum": ["bar", "doors", "prior"]},
         "p0": POINT, "p1": POINT, "length_m": {"type": "number"}}, "required": ["level", "method"]}},
    {"name": "stack_floors", "description": "Put all floors in one frame (registered on their outlines) and join "
     "stairs / lifts across floors. Returns the outlines overlaid and the connectors found.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "finish", "description": "Build and check the building. If there are errors the first call returns them "
     "(fix with label_cells, e.g. label stairs on every floor or add a door, then call finish again); the second call "
     "accepts the building with what is left.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string",
                                                                 "description": "the building's name"}},
                      "required": ["name"]}},
    {"name": "no_plan", "description": "End without a building: none of the files shows a floor plan.",
     "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}},
]


class CreatorTools:
    def __init__(self, session: ImportSession) -> None:
        self.session = session

    def call(self, name: str, args: dict) -> list[dict]:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None or name not in {tool["name"] for tool in CREATOR_TOOLS}:
            return [text({"error": f"unknown tool {name!r}"})]
        try:
            return handler(**args)
        except ToolError as error:
            return [text({"error": str(error)})]
        except TypeError as error:  # missing / unexpected arguments
            return [text({"error": f"bad arguments for {name}: {error}"})]
        except Exception as error:  # geometry libraries can fail on odd input; tell the model, don't end the import
            return [text({"error": f"{name} failed: {type(error).__name__}: {error}"[:500]})]

    # ---------- helpers ----------

    def source(self, source_id: str) -> Source:
        for source in self.session.sources:
            if source.id == source_id:
                return source
        raise ToolError(f"no source {source_id!r}; see list_sources")

    def floor(self, level) -> FloorPlan:
        floor = self.session.floors.get(level)
        if floor is None:
            raise ToolError(f"no plan registered for level {level}; registered: {sorted(self.session.floors)}")
        return floor

    @staticmethod
    def to_px(floor: FloorPlan, box) -> tuple[float, float, float, float]:
        height, width = floor.image.shape[:2]
        x0, y0, x1, y1 = (float(v) for v in box)
        return x0 * width, y0 * height, x1 * width, y1 * height

    def cells_result(self, floor: FloorPlan, extra: dict | None = None) -> list[dict]:
        summary = {"level": floor.level, "method": floor.seg.method, "cells": len(kept(floor)),
                   "door_candidates": len(floor.seg.doors), "size_px": [floor.image.shape[1], floor.image.shape[0]],
                   **(extra or {})}
        return [text(summary), image(render_cells(floor.image, floor.seg))]

    @staticmethod
    def reset(floor: FloorPlan) -> None:
        floor.labels, floor.doors, floor.carved = {}, [], []
        floor.transform = floor.alignment = None

    # ---------- tools ----------

    def tool_list_sources(self) -> list[dict]:
        listing = [{"id": source.id, "origin": source.origin, "size_px": [source.image.shape[1], source.image.shape[0]],
                    "text": source.text[:SOURCE_TEXT]} for source in self.session.sources]
        blocks = [text({"sources": listing, "warnings": self.session.warnings})]
        return blocks + [image(sheet) for sheet in contact_sheet(self.session.sources)]

    def tool_view_source(self, source_id: str) -> list[dict]:
        source = self.source(source_id)
        return [text({"id": source.id, "origin": source.origin, "text": source.text[:VIEW_TEXT]}),
                image(grid_view(source.image))]

    def tool_register_plan(self, source_id: str, level: int, floor_name: str, bbox: list, photo: bool,
                           corners: list | None = None, label_sources: list | None = None,
                           replace: bool = False) -> list[dict]:
        source = self.source(source_id)
        if source.level is not None:  # the user said which floor this file is: that wins
            level = source.level
        if level in self.session.floors and not replace:
            existing = self.session.floors[level]
            raise ToolError(f"level {level} already has a plan ({existing.source_id}, {existing.name!r}); keep the "
                            "sharper one — replace=true swaps it")
        picture, homography = source.image, None
        if photo or corners:
            picture, homography = rectify(source.image, [tuple(c) for c in corners] if corners else None)
        plan = crop(picture if homography is not None else source.image, tuple(bbox), homography,
                    source.image.shape[:2])
        floor = FloorPlan(int(level), floor_name, source_id, plan, segment_walls(plan))
        self.session.floors[floor.level] = floor
        self.session.label_sources[floor.level] = list(label_sources or [])
        self.session.finished = None
        return self.cells_result(floor, {"flattened": homography is not None})

    def tool_segment(self, level: int, method: str, gap_px: int | None = None, dark: int | None = None
                     ) -> list[dict]:
        floor = self.floor(level)
        if method == "walls":
            mask = wall_mask(floor.image, dark=dark) if dark is not None else None
            floor.seg = segment_walls(floor.image, gap_px=gap_px, mask=mask)
        elif method == "colours":
            floor.seg = segment_colours(floor.image)
        else:
            raise ToolError("method is walls or colours")
        floor.low_confidence = False
        self.reset(floor)
        return self.cells_result(floor)

    def tool_coarse_rooms(self, level: int, boxes: list) -> list[dict]:
        floor = self.floor(level)
        if not boxes:
            raise ToolError("give at least one box")
        floor.seg = cells_from_boxes(floor.image.shape[:2], [tuple(box) for box in boxes])
        floor.low_confidence = True
        self.reset(floor)
        return self.cells_result(floor, {"low_confidence": True})

    def tool_add_rooms(self, level: int, cell: int, boxes: list) -> list[dict]:
        floor = self.floor(level)
        if cell not in floor.seg.cells:
            raise ToolError(f"cell {cell} is not a cell of level {level} (0 = outside)")
        new_ids = carve(floor.seg, cell, [self.to_px(floor, box) for box in boxes])
        if not new_ids:
            raise ToolError(f"none of the boxes overlaps cell {cell}")
        floor.carved += new_ids
        return self.cells_result(floor, {"new_cells": new_ids})

    def tool_label_cells(self, level: int, cells: list, doors: list | None = None,
                         entrances: list | None = None) -> list[dict]:
        floor = self.floor(level)
        problems = apply_labels(floor, cells, doors, entrances)
        floor.transform = floor.alignment = None
        self.session.finished = None
        summary = {"level": level, "labelled": len(floor.labels), "kept_cells": len(kept(floor)),
                   "doors": len([d for d in floor.doors if "outside" not in d.cells]),
                   "entrances": len([d for d in floor.doors if "outside" in d.cells]), "problems": problems}
        return [text(summary), image(render_labels(floor))]

    def tool_set_scale(self, level: int, method: str, p0: list | None = None, p1: list | None = None,
                       length_m: float | None = None) -> list[dict]:
        floor = self.floor(level)
        if method == "bar":
            if p0 is None or p1 is None or length_m is None:
                raise ToolError("method=bar needs p0, p1 and length_m")
            value = scale_from_bar(floor, tuple(p0), tuple(p1), float(length_m))
        elif method == "doors":
            value = scale_from_doors(floor)
            if value is None:
                raise ToolError("fewer than two measured doors on this floor; use bar or prior")
        elif method == "prior":
            value = scale_prior(floor)
        else:
            raise ToolError("method is bar, doors or prior")
        floor.m_per_px, floor.scale_method = value, method
        floor.transform = floor.alignment = None
        return [text({"level": level, "m_per_px": round(value, 5), "method": method})]

    def stacked(self) -> list[FloorPlan]:
        floors = list(self.session.floors.values())
        if not floors:
            raise ToolError("no plan registered yet")
        for floor in floors:
            if not kept(floor):
                raise ToolError(f"level {floor.level} has no kept cells")
        for floor in floors:
            floor.transform = floor.alignment = None
        ensure_scales(floors)
        align(floors)
        return floors

    def tool_stack_floors(self) -> list[dict]:
        floors = self.stacked()
        joined = connectors(floors)
        summary = {"floors": {str(f.level): {"alignment": f.alignment, "scale_method": f.scale_method,
                                             "m_per_px": round(f.m_per_px, 5)} for f in floors},
                   "connectors": len(joined),
                   "joined": [{"kind": kind, "stops": [{"level": level, "cell": cell} for level, cell in stops],
                               **({"guessed": True} if guessed else {})} for kind, stops, guessed in joined]}
        return [text(summary), image(self.overlay(floors))]

    @staticmethod
    def overlay(floors: list[FloorPlan]) -> bytes:
        outlines = {f.level: [np.c_[np.float64(f.seg.cells[c].polygon), np.ones(len(f.seg.cells[c].polygon))]
                              @ f.transform.T for c in kept(f)] for f in floors}
        points = np.vstack([p for polygons in outlines.values() for p in polygons])
        low, high = points.min(axis=0), points.max(axis=0)
        scale = (MODEL_MAX_SIDE - 40) / max(float((high - low).max()), 1e-6)
        size = ((high - low) * scale + 40).astype(int)
        view = np.full((size[1], size[0], 3), 255, np.uint8)
        colours = [(200, 80, 0), (0, 140, 0), (0, 0, 200), (160, 0, 160), (0, 140, 160), (120, 120, 0)]
        for index, (level, polygons) in enumerate(sorted(outlines.items())):
            colour = colours[index % len(colours)]
            for polygon in polygons:
                xy = (polygon - low) * scale + 20
                xy[:, 1] = size[1] - xy[:, 1]
                cv2.polylines(view, [np.int32(xy)], True, colour, 1)
            cv2.putText(view, f"level {level}", (10, 20 + 18 * index), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1)
        return png(view)

    def tool_finish(self, name: str) -> list[dict]:
        if not self.session.floors:
            raise ToolError("no plan registered yet; register a plan, or call no_plan")
        for floor in self.session.floors.values():
            missing = [cell for cell in kept(floor) if cell not in floor.labels]
            if missing:
                raise ToolError(f"level {floor.level}: cells {missing} have no label (label, merge or mark outside)")
        floors = self.stacked()
        origins = sorted({self.source(f.source_id).origin for f in floors})
        building_id = f"import-{uuid.uuid4().hex[:8]}"
        building = autofix(assemble(building_id, name.strip() or "Imported building", floors, origins))
        issues = check(building)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        summary = {"spaces": len(building["spaces"]), "openings": len(building["openings"]),
                   "connectors": len(building["vertical_connectors"]),
                   "errors": [{"code": i["code"], "message": i["message"]} for i in errors][:30]}
        if errors and self.session.finish_attempts == 0:
            self.session.finish_attempts = 1
            summary["next"] = ("fix what you can with label_cells (doors, stairs on every floor), then call finish "
                               "again; the next finish accepts the building as it is")
            return [text(summary)]
        self.session.finished = {"building": building, "issues": issues}
        summary["accepted"] = True
        return [text(summary)]

    def tool_no_plan(self, reason: str) -> list[dict]:
        if self.session.floors:
            raise ToolError("plans are already registered; finish instead")
        self.session.no_plan = reason.strip() or "no floor plan found"
        return [text({"ended": True})]
