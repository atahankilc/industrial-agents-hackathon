"""Plan import, stage 5: scale, stacking, vertical connectors (core/plan_import/scale.py, stack.py)."""

import cv2
import numpy as np

from core.plan_import import stack
from core.plan_import.scale import ensure_scales, scale_from_bar, scale_from_doors, scale_prior
from core.plan_import.stack import align, connectors, to_frame
from tests.plan_fixtures import labelled_floor

M_PER_PX = 1 / 20  # fixtures are drawn at 20 px/m


def stair_id(floor) -> int:
    return next(cell_id for cell_id, label in floor.labels.items() if label.type == "stair")


def test_scale_from_doors_on_fixture():
    assert abs(scale_from_doors(labelled_floor()) - M_PER_PX) < 0.008


def test_scale_from_bar():
    floor = labelled_floor()
    width = floor.image.shape[1]
    assert abs(scale_from_bar(floor, (0.0, 0.5), (100 / width, 0.5), 5.0) - 0.05) < 1e-6


def test_scale_prior_is_rough_but_sane():
    assert 0.02 < scale_prior(labelled_floor()) < 0.1


def test_ensure_scales_prefers_doors_then_same_sheet():
    first, second = labelled_floor(), labelled_floor(level=1)
    second.doors = []
    ensure_scales([first, second])
    assert first.scale_method == "doors" and second.scale_method == "same_sheet"
    assert second.m_per_px == first.m_per_px


def test_two_shifted_floors_register_and_connect():
    ground = labelled_floor(0, stair=True)
    upper = labelled_floor(1, stair=True, offset_px=(40, 25))
    floors = [ground, upper]
    ensure_scales(floors)
    align(floors)
    assert ground.alignment == "frame" and upper.alignment == "registered"
    a = to_frame(ground, np.mean(ground.seg.cells[stair_id(ground)].polygon, axis=0))
    b = to_frame(upper, np.mean(upper.seg.cells[stair_id(upper)].polygon, axis=0))
    assert np.hypot(*(a - b)) < 0.5  # metres
    assert connectors(floors) == [("stairs", [(0, stair_id(ground)), (1, stair_id(upper))])]


def test_frame_is_metres_with_y_up():
    floor = labelled_floor()
    ensure_scales([floor])
    align([floor])
    xs, ys = zip(*[to_frame(floor, p) for c in floor.seg.cells.values() if not c.outside for p in c.polygon])
    assert abs(min(xs)) < 0.5 and abs(min(ys)) < 0.5 and 9 < max(xs) < 11 and 7 < max(ys) < 9


def test_unalignable_floor_is_centred(monkeypatch):
    def fail(*args, **kwargs):
        raise cv2.error("did not converge")

    monkeypatch.setattr(stack.cv2, "findTransformECC", fail)
    floors = [labelled_floor(0, stair=True), labelled_floor(1, stair=True, offset_px=(40, 25))]
    ensure_scales(floors)
    align(floors)
    assert floors[1].alignment == "centred" and floors[1].transform is not None
