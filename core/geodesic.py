"""Geodesic walking distances inside one space — the second route model (Q-014).

The Sunday scorer measures distance inside each space from door to door, about 15 cm off the walls, around
corners and never through walls. The exact organiser rule is UNVERIFIED (memory-bank/open-questions.md Q-014);
this module is our approximation of it.

Model:
- Walkable region W = the space polygon shrunk by `clearance` with mitre joins. With mitre joins each reflex
  corner of the room becomes one vertex of W, `clearance` away from both walls (round joins would give an arc).
- Near a door or point (within DOORWAY_RADIUS_M, clipped to the polygon) the path may be closer to the walls, so
  it can leave a door in a straight line.
- Shortest paths run on a visibility graph: the points plus the reflex vertices of W. An edge is allowed when
  its segment lies in W or a door disc (1e-6 m tolerance). A point outside W is also joined to its nearest
  point on W, so every point can reach the region.
- Fallbacks: if W is empty or a pair is not connected, the same graph on the raw polygon (clearance 0); if
  still not connected, the straight-line distance. Valid input never raises.

Results are cached per (polygon, points, clearance), rounded to the micrometre.
"""

import functools
import math

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import nearest_points, unary_union

CLEARANCE_M = 0.15  # distance kept from walls
DOORWAY_RADIUS_M = 0.3  # near a door/point the path may be closer to walls than CLEARANCE_M
COVER_TOLERANCE_M = 1e-6
REFLEX_EPS = 1e-12
ROUND_DIGITS = 6

Coord = tuple[float, float]


def space_distances(polygon: list[list[float]] | tuple, points: list[tuple[float, float]] | tuple,
                    clearance: float = CLEARANCE_M) -> list[list[float]]:
    """Symmetric matrix of geodesic distances (m) between `points` inside the space."""
    dist, _ = _solve(_poly_key(polygon), _points_key(points), round(float(clearance), ROUND_DIGITS))
    return [list(row) for row in dist]


def space_path(polygon, points, i: int, j: int, clearance: float = CLEARANCE_M) -> list[tuple[float, float]]:
    """The polyline (starting at points[i], ending at points[j]) whose length is space_distances[i][j]."""
    pts = _points_key(points)
    _, paths = _solve(_poly_key(polygon), pts, round(float(clearance), ROUND_DIGITS))
    if i == j:
        return [pts[i]]
    if i < j:
        return list(paths[(i, j)])
    return list(reversed(paths[(j, i)]))


def _poly_key(polygon) -> tuple[Coord, ...]:
    return tuple((round(float(x), ROUND_DIGITS), round(float(y), ROUND_DIGITS)) for x, y in polygon)


def _points_key(points) -> tuple[Coord, ...]:
    return tuple((round(float(x), ROUND_DIGITS), round(float(y), ROUND_DIGITS)) for x, y in points)


@functools.lru_cache(maxsize=8192)
def _solve(poly: tuple[Coord, ...], pts: tuple[Coord, ...], clearance: float):
    """(distance matrix, {(i, j): path for i < j}) with the clearance → raw polygon → straight-line fallbacks."""
    n = len(pts)
    room = _room(poly)
    dist = [[0.0] * n for _ in range(n)]
    paths: dict[tuple[int, int], tuple[Coord, ...]] = {}
    attempts = [clearance, 0.0] if clearance > 0 else [0.0]
    results = [_graph_paths(room, pts, c) for c in attempts]
    for i in range(n):
        for j in range(i + 1, n):
            d, path = math.dist(pts[i], pts[j]), (pts[i], pts[j])
            for result in results:
                if result is not None and math.isfinite(result[0][i][j]):
                    d, path = result[0][i][j], result[1][(i, j)]
                    break
            dist[i][j] = dist[j][i] = d
            paths[(i, j)] = path
    return tuple(tuple(row) for row in dist), paths


