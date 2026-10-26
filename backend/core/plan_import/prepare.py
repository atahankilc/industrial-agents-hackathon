"""Stage 2 — make a plan image clean enough to segment: flatten a photographed sheet, crop to the plan drawing, and
find the walls (dark, unsaturated pixels — coloured fills such as green escape routes are not walls)."""

import cv2
import numpy as np

from backend.core.plan_import.model import Point

MIN_SHEET_FRACTION = 0.3  # a detected sheet must cover this much of the photo
WHOLE_IMAGE_FRACTION = 0.95  # a "sheet" this large is the scan itself: no warp
CROP_MARGIN = 0.02


def order_corners(points: np.ndarray) -> np.ndarray:
    """TL, TR, BR, BL."""
    points = points.reshape(4, 2).astype(np.float32)
    total, diff = points.sum(axis=1), np.diff(points, axis=1).ravel()
    return np.float32([points[np.argmin(total)], points[np.argmin(diff)], points[np.argmax(total)],
                       points[np.argmax(diff)]])


def find_sheet(image: np.ndarray) -> np.ndarray | None:
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    image_area = image.shape[0] * image.shape[1]
    if area < MIN_SHEET_FRACTION * image_area or area > WHOLE_IMAGE_FRACTION * image_area:
        return None
    quad = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
    return order_corners(quad) if len(quad) == 4 else None


def rectify(image: np.ndarray, corners: list[Point] | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    """Warp the sheet flat. `corners`: normalised TL, TR, BR, BL from the model; else the largest bright
    quadrilateral. Returns (image, homography source → output) or (image, None) when nothing to flatten."""
    height, width = image.shape[:2]
    if corners is not None:
        quad = order_corners(np.float32([[x * width, y * height] for x, y in corners]))
    else:
        quad = find_sheet(image)
        if quad is None:
            return image, None
    tl, tr, br, bl = quad
    out_w = int(round((np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2))
    out_h = int(round((np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2))
    target = np.float32([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]])
    homography = cv2.getPerspectiveTransform(quad, target)
    return cv2.warpPerspective(image, homography, (out_w, out_h), borderValue=(255, 255, 255)), homography


def crop(image: np.ndarray, bbox: tuple[float, float, float, float], homography: np.ndarray | None,
         source_shape: tuple[int, int] | None = None) -> np.ndarray:
    """`bbox` = (x0, y0, x1, y1) normalised in the *source* image (`source_shape` = its (h, w); defaults to `image`'s
    shape, i.e. no warp), mapped through `homography`; plus a 2 % margin, clipped to the image."""
    height, width = image.shape[:2]
    src_h, src_w = source_shape or (height, width)
    x0, y0, x1, y1 = bbox
    points = np.float32([[x0 * src_w, y0 * src_h], [x1 * src_w, y0 * src_h], [x1 * src_w, y1 * src_h],
                         [x0 * src_w, y1 * src_h]]).reshape(-1, 1, 2)
    if homography is not None:
        points = cv2.perspectiveTransform(points, homography)
    xs, ys = points[:, 0, 0], points[:, 0, 1]
    left = max(0, int(xs.min() - CROP_MARGIN * width))
    right = min(width, int(round(xs.max() + CROP_MARGIN * width)))
    top = max(0, int(ys.min() - CROP_MARGIN * height))
    bottom = min(height, int(round(ys.max() + CROP_MARGIN * height)))
    if right - left < 10 or bottom - top < 10:
        raise ValueError("the box is empty")
    return image[top:bottom, left:right].copy()


def wall_mask(image: np.ndarray, dark: int = 190, contrast: int = 50, max_saturation: int = 110,
              min_blob_px: int | None = None) -> np.ndarray:
    """255 = wall. A pixel is wall when it is dark (V < `dark`), clearly darker than the paper around it (local
    background − V > `contrast`, so uneven light in photos does not matter) and not strongly coloured (S <
    `max_saturation`: coloured fills and symbols are not walls). Connected blobs whose bounding box is shorter than
    `min_blob_px` on its long side (text, symbols) are dropped; default max(12, 1.5 % of the image's long side)."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    value = hsv[:, :, 2]
    size = max(15, (max(image.shape[:2]) // 40) | 1)
    background = cv2.dilate(value, np.ones((size, size), np.uint8))  # local paper brightness
    darker = background.astype(np.int16) - value.astype(np.int16)
    mask = ((value < dark) & (darker > contrast) & (hsv[:, :, 1] < max_saturation)).astype(np.uint8) * 255
    if min_blob_px is None:
        min_blob_px = max(12, round(0.015 * max(image.shape[:2])))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    small = np.zeros(count, bool)
    small[1:] = np.maximum(stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]) < min_blob_px
    mask[small[labels]] = 0
    return mask
