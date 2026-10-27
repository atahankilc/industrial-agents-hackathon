---
id: product-visualization
summary: App visuals — the current vector plan view (backend/core/floorplan.py, GET /sessions/{id}/plan, frontend/src/plan/) and the superseded point-cloud visual language; three.js vs react-three-fiber, performance, judging fit.
sources:
  - backend/core/floorplan.py, backend/api/sessions.py (MapView.plan), frontend/src/plan/, frontend/src/building/ (verified 2026-10-24)
  - frontend/src/dev/, backend/core/routeline.py (answers on the plan, verified 2026-10-24)
  - frontend/src/plan/ObjectsLayer.tsx, src/plan/palette.ts (access mode, verified 2026-10-25)
  - frontend/src/map/bridge.ts, src/building/opening.ts, src/Root.tsx (map → building transition, verified headless 2026-10-24)
  - frontend/src/building/RouteHud.tsx, src/dev/StoryLayer.tsx, backend/core/directions.py maneuvers (route following, verified headless 2026-10-25)
  - https://threejs.org/docs/ (three.js r160)
  - https://r3f.docs.pmnd.rs/ (react-three-fiber)
related: [../../archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md, ../architecture/overview.md, personas.md, routing-profiles.md, ../architecture/ai-agents.md]
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
- **Data:** `backend/core/floorplan.py` `export_plan(building_map)` → floors, spaces (polygon, label point), walls
  per floor with door gaps cut, openings (wall angle only: the kit has no swing data, so the plan draws no door leaves, just a threshold
  strip per doorway: blue, entrances accent blue, closed doors red), connectors, assets in drawn spaces, `closed`,
  and `center` (centre of the space bounds; the y-up scene uses `X = x - cx`, `Z = -y - cz`). Served by
  `GET /sessions/{id}/plan`, cached in `MapView.plan` per building object. Route events from `/events` carry
  turn-by-turn `legs` but no polyline: a route line on the plan still needs one in the plan frame.
- **Landing:** a city map (`frontend/src/map/MapLanding.tsx`; MapLibre GL JS on OpenFreeMap's hosted
  `positron` / `dark` styles, free, no key), tilted 50°, every building in the tiles extruded from zoom 14 to its
  OSM height (`render_height` / `render_min_height`, streamed with the tiles), a pin per building that has a real
  position, and a panel listing them; tap a pin or a row → `BuildingScreen`. Positions come from `GET /buildings` `location` ({lat, lon, address}
  or null), read from `backend/api/locations.json`: the centre of the OSM outline of the 17 `osm-way*` buildings, made
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
  y north from `location.origin` (the fitted kit (0, 0) from `georef.py`, added to `backend/api/locations.json`), and
  the map narrows its field of view to 1° so its perspective matches the orthographic model (measured ≤ 10 px apart at the screen corners, ≤ 1 px at the centre; 4° was up to 40 px; below 1° MapLibre drops its tiles when tilted), and the model tilts at most 60° over the map (past 60° MapLibre switches tile selection and, at that field of view, draws no buildings at z15–18). The map blocks over the
  open building (overlap with the plan outline: block centre in it, its centre in the block, or most block corners in
  it; tile ids are not the kit's way ids) move to a see-through shell layer (`buildings-3d-shell`, opacity 0.22 light /
  0.16 dark), so a campus wing that the tiles draw as one block with its neighbours no longer boxes the model in.
  Back fades the model out (0.35 s) while the map flies out to every pin.
