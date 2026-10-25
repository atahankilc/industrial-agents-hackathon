"""Stage 5b — one XY frame for all floors (metres, y up, origin at the lowest floor's bottom-left) and the stairs /
lifts that join them. Floors are registered on their footprints (OpenCV ECC, rotation + translation) at 0.1 m/px;
if that fails the footprints' centres are put on top of each other."""

import cv2
import numpy as np

from core.plan_import.model import FloorPlan

GRID_M = 0.1  # metres per canvas pixel
PAD_M = 10.0
MIN_CORRELATION = 0.6


def kept_polygons(floor: FloorPlan) -> list[np.ndarray]:
    return [np.float64(cell.polygon) for cell in floor.seg.cells.values() if not cell.outside and len(cell.polygon) >= 3]


def to_metric(floor: FloorPlan) -> np.ndarray:
    """3×3: floor px → metres, y down, origin at the top-left of its kept cells' bounding box."""
    points = np.vstack(kept_polygons(floor))
    left, top = points.min(axis=0)
    s = floor.m_per_px
    return np.array([[s, 0, -left * s], [0, s, -top * s], [0, 0, 1]])


def canvas(floor: FloorPlan, metric: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(size, np.uint8)
    for polygon in kept_polygons(floor):
        points = (np.c_[polygon, np.ones(len(polygon))] @ metric.T)[:, :2]
        cv2.fillPoly(mask, [np.int32(np.round((points + PAD_M) / GRID_M))], 255)
    return mask


def align(floors: list[FloorPlan]) -> None:
    """Sets every floor's `transform` (2×3, px → frame metres, y up) and `alignment` ("frame" | "registered" |
    "centred")."""
    ordered = sorted(floors, key=lambda floor: floor.level)
    frame = ordered[0]
    frame_metric = to_metric(frame)
    extent = np.vstack([(np.c_[p, np.ones(len(p))] @ frame_metric.T)[:, :2] for p in kept_polygons(frame)]).max(axis=0)
    height_m = float(extent[1])
    flip = np.array([[1, 0, 0], [0, -1, height_m], [0, 0, 1]])  # metres y down → y up
    frame.transform, frame.alignment = (flip @ frame_metric)[:2], "frame"

    metrics = {id(floor): to_metric(floor) for floor in ordered}
    sizes = [np.vstack([(np.c_[p, np.ones(len(p))] @ metrics[id(f)].T)[:, :2] for p in kept_polygons(f)]).max(axis=0)
             for f in ordered]
    span = np.max(sizes, axis=0) + 2 * PAD_M
    size = (int(span[1] / GRID_M) + 1, int(span[0] / GRID_M) + 1)
    template = canvas(frame, frame_metric, size)
    for floor in ordered[1:]:
        moving = canvas(floor, metrics[id(floor)], size)
        to_grid = np.array([[1 / GRID_M, 0, PAD_M / GRID_M], [0, 1 / GRID_M, PAD_M / GRID_M], [0, 0, 1]])
        start = np.eye(2, 3, dtype=np.float32)
        a, b = cv2.moments(template, True), cv2.moments(moving, True)
        if a["m00"] and b["m00"]:
            start[0, 2] = b["m10"] / b["m00"] - a["m10"] / a["m00"]
            start[1, 2] = b["m01"] / b["m00"] - a["m01"] / a["m00"]
        warp, alignment = start, "centred"
        try:
            criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)
            blur = lambda m: cv2.GaussianBlur(m, (0, 0), 5).astype(np.float32)  # noqa: E731
            correlation, found = cv2.findTransformECC(blur(template), blur(moving), start.copy(), cv2.MOTION_EUCLIDEAN,
                                                      criteria, None, 5)
            if correlation >= MIN_CORRELATION:
                warp, alignment = found, "registered"
        except cv2.error:
            pass
        # ECC: moving(x) = warp · template(x)  →  template grid = warp⁻¹ · moving grid
        inverse = np.linalg.inv(np.vstack([warp, [0, 0, 1]]))
        from_grid = np.linalg.inv(to_grid)
        floor.transform = (flip @ from_grid @ inverse @ to_grid @ metrics[id(floor)])[:2]
        floor.alignment = alignment


def to_frame(floor: FloorPlan, point) -> np.ndarray:
    return floor.transform @ np.array([point[0], point[1], 1.0])


def centroid_m(floor: FloorPlan, cell_id: int) -> np.ndarray:
    polygon = np.float64(floor.seg.cells[cell_id].polygon)
    points = np.c_[polygon, np.ones(len(polygon))] @ floor.transform.T
    return points.mean(axis=0)


def connectors(floors: list[FloorPlan], max_dist_m: float = 3.0) -> list[tuple[str, list[tuple[int, int]]]]:
    """Stairs / lifts joined floor to floor (consecutive levels) by the nearest cell of the same type."""
    ordered = sorted(floors, key=lambda floor: floor.level)
    result: list[tuple[str, list[tuple[int, int]]]] = []
    for kind, name in (("stair", "stairs"), ("lift", "lift")):
        chains: list[list[tuple[int, int]]] = []
        open_ends: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for lower, upper in zip(ordered, ordered[1:]):
            ups = [c for c, label in upper.labels.items() if label.type == kind and c in upper.seg.cells]
            used: set[int] = set()
            for cell_id, label in sorted(lower.labels.items()):
                if label.type != kind or cell_id not in lower.seg.cells:
                    continue
                here = centroid_m(lower, cell_id)
                options = [(np.hypot(*(centroid_m(upper, up) - here)), up) for up in ups if up not in used]
                options = [option for option in options if option[0] <= max_dist_m]
                if not options:
                    continue
                _, best = min(options)
                used.add(best)
                chain = open_ends.pop((lower.level, cell_id), None)
                if chain is None:
                    chain = [(lower.level, cell_id)]
                    chains.append(chain)
                chain.append((upper.level, best))
                open_ends[(upper.level, best)] = chain
        result += [(name, chain) for chain in chains if len(chain) >= 2]
    return result
