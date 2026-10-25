"""Each floor's straightened plan, kept for Edit mode (docs/superpowers/specs/2026-10-25-plan-reference-and-location-design.md).

`reference_for` turns a floor's rectified + cropped image into a capped JPEG data URL plus the 2×3 transform from the
stored image's pixels to the building's metres (y up — the frame the floor's spaces are assembled in). The import
puts it in `source_ref.import.floors[level].reference`; `strip_references` leaves it out of every payload but
`GET /drafts/{id}/references`."""

import base64
import copy

import cv2
import numpy as np

from core.plan_import.model import FloorPlan

MAX_SIDE = 1600  # px, long side of a stored reference
JPEG_QUALITY = 80
PAPER = 235  # grey level above which a pixel counts as empty paper
EDGE_PX = 6  # kept around the drawing when the paper is cropped


def reference_for(floor: FloorPlan, max_side: int = MAX_SIDE) -> dict:
    transform = np.asarray(floor.transform, dtype=float).copy()
    image, (left, top) = drawing(floor.image)
    transform[:, 2] += transform[:, :2] @ [left, top]  # stored pixel (0, 0) is original (left, top)
    factor = max(image.shape[:2]) / max_side
    if factor > 1:
        size = (round(image.shape[1] / factor), round(image.shape[0] / factor))
        image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    else:
        factor = 1.0
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("could not encode the floor image")
    transform[:, :2] *= factor  # a stored pixel spans `factor` original pixels
    return {"image": "data:image/jpeg;base64," + base64.b64encode(data.tobytes()).decode("ascii"),
            "transform": [[float(value) for value in row] for row in transform]}


def drawing(image: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
    """The image cropped to what is drawn (empty paper around it cut off) and the crop's (left, top) in pixels."""
    grey = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = np.argwhere(grey < PAPER)
    if not len(ink):
        return image, (0, 0)
    (top, left), (bottom, right) = ink.min(axis=0), ink.max(axis=0)
    top, left = max(0, top - EDGE_PX), max(0, left - EDGE_PX)
    bottom, right = min(grey.shape[0], bottom + 1 + EDGE_PX), min(grey.shape[1], right + 1 + EDGE_PX)
    return image[top:bottom, left:right], (int(left), int(top))


def strip_references(building: dict) -> dict:
    """A deep copy without the reference images (they are large and only Edit mode's reference panel uses them)."""
    stripped = copy.deepcopy(building)
    for floor in ((stripped.get("building", {}).get("source_ref") or {}).get("import") or {}).get("floors", {}).values():
        floor.pop("reference", None)
    return stripped
