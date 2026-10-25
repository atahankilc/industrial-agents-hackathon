---
id: access-roles-design
summary: Demo feature — a facility manager sets who may go where (roles with room-type access and physical limits) by talking to the Guide; routes then respect the user's role. Benchmark untouched.
sources:
  - conversation with Utku, 2026-10-24
  - agent/tools.py (RoutingProfile, PRESETS, profile_closures, propose/apply changes)
  - core/building_map.py (closed spaces/openings/connectors leave the graph)
  - backend/persistence.py, backend/sessions.py (per-conversation state)
related: [../../product/routing-profiles.md, ../../product/personas.md, ../../architecture/ai-agents.md]
status: draft — design only, nothing built; partly replaced by 2026-10-25-access-profiles-design.md (real accounts instead of claimed roles)
---

# Access roles: who may go where (design)

> Partly replaced (2026-10-25) by [access-profiles-design](2026-10-25-access-profiles-design.md): roles are real
> accounts, access is set in settings, building-wide applied changes moved to "Later".

## Intent

Not everyone can enter every room. A janitor may enter every room; a visitor may not enter server rooms; a robot
cannot take stairs; a forklift needs openings ≥ 3 m. The **facility manager** sets these rules for a building by
talking to the Guide ("server rooms are IT only", "the delivery robot can't use stairs"). Anyone who then asks the
Guide for a route gets one that fits their role, and a clear answer when their role can't reach a place.

This is a **demo feature** (Interaction / Creativity points, Level 5 add-in feel). It must not change benchmark
answers.

## Goals

