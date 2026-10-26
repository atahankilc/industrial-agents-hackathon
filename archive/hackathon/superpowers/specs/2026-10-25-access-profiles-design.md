---
id: access-profiles-design
summary: Demo feature behind ACCESS_MODE (off by default) — accounts (one admin over all buildings, invited members), public / restricted spaces darkened on the plan and hidden from answers, remembered user preferences (global, per-building override, captured by the Guide), and moving objects (forklifts, robots) with data-backed attributes, live positions and machine-readable missions. Benchmark untouched.
sources:
  - conversation with Atahan, 2026-10-25 (decisions below)
  - docs/superpowers/specs/2026-10-24-access-roles-design.md (Utku's design; parts kept, parts replaced)
  - agent/tools.py (RoutingProfile, PRESETS, profile_closures, route_rules, set_profile, tool list)
  - backend/app.py, backend/sessions.py, backend/persistence.py, supabase/migrations/
  - "data/*/*/building.json field scan 2026-10-25: openings {id, floor_id, kind, position, space_ids, step_free, synthetic, width_m}; vertical_connectors {id, floor_ids, kind, name, space_ids, step_free, synthetic}; floors {id, level, name, elevation_m, height_m}"
  - "data/*/*/equipment.csv scan 2026-10-25: 107 forklift, 69 forklift_charging_station, 16 robot_cell assets; columns incl. x_m, y_m, width_m, depth_m, rotation_deg"
  - "room_type scan 2026-10-25: server_room in 27 buildings, technical_room in 4, production_zone in 24 (of 280)"
related: [2026-10-24-access-roles-design.md, ../../product/routing-profiles.md, ../../product/personas.md, ../../architecture/ai-agents.md]
status: accepted by Atahan 2026-10-25 — built 2026-10-25 (backend + frontend, offline tests, headless run with a fake sign-in); a real Supabase sign-in not yet tried
---

# Access, preferences and moving objects (design)

## Intent

Three demo features on top of the Guide, all behind one switch:

1. **Who sees what.** Visitors (not logged in) see public buildings and the public spaces in them. Restricted
   spaces are darkened on the plan and never used in answers or routes. Building managers log in and set access.
2. **The app remembers you.** Mobility needs and route preferences (from the personas, only what the dataset can
   honour) are remembered per user, captured by the Guide from the conversation or set in settings, and can be
   overridden per building.
3. **Moving objects.** Forklifts today, robots and other automated vehicles tomorrow: each has attributes (width,
   stairs, lifts, …), gets routes that fit them, shares its position (drawn live on the plan, where it came from,
   where it goes) and receives its route as machine-readable instructions — no conversation, the app dispatches it.

## Relation to Utku's design (2026-10-24-access-roles-design)

Kept: access enforced in code (tool layer), never by the model; the default is today's behaviour; routes to a
restricted place get a clear answer (no silent "no route"); the forklift keeps the existing `forklift` preset and
`RouteRules` (no zone allow-list, Q-015 still open); benchmark untouched.

Replaced: a role is **not** a claim in conversation any more — accounts are real (Supabase Auth). Access is set in
a settings UI (the Guide may still help). "Manager" = the one admin account (below). Building-wide applied changes
(close / reopen / add door for everyone) are **not** in scope now — see [Later](#later).

## Decided (Atahan, 2026-10-25)

- **Switch:** the feature is off by default and never reaches the benchmark (see [Switch](#switch)).
- **Auth:** Supabase Auth. For now **one admin account** with rights over every building.
- **Members:** logged-in users who are not admins exist; the admin invites them.
- **Restricted spaces:** darkened on the plan and unusable in answers.
- **Anonymous preferences:** stored in the browser (local storage).
- **What to remember:** everything we can, especially what matters for routing — the persona attributes the
  dataset supports.
- **Preferences belong to the user;** on/off in settings; the Guide may capture them from the conversation
  automatically. A building-specific override is set in that building's settings (no extra buttons on the
  screen); without one, the user's general preferences apply.
- **Object attributes:** only what the data can use; anything the data can't support is left out.
- **Objects belong to a building;** the admin manages them.
- **Machine instructions:** as proposed in [Missions](#missions).
- **Multi-robot path conflicts:** a TODO, not built.
- **Order:** auth + restricted spaces → preferences → objects + attribute routing → simulated live robot +
  mission format.

## Switch

- Backend env **`ACCESS_MODE=on`** turns it on; anything else (default) = off. `GET /config` returns
  `{"access_mode": bool, "supabase_url", "supabase_anon_key"}` so the frontend knows (no frontend build flag).
- **Off** = exactly today: no login button, every space public, preferences not remembered, no objects, the
  Guide's tool list unchanged.
- The benchmark never runs through the backend: `agent.run_benchmark`, `agent.answer`, `core/solvers`,
  `core/navigation` defaults, `SUNDAY_RULES` stay untouched. `BuildingSession` / `Guide` built directly (scripts,
  tests, `scripts/eval_guide.py` 18/18) get no access layer unless a test passes one.

## Accounts

- **Supabase Auth, email + password** (magic links depend on email delivery, which Supabase rate-limits on the
  free tier — UNVERIFIED limit). The frontend signs in with `@supabase/supabase-js` (anon key) and sends the access
  token as `Authorization: Bearer …`; the backend checks it with `GET {SUPABASE_URL}/auth/v1/user` (cached
  per token for a minute) — no JWT secret in our code.
- **Admin:** an account whose email is listed in env `ADMIN_EMAIL` (comma-separated; two admins since 2026-10-25,
  Atahan). Rights over every building.
- **Members:** the admin invites by email and picks access groups per building. The backend creates the user with
  the service-role admin API and returns an **invite link** the admin copies (Supabase `generate_link`, no email
  sent — demo-safe).
- **Viewer** of a request = anonymous | member (with groups per building) | admin.

## Access model

- **Building:** `public` (default true for every catalogue building). A non-public building is listed and opened
  only for members with a group on it and the admin.
- **Space:** public, or restricted to named **groups** (e.g. `staff`, `it`, `maintenance`; the admin creates
  groups freely). Rules per building: by `room_type` (`server_room → [it]`) and per space id (exceptions win).
- **Default rules:** none — every space is public until the admin restricts it (Atahan, 2026-10-25).
- A viewer **may enter** a space if it is public, or they hold one of its groups, or they are the admin.
- **Enforcement (code, not model):** for a viewer, restricted spaces are added to the session's closures
  (`profile_closures` gains them; the start space is never closed), so `find_route`, `tour`, `reachable_rooms`
  never use them. `search`, `locate`, `room_facts`, `count_assets`, `building_overview` drop restricted spaces and
  the assets inside them. A target that is restricted returns `{"error": "restricted", …}` → the Guide says "that
  area is restricted" (it names no detail) and offers the nearest public place.
- **Plan:** `/sessions/{id}/plan` marks restricted spaces `restricted: true` and drops their name, ref and assets;
  the plan view draws them darkened, without labels.
- **`solve` (analytics) is filtered too** (Atahan, 2026-10-25): counts, areas, lists and adjacency only see the
  spaces and assets the viewer may enter; a question about a restricted space answers "restricted".

## Preferences

**Fields** (routing ones from [routing-profiles.md](../../../../docs/product/routing-profiles.md) — only rows the data
supports):

| Field | Kind | Data it uses | Personas |
|---|---|---|---|
| `step_free` | hard filter (exists) | opening / connector `step_free` | P01, P08, P14, P15, P21 |
| `min_door_width_m` | hard filter (exists) | opening `width_m` | P01, P08, P15, P21, P25 |
| `avoid_lifts` | hard filter (exists) | connector `kind` | P07 |
| `avoid_room_types` | hard filter (new) | space `room_type` (start/destination exempt) | P09, P24 |
| `prefer_lifts` | soft: stairs penalty per floor (new) | connector `kind`, floor `elevation_m` | P12, P22 |
| `fewer_doors` | soft: door penalty (new) | opening `kind` | P14, P10 |
| `quiet` | soft: noisy room types (new) | `room_type` ∈ NOISY | P09 |
| `avoid_halls` | soft: hall penalty (new) | space `type` | P10 |
| `simple_routes` | soft: space-change penalty (new) | spaces on the path | P02, P10, P16 |
| `language`, `voice`, `reply_style` (brief / detailed) | Guide behaviour | — | P11, P03, P18 |
| `favourites` | per building: saved places | space / asset ids | all |

Soft penalties are a new cost on the router, used only when a preference is set; with none set the cost equals
the base weight, so routes stay exact (tests over the warm-up routes keep 1,338/1,338).

**Storage:** anonymous → browser local storage; logged in → a `user_preferences` row (the user owns it).
Shape: `{"remember": bool, "auto_capture": bool, "global": {...}, "buildings": {"<id>": {...}}}`.
Effective preference for a building = global, overridden field by field by that building's entry.

**Flow:** on session start the frontend sends the effective preferences → the session profile. When the Guide
calls `set_profile` (or a new `set_preference` for the non-routing fields) and `auto_capture` is on, the backend
emits a `preference` event; the frontend saves it (global, or the building's entry if the user said "here" /
"in this building") and the Guide says what it will remember ("I'll remember you use a wheelchair"). `remember:
false` = nothing stored, the session still uses what was said.

**UI:** menu → **Preferences** (global: toggles + the two switches) and menu → **Building settings** (this
building's overrides; for the admin also Access and Objects). No new buttons on the building screen.

## Moving objects

**Attributes** (only what the data can use):

| Attribute | Routing effect | Data |
|---|---|---|
| `kind` | label, icon; `forklift` applies the forklift preset + rule | — |
| `width_m` | openings narrower than width + clearance act as closed | opening `width_m` |
| `step_free_only` | no stepped openings / stairs | `step_free` |
| `can_use_lifts` | lifts closed if false | connector `kind` |
| `can_use_stairs` | (legged robots) stairs allowed even if `step_free_only` is off | connector `kind` |
| `avoid_room_types` | e.g. a cleaning robot stays out of labs | `room_type` |

Left out (no data): height (openings have no height), weight / load, lift cabin size, turning radius.
Forklifts in `equipment.csv` (107, with position and footprint) are offered as ready-made objects in factory
buildings; robots / AGVs are added by the admin.

**Positions:** each object has a device token. `POST /objects/{id}/position` `{floor_id, x, y, heading_deg?}`
(token auth) → stored as the latest position + a short trail. The app polls `GET /buildings/{id}/objects`
(~1 s; serverless, no long-lived streams) and draws each object with heading, trail and its mission's remaining
line.

<a id="missions"></a>
**Missions:** the admin dispatches (tap object → tap destination, or ask the Guide: "send R1 to Lab 2").
The route is computed with the object's attributes; the object polls `GET /objects/{id}/mission`:

```json
{"mission_id": "m-12", "version": 1, "object_id": "r1", "to": {"space_id": "...", "name": "Lab 2"},
 "length_m": 84.3,
 "steps": [
   {"op": "move", "floor_id": "F0", "waypoints": [[x, y], ...]},
   {"op": "pass_opening", "opening_id": "...", "width_m": 1.2},
   {"op": "call_lift", "connector_id": "...", "from_floor": "F0", "to_floor": "F2"},
   {"op": "move", "floor_id": "F2", "waypoints": [[x, y], ...]},
   {"op": "arrive", "space_id": "..."}]}
```

Deterministic, no LLM, building metres (same frame as the plan). Waypoints come from the existing route line
(`core/routeline.py`). If the building changes under a running mission, the mission is re-planned and `version`
goes up. **Demo:** `scripts/sim_object.py` drives a fake object along its mission and posts positions.

## Storage (Supabase, in memory when off)

New migration: `access_groups`, `space_rules` (building, room_type | space_id, groups), `building_access`
(building, public), `memberships` (user, building, groups), `user_preferences` (user, prefs jsonb),
`objects` (building, attributes jsonb, token hash), `object_positions` (latest + trail), `missions`. RLS on, no
policies — only the backend touches them (as today).

## Tests

Offline: switch off = today (tool list, plan, routes identical); viewer closures and filtered tool results;
restricted destination answer; preferences merge (global ← building); soft penalties zero = exact warm-up routes;
object attributes → closures; mission JSON from a known route; position auth. `scripts/eval_guide.py` 18/18.

<a id="later"></a>
## Later (TODO)

- Path conflicts between several objects (reservation of corridors / doors, waiting).
- Building-wide applied changes (Utku's design): a closure the admin applies reaches every conversation.
- Per-building admins, real email invites.

<a id="open-questions"></a>
## Open questions

None open. Answered 2026-10-25 (Atahan): `solve` is filtered; no default restricted room types; this design
replaces the parts of Utku's design listed above (Atahan's call).
