# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Mobile-first web app (phone in hand, inside or in front of a building); must also work on desktop for demos.

## Users

- **Visitor** (not signed in): someone in or near a building who needs to find a place, an item or a way —
  first day at work, delivery courier, wheelchair user, technician with full hands, fire warden. Often in a
  hurry, often unfamiliar with the building; does not want to "explore a model", wants the answer.
- **Facility manager / maintainer** (signed in, allowed on that building): same app plus the right to change
  the building — close an area or a door, rename a room, add or move equipment — by voice, chat or direct UI.
- Personas and their needs: `docs/product/personas.md` (17 personas, demo cast P02 → P01 → P04 → P01 → P03).

## Product Purpose

"Talk to your building": ask in plain words (typed, spoken, or by showing the phone camera) and get a correct,
grounded answer — where something is, how to get there for *you*, what changed. Every place, route and number
comes from a deterministic geometry/graph core; the language model only talks. Success: a first-time visitor
finds their way without reading a map legend; a maintainer changes the building and every visitor's next route
reflects it.

## Positioning

Not an indoor map with a search box: an agent that already knows the exact floor plans (doors, widths, stairs,
lifts, closures) and answers per person (wheelchair, pram, trolley, no lifts, forklift) — the plan is shown to
prove and explain the answer, not to make the user do the work.

## Operating Context

- **Arrival, three ways:** scan a QR code at the building (deep link, building pre-selected), pick it on a map
  that uses the phone's location, or search a list. QR codes cannot be printed yet and only some buildings have
  real coordinates (17 of 280 via OSM), so the list is required and QR is simulated by a link during development.
- **Inputs:** text chat, voice (browser speech now; ElevenLabs later), phone camera photo ("where am I?"),
  camera walk mode with turn-by-turn legs.
- **Outputs the UI must show:** highlighted spaces, a route across floors (stairs/lift legs), closed areas,
  spaces that lost access after an edit, proposed vs applied changes, follow-up suggestions.
- **Data:** 280 buildings (campus, factory, office, hospital, Swiss…), 1–many floors, rooms with names/types,
  doors with widths, stairs, lifts, equipment. Backend: FastAPI (`backend/app.py`), events via `/events` and
  `/chat/stream`.

## Capabilities and Constraints

- Frontend: React + Vite + TypeScript + three.js (react-three-fiber) in `frontend/app/`; the backend API
  contract in `src/api.ts` is fixed.
- Roles: visitor vs facility manager. Shared building edits exist on branch `collab-edits` (phase 1); sign-in
  and role checks are planned, not built (`docs/architecture/collaboration-auth.md` on that branch).
- What a role sees first is a product decision: a visitor is here to find something, so the agent leads and the
  building view supports it; a signed-in manager on their own building gets the full building view and tools.
- Maintainer edits go through propose → confirm → apply; nothing changes the building without a confirmation.
- Performance on mid-range phones matters (previous 3D prototypes felt laggy).

## Brand Commitments

- Color scheme in the spirit of Apple Maps (user's explicit reference): light, calm, map-like neutrals, clear
  semantic colors; light and dark.
- Simple and non-intimidating; must not look like a generic AI/chat app.
- No glow, no bloom, no auto-rotation or idle camera motion; not everything is 3D or rotating.
- Earlier visual decisions (monochrome D-011, point cloud) are void.

## Evidence on Hand

- Real building data in `data/` (train/dev/test, 280 buildings) and live Guide answers from the backend.
- No real user photos, testimonials, customers or real QR codes; do not invent them.

## Product Principles

1. The answer first, the map as proof: show what was understood and where, never make the user hunt.
2. One app, roles reveal more: visitors get the guide; managers get the same app with editing unlocked.
3. Any input, same result: typing, speaking, or pointing the camera all lead to the same grounded answer.
4. Calm by default: nothing moves unless the user or the answer asks for it.
5. Changes are always previewed and confirmed before they touch the building.

## Accessibility & Inclusion

Wheelchair, low-vision/blind (voice-only path), deaf (always text + visual), non-native speakers, hands-full
technicians: every flow must work by voice alone and by touch alone; large touch targets; readable contrast in
light and dark.