- **City view refinements (2026-10-25):**
  - *Wireframe instead of the shell:* the open building's own map blocks leave the map, and the model draws them as
    edge lines in its own scene (`PlanView` `City`, from `bridge.ts` `onShell`), so they share the model's depth.
    The match also tests each polygon of a merged tile feature (the tiles merge blocks of the same look into one
    MultiPolygon, the building is not always its first polygon), plus an area-share test (half the smaller shape
    inside the other) for U-shaped blocks. A filter can only hide a merged feature whole (some hold 1,300+
    buildings across the city), so its other polygons are put back from a GeoJSON source with the same paint
    (`rest` source, `buildings-3d-rest` layer), rebuilt only when the left-out ids or the loaded pieces change.
  - *No flicker on the blue blocks:* the OSM blocks under a building with a model leave the solid layer. The blue
    block is as tall as them, and two blocks on one outline z-fight, worst at the 1° field of view. Insetting or
    raising the blue by 0.4–0.6 m did not stop it.
  - *X-ray (`src/map/neighbours.ts`):* with a building open, the blocks within 500 m of it (OSM and the blue ones)
    leave the map's layers. A MapLibre custom layer draws them instead, in the map's own GL context and depth, under
    the pins. It uses MapLibre's fill-extrusion lighting, colours and opacity (`style.ts` `blockLook`), so they look
    like the map's own. Its fragment shader cuts what stands in front of the building's middle (by clip w, fully 12 m
    in front), inside a rounded box over the building's box on screen (a superellipse, 1.1× the box), dissolving
    in a 4×4 Bayer dither (2 CSS px grain) towards its rim. It follows the camera continuously, so no block switches
    on or off. Matrix composed in double precision (world pixels at street zoom are past float32). Winding measured:
    counter-clockwise from outside is front. Where a block is cut, its footprint (fill and outline, the roof colour laid on
    the ground) is drawn in exactly the cut pixels, so no z-fighting with uncut blocks. Earlier tries replaced: ghost layers by `setFilter` (each change
    re-processes tiles) and whole blocks flattened by feature-state (they popped in and out).
  - *Performance (measured 2026-10-25):* the blocks are gathered again (`applyBlocks`) and the blue blocks' heights
    read again (`MapLanding` `updateHeights` → `osmHeights`) only after new tiles arrive, not on every idle. Box tests
    run before the polygon tests, and each polygon is only tested against footprints whose box it meets.
    `applyBlocks` went from 183 ms to 16 ms (about 30 ms with the x-ray blocks), `osmHeights` from 68 ms to 7 ms. The map list panel is `visibility:
    hidden` while a building is open (a see-through blurred panel is still re-blurred every frame).
  - *Ground level:* a line traces the ground floor's outline where it meets the ground. Basements get no veil over
    them (2026-10-25: the darkening made them hard to read). Instead a basement you are not on is drawn darker
    (`PlanView.tsx` `FloorModel` `under`: its colours times `UNDER_TINT` 0.35; under the current floor at opacity
    `UNDER_FADED_OPACITY` 0.3 instead of 0.12, so the dark reads). The basement you are on looks like any floor.
  - *Back returns to where you were:* closing a building flies the map back to the camera it had when the building
    was opened (every pin if it was opened from a link).
- **Roads at their real width (2026-10-25):** the tiles carry no road width (OpenMapTiles `transportation`: class,
  subclass, surface, oneway, brunnel… no width or lanes, checked in the browser), so each class has a typical
  carriageway width in metres (`style.ts` `ROAD_M`, UNVERIFIED estimates: secondary 14 m, tertiary 11, minor 8,
  service 5, path 3…). From z15 a metre is drawn at the map's own scale (exponential base 2, pixels per metre at
  48.1° N), below that the widths ease in from the old thin lines. Light-theme casings add 1.5 m of kerb. Pedestrian
  areas (squares) are filled in the road colour. Walkways (`walk`: footway, path, pedestrian, platform; 2.5–4 m) are
  solid lines a shade off the ground, unpaved ones sandier; cycle paths (`cycle`, 2 m) a faint tint; steps
  (`steps`) drawn as treads (dash 0.2 of the width); indoor corridors left out. The earlier dashed path line read as
  noise once it had a real width.
