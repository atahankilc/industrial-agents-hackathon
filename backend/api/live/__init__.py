"""The living building: connected things that move around or are left behind, reporting where they are now and then.

A `LiveWorld` per building holds its devices. Most are SIMULATED (source "sim", clearly labelled in the app): forklifts
and an AGV in factories, delivery and cleaning robots, and pallets / carts with BLE tags that people leave in corridors
for a few minutes. Real devices can join over HTTP (source "device"): register, then post positions. Every device has a
report interval (telematics 1 s, Wi-Fi robots 2 s, BLE tags 10 s); the app only ever sees the last REPORTED position
and the trail of reports (the last `TRAIL_M` metres), never the simulation's true position.

What is reported feeds routing (backend/core/live.py): parked things cut the walks they block, moving ones cost a wait, a
cleaning robot's wet floor costs a little. Sessions get `session.live` (backend/agents/tools/), and `GET /live` re-checks the
route on a viewer's map: a route that just got blocked is replaced (event `route` with `reroute`), one whose detour is
no longer needed is offered back (`suggestion`).

A world runs while someone looks at it (GET /live polled) and stops `IDLE_S` after the last look; its things vanish
with it, so routes go back to the plain route model.

Split by part: world.py (devices, simulation, obstacles), hub.py (worlds per building, the tick thread, a session's
view), reroute.py (route re-checks for viewers), endpoints.py (HTTP router)."""

from backend.api.live.endpoints import router
from backend.api.live.hub import LiveHub, SessionLive
from backend.api.live.reroute import route_walks
from backend.api.live.world import WET_S, LiveWorld, trimmed, wet_zones

__all__ = ["WET_S", "LiveHub", "LiveWorld", "SessionLive", "route_walks", "router", "trimmed", "wet_zones"]
