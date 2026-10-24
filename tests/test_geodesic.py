"""Geodesic in-space distances (core/geodesic.py) on hand-checked rooms and one real building."""

import itertools
import json
import math
import time
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from core.geodesic import space_distances, space_path

DATA = Path(__file__).resolve().parents[1] / "data"

RECT = [[0, 0], [10, 0], [10, 4], [0, 4]]
L_ROOM = [[0, 0], [6, 0], [6, 2], [2, 2], [2, 6], [0, 6]]
U_ROOM = [[0, 0], [9, 0], [9, 6], [6, 6], [6, 2], [3, 2], [3, 6], [0, 6]]


def test_rectangle_inside_points_are_euclidean():
    d = space_distances(RECT, [(1, 1), (8, 3)])
    assert d[0][1] == pytest.approx(math.dist((1, 1), (8, 3)), abs=1e-6)
    assert d[0][0] == 0 and d[1][1] == 0
    assert d[0][1] == d[1][0]


def test_rectangle_doors_on_boundary_go_straight():
    d = space_distances(RECT, [(0, 2), (10, 2), (5, 2)])
    assert d[0][1] == pytest.approx(10.0, abs=1e-6)
    assert d[0][2] == pytest.approx(5.0, abs=1e-6)
    assert all(d[i][j] == d[j][i] for i in range(3) for j in range(3))


def test_l_room_bends_at_offset_reflex_corner():
    # The room's reflex corner (2, 2) becomes (1.85, 1.85) in the walkable region (0.15 m off both walls).
    corner = (1.85, 1.85)
    d = space_distances(L_ROOM, [(5, 1), (1, 5)])
    assert d[0][1] == pytest.approx(math.dist((5, 1), corner) + math.dist(corner, (1, 5)), abs=1e-6)
    path = space_path(L_ROOM, [(5, 1), (1, 5)], 0, 1)
    assert len(path) == 3
    for got, want in zip(path, [(5, 1), corner, (1, 5)]):
        assert got == pytest.approx(want, abs=1e-6)
    assert space_path(L_ROOM, [(5, 1), (1, 5)], 1, 0) == list(reversed(path))


def test_u_room_wraps_both_reflex_corners():
    # Reflex corners (3, 2) and (6, 2) become (2.85, 1.85) and (6.15, 1.85); from the left arm to the right arm
    # the path goes (1, 5) → (2.85, 1.85) → (6.15, 1.85) → (8, 5).
    a, b = (2.85, 1.85), (6.15, 1.85)
    expected = math.dist((1, 5), a) + math.dist(a, b) + math.dist(b, (8, 5))
    d = space_distances(U_ROOM, [(1, 5), (8, 5)])
    assert d[0][1] == pytest.approx(expected, abs=1e-6)
    path = space_path(U_ROOM, [(1, 5), (8, 5)], 0, 1)
    assert sum(math.dist(p, q) for p, q in itertools.pairwise(path)) == pytest.approx(expected, abs=1e-6)


def test_narrow_corridor_falls_back_to_straight_line():
    corridor = [[0, 0], [10, 0], [10, 0.2], [0, 0.2]]
    d = space_distances(corridor, [(0.5, 0.1), (9.5, 0.1)])
    assert d[0][1] == pytest.approx(9.0, abs=1e-6)


def _first_dev_building() -> dict:
    path = next(p / "building.json" for p in sorted((DATA / "dev").iterdir()) if (p / "building.json").exists())
    return json.loads(path.read_text())


def _space_points(building: dict) -> dict[str, list[tuple[float, float]]]:
    doors: dict[str, list[tuple[float, float]]] = {}
    for opening in building["openings"]:
        for sid in opening["space_ids"]:
            doors.setdefault(sid, []).append(tuple(opening["position"]))
    return doors


def test_real_building_door_pairs_and_timing():
    building = _first_dev_building()
    doors = _space_points(building)
    checked = 0
    for space in building["spaces"]:
        pts = doors.get(space["id"], [])
        if len(pts) < 2:
            continue
        d = space_distances(space["polygon"], pts)
        for i in range(len(pts)):
            for j in range(len(pts)):
                assert d[i][j] == d[j][i]
                assert d[i][j] >= math.dist(pts[i], pts[j]) - 1e-6
        checked += 1
        if checked >= 10:
            break
    assert checked > 0

    start = time.perf_counter()
    for space in building["spaces"]:
        rep = Polygon(space["polygon"]).representative_point()
        space_distances(space["polygon"], [*doors.get(space["id"], []), (rep.x, rep.y)])
    elapsed = time.perf_counter() - start
    print(f"\n{building['building']['id'] if isinstance(building['building'], dict) else ''}: "
          f"{len(building['spaces'])} spaces in {elapsed:.2f} s")
    assert elapsed < 10
