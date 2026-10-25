---
id: product-visualization
summary: App visuals — the current vector plan view (core/floorplan.py, GET /sessions/{id}/plan, frontend/app/src/plan/) and the superseded point-cloud visual language; three.js vs react-three-fiber, performance, judging fit.
sources:
  - core/floorplan.py, backend/sessions.py (MapView.plan), frontend/app/src/plan/, frontend/app/src/building/ (verified 2026-10-24)
  - frontend/app/src/dev/, backend/devtools.py, core/routeline.py (dev panel, verified 2026-10-24)
  - frontend/app/src/plan/ObjectsLayer.tsx, src/plan/palette.ts (access mode, verified 2026-10-25)
  - frontend/app/src/map/bridge.ts, src/building/opening.ts, src/Root.tsx (map → building transition, verified headless 2026-10-24)
  - https://threejs.org/docs/ (three.js r160)
  - https://r3f.docs.pmnd.rs/ (react-three-fiber)
related: [../architecture/overview.md, personas.md, routing-profiles.md, ../architecture/ai-agents.md]
---

# Visualization

[Docs index](../README.md) · System: [overview.md](../architecture/overview.md)

## Current: vector plan view (2026-10-24)

Direction "Drawing Set" (`PRODUCT.md`, `.impeccable/surfaces/frontend-app.md`). Landing is a map of the
buildings with a real position plus a list view for the rest (see **Landing** below); `Root.tsx` opens `BuildingScreen` (`src/building/`) over an orthographic r3f plan
(`src/plan/`: rooms, walls with door gaps, doorway threshold strips, furniture, labels that only show when they fit, tap a room →
place card) with a floating Guide conversation.

