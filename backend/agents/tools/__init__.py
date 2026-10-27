"""The Guide agent's tool layer: one building session + Anthropic tool definitions over the deterministic core.

  session = BuildingSession.load(Path("data/buildings/proc-campus-dev-000"))
  session.call("find_route", {"start": "Main lobby", "destination": "Meeting room 3.07"})
  client.messages.create(..., tools=TOOL_DEFINITIONS)   # then route every tool_use block to session.call

Every fact the agent states comes from these tools (D-003). The session holds what a conversation accumulates:
the user's routing profile (step-free, minimum door width, no lifts, forklift — docs/product/routing-profiles.md),
the route rules every route obeys (production bays destination-only, no shortcut outside — backend/core/route_models.py,
Q-014) and the route model (the kit 1.1.0 one, door to door — the only one; `route_model` kept for callers), applied
building changes (closures, new doors), pending changes awaiting the user's confirmation, and UI events
(highlight rooms, draw a route). Changes go through propose → confirm → apply so the agent can show what it
understood before it edits the plan (docs/architecture/ai-agents.md#shared-tool-layer).

Errors are returned as {"error": ...} results instead of raised, so the model can repair a vague place name by
searching or ask the user which of the listed candidates they mean.

The layer is split by area: session.py (BuildingSession: state, dispatch, place names), lookup.py, routing.py,
profile.py (RoutingProfile, presets, preferences), live.py, changes.py, map.py (app UI tools), nearby.py, and
definitions.py (the tool schemas)."""

from backend.agents.tools.definitions import TOOL_DEFINITIONS
from backend.agents.tools.changes import Change
from backend.agents.tools.profile import PRESETS, PROFILE_FIELDS, RoutingProfile
from backend.agents.tools.session import BuildingSession

__all__ = ["PRESETS", "PROFILE_FIELDS", "TOOL_DEFINITIONS", "BuildingSession", "Change", "RoutingProfile"]
