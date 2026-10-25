"""Plan import, stage 4: apply the model's labels (core/plan_import/labels.py)."""

from core.plan_import.labels import apply_labels, render_labels
from tests.plan_fixtures import FIXTURE_LABELS, floor_from, labelled_floor

PX_PER_M = 20


def test_fixture_labels_cleanly():
    floor = floor_from()
    problems = apply_labels(floor, FIXTURE_LABELS, None, [3])
    assert problems == []
    assert {label.name for label in floor.labels.values()} == {"Office 1", "Office 2", "Corridor"}
    assert len([d for d in floor.doors if "outside" not in d.cells]) == 2
    assert len([d for d in floor.doors if "outside" in d.cells]) == 1


def test_merge_and_label():
    floor = floor_from()
    problems = apply_labels(floor, [
        {"cell": 1, "action": "room", "type": "room", "room_type": "office", "name": "Office 1"},
        {"cell": 2, "action": "merge", "into": 1},
        {"cell": 3, "action": "room", "type": "corridor", "room_type": "corridor", "name": "Corridor"},
    ], None, [3])
    assert problems == []
    assert len(floor.labels) == 2 and 2 not in floor.seg.cells
    assert floor.seg.cells[1].area_px > 36 * PX_PER_M ** 2
    assert len([d for d in floor.doors if "outside" not in d.cells]) == 2  # both doors now (1, 3)


def test_unknown_room_type_and_missing_label_are_problems():
    floor = floor_from()
    problems = apply_labels(floor, [{"cell": 1, "action": "room", "type": "room", "room_type": "foyer", "name": "X"}],
                            None, None)
    text = " ".join(problems)
    assert "unknown room_type 'foyer'" in text
    assert "cell 2 has no label" in text and "cell 3 has no label" in text


def test_explicit_doors_replace_candidates_and_check_adjacency():
    floor = floor_from()
    problems = apply_labels(floor, FIXTURE_LABELS, [[1, 3], "d2", [1, 9]], [3])
    assert "cells 1 and 9 are not adjacent" in " ".join(problems)
    pairs = sorted(d.cells for d in floor.doors if "outside" not in d.cells)
    assert len(pairs) == 2


def test_entrance_without_a_candidate_is_put_on_the_outside_wall():
    floor = floor_from()
    problems = apply_labels(floor, FIXTURE_LABELS, None, [1])  # room 1 has no door to outside in the drawing
    assert problems == []
    entrance = [d for d in floor.doors if d.cells == (1, "outside")]
    assert len(entrance) == 1


def test_ground_floor_without_entrance_is_a_problem():
    floor = floor_from()
    floor.seg.doors = [d for d in floor.seg.doors if "outside" not in d.cells]
    assert "no entrance on this floor" in apply_labels(floor, FIXTURE_LABELS, None, None)


def test_labels_add_up_over_calls():
    floor = floor_from()
    apply_labels(floor, FIXTURE_LABELS[:2], None, [3])
    problems = apply_labels(floor, FIXTURE_LABELS[2:], None, [3])
    assert problems == [] and len(floor.labels) == 3


def test_stair_fixture_and_render():
    floor = labelled_floor(stair=True)
    assert any(label.type == "stair" for label in floor.labels.values())
    assert render_labels(floor)[:8] == b"\x89PNG\r\n\x1a\n"


def test_door_numbers_stay_the_ones_the_model_saw_after_a_merge():
    floor = floor_from()
    seen = {f"d{index}": door.cells for index, door in enumerate(floor.seg.doors, start=1)}  # as rendered
    to_corridor_from_2 = next(name for name, cells in seen.items() if cells == (2, 3))
    apply_labels(floor, [{"cell": 1, "action": "merge", "into": 3}], None, None)  # (1, 3) becomes a self-door, dropped
    apply_labels(floor, [{"cell": 2, "action": "room", "type": "room", "room_type": "office", "name": "Office 2"},
                         {"cell": 3, "action": "room", "type": "corridor", "room_type": "corridor", "name": "Corridor"}],
                 [to_corridor_from_2], [3])
    assert [door.cells for door in floor.doors if "outside" not in door.cells] == [(2, 3)]