- **Buildings with a model on the map:** drawn as accent-blue blocks (`MapLanding` `models` source): the kit
  footprint (`location.outline`: union of the kit's spaces on every floor, outset 0.6 m for the exterior walls,
  placed by `origin`), as tall as the kit (`location.height_m`) or the OSM block it stands in, whichever is taller,
  so the blue wraps the grey block; the grey blocks under it are left out (no z-fighting, see below). Tinting the tiles' own blocks does not work: the TUM main building is one tile
  polygon around the whole block, its kit buildings are wings of it. Light mode got its own palette (2026-10-25):
  stronger greens and water, white roads with grey casings, brighter side light on the blocks.
- **Fitting the kit onto the map** (`scripts/fit_locations.py`, 2026-10-25): the archived georef origins were up to
  ~18 m off for some buildings (N8, Arcisstraße 21, U-Trakt). The script fetches each OSM way (cached in `.cache/osm/`),
  shifts the kit's ground-floor footprint (translation only; a rotation search added nothing) and moves `origin`,
  then rewrites `outline` and `height_m`. How it shifts depends on the area ratio (kit footprint / OSM way,
  `MIN_RATIO` 0.75): where the kit is about the size of the way (≥ 0.75) the shift maximises the overlap (IoU,
  `best_shift`, grid over ±20 m); where the kit models only part of the building (< 0.75: Wolf-Ferrari-Haus
  (Ottobrunn), Mensa Arcisstraße, Terminal 2 (Freising), Haus der Weiterbildung, Pasing Arcaden, ratio 0.3–0.6) IoU
  would drag it to the way's middle, so `smallest_inside` takes the least shift (0.5 m grid over ±20 m, within 0.5 %
  of the best share) that puts the kit inside the way (e.g. Mensa: its north wing stuck ~7 m out of the way).
- **Opening a building** shows all floors stacked (one-floor buildings: that floor). The app always plays full
  motion, whatever the system's "reduce motion" setting says: `motion.ts` `reducedMotion()` returns false and the CSS
  has no `prefers-reduced-motion` rules (2026-10-25).
