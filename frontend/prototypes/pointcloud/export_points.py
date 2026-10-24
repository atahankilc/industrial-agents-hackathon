"""Sample a deterministic point cloud from a building.json for the point-cloud viewer (index.html).

  uv run python frontend/prototypes/pointcloud/export_points.py data/train/proc-campus-train-001 out.json \
      [--route FROM TO] [--step-free] [--wall-step 0.15] [--wall-vstep 0.25] [--floor-step 0.6] [--seed 7]

Thin CLI over core.pointcloud (sampling, viewer frame, route polyline live there). --route adds a `route` key:
the exact route model's path (core.navigation.find_route) drawn by core.pointcloud.route_vertices."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.building_map import BuildingMap  # noqa: E402
from core.navigation import find_route  # noqa: E402
from core.pointcloud import export_points, route_vertices  # noqa: E402


def route_export(result: dict, building_map: BuildingMap, start: str, destination: str, step_free: bool) -> dict:
    route = find_route(building_map, start, destination, step_free=step_free)
    if not route.reachable:
        raise SystemExit(f"no route: {route.reason}")
    return {
        "from": building_map.describe_space(route.from_space_id),
        "to": building_map.describe_space(route.to_space_id),
        "length_m": route.length_m,
        "step_free": step_free,
        "steps": route.steps,
        "vertices": route_vertices(result, building_map, route.space_path, route.element_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("building", type=Path, help="building directory (with building.json)")
    parser.add_argument("output", type=Path)
    parser.add_argument("--route", nargs=2, metavar=("FROM", "TO"), help="space id / exact room name or ref")
    parser.add_argument("--step-free", action="store_true")
    parser.add_argument("--wall-step", type=float, default=0.15, help="horizontal spacing along walls (m)")
    parser.add_argument("--wall-vstep", type=float, default=0.25, help="vertical spacing on walls (m)")
    parser.add_argument("--floor-step", type=float, default=0.6, help="floor-slab grid spacing (m)")
    parser.add_argument("--asset-density", type=float, default=40.0, help="asset points per m³")
    parser.add_argument("--max-points", type=int, default=180_000, help="coarsen sampling above this")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    building_map = BuildingMap.load(args.building)
    result = export_points(building_map, wall_step=args.wall_step, wall_vstep=args.wall_vstep,
                           floor_step=args.floor_step, asset_density=args.asset_density,
                           max_points=args.max_points, seed=args.seed)
    result["route"] = route_export(result, building_map, *args.route, args.step_free) if args.route else None
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    route = f", route {result['route']['length_m']} m" if result["route"] else ""
    print(f"{result['count']} points, {args.output.stat().st_size / 1e6:.2f} MB{route} -> {args.output}")


if __name__ == "__main__":
    main()
