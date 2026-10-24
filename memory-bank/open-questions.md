---
id: open-questions
summary: Unknowns (Q-###) with owner, how to resolve, and links. Resolved items keep their answer.
related: [decisions.md, project-state.md, ../docs/kit/questions.md]
---

# Open questions

[Memory bank](README.md) · Next free id: **Q-014**

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
- **Progress (2026-10-24):** `run_benchmark <building_dir> <questions> <answers>` exists
  ([BENCHMARK.md](../BENCHMARK.md)); `.json` output has reply, `Answer:` text, kind, resolved ids and solver
  result. Missing: route as ordered node ids.

<a id="q-002"></a>
### Q-002 — When is code freeze and when is the Sunday building released?
- **Status:** open · **Priority:** high · **Resolve by:** ask organisers
- **Context:** PDF says "TODO: exact time". Drives the whole plan in [project-state.md](project-state.md).
- **Owner:** Atahan will provide the times — don't chase this.

<a id="q-004"></a>
### Q-004 — Door-width rule details for `wide_delivery_count`
- **Status:** open · **Priority:** med · **Resolve by:** experiment
- **Context:** Do `opening` (no leaf) and entrances also need `width_m ≥ min_width`? Are lifts width-limited?
  Is `≥` or `>`? Is the arrival entrance itself checked?
- **How to resolve:** variants vs 80 train+dev answers.
- **Progress (2026-10-24):** applying `width_m >= min_width` to every opening kind (door, opening, entrance),
  lifts unrestricted, matches 80/80 (`core/solvers.py:reachable_rooms`). Alternatives not tested, so we do not
  know which of them the data would also accept; keep open until a failing case appears.

<a id="q-005"></a>
### Q-005 — Exact semantics of `what_if_door` (and `step_free_reachable_count`)
- **Status:** open · **Priority:** med · **Resolve by:** experiment (only 4 / 2 labelled examples)
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
  candidates. Remaining: solver policy for candidates (run all, answer if they agree). See
  [question-parsing.md](../docs/research/question-parsing.md).

<a id="q-008"></a>
### Q-008 — Benchmark question parsing: templates/regex vs LLM extraction vs hybrid
- **Status:** open · **Priority:** high · **Resolve by:** team decision + experiment
- **Context:** [ai-agents.md](../docs/architecture/ai-agents.md#benchmark-pipeline).
  Sunday wording may differ; `kind` may not be provided.
- **Evidence (2026-10-24):** one template per kind (two for room_stacked); regex parser 655/655 on train+dev,
  145/145 on test → [D-007](decisions.md#d-007) accepted 2026-10-24 (configurable modes). Remaining: live LLM
  accuracy on paraphrases (`scripts/eval_llm_parser.py --paraphrase`, needs an API key).

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

<a id="q-013"></a>
### Q-013 — May we redistribute the kit's code (scorer, starter agent) in our public repo?
- **Status:** open · **Priority:** med · **Resolve by:** ask organisers
- **Context:** Upstream repo publishes no licence; data licences are explicit, code's are not. We include it
  unmodified for reproducibility and say so in `NOTICE.md` ([D-009](decisions.md#d-009)). Fallback if they say
  no: delete `archive/initial-repo/starter_agent`, keep `benchmark/` out of git and fetch it from upstream in CI.

## Resolved

<a id="q-003"></a>
### Q-003 — Which spaces count as "rooms" in count/stack/wall questions?
- **Status:** resolved (2026-10-24) · **Priority:** high · **Resolve by:** experiment on train+dev answers
- **Context:** `type` ∈ room/corridor/stair/lift/hall/outdoor and `room_type` (incl. balcony, stairwell, lift,
  corridor). `shared_walls_count` says "corridors, stairwells and lifts don't count" — by `type` or `room_type`?
  Are halls/balconies rooms for `wide_delivery_count`? Affects 18%+12%+6% of test.
  See [questions.md](../docs/kit/questions.md#ambiguities-we-must-resolve-empirically-against-traindev-answers).
- **How to resolve:** implement variants, pick the one with 100% match on train+dev; record here.
- **Answer:** `shared_walls_count` counts spaces with `type` ∈ {room, hall} (corridor, stair, lift, outdoor
  excluded) → 143/143; `type == room` only gives 124/143, adding outdoor 90/143. Reachability counts
  (`wide_delivery_count`, `step_free_reachable_count`) and `what_if_door` count `type == room` → 80/80, 2/2, 4/4.
  Evidence: `uv run pytest tests/test_solvers.py -q -s`;
  [solver-plan.md](../docs/architecture/solver-plan.md#rules-settled-empirically-2026-10-24).

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