- **Not built yet:** Guide events on the plan (focus, route line, closures, lost access), 3D, maintainer edits.
- **Guide answers on the plan** (2026-10-25, [D-020](../../memory-bank/decisions.md#d-020)): the rooms an answer is
  about are tinted in the route blue (three soft pulses, then steady) with name badges; items get a ringed dot (names
  when ≤ 4). `search`, `locate`, `room_facts` and `show_on_map` all emit highlights (items too: `asset_ids`), and the
  camera frames them (`PlanView` `focus`, ≥ 14 m across) — all floors stacked if they spread over several. A route is
  framed whole (stacked when it crosses floors); **Start** on the route bar (`RouteHud.tsx` `RouteBar`, or a spoken "start") then frames one step at a time, reads
  it aloud and waits for "I'm there" (button, typed or spoken "geldim" / "next"). Each walking step also turns the
  map so the step runs straight up the screen (start → end of the step, `Focus.heading`; a stairs/lift step keeps
  the turn), with you (green dot + cone) at its start and the next move's arrow in a ringed blue disc at its end.
- **Route following, variant B** (2026-10-25, Atahan's pick from a mockup of two): no next-move card any more (it
  stays only inside the camera walk). A slim trip pill at the top (`building/RouteHud.tsx` `TripBar`: where to, metres
  left, step n/N, step dots, track / camera / end) and one line over the Guide's dock (`RouteBar`: "Say “start”…" +
  Start → "Reached it? Say “I'm there”" + I'm there → "You have arrived" + Done, or Continue into the next building);
  the Guide's last answer bubble steps aside while a step is walked (`Guide` `quiet`). The step itself is a callout
  pinned on the map where it is made (`dev/StoryLayer.tsx` `move` marker: arrow, "Turn left · 20 m", "into … · by the
  …"; right of the point, else left, else above it, clear of the edge buttons), and the end of the step has a small
  ring with a "then ← …" tag. The route line is thin (6 px) with no chevrons: before Start one solid line; while
  walking only the current step is solid, the walked part and the steps still to come are dotted, and one short light
  runs along the solid part the way you go. The walked part eases to a new step and the
  "you" puck glides along the line. Steps are moves, not doors: `backend/core/directions.maneuvers` joins a straight-on door
  into the step before it (each step carries `legs`, which `building/tracking.ts` uses to place it on the line), so
  Hauptgebäude 0119 → Toilet 0137 is 6 steps instead of 8; the Guide's spoken steps and the `[route note]` use the
  same list.
- **"You are here" figure** (2026-10-25): an orange person pin, dragged out of the dock at the bottom right onto the
  plan, or the dock tapped and then the plan (Esc cancels; tapping the dock again takes it off), dragged again to move.
  While in the hand it shows where it would land (room name, or `Near entrance · <room>`); put down off the building
  it stays there, with a dashed line to the nearest entrance of that floor (marked "Entrance"; routes start at that
  door); on a wall it takes the room ≤ 0.6 m away. Its room goes to
  `PUT /sessions/{id}/location`; the Guide then routes from "here" and stops asking where the user is.
- **Framing** (2026-10-25): the whole building is centred on the screen (the wide-screen Guide floats bottom left,
  360 px wide, `GUIDE_COL_PX`; the floor rail's width is mirrored left); an answer's focus still keeps clear of the Guide card.
- **Nearby buildings** (2026-10-25, [D-021](../../memory-bank/decisions.md#d-021)): a "found nearby" card lists matches
  in neighbouring buildings (Directions / Open); a route to one ends at the exit with a dashed line across outside to
  the other entrance and a Continue badge/button, which opens that building and draws the rest from its entrance.
  The same happens on "I'm there" at the exit, or when the Guide opens the neighbour itself (`open_nearby_building`
  → `open_building` UI event; `BuildingScreen` goes there through `continueTo` once the reply has been said).

## Buildings from plans: reference, trace and map position (2026-10-25)

Design: [plan-reference-and-location-design.md](../../archive/hackathon/superpowers/specs/2026-10-25-plan-reference-and-location-design.md).

- **Create here:** right-click a building (or a spot) on the map → a card at the cursor ("This building" / "This
  spot"; left click elsewhere or Esc closes it). The building under the cursor is outlined (`src/map/MapLanding.tsx`,
  `src/map/geo.ts` `outerRing` picks the part of a merged tile polygon that holds the point). "Create a building
  here" opens the import with that place; every file gets a "Floor" number the user sets (one floor per file).
  Right-click on one of ours: Open / Delete (asks once more; "Which version?" first when versions overlap).
- **Placement** (`src/map/Placement.tsx`): after the import the building is fitted onto the OSM footprint
  (dashed); drag, turn (slider, ±1°) and size (0.75–1.25) by hand. Without a tap the photos' EXIF GPS (median) or
  the browser's position place it; a tap far from the photos offers "did you mean …". Overpass busy → the map's
  own building tiles are used.
- **Edit mode:** the import's straightened plan sits right of the editor (`src/edit/ReferencePanel.tsx`, sized to
  the image, wheel zoom, drag pan, follows the floor); "Trace" draws it under the editor at an adjustable opacity
  (`EditLayer` `trace`). The window can be dragged by its header and resized from its corner (double-click the
  header puts it back). "Adjust" lets the trace be dragged, turned and resized on the editor (handles, or the
  Turn / Size buttons; edit op `set_reference`, undoable). Edit bar: "Edit position" (map pin) reopens Placement
  with the floor being edited drawn; "Add a floor" (＋) imports plans into the open draft at the floors typed per
  file; "Straighten this floor" (ruler) turns the floor shown parallel to the lowest floor. The floor chip / list
  follows the draft's floors.
- **On the map:** a saved building is drawn at its position with its bearing (`building.location.bearing`, MapLibre
  bearing = view − building); re-saving a placed user building supersedes the older one on the map.

## Answers on the plan

`frontend/src/dev/`: the current answer drawn over the plan without changing the plan's colours. (The dev
tools panel that also lived here was removed 2026-10-25; the admin button now only toggles the Edit mode. In access mode the
admin also gets a shield button above it that opens the Building settings — tabs Access / People / Objects — and the
Edit mode an Access tool: tap a room to choose who may enter it, restricted rooms hatched; both save at once through
`src/access/useAccessRules.ts`. The Edit mode frames one floor straight down.)
Verified in Chrome on `train/proc-campus-train-000` and `dev/proc-factory-dev-003`.

- **On the plan** (`StoryLayer.tsx`, from the map events of Guide replies via `story.ts`): the thin route line of
  variant B above (walked part and coming steps dotted, current step solid with a running light, no chevrons);
  start / destination / tappable floor-change badges; accent
  outlines on the rooms an answer is about; a dot per item; red hatch on closed rooms, lifts and stairs; dashed
  outlines on rooms that lost access. A new answer switches to its floor and fits it.
- **Access mode only** (`ACCESS_MODE=on`, [spec](../../archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md)):
  restricted spaces drawn as a dark neutral fill without label or furniture (`palette.restricted`); moving
  objects as markers with a heading cone, a faint trail and the remaining mission line in violet
  (`palette.object`, `src/plan/ObjectsLayer.tsx`).
- **Route line**: every route event now carries `line` ([[x, y, floor_index], …], `MapView.enrich` →
  `backend/core/routeline.py`: door to door along the shortest path inside each space (15 cm off the walls, round
  corners, doors entered at their 30 cm landing: the walk `backend/core/building_map.py` measures since kit 1.1.0), anchors kept only for the first and last space and stairs/lifts — so the line never overshoots to a
  corridor's centre and turns back; drawing only, lengths unchanged). Since 2026-10-25: a route that starts in the
  room of the "you are here" figure starts its line at the figure's point (`PUT /sessions/{id}/location` sends
  `point`, the route event carries `start_point`), not at the room's anchor; and a door between two spaces whose
  outlines overlap there (an OSM lecture hall outline that takes in its lobby) is left out of the line with its
  landings, instead of a dip into the doorway and back.
- Since 2026-10-25 (session 22): where a route changes floor, a riser as wide as the route joins the two floors,
  drawn over the slabs; walking a stairs or lift step stacks just those two floors. A position the Guide sets shows
  for 1.6 s before the route from it. With the position unknown, the rooms the user might be in (the Guide's guesses,
  else the entrances) get dashed outlines and "Here? · room" badges after the answer; a tap stands them there.
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
`frontend/` (versions pinned in `frontend/package.json`: three 0.186, @react-three/fiber 9, drei 10). No
post-processing bloom: the soft additive dots in dark mode glow enough and keep it to one draw call.

## Visual language

**Monochrome** ([D-011](../../memory-bank/decisions.md#d-011)): white points on black (dark mode), black on white
(light mode), following the system setting with a toggle. No hues — meaning is carried by density, alpha, size and
motion. (The prototype in `frontend/prototypes/pointcloud/` still uses the earlier colour scheme.)

| Element | Points (app, `frontend/src/scene/shaders.ts`) | Meaning |
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

- **App (current, 2026-10-26):** `frontend/` (Vite + React + TypeScript), entry `src/Root.tsx`; folders
  `src/map`, `src/search`, `src/building`, `src/plan`, `src/edit`, `src/import`, `src/access`, `src/live`,
  `src/voice`, `src/ui`, `src/dev`. The point-cloud files this section was written for (`src/scene/` with
  BuildingCloud, RouteFlow, Scene, shaders; the old `src/App.tsx`) were removed; see the note at the top of this
  section. Run: [commands.md](../guides/commands.md#frontend-app).
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
