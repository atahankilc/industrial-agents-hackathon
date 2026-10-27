---
id: kit-repo-layout
summary: Layout of the organiser kit (now split between repo root and archive/initial-repo/), splits, data sources and dataset statistics.
sources:
  - archive/initial-repo/README.md §2
  - data/manifest.csv
  - ATTRIBUTION.md
  - "dataset scan of all 280 building.json files, 2026-10-24"
related: [data-format.md, questions.md, ../../archive/hackathon/docs/kit/starter-agent.md, ../guides/commands.md]
---

# Kit layout (as delivered)

> **In this repo (2026-10-27, [D-028](../../memory-bank/decisions.md#d-028)):** the three split folders are merged
> into `data/buildings/<building_id>/` (the split is the manifest's `split` column), the `floor_*.png` / `.svg`
> renders are deleted, and the test set's `questions.csv` / `submission_template.csv` are in
> `archive/hackathon/test-set/`. The layout below is the kit as delivered.

[Docs index](../README.md) · Schemas: [data-format.md](data-format.md)

As of 2026-10-24 `data/` and `benchmark/` live at the **repo root**, `starter_agent/building_map.py` was
copied to `core/` (now `backend/core/`), and everything else is in `archive/initial-repo/` ([D-004](../../memory-bank/decisions.md#d-004),
[archive/README.md](../../archive/README.md)). Since 2026-10-27 the scorer is `tests/kit_oracles/score.py`
([D-024](../../memory-bank/decisions.md#d-024)). Tree as delivered:

```
initial-repo/
├── README.md                 full kit README (authoritative)
├── ATTRIBUTION.md            data sources + licences
├── pyproject.toml            python ≥3.12; deps: anthropic≥2.1.0, matplotlib, networkx≥3.7, shapely≥2.2.0
├── .env.example              ANTHROPIC_API_KEY=
├── .student-kit              marker file ("built by benchmark.student_kit")
├── starter_agent/            example agent → see archive/hackathon/docs/kit/starter-agent.md
│   ├── agent.py              Claude tool-runner loop + system prompt
│   ├── tools.py              6 tools wrapping BuildingMap
│   ├── building_map.py       deterministic core: load, search, route, close, add door
│   ├── viewer.py             matplotlib PNG of last route per floor
│   ├── evaluate.py           warm-up evaluator (questions_basic.jsonl), --oracle mode
│   └── __main__.py           `python -m starter_agent <building_dir>`
├── benchmark/
│   ├── score.py              official scorer → archive/hackathon/docs/challenge/scoring.md
│   └── evaluate.py           runs an agent on questions.jsonl, writes submission CSV
└── data/                     ~209 MB
    ├── manifest.csv          one row per building
    ├── train/<building_id>/  200 buildings, answers included
    ├── dev/<building_id>/    40 buildings, answers included — self-evaluation
    └── test/<building_id>/   40 buildings, NO answers
        ├── questions.csv            all 145 test questions
        └── submission_template.csv  question_id,answer with every test id
```

## Per-building directory

| File | Content |
|---|---|
| `building.json` | the plan → [data-format.md](data-format.md#buildingjson) |
| `equipment.csv` | assets flattened → [data-format.md](data-format.md#equipmentcsv) |
| `floor_<level>.png` / `.svg` | plan with furniture |
| `floor_<level>_plain.png` | plan without furniture (useful input for Level 4 "build from plan") |
| `questions.jsonl` | benchmark questions (answers in train/dev only) → [questions.md](questions.md#benchmark-questions) |
| `questions_basic.jsonl` | warm-up questions with answers (train/dev only) → [questions.md](questions.md#warm-up-questions) |

Level values can be negative: files like `floor_-1.png` exist.

## Splits

| Split | Buildings | Benchmark Qs | Warm-up Qs |
|---|---|---|---|
| train | 200 | 517 | 1,761 |
| dev | 40 | 138 | 369 |
| test | 40 | **145 (submitted)** | – |

`group_id` in the manifest keeps buildings from one site in the same split (no leakage).

## Sources (count per split, from `manifest.csv`)

| `source` | train | dev | test | Character | Licence |
|---|---|---|---|---|---|
| `swiss_dwellings` | 85 | 12 | 12 | multi-floor residential; some floors **centred per floor, not aligned** | CC BY 4.0 |
| `resplan` | 85 | 10 | 10 | single-floor homes | CC BY 4.0 |
| `osm_indoor` | 9 | 4 | 4 | Munich: TUM, Airport T2, Pasing Arcaden, … ; refs may repeat ("WC") | **ODbL 1.0** |
| `procedural` | 21 | 14 | 14 | factories (halls, machines, docks, offices) + campus (lecture halls, labs, cores) | CC0 1.0 |

Test procedural buildings use layouts train never sees: bigger halls, L-shaped wings, basements, more cores.
Building ids encode the source: `swiss-*`, `resplan-*`, `osm-way*`, `proc-factory-*`, `proc-campus-*`.

## Dataset statistics (all 280 buildings)

| Thing | Values (count) |
|---|---|
| floors per building | 1 (106), 2 (22), 3 (50), 4 (49), 5 (29), 6 (16), 7 (6), 8 (1), 10 (1) |
| space `type` | room 16,223 · corridor 3,369 · outdoor 1,831 · stair 532 · lift 385 · hall 385 |
| opening `kind` | door 20,606 · opening 2,155 · entrance 987 |
| connector `kind` | stairs 576 · lift 136 |
| asset `category` | furniture 60,601 · equipment 13,217 · fixture 11,032 · machine 853 |

Most common `room_type`s: bedroom, generic_room, corridor, bathroom, kitchen, balcony, office, stairwell,
living_room, storage. Full list: [data-format.md](data-format.md#room-types).

## Related

- [data-format.md](data-format.md) · [questions.md](questions.md) · [starter-agent.md](../../archive/hackathon/docs/kit/starter-agent.md)
