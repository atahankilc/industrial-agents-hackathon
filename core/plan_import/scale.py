"""Stage 5a — metres per pixel for each floor: a scale bar / written dimension the model read (measured here), the
door gaps (median gap = 0.9 m), a floor drawn on the same sheet format, or a typical room size."""

import math

import numpy as np

from core.plan_import.model import FloorPlan, Point

DOOR_M = 0.9
TYPICAL_ROOM_M2 = 20.0
SAME_SHEET = 0.10  # image sizes within 10 % → same drawing scale


def scale_from_bar(floor: FloorPlan, p0: Point, p1: Point, length_m: float) -> float:
    """`p0`, `p1`: the bar's ends, normalised in the floor image."""
    height, width = floor.image.shape[:2]
    distance = math.hypot((p1[0] - p0[0]) * width, (p1[1] - p0[1]) * height)
    if distance < 2 or length_m <= 0:
        raise ValueError("the scale bar is too short to measure")
    return length_m / distance


def scale_from_doors(floor: FloorPlan) -> float | None:
    widths = [door.width_px for door in floor.doors if door.width_px > 0]
    if len(widths) < 2:
        return None
    return DOOR_M / float(np.median(widths))


def scale_prior(floor: FloorPlan) -> float:
    rooms = [cell.area_px for cell_id, cell in floor.seg.cells.items()
             if not cell.outside and (label := floor.labels.get(cell_id)) is not None and label.type == "room"]
    if not rooms:
        rooms = [cell.area_px for cell in floor.seg.cells.values() if not cell.outside] or [1.0]
    return math.sqrt(TYPICAL_ROOM_M2 / float(np.median(rooms)))


def ensure_scales(floors: list[FloorPlan]) -> None:
    for floor in floors:
        if floor.m_per_px is None and (value := scale_from_doors(floor)) is not None:
            floor.m_per_px, floor.scale_method = value, "doors"
    for floor in floors:
        if floor.m_per_px is not None:
            continue
        for other in floors:
            if other.m_per_px is not None and other.scale_method != "same_sheet":
                h, w = floor.image.shape[:2]
                oh, ow = other.image.shape[:2]
                if abs(h - oh) <= SAME_SHEET * oh and abs(w - ow) <= SAME_SHEET * ow:
                    floor.m_per_px, floor.scale_method = other.m_per_px, "same_sheet"
                    break
        if floor.m_per_px is None:
            floor.m_per_px, floor.scale_method = scale_prior(floor), "prior"
