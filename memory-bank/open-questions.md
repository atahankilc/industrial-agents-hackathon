---
id: open-questions
summary: Unknowns (Q-###) with owner, how to resolve, and links. Resolved items keep their answer.
related: [decisions.md, project-state.md, ../docs/kit/questions.md]
---

# Open questions

[Memory bank](README.md) · Next free id: **Q-020**

Template:

```markdown
<a id="q-000"></a>
### Q-000 — Question
- **Status:** open | resolved (YYYY-MM-DD) · **Priority:** high | med | low · **Resolve by:** ask organisers | experiment | team decision
- **Context:** why it matters, links to docs
- **How to resolve:** concrete step
- **Answer:** (when resolved) + evidence + resulting D-### if any
```

## Open

<a id="q-001"></a>
### Q-001 — What is the exact Sunday benchmark input/output format?
- **Status:** open · **Priority:** high · **Resolve by:** ask organisers
- **Context:** PDF says `questions.json` in, `answers.json` out with item/room id, **route as ordered node ids**,
  route length. README says CSV `question_id,answer` (full replies) for test; Sunday format "announced with the
  release". No schema/example answer file exists in `data/`. See
  [scoring.md](../docs/challenge/scoring.md#-conflict-pdf-vs-readme).
- **How to resolve:** ask organisers; meanwhile make solvers return structured results (ids, node path, length)
  *and* prose.
- **Progress (2026-10-24):** both runners exist ([BENCHMARK.md](../SUBMISSION/BENCHMARK.md)): canonical
  `agent.run_benchmark` writes answers.json per id (`kind`, `params`, `answer`, `unit`, `area_m2`, `evidence` with
  route node/element paths, `reply`, `error`); v1 `agent.run_benchmark_v1` .json has reply, `Answer:` text, kind,
  resolved ids, solver result and `route`. Missing: the announced Sunday format itself.
- **Progress (2026-10-25):** organisers announced the graded folder `SUBMISSION/` with exactly `BENCHMARK.md` +
  `answers.json`. We submit v1 (`agent.run_benchmark_v1`, .json): the canonical runner has no solvers for the
  warm-up kinds (all 1,338 train+dev route questions → `No solver for question kind`). Content format of
  `answers.json` still unannounced.
- **Progress (2026-10-24, upstream README §3–4):** the graph's nodes are spaces (anchor =
  `representative_point()`), openings and one `"outside"` node. Warm-up route answers give the path as
  `space_path` (space ids + `"outside"`) and `element_path` (the `via` of every edge walked: an opening id twice per
  door, a connector id once per floor segment). `core.building_map` reproduces length, `space_path` and
  `element_path` exactly on all 1,457 train+dev warm-up route/tour legs. **Working assumption until answered:**
  Sunday routes use this warm-up format, one leg per stop-to-stop segment (as in `tour` answers).
- **Progress (2026-10-24, organisers' Discord note on route scoring):** a route answer is "the ordered list of
  spaces you pass through" (i.e. a space path); they check each step crosses a real door / opening / stair / lift
  and that the question's rules hold, then re-measure it with **their** distance model — our own length numbers
  do not affect the score. Score = best length ÷ our length; within 1% of best = full marks; invalid route = 0.
  If no route exists under the rules, the correct answer is to say so. Their distance model differs from the
  warm-up one → [Q-014](#q-014); new factory rules → [Q-015](#q-015). Full note:
  [route-model.md](../docs/kit/route-model.md#sunday-scoring-model-organisers-note-2026-10-24).
- **Still unknown:** (1) exact JSON key for the space path, whether `element_path` is still wanted, and whether
  `"outside"` appears in it; (2) whether Sunday questions are benchmark kinds, warm-up kinds (route, tour,
  locate…) or both; (3) multi-stop (errand, tour): one combined path or per-leg; (4) ~~route length
  tolerance~~ answered above; (5) is there an example `answers.json`; (6) where a route starts when the start is
  an item (its room, as for destinations?).
- **Message to send the organisers** (not sent yet; Utku will ask):
  > Hi! Question about the Sunday benchmark output for Track 01. The README says the format will be announced
  > with the release, and the PDF mentions an `answers.json` with the located item/room id, the route as an
  > ordered list of node ids, and the route length. Could you clarify:
  > 1. Should routes use the same fields as the warm-up answers in `questions_basic.jsonl` (`space_path` with
  >    space ids + `"outside"`, and `element_path` with opening/connector ids), or a different node-id list?
  > 2. Will the Sunday questions be like `questions.jsonl` (errand, largest_room, …), like
  >    `questions_basic.jsonl` (route, tour, locate, …), or both?
  > 3. For multi-stop questions (errand, tour): one combined path, or one path per leg as in the `tour` answers?
  > 4. Is there an example `answers.json` (the PDF says it would be in the data folder)?
  > Thanks!

<a id="q-014"></a>
### Q-014 — Sunday route scoring uses a different distance rule than the kit route model
- **Status:** partly answered by kit 1.1.0, model ported ([D-014](decisions.md#d-014)) · **Priority:** med ·
  **Resolve by:** ask organisers (3), (4)
- **Source:** organiser message on Discord, pasted by Atahan 2026-10-24 (summary, not verbatim):
  - Distance is measured inside each space **from door to door, ~15 cm off the walls, around corners** (never
    through walls). Furniture/machines are not obstacles. A route to an item ends in the room/bay that holds it.
  - **Stairs = 2 m per metre climbed; lift = 15 m + 1 m per metre of height.**
  - Without stairs: lifts, ramps, doors only. **Forklift: forklift aisles and openings ≥ 3 m only; pedestrian
    walkways don't count.** Closed areas avoided. **Factory production bays are destinations only — never driven
    through as a shortcut.** No route under the rules → the correct answer is to say so.
  - Scoring: the answer is the **ordered list of spaces**; each step must go through a real door/opening/stair/
    lift and obey the rules (else **score 0**); the route is re-measured with their rule; score = best length ÷
    our length, within 1 % = full marks. Our own distance numbers don't matter.
- **Gap vs our code** (`core/building_map.py`, [route-model.md](../docs/kit/route-model.md)): we use the kit model
  (anchor `representative_point` → door straight lines; stairs 12 m/floor; lift 15 + 6 m/floor). Floor heights in
  the data are 3.0–8.0 m, so stair/lift costs change per building and the stairs-vs-lift choice can flip (3 floors
  of 3 m: kit picks the lift 33 vs 36 m; new rule picks stairs 18 vs 24 m). We have **no production-bay rule**
  (factory halls `production_zone` 78, also assembly/logistics/warehouse/additive zones — routing through them would
  score 0), **no forklift profile** (1,065 openings ≥ 3 m; no aisle/walkway spaces in our data → Sunday likely adds
  them), and our `space_path` can pass through `outside` between two entrances (probably invalid under their check).
- **Ask organisers:** (1) does the new rule also replace the kit model for numeric distances (`errand` total walking
  distance, warm-up `length_m`) or only for Sunday route questions? (2) where does a route start/end inside the first
  and last space (door or centre)? (3) space ids or names in the list; may it contain "outside"? (4) how are forklift
  aisles, pedestrian walkways and production bays marked (type/room_type/name/new field)? (5) "metre climbed" = the
  `elevation_m` difference between floors?
- **Plan (no API cost, stays in `core/` + `agent/`):** (a) a second route model selectable per question:
  door-to-door geodesic inside each space polygon shrunk by 0.15 m (visibility graph over the polygon's reflex
  vertices), height-based stair/lift costs; keep the kit model as default until (1) is answered; (b) measure how often
  the two models pick different space sequences on train/dev warm-up routes; (c) rules: production bays = destination
  only, forklift profile (≥ 3 m, exclude walkway-like spaces), no route through `outside`; (d) benchmark "no route"
  answer wording checked.
- **Progress (2026-10-24):** (a)–(c) implemented — `core/geodesic.py`, `core/route_models.py` (`model="kit" |
  "geodesic"`, `RouteRules`, `sequence_length` re-measures a space list), wired into `core/navigation.py`,
  `core/basic_parser.run_parsed` and the Guide tools (rules always on there, `forklift` preset). Kit stays the
  default. Measured on 1,457 train/dev warm-up legs ([route-model.md](../docs/kit/route-model.md#sunday-route-model-and-route-rules-q-014)):
  sequences differ in 115 (7.9 %); kit answers score 0.930 mean / 88.8 % full marks (0.984 / 93.1 % with the
  rules), geodesic 1.000. **New finding for question (3):** 127 legs have no route once `outside` is banned (Swiss
  Dwellings stair blocks joined only via the street). Still open: the 5 organiser questions (sent to Atahan), the
  benchmark "no route" answer wording once the Sunday format is known (Q-001), lifts for forklifts.
  Factory schema (aisles, walkways, bays): [Q-015](#q-015).
- **Kit 1.1.0 (2026-10-24, organisers' patch "fixed answers that conform with the ruleset"):** answers questions
  (1), (2), (5) — see `archive/initial-repo/CHANGELOG.md` and README §3. (1) **Yes**: all train/dev expected answers
  (warm-up routes/tours, `errand`, `what_if_door`) and the hidden test answers were recomputed with the new rule;
  the kit model is obsolete. (2) A space's node is its `representative_point()`; it and every opening are joined by
  the 15 cm-off-wall shortest walk; an opening "lands" 30 cm inside each space (nearest point of
  `polygon.buffer(-0.30)`) and the opening→landing step is added; lengths rounded to 3 decimals. (5) Yes, the
  `elevation_m` difference; lift 15 m once per ride, every pair of lift stops joined; stairs floor to floor.
  Outside: no outdoor link at all — such routes are `reachable: false` (tours: `{"stops", "reachable": false}`).
  The README states **no production-bay rule** for the graded answers. Reference implementation:
  `archive/initial-repo/starter_agent/building_map.py` (1.1.0). Our `geodesic` model on dev warm-up routes (gold
  ids, `no_outside`): reachability 189/189 right, length within 1 m 158/161 but exact (≤ 2 cm) only 3 — systematically
  0.3–1.5 m short (missing door landings). Still open: (3), (4), lifts for forklifts.

<a id="q-002"></a>
### Q-002 — When is code freeze and when is the Sunday building released?
- **Status:** open · **Priority:** high · **Resolve by:** ask organisers
- **Context:** PDF says "TODO: exact time". Drives the whole plan in [project-state.md](project-state.md).
- **Owner:** Atahan will provide the times — don't chase this.



<a id="q-005"></a>
### Q-005 — Exact semantics of `what_if_door` (and `step_free_reachable_count`)
- **Status:** open · **Priority:** med · **Resolve by:** experiment (only 4 / 2 labelled examples)
- **Progress (2026-10-24):** what_if_door 4/4 and step_free_reachable_count 2/2 with the rules in
  [solver-plan.md](../docs/architecture/solver-plan.md#what_if_door) (full graph, `type == room`, > 1 m, longest
  shared stretch midpoint; robustness sweep over 1044 pairs). Stays open only because labelled examples are few
  and the closure never changes the count in the 2 step-free examples.
- **Context:** New door width/step-free? "Middle of the shared wall" when the shared boundary is multiple
  segments? Which rooms on the target floor are counted; is improvement measured strictly > 1 m? Unreachable
  rooms? See [solver-plan.md](../docs/architecture/solver-plan.md#what_if_door).
- **Progress (2026-10-24):** 0.9 m step-free door at the midpoint of the longest shared-boundary piece, rooms with
  `type == room`, gain strictly > 1 m → 4/4 `what_if_door`; step-free BFS with the connector closed → 2/2. Too few
  labels to rule out alternatives; stays open.

<a id="q-006"></a>
### Q-006 — How to resolve names in question text to space ids robustly
- **Status:** open · **Priority:** high · **Resolve by:** experiment
- **Context:** Questions use `"<name> (<floor name>)"`, e.g. "Büro (Ground floor)", "Bedroom 2.10 (apartment 8)
  (Floor 2)". OSM names repeat ("WC"). Train/dev `inputs` give the gold mapping to test a resolver.
- **Progress (2026-10-24):** resolver in `core/question_parser.py` handles all train/dev/test; 7 train/dev
  questions are inherently ambiguous (same OSM name twice on one floor, e.g. "Büro (Ground floor)") — returns all
  candidates. Solver policy implemented in `agent/benchmark_agent.py`: run every candidate, keep the answer when they
  agree, else first candidate (sorted id). Costs 2 train questions (osm-way37850565-H02/H03 are identical text
  with different gold answers, H04) — irreducible without more context. See
  [question-parsing.md](../docs/research/question-parsing.md).

<a id="q-008"></a>
### Q-008 — Benchmark question parsing: templates/regex vs LLM extraction vs hybrid
- **Status:** open · **Priority:** high · **Resolve by:** team decision + experiment
- **Context:** [ai-agents.md](../docs/architecture/ai-agents.md#benchmark-pipeline).
  Sunday wording may differ; `kind` may not be provided.
- **Evidence (2026-10-24):** one template per kind (two for room_stacked); regex parser 655/655 on train+dev,
  145/145 on test → [D-007](decisions.md#d-007) accepted 2026-10-24 (configurable modes).
- **Live paraphrase check (2026-10-24):** 31 reworded dev questions, all 9 kinds: regex 0/31, llm 31/31,
  hybrid 31/31 ([question-parsing.md](../docs/research/question-parsing.md#risks)). Hybrid stays the default;
  open only for kinds that don't exist yet (new Sunday kinds can only map onto our solvers).

<a id="q-010"></a>
### Q-010 — Which Level 5 add-in do we pick?
- **Status:** open · **Priority:** low (decide after Phase 2) · **Resolve by:** team decision
- **Context:** "Pick one and do it well." Options in [brief.md](../docs/challenge/brief.md#levels).

<a id="q-012"></a>
### Q-012 — Model choice and API budget
- **Status:** open · **Priority:** med · **Resolve by:** experiment
- **Context:** Starter uses `claude-opus-5-5` at medium effort, ~$0.10–0.25/question. With deterministic
  solvers the LLM only parses/phrases — Sonnet/Haiku may suffice.
- **Known budget (2026-10-24):** **$150 Claude API credits** from the organisers, usable for the product agent and
  for agentic dev work. One full test run with the starter-style Opus agent ≈ 145 × $0.10–0.25 ≈ $15–36; with
  deterministic solvers + template parser the LLM cost of a benchmark run should be near $0. Track spend in
  [log.md](log.md).
- **Guide (2026-10-24):** `agent/guide.py` defaults to `claude-opus-5-5` at effort `medium`; switch with
  `GUIDE_MODEL` / `GUIDE_EFFORT` (e.g. `claude-sonnet-5-5`, `low` for voice latency). `guide.usage` counts tokens
  incl. cache reads.
- **Live evidence (2026-10-24, `scripts/live_guide.py`, 7 tricky-user turns):** Opus 5.5 medium ~5.9–7.3 s/turn
  (7.3 pre-fix, 5.9 post-fix), $0.13–0.16; Opus 5.5 low ~6.8 s/turn (one pre-fix run), $0.12; Sonnet 5.5 low
  ~3.3–3.9 s/turn (3.3 pre-fix, 3.9 post-fix), $0.06 — all correct, 0 ungrounded. Proposal:
  Opus 5.5 medium for text chat, Sonnet 5.5 low for voice (latency). Needs Atahan's call; default unchanged.

<a id="q-013"></a>
### Q-013 — May we redistribute the kit's code (scorer, starter agent) in our public repo?
- **Status:** open · **Priority:** med · **Resolve by:** ask organisers
- **Context:** Upstream repo publishes no licence; data licences are explicit, code's are not. We include it
  unmodified for reproducibility and say so in `NOTICE.md` ([D-009](decisions.md#d-009)). Fallback if they say
  no: delete `archive/initial-repo/starter_agent`, keep `benchmark/` out of git and fetch it from upstream in CI.

<a id="q-015"></a>
### Q-015 — Factory buildings: forklift aisles, pedestrian walkways, production bays — what is the schema?
- **Status:** open · **Priority:** high · **Resolve by:** ask organisers / wait for Sunday building
- **Context:** Organisers' note (2026-10-24): *forklift* routes use forklift aisles and openings **≥ 3 m wide**
  only (pedestrian walkways don't count); *production bays* are destinations — you may drive into one but not
  through one; a route to a machine/item ends in the room or bay that holds it. Current `data/` has no space
  `type`/`room_type` for aisles, walkways or bays (`forklift` / `forklift_charging_station` exist only as
  equipment types; `production_zone` is a `room_type`) — so the Sunday building likely uses a schema we have not
  seen. Also: "without stairs" = lifts, ramps and doors only (matches our step-free filter).
- **Finding (2026-10-24):** with `bays_destination_only` (production + assembly + logistics + warehouse + additive
  zones) and `no_outside`, **26/26** factory buildings (train/dev/test) cut the office wing off from the hall: the
  only way in is through a first-row zone (`Hall access → Assembly zone`) or outside. E.g. proc-factory-dev-004:
  Locker room 0.30 → Production zone H-A2 has no route (61.56 m via Assembly zone H-A1 without rules). Counting only
  `production_zone` as a bay still leaves 706 spaces cut off. The rule text we have is our own summary of the
  Discord note ("you may drive into one to deliver, not through one as a shortcut"), not the PDF or kit README; the
  extra zone types and applying it to pedestrians are our reading. Ask for the original wording.
- **How to resolve:** ask which fields mark aisles / walkways / bays (and whether `production_zone` is a bay);
  meanwhile make the router take a rule set (allowed space predicate, min opening width, no-pass-through
  predicate) so it can be wired to new fields without code changes elsewhere.

<a id="q-017"></a>
### Q-017 — Kit 1.1.0 README dropped the "alignment" text: which judging/submission text is authoritative?
- **Status:** open · **Priority:** high · **Resolve by:** ask organisers
- **Context:** The organisers' 1.1.0 patch (commit 6a2cdec, merged as dc03c44) rewrote `README.md` from their
  older 721f1b9 text, not from cb51a6f ("Align README with challenge brief and kickoff deck"), which our archive
  held. Lost in 1.1.0: "The story", "What you build" (incl. "Directions, not instructions", "Put yourself in their
  shoes"), "Sunday benchmark" (single command, `BENCHMARK.md`), "Submission and judging process" (online
  submission, no pitch rooms). The judging row changed from **"Submission demo — demo video and technical
  explanation"** (cb51a6f, matches [brief.md](../docs/challenge/brief.md)) to **"Pitch and demo — a 3–5 minute
  live demo that works without a restart"** (1.1.0). Probably accidental (the CHANGELOG lists only the route-model
  section as a README change), but UNVERIFIED.
- **Meanwhile:** `archive/initial-repo/README.md` = 1.1.0 verbatim (route model, data, questions);
  `archive/initial-repo/README-cb51a6f.md` = the previous text, still cited for the sections 1.1.0 dropped. Prepare
  for both: a video + technical explanation, and a live demo that runs without a restart.
- **How to resolve:** ask the organisers whether the cb51a6f judging/submission text still holds.

<a id="q-019"></a>
### Q-019 — `SUBMISSION/answers.json`: which questions, which format?
- **Status:** open · **Priority:** high · **Resolve by:** organisers' Discord image / ask organisers
- **Context:** Organisers' Discord note (pasted by Atahan 2026-10-25 00:10, ~14 h before the deadline): the
  benchmark (55 points) is graded from a repo folder named exactly `SUBMISSION` with exactly two files,
  `BENCHMARK.md` and `answers.json` ("wrong file names = we can't grade your benchmark"); the reference structure
  is in an image we have not seen. The remaining 45 points come through the Hack and More form: repo link, a strictly
  2-minute demo video (YouTube/Luma), a short technical explanation. **Done (8537ca0, Utku, 2026-10-25 01:10):**
  `SUBMISSION/BENCHMARK.md` + `SUBMISSION/answers.json` from `agent.run_benchmark_v1`: a list of 145 objects
  (`question_id`, `reply`, `answer`, `kind`, `inputs`, `result`, `route`, `error`), ids = `data/test/questions.csv`,
  0 errors (checked 2026-10-25). The schema is our own, see [BENCHMARK.md](../SUBMISSION/BENCHMARK.md).
  **Since branch `4-sunday-agent` (2026-10-25):** also `parser` and the PDF's top-level ids (`item_id`, `space_id`,
  whole-route `space_path`, `element_path`, `length_m`, `reachable`); `--layout dict` keys it by question id. The 145
  replies are unchanged.
- **Unknown:** (1) does `answers.json` hold the 145 test questions, the Sunday building's questions, or both;
  (2) its schema (the image may show it; links to [Q-001](#q-001)).
- **How to resolve:** compare with the Discord image; if Sunday questions belong there, regenerate with
  `agent.run_benchmark_v1` (never hand-edited), keeping the folder to exactly those two files.

<a id="q-018"></a>
### Q-018 — Level 4 "Build": what is the input, and how is "built correctly" checked?
- **Status:** open (question drafted 2026-10-25, not sent yet) · **Priority:** med · **Resolve by:** ask organisers
- **Context:** PDF p.3 and kit README only say "Build: create or update a building from floor plans, by
  conversation" and score "buildings built correctly from plans" under Does it work (55). The kit ships
  "structured plan files plus PNG images" (PDF); the images are Matplotlib renders of `building.json` (floor 0 of
  `osm-way27917482`: polygons match to 1e-5 px at ~9.98 px/m, y flipped; per-type counts match), so they add no
  information. None of the 15 question kinds in train/dev/test is a build task, and the kit has no build test.
- **Unknown:** input (plain PNG only? PDF? `building.json` withheld?), expected output (kit-schema `building.json`;
  spaces only or also openings/connectors/assets), metric, whether it runs inside `run_benchmark`, and whether
  "update by conversation" is checked automatically.
- **Meanwhile:** with ~14 h left, Level 4 Builder is not a priority over the submission ([Q-019](#q-019)). If needed,
  the 797 `floor_*_plain.png` renders across 280 buildings (each with its `building.json`) are a ready eval set
  ([ai-agents.md](../docs/architecture/ai-agents.md#builder-level-4)).

<a id="q-016"></a>
### Q-016 — Level 3 "several buildings": what format, and how do walkways link them?
- **Status:** open · **Priority:** high · **Resolve by:** ask organisers / wait for Sunday building
- **Context:** Brief: "several floors, then several buildings; stairs, lifts, walkways between buildings"
  ([brief.md](../docs/challenge/brief.md)). Several floors work end to end (174/280 datasets multi-floor, up to 10;
  routes over stairs/lifts verified). Several buildings exist nowhere: every `building.json` holds one `building`,
  every `group_id` in `data/manifest.csv` is unique, no data names a walkway/bridge, `BuildingMap`,
  `BuildingSession`, the backend session and the UI each hold one building, and `no_outside` makes `outside` an
  endpoint only (scan 2026-10-24).
- **How to resolve:** ask whether Sunday brings one file with several buildings, several files plus links, or
  outdoor travel via `outside`; meanwhile a site layer (several `BuildingMap`s + typed links: walkway / outdoor
  path with length) is the smallest change (starter README idea, [starter-agent.md](../docs/kit/starter-agent.md)).

## Resolved

<a id="q-004"></a>
### Q-004 — Door-width rule details for `wide_delivery_count`
- **Status:** resolved (2026-10-24) · **Priority:** med · **Resolve by:** experiment
- **Context:** Do `opening` (no leaf) and entrances also need `width_m ≥ min_width`? Are lifts width-limited?
  Is `≥` or `>`? Is the arrival entrance itself checked?
- **How to resolve:** variants vs 80 train+dev answers.
- **Answer:** every opening kind (door, opening, entrance) needs `width_m >= min_width`; lifts unlimited (no width
  field); start counts if it is a room. 80/80 — [solver-plan.md](../docs/architecture/solver-plan.md#wide_delivery_count).


<a id="q-003"></a>
### Q-003 — Which spaces count as "rooms" in count/stack/wall questions?
- **Status:** resolved (2026-10-24) · **Priority:** high · **Resolve by:** experiment on train+dev answers
- **Context:** `type` ∈ room/corridor/stair/lift/hall/outdoor and `room_type` (incl. balcony, stairwell, lift,
  corridor). `shared_walls_count` says "corridors, stairwells and lifts don't count" — by `type` or `room_type`?
  Are halls/balconies rooms for `wide_delivery_count`? Affects 18%+12%+6% of test.
  See [questions.md](../docs/kit/questions.md#ambiguities-we-must-resolve-empirically-against-traindev-answers).
- **How to resolve:** implement variants, pick the one with 100% match on train+dev; record here.
- **Answer:** the room definition is per kind — shared walls: `type` ∉ {corridor, stair, lift, outdoor} (halls
  count); reachability/what-if counts: `type == "room"` (= manifest `rooms`); room_stacked: any space. Scores and
  rejected variants in [solver-plan.md](../docs/architecture/solver-plan.md#room-definition-per-kind).


<a id="q-007"></a>
### Q-007 — App/UI and voice stack
- **Status:** resolved (2026-10-24) · **Priority:** med · **Resolve by:** team decision
- **Context:** Options: Lovable-generated web app vs own React/three.js; voice via ElevenLabs (subscription).
  See [overview.md](../docs/architecture/overview.md).
- **Answer:** own Vite/React + r3f frontend and FastAPI backend in one Vercel project, Supabase, ElevenLabs Custom LLM — zero cost → [D-006](decisions.md#d-006).


<a id="q-009"></a>
### Q-009 — Where does our code live?
- **Status:** resolved (2026-10-24) · **Priority:** high · **Resolve by:** team decision
- **Context:** Option A: develop inside `initial-repo/` (scorer/evaluator imports work as-is, `--agent` module
  on path). Option B: own package at repo root, keep `initial-repo/` pristine as upstream and import from it.
  Submission repo must contain `BENCHMARK.md` + answers.

- **Answer:** build at the repo root; extract useful parts, archive the kit → [D-004](decisions.md#d-004).

<a id="q-011"></a>
### Q-011 — Commit the 209 MB dataset to git / publish the repo?
- **Status:** resolved (2026-10-24) · **Priority:** med · **Resolve by:** team decision
- **Context:** Size; OSM-derived data is ODbL (share-alike + attribution) if published. Could `.gitignore`
  `data/` and document how to fetch it from upstream.

- **Answer:** yes, commit it (upstream repo is public) → [D-005](decisions.md#d-005).
