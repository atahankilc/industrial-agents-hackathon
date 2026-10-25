"""Stage 5b — one XY frame for all floors (metres, y up, origin at the lowest floor's bottom-left) and the stairs /
lifts that join them. Floors are registered on their footprints (OpenCV ECC, rotation + translation, trying a few
relative scales because every photo has its own px/m estimate) at 0.1 m/px; if that fails the footprints' centres are
put on top of each other. Stairs / lifts join by name first, then by distance; consecutive floors that would stay
unconnected get their nearest pair, marked as a guess."""

import cv2
import numpy as np

from core.plan_import.model import FloorPlan

GRID_M = 0.1  # metres per canvas pixel
PAD_M = 10.0
MIN_CORRELATION = 0.6
SCALE_FACTORS = (1.0, 0.93, 1.07, 0.87, 1.15, 0.8, 1.25)


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
        warp, alignment, factor = start, "centred", 1.0
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5)
        blur = lambda m: cv2.GaussianBlur(m, (0, 0), 5).astype(np.float32)  # noqa: E731
        best = MIN_CORRELATION
        trials = (1.0,) if floor.scale_method == "bar" else SCALE_FACTORS  # a scale read off the plan is trusted
        for trial in trials:  # each photo has its own px/m estimate; search the relative scale too
            metric = np.diag([trial, trial, 1.0]) @ metrics[id(floor)]
            candidate = canvas(floor, metric, size)
            b = cv2.moments(candidate, True)
            guess = start.copy()
            if a["m00"] and b["m00"]:
                guess[0, 2] = b["m10"] / b["m00"] - a["m10"] / a["m00"]
                guess[1, 2] = b["m01"] / b["m00"] - a["m01"] / a["m00"]
            try:
                correlation, found = cv2.findTransformECC(blur(template), blur(candidate), guess, cv2.MOTION_EUCLIDEAN,
                                                          criteria, None, 5)
            except cv2.error:
                continue
            if correlation > best:
                best, warp, alignment, factor = correlation, found, "registered", trial
        if factor != 1.0:
            floor.m_per_px *= factor
            if not str(floor.scale_method).endswith("+aligned"):  # the notes show the alignment changed it (once)
                floor.scale_method = f"{floor.scale_method}+aligned"
            metrics[id(floor)] = np.diag([factor, factor, 1.0]) @ metrics[id(floor)]
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


def connectors(floors: list[FloorPlan], max_dist_m: float = 3.0) -> list[tuple[str, list[tuple[int, int]], bool]]:
    """(kind, stops, guessed). Consecutive levels: a stair / lift joins the one of the same type with the same name,
    else the nearest within `max_dist_m`. If two consecutive floors end up with no join at all, their nearest stair
    (or lift) pair is joined anyway and the chain is marked guessed — a building must not fall apart into floors."""
    ordered = sorted(floors, key=lambda floor: floor.level)
    links: dict[str, list[tuple[tuple[int, int], tuple[int, int], bool]]] = {"stair": [], "lift": []}

    def cells(floor: FloorPlan, kind: str) -> list[int]:
        return [c for c, label in sorted(floor.labels.items()) if label.type == kind and c in floor.seg.cells]

    for lower, upper in zip(ordered, ordered[1:]):
        joined_any = False
        for kind in ("stair", "lift"):
            downs, ups = cells(lower, kind), cells(upper, kind)
            used: set[int] = set()
            for down in downs:
                here = centroid_m(lower, down)
                name = lower.labels[down].name.strip().lower()
                same = [up for up in ups if up not in used and upper.labels[up].name.strip().lower() == name]
                near = [up for up in ups if up not in used and np.hypot(*(centroid_m(upper, up) - here)) <= max_dist_m]
                choice = (same or near)
                if choice:
                    best = min(choice, key=lambda up: np.hypot(*(centroid_m(upper, up) - here)))
                    used.add(best)
                    links[kind].append(((lower.level, down), (upper.level, best), False))
                    joined_any = True
        if not joined_any:
            for kind in ("stair", "lift"):
                pairs = [(np.hypot(*(centroid_m(upper, up) - centroid_m(lower, down))), down, up)
                         for down in cells(lower, kind) for up in cells(upper, kind)]
                if pairs:
                    _, down, up = min(pairs)
                    links[kind].append(((lower.level, down), (upper.level, up), True))
                    break

    result: list[tuple[str, list[tuple[int, int]], bool]] = []
    for kind, name in (("stair", "stairs"), ("lift", "lift")):
        chains: list[list] = []
        ends: dict[tuple[int, int], list] = {}
        for low, high, guessed in links[kind]:
            chain = ends.pop(low, None)
            if chain is None:
                chain = [[low], False]
                chains.append(chain)
            chain[0].append(high)
            chain[1] = chain[1] or guessed
            ends[high] = chain
        result += [(name, stops, guessed) for stops, guessed in chains]
    return result
