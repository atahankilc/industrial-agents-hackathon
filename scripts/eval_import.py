"""Plan-import eval on the dataset's floor renders (`floor_<k>_plain.png` = a drawing of the floor's building.json,
docs/superpowers/specs/2026-10-25-plan-import-design.md#evaluation).

    uv run python scripts/eval_import.py --segment-only [--n 30] [--method walls|colours]
        no model: segmentation cells vs the floor's spaces (count ratio, best IoU per space after fitting bboxes)
    uv run --env-file .env python scripts/eval_import.py --full [--n 10]
        the whole Creator per floor image: room count, matched IoU, door-connected pairs found, check() errors

The sample is fixed (seeded) and mixes the dataset's sources. Stop-tuning bar (spec): median room count within
±20 %, ≥ 70 % of door-connected pairs found, 0 validate errors."""

import argparse
import json
import random
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = 7


def sample(n: int) -> list[tuple[Path, int]]:
    """(building dir, floor index) pairs, balanced over the sources (procedural, osm, resplan, swiss)."""
    by_source: dict[str, list[tuple[Path, int]]] = {}
    for render in sorted(DATA.glob("*/*/floor_*_plain.png")):
        if render.parent.parent.name == "test":
            continue
        source = render.parent.name.split("-")[0]
        by_source.setdefault(source, []).append((render.parent, int(render.stem.split("_")[1])))
    rng = random.Random(SEED)
    picked: list[tuple[Path, int]] = []
    pools = {source: rng.sample(items, len(items)) for source, items in sorted(by_source.items())}
    while len(picked) < n and any(pools.values()):
        for pool in pools.values():
            if pool and len(picked) < n:
                picked.append(pool.pop())
    return picked


def truth(building_dir: Path, level: int) -> tuple[dict, list[dict]]:
    """`floor_<k>_plain.png`: k is the floor's level."""
    building = json.loads((building_dir / "building.json").read_text(encoding="utf-8"))
    floor = next(f for f in building["floors"] if f["level"] == level)
    return building, [s for s in building["spaces"] if s["floor_id"] == floor["id"]]


def fit(points: np.ndarray, source_box, target_box, flip: bool) -> np.ndarray:
    (sx0, sy0, sx1, sy1), (tx0, ty0, tx1, ty1) = source_box, target_box
    x = (points[:, 0] - sx0) / max(sx1 - sx0, 1e-9) * (tx1 - tx0) + tx0
    y = ((sy1 - points[:, 1]) if flip else (points[:, 1] - sy0)) / max(sy1 - sy0, 1e-9) * (ty1 - ty0) + ty0
    return np.c_[x, y]


def match(cells: list[Polygon], spaces: list[Polygon]) -> list[float]:
    """Best IoU of every true space with any cell."""
    scores = []
    for space in spaces:
        best = 0.0
        for cell in cells:
            if cell.intersects(space):
                union = cell.union(space).area
                best = max(best, cell.intersection(space).area / union if union else 0.0)
        scores.append(best)
    return scores


def bounds(polygons: list[Polygon]):
    xs = [b for p in polygons for b in (p.bounds[0], p.bounds[2])]
    ys = [b for p in polygons for b in (p.bounds[1], p.bounds[3])]
    return min(xs), min(ys), max(xs), max(ys)


def segment_only(n: int, method: str) -> None:
    from core.plan_import.cells import segment_colours, segment_walls

    rows = []
    for building_dir, index in sample(n):
        image = cv2.imread(str(building_dir / f"floor_{index}_plain.png"))
        seg = segment_walls(image) if method == "walls" else segment_colours(image)
        cells = [Polygon(c.polygon).buffer(0) for c in seg.cells.values() if not c.outside and len(c.polygon) >= 3]
        _, spaces = truth(building_dir, index)
        true = [Polygon(s["polygon"]).buffer(0) for s in spaces]
        if not cells or not true:
            rows.append((building_dir.name, index, len(cells), len(true), 0.0, 0.0))
            continue
        mapped = [Polygon(fit(np.array(p.exterior.coords), bounds(true), bounds(cells), flip=True)).buffer(0)
                  for p in true]
        scores = match(cells, mapped)
        rows.append((building_dir.name, index, len(cells), len(true), float(np.mean(scores)),
                     sum(score >= 0.5 for score in scores) / len(scores)))
    print(f"{'building':28} {'floor':>5} {'cells':>6} {'rooms':>6} {'meanIoU':>8} {'IoU≥.5':>7}")
    for name, index, cells, rooms, mean, good in rows:
        print(f"{name:28} {index:>5} {cells:>6} {rooms:>6} {mean:>8.2f} {good:>7.0%}")
    ratios = [cells / rooms for _, _, cells, rooms, _, _ in rows if rooms]
    print(f"\nmedian count ratio {statistics.median(ratios):.2f} · within ±20 %: "
          f"{sum(0.8 <= r <= 1.2 for r in ratios)}/{len(ratios)} · median mean-IoU "
          f"{statistics.median(r[4] for r in rows):.2f} · median share IoU≥0.5 {statistics.median(r[5] for r in rows):.0%}")