- A **role** = a name + **access** (which room types / spaces it may enter) + **physical limits** (stairs, lifts,
  minimum opening width, vehicle rules). Built-in roles come with sensible defaults; the manager can create roles
  and change any of these values, physical limits included (Utku: "robotun merdiven çıkmayacağını yönetici
  girebilir").
- The manager edits rules **by conversation**, through the same propose → confirm → apply flow the Guide uses
  for building changes: the proposal shows the effect ("visitors lose access to 12 rooms") before it is applied.
- Rules and building changes belong to the **building**, not to one conversation: what the manager applies
  reaches every conversation on that building, already open ones on their next turn.
- A user's role is set once per conversation (they say it, or the demo picks it) and every route uses it.
- A route to a place the role can't enter: the Guide says so, names why, and offers the nearest place it can
  reach or who can (no silent "no route").

## Non-goals

- UI for editing roles and rules (later; Utku: not now).
- Real access control: badges, locks, authentication. A role is a claim, not a credential.
- Per-person identities, schedules (night-shift-only access), multi-building rules.

## Anti-goals (failure even if it works)

- **Any change to benchmark output.** `agent.run_benchmark`, `agent.answer`, `core/solvers`, `SUNDAY_RULES` and
  `core/navigation` defaults stay as they are; the default role is unrestricted, so a conversation that never
  mentions roles routes exactly as today. `scripts/eval_guide.py` must stay 18/18.
- A user who never mentioned a role suddenly hitting "no access" walls.
- The model deciding access itself: access must be enforced in code (tool layer), like closures and profiles.

## Constraints and facts

- `building.json` has **no access data** (spaces: id, floor_id, type, room_type, name, ref, polygon, synthetic).
  Access is our layer on top, keyed by `room_type` (e.g. `server_room`, `technical_room`, `storage`,
  `production_zone`) or by space id for exceptions.
- Enforcement already exists: `BuildingSession.profile_closures()` returns element ids that act as closed for the
  current profile, and closed spaces/openings/connectors leave the routing graph (`core/building_map.py`).
  A role's forbidden spaces plus its physical limits can feed the same mechanism.
- Physical limits overlap `RoutingProfile` (step_free, min_door_width_m, avoid_lifts, forklift) and its
  `PRESETS` (wheelchair, pram, trolley, no_lifts, forklift). A role extends this rather than living beside it.
- Persistence today is **per conversation** (`backend/persistence.py`, Supabase row per conversation, replayed
  changes; `SessionStore` caches conversations in memory and checks only their own row's version). Shared rules and
  changes need a building-level store and a version check on every turn of every open conversation.
- Mobility needs of a person (wheelchair) still come from the conversation and combine with the role (a
  wheelchair-using IT technician).

## Decided

- Manager sets rules via the Guide in conversation now; UI later.
- Physical limits are editable by the manager, with defaults per built-in role.
- Rules apply building-wide, **including conversations that are already open**: a rule the manager applies
  takes effect on the user's next question in another tab (Utku, 2026-10-24).
- **Building changes become building-wide too** (Utku, 2026-10-24): close / reopen / add door, applied in any
  conversation, reach every conversation on that building, open ones included — today they live in one
  conversation only (`backend/persistence.py` replays them per conversation). One building-level state holds both
  the access rules and the applied changes; the effect summary of a proposal is computed on that shared state.
- **Only a manager may change rules or the building** (Utku, 2026-10-24): `manager` is a role, claimed in
  conversation ("I'm the facility manager") like any role — a claim, not a credential. In a conversation without
  the manager role, the Guide refuses rule and building edits in code (the tool returns an error the model must
  relay: "only the facility manager can change this"); reading, routing and reporting a problem still work.
- Demo only; benchmark untouched.

## My calls (not discussed — check these)

- **No role = today's behaviour, edits included:** a conversation that never claims a role stays unrestricted and
  may still close/reopen/add doors as today (the `lift_closure` scripted conversation and `tests/test_guide.py`
  depend on it). The manager-only refusal applies once a conversation has claimed a non-manager role.
- **Where the shared state lives:** in the backend (`SessionStore` + the building-level store). Scripts and tests
  that build a `BuildingSession` / `Guide` directly (`scripts/eval_guide.py`, `scripts/interaction_eval.py`,
  `tests/`) keep today's isolated per-session state, so eval runs can't leak changes into each other.
- **Built-in roles:** `manager` (all rooms; may edit rules and the building), `visitor` (no server/technical rooms, no storage, no production zones), `employee`
  (no server/technical rooms), `it` (all rooms except production zones), `janitor` (all rooms), `forklift`
  (production/logistics/warehouse zones and aisles only, openings ≥ 3 m, no stairs), `robot` (no stairs, lifts
  allowed, openings ≥ 0.9 m). Default for a conversation: **unrestricted** (today's behaviour), not `visitor`.
- **Two sessions in the demo:** the manager's conversation and a user's conversation are separate (two tabs),
  which shows the rules are building-wide. Switching role inside one conversation ("ask as a visitor") is also
  allowed, for a one-tab demo.
- **Store:** one versioned per-building record (access rules + applied changes) next to conversations (a
  `building_state` table in the same Supabase database, in-memory when Supabase is off). Each turn compares the
  record's version with the one the conversation last saw and reloads on change; a conversation then no longer
  stores its own applied changes. "Reporting a problem" by a non-manager (e.g. "Lift 1 is broken") is answered and
  noted for the manager, not applied — my call.
- **Destination rule:** a forbidden room can't be a destination either; the Guide names who may enter it.
- **Setting a user's role:** only in conversation (a Guide tool, like `set_profile`); no backend API field or
  frontend change ("the demo picks it" = the demo script's first message says the role).
- **Rule model:** per role, a deny-list of room types / space ids, plus an optional allow-list for vehicle-like
  roles (forklift: "only these zones"). Room types a role doesn't mention are open (deny-list default). The
  `forklift` role reuses the existing `forklift` profile and `RouteRules` (openings ≥ 3 m, no stairs, no
  walkways) and adds its zone allow-list on top; the existing forklift preset keeps working unchanged.
- **Combining limits:** role limits and the person's own mobility needs combine by the stricter value; the user's
  start room is never closed for them; role closures apply to `find_route`, `tour`, `reachable_rooms` (not
  `solve`, which serves analytics questions); a restored conversation uses the building's latest rules; a reset
  hook clears a building's rules for demos and tests.

## Left to the builder

- Exact tool names and schemas (e.g. `set_role`, `propose_access_rule` / reuse of `propose_change` with new
  actions), and how roles merge with `RoutingProfile` (one dataclass or role → profile defaults).
- How a role's room-type access becomes closed space ids (computed per building, cached).
- Wording of the "no access" answer and of the proposal's effect summary.
- Tests: offline tests for enforcement and the propose/confirm flow; one interaction-eval scenario (manager sets a
  rule, visitor asks for a forbidden room) to measure the conversation.
