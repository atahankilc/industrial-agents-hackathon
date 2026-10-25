---
id: access-profiles-plan
summary: Implementation plan for the access-profiles design — phase 1 (switch, accounts, restricted spaces) in tasks, phases 2–4 (preferences, moving objects, live missions) outlined.
sources:
  - docs/superpowers/specs/2026-10-25-access-profiles-design.md
  - backend/app.py, backend/sessions.py, backend/persistence.py, agent/tools.py, core/floorplan.py
related: [../specs/2026-10-25-access-profiles-design.md]
status: phases 1–4 built (2026-10-25)
---

# Access profiles — implementation plan

Design: [access-profiles-design](../specs/2026-10-25-access-profiles-design.md). Everything below runs only with
`ACCESS_MODE=on`; with it off, every endpoint and the Guide behave exactly as before.

## Phase 1 — switch, accounts, restricted spaces

**Core idea:** a viewer who may not enter some spaces gets a session on a **filtered copy** of the building
(`core/access.py filter_building`: restricted spaces, the openings into them, their assets and their connector
stops removed). Every Guide tool, `solve` included, then simply can't see them — no per-tool filtering to forget.
The plan export is built from that filtered copy, plus the restricted polygons (no name, ref, type or assets) as
`restricted`, which the plan view darkens. A named restricted place answers `restricted` instead of "unknown".

1. **`core/access.py`** — `filter_building(data, restricted) -> data` (pure), `restricted_names(data, restricted)`.
   Tests: filtered map loads, routes avoid nothing else, warm-up routes untouched when `restricted` is empty.
2. **`backend/access.py`** — `access_mode()` (env `ACCESS_MODE`), `Viewer` (anonymous | member | admin),
   `viewer_from_token` (Supabase `GET /auth/v1/user`, cached 60 s; admin = `ADMIN_EMAIL`), `AccessStore`
   (memory / Postgres): building public flag, rules (room_type / space id → groups), memberships (user, building,
   groups); `restricted_for(viewer, building_id, data)`, `visible(viewer, building_id)`; invite (Supabase admin
   `generate_link`, service-role key).
3. **Migration** `supabase/migrations/20261025200000_access.sql`: `access_buildings`, `access_rules`,
   `access_members`. RLS on, no policies.
4. **Sessions** — `Conversation.restricted` (frozenset); `SessionStore.ensure_access(conversation, restricted)`
   rebuilds the session on the filtered building and replays its state when the set differs (rules changed, other
   viewer); a replay that no longer applies starts a fresh conversation on that building.
5. **API** — `GET /config`; `GET /me`; every session endpoint reads `Authorization` and calls `ensure_access`;
   `/buildings` lists only visible buildings; admin: `GET/PUT /access/building?id=…` (public flag + rules),
   `GET /access/members?building=…`, `POST /access/invite`, `PUT /access/members`. Plan adds `restricted`.
6. **Guide** — `BuildingSession.restricted_names`; a tool call naming one returns
   `{"error": "restricted", …}`; one system-prompt line on how to answer it. Tool list unchanged.
7. **Frontend** — `/config` on start; with access mode: sign in / out in the menu (`@supabase/supabase-js`),
   token on every API call, restricted spaces darkened without labels, menu → Building settings → Access (admin:
   public toggle, room-type rules, per-space exceptions, members + invite link).
8. **Checks** — pytest (switch off = identical tool list / plan / routes; filtered sessions; restricted answer;
   API auth with a fake verifier), `scripts/eval_guide.py` unchanged, `tsc`, headless Chrome run.

## Phase 2 — preferences (outline)

New `RoutingProfile` fields (`avoid_room_types`, soft penalties) with a cost weight in routing used only when set;
`set_preference` tool + `preference` events; local storage / `user_preferences`; Preferences and Building settings
sheets; effective = global ← building.

## Phase 3 — moving objects (outline)

`objects` table, attributes → closures (width, step-free, lifts, stairs, room types), forklifts from
`equipment.csv`, Objects tab, objects drawn on the plan.

## Phase 4 — live positions + missions (outline)

Position API with device tokens, polling in the app (trail, heading, remaining line), mission JSON
(design § Missions), re-plan on change, `scripts/sim_object.py`.
