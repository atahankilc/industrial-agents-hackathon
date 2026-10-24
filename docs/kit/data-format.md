---
id: kit-data-format
summary: Schema of building.json, equipment.csv and manifest.csv, with conventions (units, frames, levels, outside, synthetic) and per-source quirks.
sources:
  - archive/initial-repo/README.md §3
  - ATTRIBUTION.md
  - "dataset scan of all 280 building.json files, 2026-10-24"
related: [route-model.md, questions.md, repo-layout.md, ../guides/glossary.md]
---

# Data format

[Docs index](../README.md) · Graph built from this: [route-model.md](route-model.md)

## Conventions

- **Units:** metres, local frame, x right, y up.
- **One XY frame per building** — floors stack. **Exception:** some Swiss Dwellings floors are centred per
  floor (not aligned). `room_stacked` questions therefore only use procedural and OSM buildings
  ([questions.md](questions.md#precise-definitions)).
- **`level`:** integer; 0 = ground, −1 = first basement, 1 = first upper floor.
- **Outside:** an opening whose `space_ids` contain the literal `"outside"` is an entrance.
- **`synthetic: true`:** added by the dataset, not in the source (recovered Swiss stair halls, OSM point-lifts
  turned into small spaces, guessed OSM doors). Treat as real for routing.

## `building.json`

Top-level keys (identical in all 280 files): `building`, `floors`, `spaces`, `openings`,
`vertical_connectors`, `assets`.

```jsonc
{
  "building": { "id": "proc-factory-dev-003", "name": "Fertigung Ost 27", "source": "procedural",
                "source_ref": {...}, "license": "CC0-1.0", "attribution": "...", "split": "dev", "units": "m" },
  "floors": [ { "id": "proc-factory-dev-003-F0", "level": 0, "name": "Ground floor",
                "elevation_m": 0.0, "height_m": 8.0 } ],
  "spaces": [ { "id": "proc-factory-dev-003-F0-S021", "floor_id": "proc-factory-dev-003-F0",
                "type": "room",               // room | corridor | stair | lift | hall | outdoor
                "room_type": "quality_lab",   // see Room types
                "name": "Quality lab 0.21", "ref": "0.21",
                "polygon": [[2.0,10.5],[6.5,10.5],[6.5,15.0],[2.0,15.0]],   // outline, NOT closed
                "synthetic": false } ],
  "openings": [ { "id": "...-F0-O0035", "floor_id": "...-F0",
                  "space_ids": ["...-S030", "...-S016"],  // exactly two; "outside" for entrances
                  "kind": "door",                         // door | opening (no leaf) | entrance
                  "position": [12.4, -5.0], "width_m": 0.9, "step_free": true, "synthetic": false } ],
  "vertical_connectors": [ { "id": "...-V02", "kind": "lift",   // stairs | lift
                             "name": "Office lift",
                             "floor_ids": ["...-F0", "...-F1"],         // one stop per floor
                             "space_ids": ["...-F0-S004", "...-F1-S004"],  // space of each stop (same order)
                             "step_free": true, "synthetic": false } ],
  "assets": [ { "id": "...-A00117", "name": "Coordinate measuring machine 0.21",
                "category": "machine",        // furniture | fixture | machine | equipment
                "type": "coordinate_measuring_machine",
                "space_id": "...-F0-S021", "floor_id": "...-F0",
                "position": [2.941, 12.964],
                "footprint": { "width_m": 2.0, "depth_m": 1.5, "rotation_deg": 90.0 },
                "source": "generated" } ]     // dataset | generated
}
```

### ID scheme

`<building_id>-F<level>` floor · `…-F<level>-S###` space · `…-F<level>-O####` opening · `…-V##` connector ·
`…-A#####` asset. Observed pattern, not a documented guarantee — use the `floor_id` field, not id parsing.
Basements use `F-1` (verified: `osm-way50300147-F-1`, level −1, name "Basement 1", elevation −3.0).
Floor names follow "Ground floor", "Floor 1", "Basement 1" — questions refer to floors as e.g. "the floor 1".

### Field notes

- **`name` / `ref`:** `name` usually contains the ref (`"Quality lab 0.21"`, ref `"0.21"`). Refs are unique per
  building for procedural, Swiss and ResPlan. **OSM refs come from the map; a few rooms share names ("WC").**
  Swiss names can carry apartment info: `"Bedroom 1.02 (apartment 5)"`.
- **Space area / centre:** not stored — compute from `polygon` with shapely (`Polygon(p).area`, `.centroid`).
- **Door widths (`width_m`):** Swiss/ResPlan from drawings. Procedural: 0.9 m offices · 1.1 m lifts · 1.2 m labs,
  seminar, meeting, libraries, toilets, stairwells · 1.6 m double doors for halls, storage, server, technical.
  OSM default 0.9 m.
- **`step_free: false`:** steps (a stair connector, or an entrance with steps).
- **Connectors:** join stop spaces floor-to-floor in level order (consecutive stops only).
- **Asset names** are unique within a building, e.g. `Desk 2.03-B` = second desk in room 2.03.
- **Asset `source`:** `dataset` = from the source data, `generated` = placed by rules.

### Room types

`bedroom`, `living_room`, `kitchen`, `bathroom`, `toilet`, `storage`, `corridor`, `balcony`, `stairwell`,
`lift`, `office`, `meeting_room`, `seminar_room`, `lecture_hall`, `lab`, `makerspace`, `library`,
`server_room`, `technical_room`, `lobby`, `canteen`, `shop`, `print_room`, `locker_room`, `production_zone`,
`additive_zone`, `assembly_zone`, `warehouse_zone`, `logistics_zone`, `quality_lab`, `generic_room`
(OSM room without type tag). `shop` is listed in the README but did not occur in the 2026-10-24 scan.

`type` (coarse) vs `room_type` (fine) are different fields. Which one defines "room" in count questions is
**not specified** → [Q-003](../../memory-bank/open-questions.md#q-003).

## `equipment.csv`

Columns: `asset_id, name, type, category, source, building_id, floor_level, floor_name, space_id, space_name,
room_ref, room_type, x_m, y_m, width_m, depth_m, rotation_deg`. Same data as `assets`, flattened + joined with
space/floor info.

## `manifest.csv`

Columns: `building_id, split, source, group_id, name, license, floors, levels, spaces, rooms, openings,
connectors, assets, has_stairs, has_lift, has_step_free_entrance, questions, path`. `levels` is `;`-separated
(e.g. `-1;0;1;2`); `path` is relative to `data/`.

## Related

- [route-model.md](route-model.md) — how spaces/openings/connectors become a graph
- [questions.md](questions.md) — which fields each question kind needs
- [glossary.md](../guides/glossary.md)