def _room(poly: tuple[Coord, ...]) -> Polygon:
    room = Polygon(poly)
    if not room.is_valid:
        room = room.buffer(0)
    return room


def _graph_paths(room, pts: tuple[Coord, ...], clearance: float):
    """Shortest paths between `pts` on the visibility graph of `room` shrunk by `clearance`; None if W is empty."""
    walk = room.buffer(-clearance, join_style="mitre") if clearance > 0 else room
    if walk.is_empty:
        return None
    discs = [Point(p).buffer(DOORWAY_RADIUS_M).intersection(room) for p in pts]
    region = unary_union([walk, *discs]).buffer(COVER_TOLERANCE_M)
    shapely.prepare(region)
    walk_tol = walk.buffer(COVER_TOLERANCE_M)
    shapely.prepare(walk_tol)

    nodes: list[Coord] = list(pts)
    forced: list[tuple[int, int]] = []
    for idx, p in enumerate(pts):
        if not walk_tol.covers(Point(p)):
            q = nearest_points(walk, Point(p))[0]
            forced.append((idx, len(nodes)))
            nodes.append((q.x, q.y))
    nodes.extend(_reflex_vertices(walk))

    weights = _edge_weights(nodes, region, forced)
    dist, nxt = _floyd_warshall(weights)
    n = len(pts)
    paths = {}
    for i in range(n):
        for j in range(i + 1, n):
            paths[(i, j)] = _walk_path(nxt, nodes, pts, i, j) if math.isfinite(dist[i, j]) else None
    return dist[:n, :n].tolist(), paths


def _reflex_vertices(walk) -> list[Coord]:
    """Vertices where the region turns right (interior angle > 180°), on every ring of every part."""
    parts = walk.geoms if isinstance(walk, MultiPolygon) else [walk]
    out: list[Coord] = []
    for part in parts:
        if not isinstance(part, Polygon) or part.is_empty:
            continue
        part = orient(part, 1.0)
        for ring in [part.exterior, *part.interiors]:
            coords = list(ring.coords)[:-1]
            m = len(coords)
            for k in range(m):
                (ax, ay), (bx, by), (cx, cy) = coords[k - 1], coords[k], coords[(k + 1) % m]
                if (bx - ax) * (cy - by) - (by - ay) * (cx - bx) < -REFLEX_EPS:
                    out.append((bx, by))
    return out


def _edge_weights(nodes: list[Coord], region, forced: list[tuple[int, int]]) -> np.ndarray:
    m = len(nodes)
    weights = np.full((m, m), np.inf)
    np.fill_diagonal(weights, 0.0)
    pairs = [(a, b) for a in range(m) for b in range(a + 1, m)]
    if pairs:
        segments = [LineString([nodes[a], nodes[b]]) for a, b in pairs]
        ok = shapely.covers(region, segments)
        for (a, b), covered in zip(pairs, ok):
            if covered:
                weights[a, b] = weights[b, a] = math.dist(nodes[a], nodes[b])
    for a, b in forced:
        weights[a, b] = weights[b, a] = min(weights[a, b], math.dist(nodes[a], nodes[b]))
    return weights


def _floyd_warshall(weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dist = weights.copy()
    m = len(dist)
    nxt = np.where(np.isfinite(dist), np.arange(m)[None, :], -1)
    for k in range(m):
        alt = dist[:, k, None] + dist[None, k, :]
        better = alt < dist - 1e-12
        if better.any():
            dist = np.where(better, alt, dist)
            nxt = np.where(better, nxt[:, k, None], nxt)
    return dist, nxt


def _walk_path(nxt: np.ndarray, nodes: list[Coord], pts: tuple[Coord, ...], i: int, j: int) -> tuple[Coord, ...]:
    path = [pts[i]]
    cur = i
    while cur != j:
        cur = int(nxt[cur, j])
        path.append(nodes[cur] if cur >= len(pts) else pts[cur])
    return tuple(path)
