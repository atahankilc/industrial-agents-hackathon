# Dataset licences

The buildings in this folder come from the Industrial Agents Hackathon 2026 student kit
([Synera-GmbH/industrial-agents-hackathon-2026](https://github.com/Synera-GmbH/industrial-agents-hackathon-2026)),
which converted them from the sources below. The data is **not** covered by this repository's MIT licence.
Every `building.json` names its own licence and attribution in `building.license` / `building.attribution`, and
so does `manifest.csv` (`license` column). Details of what the kit changed: [../ATTRIBUTION.md](../ATTRIBUTION.md).

| `source` | Buildings | Licence | Attribution |
|---|---|---|---|
| `swiss_dwellings` | 109 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Swiss Dwellings, Archilyse AG / Standfest et al., https://zenodo.org/records/7070952 |
| `resplan` | 105 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | ResPlan, Agour et al., https://github.com/m-agour/ResPlan |
| `osm_indoor` | 17 | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | © OpenStreetMap contributors, https://www.openstreetmap.org/copyright |
| `procedural` | 49 | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | generated for the Munich hackathon |

## What this means for us

- **CC BY 4.0:** sharing and adapting are allowed if we credit the source, link the licence and indicate changes.
  Credit is in each file and here; the kit's changes are listed in `ATTRIBUTION.md`; buildings we edit or build
  are marked `synthetic: true` / saved as new files, never silently overwritten.
- **ODbL 1.0 (OSM buildings):** these files are a derived database. When shared they **stay under the ODbL**, and
  any modified version we publish must also be ODbL with "© OpenStreetMap contributors" credit. Maps or images we
  render from them (screenshots, demo video) are "produced works" and need the credit
  "© OpenStreetMap contributors" visible.
- **CC0:** no conditions.
