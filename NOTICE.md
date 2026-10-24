# Notice: what is ours and what comes from elsewhere

This repository mixes **our own code** with **third-party material from the organiser kit**. They are under
different terms. Not legal advice; this is our good-faith reading of the sources below (checked 2026-10-24).

| Path | Origin | Terms |
|---|---|---|
| everything not listed below | written by this team | MIT — see [LICENSE](LICENSE); the MIT licence covers only this team's code |
| `data/` | Industrial Agents Hackathon 2026 student kit, [Synera-GmbH/industrial-agents-hackathon-2026](https://github.com/Synera-GmbH/industrial-agents-hackathon-2026), built from the sources in [ATTRIBUTION.md](ATTRIBUTION.md) | **per source** — see [data/README.md](data/README.md) (CC BY 4.0, ODbL 1.0, CC0 1.0). **Not** MIT. |
| `benchmark/` | organiser kit (official scorer + evaluator), unmodified | © the organisers; the kit repo publishes no licence. Included unmodified so judges can reproduce our scores. |
| `archive/initial-repo/` | organiser kit (starter agent, kit README), unmodified | as `benchmark/` |
| `core/building_map.py` | derived from the kit's `starter_agent/building_map.py` | kit portions as `benchmark/`; our modifications MIT |
| `frontend/app/src/ui/VoiceOrb.tsx` (the `NOISE` GLSL string: 3D simplex noise) | adapted from [stegu/webgl-noise](https://github.com/stegu/webgl-noise) (fork of [ashima/webgl-noise](https://github.com/ashima/webgl-noise)) | MIT — Copyright (C) 2011 Ashima Arts (Simplex noise); Copyright (C) 2011-2016 Stefan Gustavson; full notice kept in the file. Rest of the file is ours (MIT). |
| `backend/locations.json` | positions of the kit's OSM buildings, derived from OpenStreetMap ways via the OSM API | ODbL 1.0 — © OpenStreetMap contributors |
| `Hackathon Challenge - Talk to Your Building.pdf` | challenge brief by Synera | © Synera; included for reference |

If the organisers or any rights holder want kit material removed from this public repository, open an issue and
we will remove it. Confirmation requested from the organisers: see `memory-bank/open-questions.md` (Q-013).
