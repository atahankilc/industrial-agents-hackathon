# Point-cloud building prototype

Standalone three.js viewer: a building rendered as a point cloud that **emerges** from a scattered noise
cloud, **densifies** with a slider, separates floors vertically, highlights a room and shows a route as
flowing particles. Design rationale: [docs/product/visualization.md](../../../docs/product/visualization.md).

The sampler now lives in `core/pointcloud.py` (also served by the backend at `GET /sessions/{id}/points` for
the app in `frontend/app/`); `export_points.py` is a thin CLI over it with the same flags and output.

## Run

```bash
# 1. export points (from the repo root); --route is optional, names/refs/ids resolved by core.BuildingMap
uv run python frontend/prototypes/pointcloud/export_points.py data/train/proc-campus-train-001 \
    frontend/prototypes/pointcloud/sample.json --route "Lecture hall 0.17" "Meeting room 3.04"

# 2. serve this folder and open http://127.0.0.1:8765/  (any export: ?data=<file>.json)
cd frontend/prototypes/pointcloud && python3 -m http.server 8765
```

Exporter options: `--wall-step` (0.15 m), `--wall-vstep` (0.25 m), `--floor-step` (0.6 m),
`--asset-density` (40 pts/m³), `--max-points` (180 000; sampling coarsens automatically above it),
`--step-free`, `--seed`.

## What is in a point

Viewer frame is y-up: building `(x, y, elevation)` → `(x, elevation, -y)`, centred on the bounding box,
positions stored as integer centimetres. Per point: `kind` (wall · floor · door · core · asset), `floor` index,
`space` index (into `spaces[]`), `reveal` 0–255 (random per point, deterministic by `--seed`).
Walls: polygon edges extruded up to min(floor height, 3 m); door openings are gaps up to 2.1 m with a lintel
row. Floors: jittered grid. Stairs/lifts: `core`. Assets: random cluster in the rotated footprint.
Route: full node path (rooms + door nodes) of the **exact** benchmark route model; vertical connectors drawn as
straight risers.

## Verified (2026-10-24, Chrome via Claude in Chrome)

| Building | Points | JSON | Notes |
|---|---|---|---|
| `proc-campus-train-001` (4 floors) — `sample.json` | 154 380 | 3.74 MB | route Lecture hall 0.17 → Meeting room 3.04 = 78.81 m |
| `osm-way22744230` (8 floors, dev) | 164 729 | 4.16 MB | budget auto-coarsened steps to 0.27 / 0.46 / 1.10 m |
| `proc-factory-test-001` | 135 292 | 3.68 MB | — |

- Renders, emergence animation completes in 4 s, density slider (15 %) thins the cloud, floor separation lifts
  floors and the route, search "Lecture hall" highlights the room and recentres the camera, OSM building loads
  via `?data=`. **No console errors.** Screenshots: `screenshots/`.
- Not tested: mobile browsers, performance on low-end GPUs.

`sample.json` is derived from a procedural (CC0) building.

## Data licence

The viewer shows each building's `attribution` in its info line. `sample.json` is a procedural building (CC0).
Exports and screenshots of OSM buildings (`osm-*`, e.g. `screenshots/osm-way22744230.jpg`) are produced works of
ODbL data: credit **© OpenStreetMap contributors** (https://www.openstreetmap.org/copyright) wherever they are
shown. See [../../../data/README.md](../../../data/README.md).
