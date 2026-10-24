---
id: product-personas
summary: 17 personas with special needs, ranked for the Interaction score and demo — scenario, needs, what to ask / never ask, direction style, and which data fields make each feasible (or not).
status: proposed (product thinking; no code yet)
sources:
  - archive/initial-repo/README-cb51a6f.md §1 "Put yourself in their shoes" (dropped from the 1.1.0 README, Q-017)
  - "Hackathon Challenge - Talk to Your Building.pdf p.1-3"
  - docs/kit/data-format.md
  - "dataset scan of all 280 buildings with core/building_map.py, 2026-10-24 (numbers in routing-profiles.md#dataset-reality-check)"
related: [routing-profiles.md, ../challenge/brief.md, ../kit/data-format.md, ../kit/route-model.md]
---

# Personas

[Docs index](../README.md) · Routing per persona: [routing-profiles.md](routing-profiles.md) · Organiser
personas: [brief.md](../challenge/brief.md#personas-put-yourself-in-their-shoes)

Why this exists: **Interaction = 25 pts**, judged by "a short scripted conversation with tricky users" on three
rubric points: *asks only what it needs · shows what it understood · gives directions a person can follow*
([brief.md](../challenge/brief.md#judging)). Each persona below is a likely tricky user. Everything the agent
says about places and routes must come from the deterministic core; personas only change **which profile**
the core routes with and **how** the result is phrased.

Legend for "Data": ✅ supported by existing fields · ⚠ partially (proxy / heuristic) · ❌ not in our data.

## Ranking (value for Interaction score + demo)

| Rank | Persona | Why it scores |
|---|---|---|
| 1 | [P01 Wheelchair user](#p01--wheelchair-user) | named by organisers; "every time, without asking twice" tests memory |
| 2 | [P02 First day at work](#p02--first-day-at-work) | vague intent ("coffee") → clarify vs. infer; landmark directions |
| 3 | [P04 Facility manager](#p04--facility-manager) | EDIT + REACT verbs; "show what I understood before changing the plan" |
| 4 | [P03 Service technician](#p03--service-technician-hands-full) | voice-first (ElevenLabs), "turn left at the press" |
| 5 | [P08 Hospital-bed / trolley mover](#p08--hospital-bed--trolley-mover) | door widths — mirrors `wide_delivery_count` benchmark kind |
| 6 | [P05 Forklift driver](#p05--forklift-driver) | blocked aisles, industrial add-in (Level 5) |
| 7 | [P13 Fire warden / evacuation](#p13--fire-warden--evacuation) | safety twist: lifts forbidden, nearest exit; strong demo moment |
| 8 | [P10 Blind / low-vision](#p10--blind--low-vision-user) | voice-only, door counting — differentiator for Creativity |
| 9 | [P11 Non-native speaker](#p11--non-native-speaker) | multilingual voice in/out — cheap with ElevenLabs |
| 10 | [P07 Claustrophobic](#p07--claustrophobic--wont-take-lifts) | "no lifts" is the inverse of wheelchair — tests profile logic |
| 11 | [P09 Sensory-sensitive](#p09--autistic--sensory-sensitive) | quiet routes — distinctive, data-backed by `room_type` |
| 12 | [P06 Logistics](#p06--logistics-clerk) | FIND of moved assets — "this is now here" add-in |
| 13 | [P12 Elderly, limited stamina](#p12--elderly-visitor-limited-stamina) | fewer stairs, shorter legs |
| 14 | [P14 Crutches (temporary)](#p14--temporary-injury-on-crutches) | step-free but lifts fine; prefers fewer doors |
| 15 | [P15 Parent with pram](#p15--parent-with-pram) | step-free + width, like P08 lite |
| 16 | [P16 Delivery courier / visitor](#p16--delivery-courier--visitor) | start at entrance, unknown names |
| 17 | [P17 Night cleaning / security](#p17--night-cleaning--security-staff) | multi-stop tour (warm-up `tour` kind) |
| – | [P18 Deaf / hard of hearing](#p18--deaf--hard-of-hearing) | UI requirement more than routing — always offer text + visual |

Suggested **demo script cast**: P02 → P01 → P04 (closes lift) → P01 again (route changes, no re-asking) →
P03 by voice. Covers FIND, ROUTE, EDIT, REACT and voice in ~3 minutes.

---

<a id="p01--wheelchair-user"></a>
### P01 — Wheelchair user
- **Quote:** "I'm in a wheelchair. How do I get to the lecture hall on floor 2?"
- **Needs:** step-free every time; doors wide enough; lift availability; warn early if unreachable.
- **Ask:** nothing extra if start is known. **Never ask** "do you want step-free?" again after it was said once.
- **Direction style:** room names + lift name + distance; mention door widths only if tight.
- **Profile:** [`wheelchair`](routing-profiles.md#profiles-per-persona).
- **Data:** ✅ `opening.step_free`, `vertical_connector.step_free`/`kind`, `opening.width_m`. ⚠ wheelchair
  width threshold (0.8–0.9 m) is our assumption — 31% of openings are < 0.9 m.
- **Gap:** ❌ lift *out-of-order* status is only known when a user reports it (closures).

<a id="p02--first-day-at-work"></a>
### P02 — First day at work
- **Quote:** "Where do I get coffee?" / "Where's the toilet near the meeting room?"
- **Needs:** map vague intents to `room_type` / asset type (coffee → `canteen` or kitchen-type asset);
  nearest by route, not by straight line.
- **Ask:** start location only if needed ("Where are you now? A room number or what you see works.").
  If several candidates are close, offer the nearest two — don't list fifteen.
- **Never ask:** for room ids or codes.
- **Direction style:** landmarks first ("past the print room, it's the second door on your left"), room number
  as confirmation.
- **Data:** ✅ `room_type` (canteen, kitchen, toilet, lobby…), `assets[].type`. ⚠ intent→type mapping is our
  synonym table. ⚠ "left/right" needs heading from geometry (polygons + door positions) — derivable, not stored.

<a id="p03--service-technician-hands-full"></a>
### P03 — Service technician (hands full)
- **Quote (voice):** "Which of the three presses is line 4, and how do I get there?"
- **Needs:** voice in/out; short steps, one at a time ("say next"); asset disambiguation by name/room.
- **Ask:** a single disambiguation question with the options' distinguishing features (room, floor).
- **Direction style:** landmark + machine names ("turn left at the press"), no long distances lists.
- **Data:** ✅ `assets[].name`, `type`, `category: machine`, `space_id`, `position`. ⚠ "line 4" only works if
  the name contains it — otherwise say so honestly.

<a id="p04--facility-manager"></a>
### P04 — Facility manager
- **Quote:** "Close the east lift for maintenance — what changes?" / "Add a door between 2.03 and 2.04." /
  "The 3D printer is now in 1.12."
- **Needs:** edits applied to the shared building state; a preview + confirmation before writing; impact
  summary (which routes/rooms are affected).
- **Ask:** confirm the resolved element ("Lift 2 (east core, floors 0–4) — close it?"). "East" must be resolved
  from geometry (connector space positions) and stated back.
- **Direction style:** n/a — impact report: "3 rooms on floor 4 are no longer step-free reachable: …".
- **Data:** ✅ connectors, openings, polygons for "middle of shared wall", `assets[].space_id/position`.
  ⚠ compass words (east/west) assume +x = east — our convention, state it.

<a id="p05--forklift-driver"></a>
### P05 — Forklift driver
- **Quote:** "Aisle 4 is blocked. Fastest route to dock B?"
- **Needs:** vehicle-legal route: no stairs/steps, wide openings, halls and logistics zones preferred, avoid
  offices; closures of hall *zones*.
- **Ask:** nothing if the vehicle is known from earlier; confirm which aisle/zone is blocked.
- **Data:** ✅ `room_type` production/warehouse/logistics zones, `width_m` (1.6 m hall doors in procedural
  data), step-free. ❌ aisles inside a hall are not modelled — a hall is one polygon/node. Level 5 add-in would
  need sub-zone graphs.

<a id="p06--logistics-clerk"></a>
### P06 — Logistics clerk
- **Quote:** "Where is the steel drum delivered yesterday?"
- **Needs:** asset lookup with history ("moved here at 14:05 by X").
- **Data:** ✅ asset search. ❌ timestamps / delivery history — only exists once our edit log records moves
  (collaboration feature).

<a id="p07--claustrophobic--wont-take-lifts"></a>
### P07 — Claustrophobic / won't take lifts
- **Quote:** "No lifts please, I'll take the stairs."
- **Needs:** `avoid_lifts` hard filter; if unreachable without lifts, say so and offer the lift route as a
  clearly-labelled alternative.
- **Data:** ✅ connector `kind`.

<a id="p08--hospital-bed--trolley-mover"></a>
### P08 — Hospital-bed / trolley mover
- **Quote:** "I'm pushing a 1.1 m trolley from the loading dock to the server room on floor 3."
- **Needs:** min door width filter, no steps, lifts OK (benchmark semantics of `wide_delivery_count`).
- **Ask:** width if not given ("How wide is it? Standard pallets are 0.8 or 1.2 m.").
- **Data:** ✅ `width_m`, `step_free`. Reality check: with ≥ 1.1 m doors only **2,025 of 16,223** rooms are
  reachable from outside step-free — the agent must explain *which door* blocks it.
  ⚠ lift cabin width not in data ([Q-004](../../memory-bank/open-questions.md#q-004)).

<a id="p09--autistic--sensory-sensitive"></a>
### P09 — Autistic / sensory-sensitive
- **Quote:** "Is there a quiet way to the library? I'd rather not go through the canteen."
- **Needs:** soft penalty on noisy `room_type`s; avoid crossing halls; predictable, detailed steps.
- **Data:** ⚠ noise is a proxy from `room_type` (lobby 94, production_zone 78, warehouse_zone 78,
  logistics_zone 69, assembly_zone 48, canteen 35, additive_zone 18 spaces in the dataset). ❌ real-time crowding/noise.

<a id="p10--blind--low-vision-user"></a>
### P10 — Blind / low-vision user
- **Quote (voice):** "Guide me to room 0.21."
- **Needs:** voice only; step-by-step with **door counting** and turn directions; avoid open halls (no walls to
  follow); fewer doors; confirm arrival.
- **Never:** "as you can see on the map".
- **Data:** ⚠ door count per leg ✅ (openings on path), turn directions derivable from door positions;
  hall avoidance ✅ (`type: hall`). ❌ tactile paving, braille signage, obstacles.

<a id="p11--non-native-speaker"></a>
### P11 — Non-native speaker
- **Quote:** "Wo ist der Drucker?" (German; many OSM names are German, e.g. "Büro")
- **Needs:** reply in the user's language; keep room names/refs verbatim.
- **Data:** ✅ names as-is. Multilingual STT/TTS via ElevenLabs ([elevenlabs.md](../research/elevenlabs.md)).

<a id="p12--elderly-visitor-limited-stamina"></a>
### P12 — Elderly visitor, limited stamina
- **Quote:** "My knees aren't great — shortest walk with as few stairs as possible."
- **Needs:** lift preferred over stairs (soft), shorter total walk, optional rest stop suggestion.
- **Data:** ✅ connectors. ⚠ rest stops via assets of type seating (sofa/chair/bench) in rooms along the route
  — heuristic.

<a id="p13--fire-warden--evacuation"></a>
### P13 — Fire warden / evacuation
- **Quote:** "Fire alarm on floor 3 — fastest way out for everyone, no lifts."
- **Needs:** nearest entrance per room (same computation as `what_if_door` baseline); lifts excluded;
  step-free exits flagged for wheelchair users (who need refuge areas when only stairs exist).
- **Data:** ✅ entrances (`"outside"`), connectors. ❌ designated emergency exits, refuge areas, fire doors.
  Must carry a disclaimer: not a certified evacuation plan.

<a id="p14--temporary-injury-on-crutches"></a>
### P14 — Temporary injury on crutches
- **Quote:** "I'm on crutches this week."
- **Needs:** step-free; fewer doors (heavy door leaves); lifts fine. Remember for the session only.
- **Data:** ✅ step_free, `opening.kind` (door vs opening without leaf).

<a id="p15--parent-with-pram"></a>
### P15 — Parent with pram
- **Needs:** step-free, ≥ 0.8 m doors (assumption), toilets with changing — ❌ changing tables not in data
  unless an asset type exists.
- **Data:** ✅ step_free, width_m.

<a id="p16--delivery-courier--visitor"></a>
### P16 — Delivery courier / visitor
- **Quote:** "I have a parcel for Dr. Weber in the lab building."
- **Needs:** start at an entrance; route to reception/lobby or the right room.
- **Ask:** which entrance they are at, only if the building has several.
- **Data:** ✅ entrances, `room_type: lobby`. ❌ people/occupant directory.

<a id="p17--night-cleaning--security-staff"></a>
### P17 — Night cleaning / security staff
- **Quote:** "Plan my round: all toilets on floors 1 and 2, then back to the locker room."
- **Needs:** multi-stop tour; order optimisation (TSP-lite) or fixed order (warm-up `tour` kind is fixed-order).
- **Data:** ✅ `room_type`, routing with `via`.

<a id="p18--deaf--hard-of-hearing"></a>
### P18 — Deaf / hard of hearing
- **Needs:** full text parity with voice; visual route highlight; captions of any voice output; no
  voice-only confirmations.
- **Data:** n/a — UI requirement. Captions come free from ElevenLabs transcripts.

<a id="added-personas-2026-10-24"></a>
## Added personas (2026-10-24, not yet ranked)

These come from the [preference-extraction TODO](routing-profiles.md#todo-preference-extraction). Most of them
test *whose* profile applies and how profiles combine, not new graph filters.

<a id="p19--carer--companion"></a>
### P19 — Carer / companion
- **Quote:** "Where's the nearest toilet for my mother? She uses a wheelchair."
- **Needs:** the profile belongs to the person being guided, not the speaker; don't ask the speaker about their
  own mobility.
- **Data:** ✅ same as [P01](#p01--wheelchair-user).

<a id="p20--group--school-tour-leader"></a>
### P20 — Group / school tour leader
- **Quote:** "30 kids, one in a wheelchair, and a teacher who won't take lifts."
- **Needs:** the group's profile is the composition of all members' profiles. If nothing satisfies all of them
  (step-free needs a lift, someone refuses lifts), say so and offer to split the group.
- **Data:** ✅ connectors, step_free.

<a id="p21--mobility-scooter-user"></a>
### P21 — Mobility scooter user
- **Needs:** step-free with a wider minimum door width than a wheelchair.
- **Data:** ✅ `width_m`. ❌ lifts carry no width/cabin-size field in the data (see the
  [Q-004](../../memory-bank/open-questions.md#q-004) answer), so the agent must say it can't confirm the scooter
  fits the lift. ⚠ UNVERIFIED: no scooter door width in our sources, so there is no `mobility_scooter` preset; a
  scooter cue sets step-free only and the Guide asks the width
  ([implemented presets](routing-profiles.md#implemented-presets)).

<a id="p22--pregnant--heart-condition"></a>
### P22 — Pregnant / heart condition
- **Needs:** stairs allowed but discouraged: soft stairs penalty, like `low_stamina` in
  [routing-profiles.md](routing-profiles.md#profiles-per-persona).
- **Data:** ✅ connectors.

<a id="p23--hazardous-goods-carrier"></a>
### P23 — Hazardous-goods carrier
- **Quote:** "I'm moving a chemical drum to the lab."
- **Needs:** no passenger lifts, avoid canteen and office-type rooms (`avoid_room_types`), width limit.
- **Data:** ✅ `room_type`, `width_m`. ❌ goods lifts vs passenger lifts aren't distinguished. ⚠ which room types
  to avoid is our policy.

<a id="p24--hygiene-zone--cleanroom-worker"></a>
### P24 — Hygiene-zone / cleanroom worker
- **Needs:** don't pass through "dirty" zones on the way to a clean area (`avoid_room_types`).
- **Data:** ⚠ UNVERIFIED: no clean/dirty classification seen in the data; we would have to map it from
  `room_type` ourselves.

<a id="p25--long-load-carrier"></a>
### P25 — Technician carrying a long load (ladder, pipes)
- **Needs:** door width limit; tight turns are also a problem.
- **Data:** ✅ `width_m`. ❌ turn angles and corridor geometry aren't modelled.

<a id="p26--changing-constraints-user"></a>
### P26 — User whose constraints change
- **Quote:** "Actually my chair is narrow, 0.7 m." / "I'm out of the cast now."
- **Needs:** update or reset the profile and confirm the change in one line; don't keep the old constraint.
- **Data:** n/a, session state only.

## Cross-cutting interaction rules (derived from the personas)

1. **State the understood profile once**, then remember it for the conversation: "Step-free route, doors ≥ 0.9 m."
2. **Ask at most one question at a time**, and only when the answer changes the route.
3. **Every route reply** = one-line understanding + numbered steps + total distance + profile caveats.
4. **Unreachable is an answer**, with the blocking element named ("Stairs only between floors 1 and 2").
5. **Edits:** preview → confirm → apply → impact summary.
6. **Honesty about data gaps** (crowding, aisles, emergency exits) rather than making things up.

## Related

- [routing-profiles.md](routing-profiles.md) — parameters per persona
- [brief.md](../challenge/brief.md#personas-put-yourself-in-their-shoes) · [route-model.md](../kit/route-model.md)
