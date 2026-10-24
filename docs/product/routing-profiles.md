---
id: product-routing-profiles
summary: Deterministic, explainable routing profiles (hard filters + soft penalties) layered on the exact benchmark route model; DEFAULT reproduces benchmark costs exactly. Persona parameter table, inference/memory rules, "what changes" diffs, dataset reality check.
status: proposed (design sketch; nothing implemented)
sources:
  - docs/kit/route-model.md
  - core/building_map.py (BuildingMap.graph, route)
  - "dataset scan of all 280 buildings with core/building_map.py, 2026-10-24"
related: [personas.md, ../kit/route-model.md, ../architecture/solver-plan.md, ../architecture/overview.md]
---

# Routing profiles

[Docs index](../README.md) · Who needs what: [personas.md](personas.md) · Base model:
[route-model.md](../kit/route-model.md) · Organiser personas:
[brief.md](../challenge/brief.md#personas-put-yourself-in-their-shoes)

## Principle

A **profile** is a pure function input to the router: same building + same closures + same profile → same
route, every time. The LLM only **selects and fills** a profile from the conversation; it never computes
routes. Profiles are layered on the benchmark route model:

```
building.json ──► base graph (exact benchmark model: anchors, door nodes, 12 m/floor stairs, 15+6 m lift)
                     │
                     ├─ 1. hard filters   → remove edges/nodes   (changes WHAT is reachable)
                     └─ 2. soft penalties → add cost to edges    (changes WHICH route wins)
                                 │
                     Dijkstra on "cost"; report "length_m" = sum of base weights (true metres)
```

**Two weights per edge:** `weight` (true metres, base model) and `cost` (weight + penalties). Routing
minimises `cost`; the answer always reports metres from `weight`. With every penalty at 0, `cost == weight`
→ the **DEFAULT profile is the benchmark model exactly** (must keep the 369/369 oracle result on dev).

Benchmark solvers must call the router with `DEFAULT` (or the exact filters a question states, e.g.
`wide_delivery_count` = step-free + `min_door_width_m`). Soft penalties are **never** used for scored answers.

## Parameters

### Hard filters (remove from graph)

| Parameter | Type | Effect on `BuildingMap.graph` | Data field |
|---|---|---|---|
| `step_free` | bool | drop openings/connectors with `step_free: false` (exists today) | `step_free` |
| `min_door_width_m` | float \| None | drop openings with `width_m < min` | `opening.width_m` |
| `avoid_lifts` | bool | drop connectors with `kind == "lift"` | `vertical_connectors[].kind` |
| `avoid_stairs` | bool | drop connectors with `kind == "stairs"`. In the data all 576 stairs are `step_free: false` and all 136 lifts `true`, so this equals the connector part of `step_free`; it stays separate because it is a different user intent (it doesn't also block stepped entrances) | `kind` |
| `closed` | set[id] | drop element / space node (exists today) | ids |
| `avoid_room_types` | set[str] | drop space nodes of these types, except start/destination | `room_type` |
| `avoid_space_ids` | set[str] | drop specific spaces (e.g. blocked aisle zone) | ids |
| `max_floor_changes` | int \| None | constrained search: count connector edges on path (layered graph by "changes used") | connectors |

### Soft penalties (add metres-equivalent cost)

| Parameter | Default | Applied to | Purpose |
|---|---|---|---|
| `stairs_penalty_per_floor_m` | 0 | stair edges, × floor span | elderly, crutches: prefer lifts |
| `lift_extra_wait_m` | 0 | lift edges | "I'd rather walk" without forbidding lifts |
| `door_penalty_m` | 0 | each space→door edge with `kind == "door"` (leaf) | crutches, blind: fewer heavy doors |
| `hall_crossing_penalty_m` | 0 | entering a `type: hall` space | blind (no walls to follow), forklift *negative* = prefer halls |
| `noisy_penalty_m` | 0 | entering a space whose `room_type` ∈ `NOISY` | sensory-sensitive |
| `space_change_penalty_m` | 0 | each space traversed (proxy for turns / decision points) | blind, first-day: simpler routes |

`NOISY = {lobby, canteen, production_zone, assembly_zone, additive_zone, warehouse_zone, logistics_zone, shop}`
— a heuristic from `room_type`, stated as such to the user.

Penalties go on the edge **into** the space (space ↔ door edges), never on start/destination, so they don't
change trivially-forced segments. Negative penalties allowed only where `cost` stays ≥ 0.

## Profiles per persona

| Profile | Personas | step_free | min_door_width_m | avoid_lifts | avoid_stairs | soft penalties |
|---|---|---|---|---|---|---|
| `default` | everyone, benchmark | – | – | – | – | none |
| `wheelchair` | [P01](personas.md#p01--wheelchair-user) | ✔ | 0.8 (assumed) | – | ✔ | – |
| `trolley(w)` | [P08](personas.md#p08--hospital-bed--trolley-mover), [P15](personas.md#p15--parent-with-pram) | ✔ | w (user-given; pram 0.8) | – | ✔ | – |
| `forklift(w)` | [P05](personas.md#p05--forklift-driver) | ✔ | w (default 1.6) | ✔ (no vehicles in lifts) | ✔ | hall −, office-type rooms avoided via `avoid_room_types` |
| `no_lifts` | [P07](personas.md#p07--claustrophobic--wont-take-lifts) | – | – | ✔ | – | – |
| `low_stamina` | [P12](personas.md#p12--elderly-visitor-limited-stamina) | – | – | – | – | stairs 20 m/floor |
| `crutches` | [P14](personas.md#p14--temporary-injury-on-crutches) | ✔ | – | – | ✔ | door 3 m |
| `quiet` | [P09](personas.md#p09--autistic--sensory-sensitive) | – | – | – | – | noisy 40 m, hall 10 m |
| `low_vision` | [P10](personas.md#p10--blind--low-vision-user) | – | – | – | – | hall 30 m, door 2 m, space change 5 m |
| `evacuation` | [P13](personas.md#p13--fire-warden--evacuation) | per person | – | ✔ (fire) | – | none; destination = nearest `"outside"` |
| `simple` | [P02](personas.md#p02--first-day-at-work), [P16](personas.md#p16--delivery-courier--visitor) | – | – | – | – | space change 3 m |

Penalty values are starting points to tune in the demo; each is metres-equivalent so it can be explained:
"I took a route 12 m longer to avoid the canteen."

Profiles **compose**: wheelchair + quiet = union of filters, max of penalties. Composition is explicit in the
reply ("step-free, quiet route").

## Inferring, confirming, remembering

1. **Infer** from cue words via an LLM tool call `set_profile(profile, params)` with a strict schema — e.g.
   wheelchair, rollator, pram, crutches, "no stairs", "no lifts", "claustrophobic", trolley/pallet/bed + width,
   forklift, "quiet", "I can't see", "fire".
2. **Confirm once**, inside the first answer rather than as a separate question:
   "Understood: step-free, doors ≥ 0.8 m. From Lobby 0.01 to Lecture hall 2.10: …". Ask only if a required
   number is missing (trolley width).
3. **Remember** in the conversation state (`session.profile`); every later route call uses it automatically.
   The organiser rubric: *"Step-free routes and wide doors, every time, without asking twice."*
4. **Override explicitly**: "this time I'm without the trolley" → temporary override for one route.
5. **Persist** per user (optional, collaboration backend) so the profile survives reloads.
6. **Never silently relax a hard filter.** If unreachable, say why and offer the relaxed alternative as a
   separate, labelled option.

## "What changes?" — closure diffs

REACT questions ("The east lift is closed. What changes?") are answered by diffing deterministic results:

1. Snapshot current state S₀ (closures, profile). Apply the change → S₁.
2. For the **user's active route** (if any): recompute; report old vs new length, new steps, or "no longer
   reachable" with the blocking element.
3. **Building-wide impact** (facility manager): for each room, reachability + distance to nearest entrance
   (or from a reference point) under S₀ vs S₁, for `default` and `wheelchair` profiles. Report counts and the
   top affected rooms: "With Lift 2 closed, 14 rooms on floors 3–4 are no longer step-free reachable; 22 rooms
   get 30 m+ longer walks."
4. Same machinery answers `what_if_door` (S₁ = added door) and `step_free_reachable_count` (closure +
   step-free) — see [solver-plan.md](../architecture/solver-plan.md#what_if_door).

All diffs are deterministic; the LLM only summarises the structured diff.

## Sketch (not production code)

```python
@dataclass(frozen=True)
class RoutingProfile:
    name: str = "default"
    # hard filters
    step_free: bool = False
    min_door_width_m: float | None = None
    avoid_lifts: bool = False
    avoid_stairs: bool = False
    avoid_room_types: frozenset[str] = frozenset()
    avoid_space_ids: frozenset[str] = frozenset()
    max_floor_changes: int | None = None
    # soft penalties, metres-equivalent (all 0 → exact benchmark model)
    stairs_penalty_per_floor_m: float = 0.0
    lift_extra_wait_m: float = 0.0
    door_penalty_m: float = 0.0
    hall_crossing_penalty_m: float = 0.0
    noisy_penalty_m: float = 0.0
    space_change_penalty_m: float = 0.0

    def compose(self, other: "RoutingProfile") -> "RoutingProfile": ...  # OR filters, max penalties

DEFAULT = RoutingProfile()
```

Mapping onto `BuildingMap.graph(step_free)` (`core/building_map.py:179-212`):

- Signature becomes `graph(profile, endpoints)`; `step_free=profile.step_free` keeps today's behaviour.
- In the opening loop: also `continue` if `width_m < min_door_width_m`; add `cost = weight + door/space
  penalties` on the space↔door edge into a penalised space (skip if the space ∈ endpoints).
- In the connector loop: skip by `kind` for `avoid_lifts`/`avoid_stairs`; `cost = weight + stairs_penalty × span`
  or `+ lift_extra_wait_m`.
- Node filter: drop `avoid_room_types` / `avoid_space_ids` (except endpoints) alongside `closed`.
- `route()` runs Dijkstra on `"cost"`, then sums `"weight"` along the chosen path for `length_m`.
- Regression test: `graph(DEFAULT)` routes == current routes on all dev warm-up questions (120/120 exact today).

## Dataset reality check

From a scan of all 280 buildings (all splits) with `core/building_map.py`, counting spaces with `type == "room"`
reachable from `"outside"` (2026-10-24):

| Fact | Number | Implication |
|---|---|---|
| Multi-floor buildings | 174 / 280 | floor changes matter in most buildings |
| Buildings with a lift | 97 | **77 multi-floor buildings have no lift** → upper floors unreachable step-free |
| Openings with `step_free: false` | 30 / 23,748 (0.1%) — all of them entrances | step-free limits come from stairs-only cores, not doors |
| Openings < 0.8 m / < 0.9 m / < 1.1 m | 3,208 / 7,256 / 17,688 (median 0.9 m) | width filters are the strongest constraint |
| Rooms reachable from outside: any profile | 16,223 | – |
| … without lifts (`no_lifts`) | 16,150 | stairs almost always exist; P07 is rarely blocked |
| … step-free | 11,193 (69%) | wheelchair blocked for 31% of rooms → explain the blocker |
| … step-free + doors ≥ 0.9 m | 8,342 (51%) | 0.8 vs 0.9 m threshold choice matters a lot |
| … step-free + doors ≥ 1.1 m | 2,025 (12%) | trolley/bed deliveries are mostly impossible → name the narrow door |
| Noisy-type spaces | lobby 94, production 78, warehouse 78, logistics 69, assembly 48, canteen 35, additive 18 | quiet profile only meaningful in procedural/OSM buildings |
| Halls (`type: hall`) | 385 | hall penalties matter for factories/campus |

Not in the data (say so honestly): crowding, live noise, lift cabin sizes, emergency exits/refuge areas,
aisles inside halls, door opening direction or automatic doors.

## Related

- [personas.md](personas.md) · [route-model.md](../kit/route-model.md) ·
  [solver-plan.md](../architecture/solver-plan.md) · [overview.md](../architecture/overview.md)
