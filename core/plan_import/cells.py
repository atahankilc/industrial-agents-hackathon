"""Stage 3 — split a plan into cells (candidate rooms) in code; the model only labels them.

Three ways to get a label image, one way to turn it into a `Segmentation`:
- `segment_walls`: free space between walls, after closing door-sized gaps (6 × the measured wall thickness, so it
  works at any scale); the pixels the closing added are the door candidates.
- `segment_colours`: the same pipeline over a separator mask (dark lines, thin white lines, colour boundaries) for
  plans whose rooms are coloured fills split by light lines.
- `cells_from_boxes`: the model's coarse boxes, the last resort (marked low confidence by the caller).
Cells are grown into the walls around them up to the wall's centre line, so neighbours share their boundary like the
dataset's polygons do. The exterior (free space touching the image border) is one cell with id 0, `outside=True`."""

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from core.plan_import.ingest import png
from core.plan_import.model import Cell, DoorCandidate, Point, Segmentation
from core.plan_import.prepare import wall_mask

OUTSIDE_ID = 0
DOOR_FACTOR = 6  # door gap ≈ this many wall thicknesses
SIMPLIFY_PX = 1.5
MAX_BOUNDARY_POINTS = 40


def wall_thickness(mask: np.ndarray) -> float:
    """Typical wall thickness in px: twice the 90th percentile of the distance to the nearest non-wall pixel."""
    if not mask.any():
        return 1.0
    distance = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    return max(1.0, 2 * float(np.percentile(distance[mask > 0], 90)))


def simplify(polygon: list[Point], tolerance_px: float = SIMPLIFY_PX) -> list[Point]:
    shape = Polygon(polygon).simplify(tolerance_px, preserve_topology=True)
    if shape.is_empty or shape.geom_type != "Polygon":
        return polygon
    return [(float(x), float(y)) for x, y in list(shape.exterior.coords)[:-1]]


def outline(mask: np.ndarray) -> list[Point]:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea)
    return simplify([(float(x), float(y)) for x, y in contour[:, 0, :]]) if len(contour) >= 3 else []


