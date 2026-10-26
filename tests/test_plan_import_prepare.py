"""Plan import, stage 2: rectify a photographed sheet, crop the plan, wall mask (backend/core/plan_import/prepare.py)."""

import cv2
import numpy as np

from backend.core.plan_import.prepare import crop, rectify, wall_mask
from tests.plan_fixtures import TWO_ROOMS_AND_CORRIDOR, draw_plan

PX_PER_M, MARGIN_M = 20, 2


def sheet() -> np.ndarray:
    return draw_plan(*TWO_ROOMS_AND_CORRIDOR, px_per_m=PX_PER_M, margin_m=MARGIN_M)


def photographed(flat: np.ndarray) -> np.ndarray:
    """The sheet on a grey wall, seen at an angle."""
    h, w = flat.shape[:2]
    canvas = np.full((h * 2, w * 2, 3), 90, np.uint8)
    source = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    target = np.float32([[w * 0.35, h * 0.3], [w * 1.7, h * 0.4], [w * 1.6, h * 1.6], [w * 0.4, h * 1.5]])
    warp = cv2.getPerspectiveTransform(source, target)
    return cv2.warpPerspective(flat, warp, (w * 2, h * 2), dst=canvas, borderMode=cv2.BORDER_TRANSPARENT)


def test_rectify_flattens_a_skewed_sheet():
    flat = sheet()
    out, homography = rectify(photographed(flat))
    assert homography is not None
    assert abs(out.shape[1] / out.shape[0] - flat.shape[1] / flat.shape[0]) < 0.08


def test_rectify_leaves_a_scan_alone():
    out, homography = rectify(sheet())
    assert homography is None and out.shape == sheet().shape


def test_rectify_with_model_corners():
    skewed = photographed(sheet())
    corners = [(0.175, 0.15), (0.85, 0.2), (0.8, 0.8), (0.2, 0.75)]
    out, homography = rectify(skewed, corners=corners)
    assert homography is not None and min(out.shape[:2]) > 50


def test_crop_maps_the_box_through_the_homography():
    image = sheet()
    out = crop(image, (0.5, 0.0, 1.0, 1.0), None)
    assert abs(out.shape[1] - image.shape[1] * 0.52) <= 3  # half + 2 % margin on the open side
    assert out.shape[0] == image.shape[0]


def test_wall_mask_ignores_green_fill_and_text():
    image = sheet()
    corridor_centre = (MARGIN_M * PX_PER_M + 5 * PX_PER_M, MARGIN_M * PX_PER_M + 6 * PX_PER_M)  # (x, y) px
    cv2.floodFill(image, None, corridor_centre, (120, 200, 120))  # green escape-route fill (BGR)
    cv2.putText(image, "WC", (MARGIN_M * PX_PER_M + 30, MARGIN_M * PX_PER_M + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                (0, 0, 0), 1)
    mask = wall_mask(image)
    x, y = corridor_centre
    assert mask[y, x] == 0
    text_box = mask[MARGIN_M * PX_PER_M + 28:MARGIN_M * PX_PER_M + 42, MARGIN_M * PX_PER_M + 28:MARGIN_M * PX_PER_M + 52]
    assert text_box.sum() == 0
    assert mask[MARGIN_M * PX_PER_M, MARGIN_M * PX_PER_M + 50] == 255  # top wall
