---
id: living-building
summary: The living building — connected things (forklifts, AGVs, robots, pallets/carts with BLE tags) that report positions; what they do to routes (cut walks, waits, wet floors), the reroute of the route on the map, the plan layer and the demo simulation.
sources:
  - core/live.py
  - backend/live.py
  - agent/tools.py (live_effects, reroute, live_status)
  - frontend/app/src/live/
  - tests/test_live.py
related: [routing-profiles.md, visualization.md, ../kit/route-model.md, ../architecture/ai-agents.md]
---

# The living building

[Docs index](../README.md) · Route model it sits on: [route-model.md](../kit/route-model.md) · Profiles:
[routing-profiles.md](routing-profiles.md)

Branch `5-living-building` (2026-10-25). App only: benchmark answers never pass live state.

## What reports

A live world per building (`backend/live.py` `LiveWorld`) holds connected things. Each one has a footprint
(length × width, heading), a state and a **report interval**; the app and routing see only the **last reported**
position, never the simulation's own.

| Kind | Footprint | Reports via, every | Behaviour (simulated) |
|---|---|---|---|
| forklift | 2.6 × 1.2 m | telematics, 1 s | missions between factory zones (forklift rules, else no stairs/lifts); 60 % stop 30–55 s to load **in an aisle** |
| agv | 1.6 × 0.9 m | fleet manager, 1 s | missions between factory zones |
| delivery_robot | 0.8 × 0.6 m | Wi-Fi, 2 s | room to room, lifts allowed |
| cleaning_robot | 0.9 × 0.7 m | Wi-Fi, 2 s | drives walkways; floor it passed is **wet** for 120 s |
| pallet / cart / pallet_jack | per item | BLE tag, 10 s (±0.12 m per fix; the reported position is the mean of the last 6 fixes) | left in a walkway for 150–320 s, then picked up; a new one every 45–110 s |
| device | registered | API, any | a real device: `POST /live/devices`, then `POST /live/devices/{id}/report` (`X-Device-Token`) |

Factories get forklifts (the building's forklift assets, at their positions) + an AGV; other buildings delivery
robots; every building with walkways a cleaning robot. **Everything except registered devices is simulated** and the
app labels it so (`simulated`, "SIMULATED" in the panel) — the data has no live feed.

A world runs while someone polls `GET /live` and stops 90 s after the last poll; its things vanish with it. One
thread ticks every world (0.2 s); robots' route planning runs on a second thread (`LiveHub.plan`), on a copy of the
device, so a slow plan never holds up the clock. A world is built outside the hub's lock. Robots plan round what
stands (not what moves), without route notes, at most one new mission per tick.

## What they do to routes (`core/live.py`)

The route graph walks each space door to door. An obstacle doesn't close a space — it cuts the walks **across** it:

- free area of a space = outline shrunk by half the walker's **clearance**, minus every footprint grown by the same;
- a walk (anchor or door landing → another) is **cut** when its two ends were joined in the free area without the
  obstacles and are not with them (each door landing belongs to the nearest free piece only, so a door beside the
  obstacle is no way through it);
- the start and destination spaces count as reached from any free door (you can enter the room the forklift is in);
- a space narrower than the clearance somewhere falls apart even when empty; there a walk is cut when a standing
  footprint, grown by half the clearance, lies across its walking line;
- a door the path only touches (door → door → door inside one space) is taken out (`collapse_hops`), so paths stay
  well-formed.

So pallets half-way down a corridor cut it between the doors either side; a room just before them is entered as
usual; in a wide hall nothing is cut. Clearance: walker 0.7 m; step-free 0.9 m; a profile's minimum door width if
larger; forklift profile 1.6 m — the same pallets can let a walker squeeze past and send a wheelchair round.

| Effect | When | Cost |
|---|---|---|
| blocked | standing thing (left behind, parked, loading, unloading) cuts the walk | walk removed |
| wait | a moving thing would cut it | +10 m |
| squeeze | walk passes within 0.35 m of a footprint | said, no cost |
| wet_floor | walk crosses a wet zone | +6 m |

Costs only steer the search; lengths are true metres (`Penalties.path_only`). In an outline with more than 100
corners (3 OSM corridors) the squeeze / wet / narrow checks use the straight line between door landings, for speed;
cutting is still the free-area test. Route results carry
`live: {avoided, passing, detour_m, without_live_m}` or, with no route, `blocked_by` and a reason naming the blocker.

## The route on the map

Every route event carries its `request` (start, destination, via, closed): `find_route`, `route_to_building` (to the
exit) and the arrival from a nearby building. `GET /live?building&session_id` re-asks the **route on the map** by
its own request, never an older question (`live_check`); a route event without one only gets the alert:

- cut now → recomputed from where the user is (else the route's start); the new route is appended as a `route`
  event with `reroute: {by, was_m}`, the Guide gets a `[live note]`, the app swaps the route (the step guide goes
  on), shows a notice and speaks it while guiding;
- cut with no way round → one `alert` per blocker set;
- a detour whose blocker is gone and the plain route ≥ 4 m shorter → `suggestion`; `POST /live/shorter` takes it.

The Guide's `find_route`, `find_nearest`, `tour` and option lists route with live state; `live_status` answers "where
is the forklift / is anything in the way". The "clear again" check routes, so it runs at most every 4 s per session.

Access mode: a non-admin never sees a thing standing in (or a wet patch in) a space hidden from them — neither in
`GET /live` nor in `live_status`; routes are on their filtered building copy, so hidden spaces have no effect either.
Only the building admin may use the demo controls (`POST /live/control`) and register a device (`POST /live/devices`);
with access mode off both stay open for the demo. A registered device reports with its own `X-Device-Token`.

## Tested (2026-10-25)

`tests/test_live.py` (37): blockage, near side, squeeze vs wheelchair, wait, no way round, wet floor, door hops,
obstacle in the destination / on its only door, narrow spaces, other floor / outside, degenerate shapes, outside
starts, tours, via stops, preferences + live (true metres), well-formed paths in a busy corridor, trails, BLE
steadiness, wet zones drying, idle worlds, every kind moving inside the building, the planner thread, control
errors, device ingest, admin-only controls in access mode, the reroute following the route on the map, alerts, access
filtering, `live_status`, saving.
A stress run over all 280 buildings (world, 150 s of simulation, snapshot, live routes, a blocked-route reroute)
checks crashes, path shape and timing. Headless Chrome with the live Guide: reroute while guiding (the step guide
goes on), alert + dismiss, "clear again" + Take it, tap to drop (outside the building refused), Edit mode hides it.

## On the plan (`frontend/app/src/live/`)

Footprints at real size — violet moving, orange standing in the way (with the no-pass zone routing uses: footprint +
clearance), grey standing out of the way; a marker with the kind's icon and one ping per report; trails = the last
**50 m** of reports fading with age; a dashed line ≈ 12 m ahead of moving things; wet floors as a pale blue patch.
The Live button (top of the plan's button column) opens the panel: every thing with state, place, link and report
age, and demo controls — Drop pallet / Park forklift (tap the plan), Block my route, Pick up, pause, 1×/2×/4×.