- **Furniture heights are ours:** the kit gives each asset only a footprint (width, depth, rotation), so heights and parts
  are per-type models in `src/plan/furniture.ts`. Pieces whose length varies are laid out from the real width instead of
  stretched: lecture seating rows get one seat per 0.50 m (the kit's chair width), kitchen counters and wardrobes one
  front seam per 0.60 m module (the kit's wardrobe/appliance widths). No invented detail (no sink or hob on counters,
  no stair direction: the kit has neither).
- **Data:** `core/floorplan.py` `export_plan(building_map)` → floors, spaces (polygon, label point), walls
  per floor with door gaps cut, openings (wall angle only: the kit has no swing data, so the plan draws no door leaves, just a threshold
  strip per doorway: blue, entrances accent blue, closed doors red), connectors, assets in drawn spaces, `closed`,
  and `center` (centre of the space bounds; the y-up scene uses `X = x - cx`, `Z = -y - cz`). Served by
  `GET /sessions/{id}/plan`, cached in `MapView.plan` per building object. Route events from `/events` carry
  turn-by-turn `legs` but no polyline: a route line on the plan still needs one in the plan frame.
- **Landing:** a city map (`frontend/app/src/map/MapLanding.tsx`; MapLibre GL JS on OpenFreeMap's hosted
  `positron` / `dark` styles, free, no key), tilted 50°, every building in the tiles extruded from zoom 14 to its
  OSM height (`render_height` / `render_min_height`, streamed with the tiles), a pin per building that has a real
  position, and a panel listing them; tap a pin or a row → `BuildingScreen`. Positions come from `GET /buildings` `location` ({lat, lon, address}
  or null), read from `backend/locations.json`: the centre of the OSM outline of the 17 `osm-way*` buildings, made
  by the archived twin-lab `georef.py` (OSM API; fit median 0.05–6.6 m). Swiss, ResPlan and procedural buildings
  have no position; the list view (`?view=list`, `src/search/`) searches all 280 and has a "No location" filter.
  The building's back pill returns to whichever of the two it was opened from. "All floors" stacks the cutaway
  floors at their real `elevation_m`. (An outside "shell" view of the closed building was tried and removed the
  same day: the data has no windows, and Atahan preferred the map.)
- **Map → building (2026-10-24):** the map stays mounted under the building screen (`src/Root.tsx`). A tap flies
  the map in to the building (`MapLanding` focus, 1.5 s) while the session and plan load (`src/building/opening.ts`,
  started on the tap, one session per visit); the model then takes over from the map's own camera and eases to its
  first framing while it rises out of the ground (`PlanView` `Reveal`, 0.9 s; also for buildings with no position).
  From then on the map follows the model's camera every frame (`src/map/bridge.ts`): the kit frame is metres x east,
  y north from `location.origin` (the fitted kit (0, 0) from `georef.py`, added to `backend/locations.json`), and
  the map narrows its field of view to 1° so its perspective matches the orthographic model (measured ≤ 10 px apart at the screen corners, ≤ 1 px at the centre; 4° was up to 40 px; below 1° MapLibre drops its tiles when tilted), and the model tilts at most 60° over the map (past 60° MapLibre switches tile selection and, at that field of view, draws no buildings at z15–18). The map blocks over the
  open building (overlap with the plan outline: block centre in it, its centre in the block, or most block corners in
  it; tile ids are not the kit's way ids) move to a see-through shell layer (`buildings-3d-shell`, opacity 0.22 light /
  0.16 dark), so a campus wing that the tiles draw as one block with its neighbours no longer boxes the model in.
  Back fades the model out (0.35 s) while the map flies out to every pin.
- **Buildings with a model on the map:** drawn as accent-blue blocks (`MapLanding` `models` source): the kit
  footprint (`location.outline`: union of the kit's spaces on every floor, outset 0.6 m for the exterior walls,
  placed by `origin`), as tall as the kit (`location.height_m`) or the OSM block it stands in, whichever is taller,
  so the blue wraps the grey block. Tinting the tiles' own blocks does not work: the TUM main building is one tile
  polygon around the whole block, its kit buildings are wings of it. Light mode got its own palette (2026-10-25):
  stronger greens and water, white roads with grey casings, brighter side light on the blocks.
- **Fitting the kit onto the map** (`scripts/fit_locations.py`, 2026-10-25): the archived georef origins were up to
  ~18 m off for some buildings (N8, Arcisstraße 21, U-Trakt). The script fetches each OSM way (cached in `.cache/osm/`),
  shifts the kit's ground-floor footprint to the best overlap (a rotation search added nothing) and moves `origin`,
  then rewrites `outline` and `height_m`. Only where the kit footprint is ≥ 75 % of the way: Wolf-Ferrari-Haus (Ottobrunn),
  Mensa Arcisstraße, Terminal 2 (Freising), Haus der Weiterbildung and Pasing Arcaden model only part of their OSM
  building (area ratio 0.3–0.6), so no shift can make them match. Overlap with the way after the fit: 0.78–0.99.
- **Opening a building** shows all floors stacked (one-floor buildings: that floor). The fly-in, hand-off and rise also
  play with the system's "reduce motion" on (flight 1.0 s instead of 1.5 s); the app's global reduced-motion CSS rule
  (`styles.css`) still turns the fades into cuts.
- **Two ways to show a building with a position** (menu, remembered per browser, `ttyb-building-showing`): **in the
  city** (default, the neighbours and their pins around the model; tapping a pin flies over and opens that building)
  or **alone** (the plan's own stage and grid cover the map once the model is there; meant for building managers).
  Buildings without a position only have the alone view.
- **Not built yet:** Guide events on the plan (focus, route line, closures, lost access), 3D, maintainer edits.

## Dev panel

`frontend/app/src/dev/` (merged into the app 2026-10-24): a panel to try every Guide capability by hand through
the backend's `/dev` endpoints (`backend/devtools.py`), and the current answer drawn over the plan without
changing the plan's colours. Shown in the Vite dev server or with `?dev`
([commands.md](../guides/commands.md#dev-panel)). Verified in Chrome on `train/proc-campus-train-000` and
`dev/proc-factory-dev-003`.

- **Panel** (`DevPanel.tsx`): Find (rooms and items, one-tap examples from the building, count, "Route here"),
  Route (searchable place pickers, "use selected" from the plan, stop on the way, ambiguous-destination picker,
  reachable rooms, steps in words), Profile (presets with what they mean, fine-tune, rooms unreachable from the
  entrance), Edits (lifts and stairs with open/closed state, close the selected room, add a door; impact in words
  before Apply, measured from the entrance room; reset), View (furniture, room colours, pins, hover, wall height,
  theme), Log (every call in words, run again, any tool by hand).
- **On the plan** (`StoryLayer.tsx`, from map events via `story.ts`; Guide replies in the chat feed the same
  story): route as an accent band drawn in once, start / destination / tappable floor-change badges; accent
  outlines on the rooms an answer is about; a dot per item; red hatch on closed rooms, lifts and stairs; dashed
  outlines on rooms that lost access. A new answer switches to its floor and fits it.
- **Access mode only** (`ACCESS_MODE=on`, [spec](../superpowers/specs/2026-10-25-access-profiles-design.md)):
  restricted spaces drawn as a dark neutral fill without label or furniture (`palette.restricted`); moving
  objects as markers with a heading cone, a faint trail and the remaining mission line in violet
  (`palette.object`, `src/plan/ObjectsLayer.tsx`).
- **Route line**: every route event now carries `line` ([[x, y, floor_index], …], `MapView.enrich` →
  `core/routeline.py`: door to door along the shortest path inside each space (15 cm off the walls, round
  corners, doors entered at their 30 cm landing: the walk `core/building_map.py` measures since kit 1.1.0), anchors kept only for the first and last space and stairs/lifts — so the line never overshoots to a
  corridor's centre and turns back; drawing only, lengths unchanged).
- An earlier visual-concepts experiment (streets, muted rooms, quiet furniture, semantic zoom) was dropped: it made
  the plan less colourful.
- **Not verified:** a Guide reply driving the plan end to end (the offline Guide answered neither question tried);
  phone layout.

## Superseded: point-cloud scene

Everything below describes the earlier point-cloud scene. Its code (`src/scene/*` shaders, BuildingCloud,
RouteFlow) and the `frontend/prototypes/pointcloud/` prototype were moved out of the repo to the gitignored
`.viz-archive/` on 2026-10-24; the rest (`core/pointcloud.py`, `GET /sessions/{id}/points`, route `vertices`, the old
`App.tsx`, the `src/scene/` placeholder) was removed the same day and lives on in git history. Kept for the ideas,
not as a description of the app.

## three.js vs react-three-fiber

| | three.js | react-three-fiber (r3f) |
|---|---|---|
| What | The WebGL engine: scene graph, cameras, `BufferGeometry`, `Points`, `ShaderMaterial`, controls | A **React renderer for three.js** — same engine underneath, nothing re-implemented |
| Style | Imperative: `scene.add(mesh)`, own render loop, manual cleanup | Declarative JSX: `<points><bufferGeometry/><shaderMaterial/></points>`, hooks (`useFrame`, `useThree`), automatic disposal |
| Ecosystem | three examples (`OrbitControls`, post-processing) | **drei** (controls, `<Html>` labels, `<Bvh>`, `<PointMaterial>`), `@react-three/postprocessing` (bloom), react state for UI ↔ scene |
| Fit for us | Prototype (this folder) | The real app ([D-006](../../memory-bank/decisions.md#d-006): React frontend): chat, panels and 3D share React state (selected room, active route, closures) |

Done (2026-10-24): the exporter became `core/pointcloud.py` and the shader an r3f `<BuildingCloud/>` in
`frontend/app/` (versions pinned in `frontend/app/package.json`: three 0.186, @react-three/fiber 9, drei 10). No
post-processing bloom: the soft additive dots in dark mode glow enough and keep it to one draw call.

## Visual language

**Monochrome** ([D-011](../../memory-bank/decisions.md#d-011)): white points on black (dark mode), black on white
(light mode), following the system setting with a toggle. No hues — meaning is carried by density, alpha, size and
motion. (The prototype in `frontend/prototypes/pointcloud/` still uses the earlier colour scheme.)

| Element | Points (app, `frontend/app/src/scene/shaders.ts`) | Meaning |
|---|---|---|
| Walls | dense, strong alpha, extruded to ≤ 3 m | the structure "emerges" from these first |
| Floors | sparse jittered grid, faint | footprint without hiding the level below |
| Doors | gaps in walls + brightest, larger lintel row | you can literally see the way through |
| Stairs / lifts | medium alpha, soft pulse | vertical cores, where floors connect |
| Assets | small clusters in their footprint | machines, desks, printers — the things people ask for |
| Route | line draws itself in; 7 comets with fading tails flow along the exact route-model path; destination ring pulses; rooms off the route step back | animated directions; floor changes are vertical risers |
| Highlight | room points brighten, grow and float; everything else dims; camera flies to them | "show what I understood" |
| Closure | the closed element's spaces flicker, then stay faint | "the lift is out" |
| Lost access | rooms that lose access sink and fade | consequence of a closure (`compare_routes`) |

**Emergence and densification** (built): every point has a random `reveal` value. On load, points fly from a
noise shell to their positions in reveal order — the outline appears first, then fills in. The density slider
is a threshold on `reveal`, so the cloud gets denser or sparser without re-uploading geometry.

**Built in the app (2026-10-24)** besides emergence: a scan plane sweeps up through the floors while points
arrive; highlight / closure / lost-access / on-route states ease per space through a 1-row state texture; floor
solo + animated floor separation; idle breathing and slow auto-rotate after 9 s without input; camera fly-to that
yields to any drag. Verified in Chrome (dark + light, offline Guide: printer, wheelchair, route, Lift 1 closed →
re-route via Lift 2), no console errors. Not tested: phone layout, low-end GPUs.

**Planned effects** (same mechanism, new uniforms/attributes):

- **Collaboration edits** (another user moves a machine / adds a door): a ripple ring expands from the edit
  position, then points settle into the new geometry — instant-update feedback for
  [collaboration](../architecture/overview.md#collaboration-flow-instant-updates).
- **Level 4 "scan" build**: while the Builder agent drafts a building from a plan image, each accepted room's
  points materialise as it is added — the building is literally scanned into existence.
- **Profiles** ([routing-profiles.md](routing-profiles.md)): doors too narrow for the active profile drawn
  hollow/faint (monochrome).
- Floor explode slider = isometric stacked floors from the brief's presentation add-in.

## App and data path

- **App:** `frontend/app/` (Vite + React + TypeScript, three.js via react-three-fiber + drei). `src/scene/`
  (BuildingCloud, RouteFlow, Scene with the camera rig, shaders), `src/ui/Chat.tsx`, `src/App.tsx` (session,
  events → scene). Run: [commands.md](../guides/commands.md#frontend-app).
- **Points:** `core/pointcloud.py` `export_points(building_map)` (the prototype's sampler as a library, plus
  `connectors`, `openings`, `closed`) served by `GET /sessions/{id}/points` (gzip, cached per building object).
- **Events:** the app polls `GET /events` with a cursor; the backend adds `vertices` (viewer-frame polyline from
  `route_vertices`) to route events and `space_ids` to change events. The scene is driven only by events, so a
  voice conversation through `/v1/chat/completions` moves the same view.

## Performance

- Budget ~150–200 k points per building (exporter `--max-points`, auto-coarsens): one `THREE.Points` draw call,
  one `BufferGeometry` with typed arrays; measured JSON 3.7–4.2 MB (campus, factory, 8-floor OSM).
- All animation happens in the vertex shader via uniforms (no per-frame CPU work except ~500 route particles).
- Additive blending + `depthWrite: false` avoids sorting. Point size is perspective-correct with a 1.5 px floor.
- Next steps if needed: binary transfer (Float32/Int16 + gzip) instead of JSON, per-floor geometry chunks,
  LOD (lower reveal threshold when zoomed out). Instancing is not needed for points; it would be for meshes.

## Why it matters for judging

- **Interaction (25)**: highlight + fly-to shows what the agent understood; animated route = directions people
  can follow; closures visibly change routes.
- **Submission demo (10)**: the emerge animation is a strong first 5 seconds of the video.
- **Creativity (10)**: "scan" emergence for Level 4 and edit ripples for multi-user updates.

## Related
- [overview.md](../architecture/overview.md) · [ai-agents.md](../architecture/ai-agents.md) ·
  [personas.md](personas.md) · [routing-profiles.md](routing-profiles.md)
