---
id: product-visualization
summary: App visuals — the current vector plan view (core/floorplan.py, GET /sessions/{id}/plan, frontend/app/src/plan/) and the superseded point-cloud visual language; three.js vs react-three-fiber, performance, judging fit.
sources:
  - core/floorplan.py, backend/sessions.py (MapView.plan), frontend/app/src/plan/, frontend/app/src/building/ (verified 2026-10-24)
  - core/pointcloud.py (point-cloud export, still served by /points)
  - https://threejs.org/docs/ (three.js r160)
  - https://r3f.docs.pmnd.rs/ (react-three-fiber)
related: [../architecture/overview.md, personas.md, routing-profiles.md, ../architecture/ai-agents.md]
---

# Visualization

[Docs index](../README.md) · System: [overview.md](../architecture/overview.md)

## Current: vector plan view (2026-10-24)

Direction "Drawing Set" (`PRODUCT.md`, `.impeccable/surfaces/frontend-app.md`). Landing is a building search
(`frontend/app/src/search/`); `Root.tsx` opens `BuildingScreen` (`src/building/`) over an orthographic r3f plan
(`src/plan/`: rooms, walls with door gaps, door swings, furniture, labels that only show when they fit, tap a room →
place card) with a floating Guide conversation.

- **Data:** `core/floorplan.py` `export_plan(building_map, center)` → floors, spaces (polygon, label point), walls
  per floor with door gaps cut, openings (wall angle, swing side), connectors, assets in drawn spaces, `closed`.
  Served by `GET /sessions/{id}/plan`, cached in `MapView.plan` with the point-cloud export's `center` so route
  vertices from `/events` map back onto the plan (`x = vx + cx`, `y = -(vz + cz)`).
- **Not built yet:** Guide events on the plan (focus, route line, closures, lost access), 3D, maintainer edits.

## Superseded: point-cloud scene

Everything below describes the earlier point-cloud scene. Its code (`src/scene/*` shaders, BuildingCloud,
RouteFlow) and the `frontend/prototypes/pointcloud/` prototype were moved out of the repo to the gitignored
`.viz-archive/` on 2026-10-24; `src/scene/` is now a placeholder. Kept for the ideas, not as a description of the app.

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