def reading_order(labels: np.ndarray, ids: list[int]) -> list[int]:
    band = max(1, labels.shape[0] // 20)
    keys = {}
    for region in ids:
        ys, xs = np.nonzero(labels == region)
        keys[region] = (int(ys.mean()) // band, float(xs.mean()))
    return sorted(ids, key=keys.__getitem__)


def grow(labels: np.ndarray, into: np.ndarray, steps: int) -> np.ndarray:
    """Spread the positive labels into `into` pixels (walls) for `steps` px."""
    grown = labels.astype(np.float32)
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(steps):
        spread = cv2.dilate(grown, kernel)
        take = (grown <= 0) & into & (spread > 0)
        if not take.any():
            break
        grown[take] = spread[take]
    return grown.astype(np.int32)


def from_labels(labels: np.ndarray, outside: np.ndarray | None, walls: np.ndarray, steps: int, method: str,
                added: np.ndarray | None = None, keep_ids: bool = False) -> Segmentation:
    """`labels`: int32, > 0 = a region; `outside`: bool mask of the exterior (or None); `walls`: bool, pixels the
    regions may grow into; `added`: bool, gap pixels the door closing added (door candidates)."""
    ids = [int(v) for v in np.unique(labels) if v > 0]
    order = ids if keep_ids else reading_order(labels, ids)
    renumber = np.zeros(int(labels.max()) + 1 if labels.size else 1, np.int32)
    for new, old in enumerate(order, start=1):
        renumber[old] = new
    base = renumber[np.clip(labels, 0, None)]
    base[labels <= 0] = 0
    grown = grow(base, walls, steps)

    cells: dict[int, Cell] = {}
    for cell_id in range(1, len(order) + 1):
        mask = grown == cell_id
        polygon = outline(mask)
        if len(polygon) >= 3:
            cells[cell_id] = Cell(cell_id, polygon, float(mask.sum()), False)
    if outside is not None and outside.any():
        cells[OUTSIDE_ID] = Cell(OUTSIDE_ID, [], float(outside.sum()), True)

    adjacency: dict[tuple[int, int], list[Point]] = {}
    kernel = np.ones((5, 5), np.uint8)
    for cell_id in cells:
        if cell_id == OUTSIDE_ID:
            continue
        ys, xs = np.nonzero(grown == cell_id)
        top, bottom, left, right = max(ys.min() - 3, 0), ys.max() + 4, max(xs.min() - 3, 0), xs.max() + 4
        window = grown[top:bottom, left:right]
        ring = cv2.dilate((window == cell_id).astype(np.uint8), kernel).astype(bool) & (window != cell_id)
        for other in np.unique(window[ring]):
            other = int(other)
            if other <= cell_id or other not in cells:
                continue
            py, px = np.nonzero(ring & (window == other))
            step = max(1, len(px) // MAX_BOUNDARY_POINTS)
            adjacency[(cell_id, other)] = [(float(x + left), float(y + top)) for x, y in zip(px[::step], py[::step])]

    doors: list[DoorCandidate] = []
    if added is not None and added.any():
        exterior = outside if outside is not None else np.zeros_like(added)
        count, components, stats, centroids = cv2.connectedComponentsWithStats(added.astype(np.uint8), 8)
        reach = steps + 3
        for index in range(1, count):
            x, y, w, h = stats[index, :4]
            top, left = max(y - reach, 0), max(x - reach, 0)
            window = components[top:y + h + reach, left:x + w + reach] == index
            touch = cv2.dilate(window.astype(np.uint8), np.ones((2 * reach + 1, 2 * reach + 1), np.uint8)).astype(bool)
            near = {int(v) for v in np.unique(base[top:y + h + reach, left:x + w + reach][touch]) if v > 0}
            near &= cells.keys()
            touches_outside = bool(exterior[top:y + h + reach, left:x + w + reach][touch].any())
            points = np.column_stack(np.nonzero(window))[:, ::-1].astype(np.float32)
            width = float(max(cv2.minAreaRect(points)[1])) if len(points) >= 2 else 1.0
            position = (float(centroids[index][0]), float(centroids[index][1]))
            if len(near) == 2:
                a, b = sorted(near)
                doors.append(DoorCandidate((a, b), position, width))
            elif len(near) == 1 and touches_outside:
                doors.append(DoorCandidate((next(iter(near)), "outside"), position, width))
    for number, door in enumerate(doors, start=1):
        door.number = number
    return Segmentation(method, cells, adjacency, doors)


def fill_holes(mask: np.ndarray) -> np.ndarray:
    padded = cv2.copyMakeBorder(mask.astype(np.uint8), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    flood = padded.copy()
    cv2.floodFill(flood, None, (0, 0), 1)
    return (padded.astype(bool) | (flood == 0))[1:-1, 1:-1]


def footprint(closed: np.ndarray) -> np.ndarray:
    """The building's area: walls bridged over wide openings (6 % of the short side), holes filled."""
    size = max(9, int(0.06 * min(closed.shape[:2]))) | 1  # odd: an even kernel shifts the result
    bridged = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, np.ones((size, size), np.uint8))
    return fill_holes(bridged > 0)


def segment_walls(image: np.ndarray, gap_px: int | None = None, mask: np.ndarray | None = None) -> Segmentation:
    """Rooms = free space between walls inside the building's footprint, door gaps closed. `gap_px` default: 6 × wall
    thickness, at most 10 % of the image's short side. The closing only bridges *thin* gaps: where it filled a fat
    area (a room narrower than the gap) that area is given back."""
    mask = wall_mask(image) if mask is None else mask
    thickness = wall_thickness(mask)
    if gap_px is None:
        gap_px = int(round(min(max(6.0, DOOR_FACTOR * thickness), 0.1 * min(image.shape[:2]))))
    gap_px |= 1  # odd: an even kernel shifts the result
    closed = np.maximum(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, gap_px), np.uint8)),
                        cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((gap_px, 1), np.uint8)))
    added = ((closed > 0) & (mask == 0)).astype(np.uint8)
    added = cv2.morphologyEx(added, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))  # 1-px fringes along walls
    count, parts, stats, _ = cv2.connectedComponentsWithStats(added, 8)
    for index in range(1, count):
        points = np.column_stack(np.nonzero(parts == index))[:, ::-1].astype(np.float32)
        if min(cv2.minAreaRect(points)[1]) > 2.0 * thickness:  # a filled room, not a door
            closed[parts == index] = 0
            added[parts == index] = 0
    inside = footprint(closed)
    free = ((closed == 0) & inside).astype(np.uint8)
    count, labels = cv2.connectedComponents(free, connectivity=4)
    outside = ~inside
    sizes = np.bincount(labels.ravel(), minlength=count)
    small = sizes < max((3 * thickness) ** 2, 16)  # specks between lines, not rooms
    small[0] = False
    labels = labels.copy()
    labels[small[labels]] = 0
    walls = (labels == 0) & inside
    steps = int(np.ceil(thickness / 2)) + 1
    return from_labels(labels, outside, walls, steps, "walls", added.astype(bool))


