---
id: open-questions
summary: Unknowns (Q-###) with owner, how to resolve, and links. Resolved items keep their answer.
related: [decisions.md, project-state.md, ../docs/kit/questions.md]
---

# Open questions

[Memory bank](README.md) · Next free id: **Q-015**

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

<a id="q-014"></a>
### Q-014 — Sunday route scoring uses a different distance rule than the kit route model
- **Status:** open · **Priority:** HIGH · **Resolve by:** ask organisers + implement a second route model
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