def door_pairs(building: dict, space_ids: set[str]) -> set[frozenset]:
    return {frozenset(o["space_ids"]) for o in building["openings"]
            if "outside" not in o["space_ids"] and set(o["space_ids"]) <= space_ids}


def full(n: int) -> None:
    from agent.creator import Creator
    from agent.creator_tools import ImportSession
    from core.plan_import.ingest import load_sources

    rows, spent = [], {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0}
    for building_dir, index in sample(n):
        render = building_dir / f"floor_{index}_plain.png"
        sources, warnings = load_sources([(render.name, render.read_bytes())])
        started = time.monotonic()
        result = Creator(ImportSession(sources, warnings)).run()
        seconds = time.monotonic() - started
        usage = result.usage
        spent["in"] += usage.input_tokens
        spent["out"] += usage.output_tokens
        spent["cache_read"] += usage.cache_read_input_tokens
        spent["cache_write"] += usage.cache_creation_input_tokens
        gold, spaces = truth(building_dir, index)
        if result.building is None:
            rows.append((building_dir.name, index, result.status, 0, len(spaces), 0.0, 0.0, -1, seconds))
            continue
        made = [s for s in result.building["spaces"]]
        true = [Polygon(s["polygon"]).buffer(0) for s in spaces]
        mine = [Polygon(s["polygon"]).buffer(0) for s in made]
        mapped = [Polygon(fit(np.array(p.exterior.coords), bounds(mine), bounds(true), flip=False)).buffer(0)
                  for p in mine]
        scores = match(mapped, true)
        # door-connected pairs: map each true space to the made space with the best IoU (≥ 0.5)
        owner = {}
        for space, polygon in zip(spaces, true):
            best = max(range(len(mapped)), key=lambda i: polygon.intersection(mapped[i]).area, default=None)
            if best is not None:
                union = polygon.union(mapped[best]).area
                if union and polygon.intersection(mapped[best]).area / union >= 0.5:
                    owner[space["id"]] = made[best]["id"]
        true_pairs = door_pairs(gold, {s["id"] for s in spaces})
        made_pairs = door_pairs(result.building, {s["id"] for s in made})
        found = sum(1 for pair in true_pairs
                    if all(p in owner for p in pair) and frozenset(owner[p] for p in pair) in made_pairs)
        errors = sum(issue["severity"] == "error" for issue in result.issues)
        rows.append((building_dir.name, index, "done", len(made), len(spaces), float(np.mean(scores)),
                     found / len(true_pairs) if true_pairs else 1.0, errors, seconds))
    print(f"{'building':28} {'floor':>5} {'status':>8} {'rooms':>9} {'meanIoU':>8} {'doors':>6} {'errors':>6} {'s':>5}")
    for name, index, status, made, rooms, mean, doors, errors, seconds in rows:
        print(f"{name:28} {index:>5} {status:>8} {made:>4}/{rooms:<4} {mean:>8.2f} {doors:>6.0%} {errors:>6} "
              f"{seconds:>5.0f}")
    done = [r for r in rows if r[2] == "done"]
    if done:
        print(f"\nmedian count ratio {statistics.median(r[3] / r[4] for r in done if r[4]):.2f} · median mean-IoU "
              f"{statistics.median(r[5] for r in done):.2f} · median doors found {statistics.median(r[6] for r in done):.0%}"
              f" · runs with 0 errors {sum(r[7] == 0 for r in done)}/{len(done)} · finished {len(done)}/{len(rows)}")
    print(f"tokens: {spent}")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--segment-only", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument("--method", choices=["walls", "colours"], default="walls")
    args = parser.parse_args()
    if args.segment_only:
        segment_only(args.n or 30, args.method)
    else:
        full(args.n or 10)


if __name__ == "__main__":
    main()
