"""Synthetic floor-plan images for the plan-import tests: white paper, black walls, door gaps."""

import cv2
import numpy as np

DOOR_M = 0.9

# Two 5×4 m rooms over a 10×4 m corridor; a door from each room to the corridor, an entrance on the corridor's west wall.
TWO_ROOMS_AND_CORRIDOR = (
    [(0, 4, 5, 8), (5, 4, 10, 8), (0, 0, 10, 4)],
    [(2.5, 4, "h"), (7.5, 4, "h"), (0, 2, "v")],
)


def draw_plan(rooms, doors, px_per_m: float = 20, wall_px: int = 4, margin_m: float = 2) -> np.ndarray:
    """`rooms`: (x0, y0, x1, y1) in metres (y up); `doors`: (x, y, "h"|"v") centres of 0.9 m gaps in a horizontal /
    vertical wall."""
    xs = [v for r in rooms for v in (r[0], r[2])]
    ys = [v for r in rooms for v in (r[1], r[3])]
    width = int((max(xs) - min(xs) + 2 * margin_m) * px_per_m)
    height = int((max(ys) - min(ys) + 2 * margin_m) * px_per_m)

    def px(x: float, y: float) -> tuple[int, int]:
        return (round((x - min(xs) + margin_m) * px_per_m), round((max(ys) - y + margin_m) * px_per_m))

    image = np.full((height, width, 3), 255, np.uint8)
    for x0, y0, x1, y1 in rooms:
        cv2.rectangle(image, px(x0, y1), px(x1, y0), (0, 0, 0), wall_px)
    half = DOOR_M / 2
    for x, y, orientation in doors:
        if orientation == "h":
            a, b = px(x - half, y), px(x + half, y)
            cv2.rectangle(image, (a[0], a[1] - wall_px), (b[0], b[1] + wall_px), (255, 255, 255), -1)
        else:
            a, b = px(x, y + half), px(x, y - half)
            cv2.rectangle(image, (a[0] - wall_px, a[1]), (b[0] + wall_px, b[1]), (255, 255, 255), -1)
    return image


def to_png(image: np.ndarray) -> bytes:
    return cv2.imencode(".png", image)[1].tobytes()


# Labels for the fixture's cells (reading order: room west = 1, room east = 2, corridor = 3, stair = 4).
FIXTURE_LABELS = [
    {"cell": 1, "action": "room", "type": "room", "room_type": "office", "name": "Office 1", "ref": "1"},
    {"cell": 2, "action": "room", "type": "room", "room_type": "office", "name": "Office 2", "ref": "2"},
    {"cell": 3, "action": "room", "type": "corridor", "room_type": "corridor", "name": "Corridor"},
]
STAIR_LABEL = {"cell": 4, "action": "room", "type": "stair", "room_type": "stairwell", "name": "Stairs"}
WITH_STAIR = (
    TWO_ROOMS_AND_CORRIDOR[0] + [(10, 0, 13, 3)],
    TWO_ROOMS_AND_CORRIDOR[1] + [(10, 1.5, "v")],
)


def floor_from(fixture=TWO_ROOMS_AND_CORRIDOR, level: int = 0, offset_px: tuple[int, int] = (0, 0)):
    """A segmented, unlabelled FloorPlan of a fixture (optionally shifted on its sheet)."""
    from backend.core.plan_import.cells import segment_walls
    from backend.core.plan_import.model import FloorPlan

    image = draw_plan(*fixture)
    dx, dy = offset_px
    if dx or dy:
        image = cv2.copyMakeBorder(image, max(dy, 0), max(-dy, 0), max(dx, 0), max(-dx, 0), cv2.BORDER_CONSTANT,
                                   value=(255, 255, 255))
    return FloorPlan(level, "Ground floor" if level == 0 else f"Floor {level}", "s1", image, segment_walls(image))


def labelled_floor(level: int = 0, stair: bool = False, offset_px: tuple[int, int] = (0, 0)):
    from backend.core.plan_import.labels import apply_labels

    floor = floor_from(WITH_STAIR if stair else TWO_ROOMS_AND_CORRIDOR, level, offset_px)
    labels = FIXTURE_LABELS + ([STAIR_LABEL] if stair else [])
    problems = apply_labels(floor, labels, None, [3] if level == 0 else [])
    assert problems == [], problems
    return floor
