"""Plan import, stage 3: rooms as cells (core/plan_import/cells.py)."""

import cv2
import numpy as np

from core.plan_import.cells import cells_from_boxes, render_cells, segment_colours, segment_walls, wall_thickness
from core.plan_import.prepare import wall_mask
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan

PX_PER_M = 20


def inner(seg):
    return [cell for cell in seg.cells.values() if not cell.outside]


def test_wall_thickness_is_measured():
    assert 3 <= wall_thickness(wall_mask(draw_plan(*TWO_ROOMS_AND_CORRIDOR))) <= 7  # cv2 draws thickness 4 as ~5 px


def test_two_rooms_and_corridor():
    seg = segment_walls(draw_plan(*TWO_ROOMS_AND_CORRIDOR, px_per_m=PX_PER_M))
    areas = sorted(cell.area_px / PX_PER_M ** 2 for cell in inner(seg))
    assert len(areas) == 3
    assert all(abs(area - want) / want < 0.12 for area, want in zip(areas, [20, 20, 40]))  # m², to the wall centre
    between = [door for door in seg.doors if "outside" not in door.cells]
    entrances = [door for door in seg.doors if "outside" in door.cells]
    assert len(between) == 2 and len(entrances) == 1
    assert all(0.9 * PX_PER_M * 0.8 < door.width_px < 0.9 * PX_PER_M * 1.25 for door in seg.doors)
    assert len(seg.adjacency) >= 3  # room–room, room–corridor ×2


def test_cells_are_numbered_in_reading_order():
    seg = segment_walls(draw_plan(*TWO_ROOMS_AND_CORRIDOR))
    first, second, third = sorted(inner(seg), key=lambda cell: cell.id)
    centre = lambda cell: np.mean(cell.polygon, axis=0)  # noqa: E731
    assert centre(first)[0] < centre(second)[0] and centre(third)[1] > centre(first)[1]


def test_render_cells_is_png():
    image = draw_plan(*TWO_ROOMS_AND_CORRIDOR)
    assert render_cells(image, segment_walls(image))[:8] == b"\x89PNG\r\n\x1a\n"


def filled_rooms_no_walls() -> np.ndarray:
    image = np.full((300, 600, 3), 255, np.uint8)
    cv2.rectangle(image, (50, 50), (250, 250), (180, 220, 180), -1)
    cv2.rectangle(image, (250, 50), (450, 250), (170, 200, 240), -1)
    cv2.rectangle(image, (450, 50), (560, 250), (240, 200, 170), -1)
    for x in range(250, 460, 12):  # diagonal hatching over the middle room
        cv2.line(image, (x, 50), (x - 60, 250), (120, 150, 200), 1)
    return image


def test_colour_regions_become_cells():
    seg = segment_colours(filled_rooms_no_walls())
    assert seg.method == "colours"
    assert len(inner(seg)) == 3
    assert len(seg.adjacency) >= 2


def test_boxes_become_cells():
    seg = cells_from_boxes((400, 800), [(0, 0, .5, 1), (.5, 0, 1, 1)])
    assert seg.method == "coarse" and len(seg.cells) == 2 and (1, 2) in seg.adjacency


def test_boxes_with_small_gaps_still_touch():
    seg = cells_from_boxes((400, 800), [(0, 0, .48, 1), (.52, 0, 1, 1)])
    assert (1, 2) in seg.adjacency