def straight(mask: np.ndarray, length: int) -> np.ndarray:
    """Only the horizontal / vertical runs of at least `length` px (drops diagonal hatching, text, dots)."""
    mask = mask.astype(np.uint8)
    return np.maximum(cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, length), np.uint8)),
                      cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((length, 1), np.uint8))).astype(bool)


def separator_mask(image: np.ndarray, k: int = 8, contrast: int = 18) -> np.ndarray:
    """Walls for plans drawn with fills: dark walls (wall_mask) + thin lines darker or lighter than the fill around
    them (black / white top-hat on lightness, any colour) + boundaries between fill colours (k-means in Lab on a
    blurred copy). The last two keep only straight horizontal / vertical runs, so hatching does not cut rooms."""
    lightness = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)[:, :, 0]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    lines = ((cv2.morphologyEx(lightness, cv2.MORPH_BLACKHAT, kernel) > contrast)
             | (cv2.morphologyEx(lightness, cv2.MORPH_TOPHAT, kernel) > contrast))

    smooth = cv2.cvtColor(cv2.medianBlur(image, 9), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    sample = smooth[:: max(1, len(smooth) // 60000)]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0)
    _, _, centres = cv2.kmeans(sample, k, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    cluster = np.zeros(len(smooth), np.uint8)
    best = np.full(len(smooth), np.inf, np.float32)
    for index, centre in enumerate(centres):
        distance = ((smooth - centre) ** 2).sum(axis=1)
        closer = distance < best
        cluster[closer], best[closer] = index, distance[closer]
    cluster = cluster.reshape(image.shape[:2])
    edges = cv2.dilate(cluster, np.ones((3, 3), np.uint8)) != cv2.erode(cluster, np.ones((3, 3), np.uint8))

    length = max(15, max(image.shape[:2]) // 120)
    mask = (wall_mask(image) > 0) | straight(lines, length) | straight(edges, length)
    return mask.astype(np.uint8) * 255


def segment_colours(image: np.ndarray, k: int = 8) -> Segmentation:
    """Rooms separated by fills rather than dark walls (coloured brochures): `separator_mask` → the walls pipeline."""
    seg = segment_walls(image, mask=separator_mask(image, k))
    seg.method = "colours"
    return seg


def cells_from_boxes(shape: tuple[int, int], boxes: list[tuple[float, float, float, float]]) -> Segmentation:
    """The model's normalised boxes → rectangular cells, ids in box order; an earlier box wins an overlap."""
    height, width = shape
    labels = np.zeros((height, width), np.int32)
    for index in range(len(boxes), 0, -1):
        x0, y0, x1, y1 = boxes[index - 1]
        labels[int(round(min(y0, y1) * height)):int(round(max(y0, y1) * height)),
               int(round(min(x0, x1) * width)):int(round(max(x0, x1) * width))] = index
    steps = int(np.ceil(0.03 * max(height, width)))  # boxes read off a grid leave gaps; grow them shut
    return from_labels(labels, None, labels == 0, steps, "coarse", keep_ids=True)


def carve(seg: Segmentation, cell_id: int, boxes: list[tuple[float, float, float, float]]) -> list[int]:
    """Cut px boxes out of one cell as new cells (the model saw rooms the segmentation merged), or — with the outside
    cell — add rooms where no cell is (open rooms the walls did not close). Returns the new ids;
    adjacency is recomputed from the shapes for every cell the carving touched."""
    from shapely.geometry import box as make_box

    parent = seg.cells[cell_id]
    if parent.outside:  # rooms the walls left open (a foyer without a front wall): take them from what no cell covers
        covered = unary_union([Polygon(c.polygon) for c in seg.cells.values() if not c.outside and len(c.polygon) >= 3])
        remaining = make_box(-1e9, -1e9, 1e9, 1e9).difference(covered)
    else:
        remaining = Polygon(parent.polygon)
    new_ids: list[int] = []
    for x0, y0, x1, y1 in boxes:
        piece = remaining.intersection(make_box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        if piece.is_empty or piece.area < 4:
            continue
        if piece.geom_type != "Polygon":
            piece = max(piece.geoms, key=lambda part: part.area)
        new_id = max(seg.cells) + 1
        seg.cells[new_id] = Cell(new_id, [(float(x), float(y)) for x, y in list(piece.exterior.coords)[:-1]],
                                 float(piece.area), False)
        remaining = remaining.difference(piece)
        new_ids.append(new_id)
    if not parent.outside:
        if remaining.geom_type != "Polygon":
            remaining = max(remaining.geoms, key=lambda part: part.area)
        parent.polygon = [(float(x), float(y)) for x, y in list(remaining.exterior.coords)[:-1]]
        parent.area_px = float(remaining.area)
    touched = [cell_id, *new_ids] if not parent.outside else new_ids
    shapes = {other: Polygon(cell.polygon) for other, cell in seg.cells.items() if not cell.outside}
    for a in touched:
        for b, shape in shapes.items():
            if a == b:
                continue
            pair = (min(a, b), max(a, b))
            seg.adjacency.pop(pair, None)
            shared = shapes[a].buffer(3).intersection(shape.boundary)
            if not shared.is_empty and shared.length > 3:
                points = [shared.interpolate(t, normalized=True) for t in np.linspace(0, 1, 9)]
                seg.adjacency[pair] = [(float(point.x), float(point.y)) for point in points]
    return new_ids


PALETTE = [(230, 159, 0), (86, 180, 233), (0, 158, 115), (240, 228, 66), (0, 114, 178), (213, 94, 0),
           (204, 121, 167), (120, 120, 220), (100, 200, 160), (200, 140, 90)]


def render_cells(image: np.ndarray, seg: Segmentation) -> bytes:
    """The plan with every cell tinted and numbered, door candidates as red dots labelled d1, d2, …"""
    view = image.copy()
    overlay = image.copy()
    for cell in seg.cells.values():
        if cell.outside or len(cell.polygon) < 3:
            continue
        points = np.int32(cell.polygon)
        cv2.fillPoly(overlay, [points], PALETTE[cell.id % len(PALETTE)])
    view = cv2.addWeighted(overlay, 0.35, view, 0.65, 0)
    scale = max(0.4, max(image.shape[:2]) / 1600)
    for cell in seg.cells.values():
        if cell.outside or len(cell.polygon) < 3:
            continue
        cv2.polylines(view, [np.int32(cell.polygon)], True, (60, 60, 60), 1)
        point = Polygon(cell.polygon).representative_point()
        text, at = str(cell.id), (int(point.x) - 8, int(point.y) + 6)
        cv2.putText(view, text, at, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 4)
        cv2.putText(view, text, at, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 1)
    for door in seg.doors:
        x, y = int(door.position[0]), int(door.position[1])
        cv2.circle(view, (x, y), max(3, int(3 * scale)), (0, 0, 230), -1)
        cv2.putText(view, f"d{door.number}", (x + 4, y - 4), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.7, (0, 0, 230), 1)
    return png(view)
