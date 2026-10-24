---
id: research-question-parsing
summary: Evidence for Q-008. Benchmark questions use one fixed template per kind; a regex parser plus a building-aware resolver matches 655/655 train+dev inputs and parses 145/145 test questions. Recommendation is regex first with an LLM fallback that reuses the same resolver.
sources:
  - core/question_parser.py
  - tests/test_question_parser.py
  - "data/{train,dev}/*/questions.jsonl, data/test/questions.csv (scan, 2026-10-24)"
  - benchmark/evaluate.py (PRICE_PER_MILLION, used for the cost estimate)
related: [../kit/questions.md, ../challenge/scoring.md, ../architecture/overview.md, ../architecture/solver-plan.md]
---

# Question parsing (evidence for Q-008)

[Docs index](../README.md) · Open questions: [Q-008](../../memory-bank/open-questions.md#q-008) (parser strategy),
[Q-006](../../memory-bank/open-questions.md#q-006) (name resolution) · Kinds: [questions.md](../kit/questions.md)

## Result in one paragraph

Each benchmark kind uses exactly **one sentence template** (`room_stacked` has two: above and below). This holds
across train, dev and test, and test uses no template that train/dev lack. A regex per template plus a resolver
that checks names against the building reproduces the gold `inputs` for **655/655** train+dev questions and
resolves **145/145** test questions, at zero API cost, in about 0.6 s for all 800. The only hard cases are 7
train/dev questions whose text is **genuinely ambiguous**: an OSM name repeats on the same floor. No parser can
resolve those, LLM or not, so the parser returns every candidate.

Run it: `uv run pytest tests/test_question_parser.py -q -s` (prints the tables below).

## Templates

Slots: `{space}` = `<space name> (<floor name>)`, `{floor}` = `the ground floor | the floor N | the basement N`,
`{room_type}` / `{asset_type}` = the type with spaces instead of underscores. Every question ends with
`Finish with a line '<instruction>'.`

| Kind | Template (body) | Answer instruction | train / dev / test |
|---|---|---|---|
| `largest_room` | Which is the largest {room_type} on {floor}, and how big is it in m²? | `Answer: <room name or number>, <area> m²` | 76 / 20 / 21 |
| `floor_area_total` | Facilities want the total floor area of every {room_type} on {floor} added together. How many square metres is that? | `Answer: <number>` | 150 / 31 / 33 |
| `errand` | I'm in {space}. I need to grab a(n) {asset_type} from the room that has one closest to me, then carry it to the largest {room_type} on {floor}. {carry}. How far will I walk in total, in metres? | `Answer: <number>` | 74 / 19 / 20 |
| `shared_walls_count` | We're soundproofing {space}. How many other rooms on that floor share a wall with it? Count every room whose wall runs along it for at least 1 m, … corridors, stairwells and lifts don't count. | `Answer: <number>` | 119 / 24 / 26 |
| `wide_delivery_count` | I'm moving a {w} m wide {item}. It can't go on stairs or steps (lifts are fine), and every door it passes through must be at least {min_width} m wide. It arrives through the entrance into {space}. Into how many rooms on {floor} can it be delivered? | `Answer: <number>` | 61 / 19 / 18 |
| `straight_line_3d` | We're planning a wireless sensor link between {space} and {space}. What is the straight-line distance … | `Answer: <number>` | 17 / 13 / 15 |
| `room_stacked` (above) | There's water dripping from the ceiling in {space}. Which room is directly above it? | `Answer: <room name or number>` | 10 / 2 / 6 |
| `room_stacked` (below) | A washing machine is leaking onto the floor of {space}. Which room directly below it will the water reach? | `Answer: <room name or number>` | 7 / 7 / 3 |
| `step_free_reachable_count` | {connector} is out of service. A wheelchair user comes in through the entrance into {space}. How many rooms on {floor} can they still reach? | `Answer: <number>` | 1 / 1 / 0 |
| `what_if_door` | What if we add a door between {space} and {space}, in the middle of the wall they share? How many rooms on {floor} would then have a shorter walk out of the building, to their nearest entrance, by more than 1 m? | `Answer: <number>` | 2 / 2 / 3 |

### Slot values seen

| Slot | Values in train/dev | New in test |
|---|---|---|
| errand `{carry}` | only "I can carry it on the stairs" | none. The parser still sets `step_free` from this phrase in case Sunday varies it. |
| wide_delivery `{item}` | cleaning machine, hospital bed, pallet of equipment, trolley | none. The item is descriptive only; `min_width` carries the constraint. |
| wide_delivery `{min_width}` | 1.0, 1.1 (always equal to the item width) | none |
| step_free `{connector}` | Lift 1, Lift 2 | kind absent from test |
| `{room_type}` | 14 types, incl. generic room, warehouse zone | **production zone** |
| `{asset_type}` | 27+ types | **chemical cabinet, drill press, server rack** |

The test-only values resolve without changes: type phrases are matched against the building's own
`room_type` / asset `type` vocabulary, not against a hard-coded list.

## How the resolver works (`core/question_parser.py`)

1. Strip the answer instruction and try each template regex (`TEMPLATES`).
2. Floor phrase → the floor whose `name` matches after normalisation ("the floor 1" → `Floor 1`, "the basement 1"
   → `Basement 1`). Basement ids look like `…-F-1`.
3. `{space}` → spaces **on that floor** whose `name` matches exactly, then case-insensitively, then by `ref`.
   Swiss names such as `Bedroom 2.10 (apartment 8) (Floor 2)` work because the regex takes the **last**
   parenthesised group as the floor and is non-greedy on the name.
4. Type phrase → the vocabulary with underscores (`meeting room` → `meeting_room`); plural `-s` / `-es` is tolerated.
5. `what_if_door.door_floor_id` = floor of the first space; `room_stacked.direction` comes from which template matched.
6. Output: `ParsedQuestion(kind, params, notes, alternatives)`. `params` uses the same keys as `inputs`.
   `alternatives` lists every candidate when a name repeats.

## Accuracy

| Kind | train+dev params == `inputs` | ambiguous text | test parses + resolves |
|---|---|---|---|
| errand | 93 / 93 | 1 | 20 / 20 |
| floor_area_total | 181 / 181 | 0 | 33 / 33 |
| largest_room | 96 / 96 | 0 | 21 / 21 |
| room_stacked | 26 / 26 | 2 | 9 / 9 |
| shared_walls_count | 143 / 143 | 2 | 26 / 26 |
| step_free_reachable_count | 2 / 2 | 0 | – |
| straight_line_3d | 30 / 30 | 2 | 15 / 15 |
| what_if_door | 4 / 4 | 0 | 3 / 3 |
| wide_delivery_count | 80 / 80 | 0 | 18 / 18 |
| **all** | **655 / 655** | **7** | **145 / 145** (0 ambiguous) |

Ambiguous questions count as correct when the gold space is among `alternatives`.

## Failure analysis: the 7 ambiguous questions

All are OSM buildings where several spaces on one floor share a `name`:

| Question | Text names | Candidates on that floor | Notes |
|---|---|---|---|
| osm-way37850565-H02, -H03 | "Büro (Ground floor)" | 3 offices, refs 0.10 / 0.11 / 0.12 | **Identical text, different gold** (S011 vs S010), so no approach can be certain |
| osm-way37850565-H04 | "Büro (Floor 1)" | 9 offices | the room's ref would settle it, but the text gives only the name |
| osm-way52060470-H06 | "Genusswerk (Floor 1)" | 2 canteens (50 m² and 191 m²) | different rooms |
| osm-way58216509-H04, -H05, -H06 | "Generic room N2135 / N2148A / N2197D" | 2 each, same ref, near-identical area | look like duplicated OSM polygons, so the answer is probably the same for both |

Handling (proposed):
- **Benchmark:** the solver runs on every candidate. If all answers agree, answer. If not, answer for the first
  candidate (lowest id); there is no better signal in the text. The test set has **0** such questions, so this
  only matters for a Sunday building with duplicate names.
- **Conversation:** this is the "ask only what it needs" case from the Interaction rubric. List the candidates
  with ref and size ("There are three offices called Büro on the ground floor: 0.10, 0.11, 0.12. Which one?").

## Recommendation for Q-008

**Regex templates first, LLM fallback second, one shared resolver.**

1. **Primary: `parse_question`.** 100% on all labelled data, deterministic, free, fast. Guards the 55-point
   benchmark ([D-003](../../memory-bank/decisions.md#d-003)).
2. **Fallback: Claude with a strict tool schema** that runs only when no template matches (rephrased Sunday
   questions, or free chat). The LLM returns the `kind` and the **surface strings** of each slot
   (`{"kind": "errand", "start": {"name": "Bedroom 2.10 (apartment 8)", "floor": "Floor 2"}, "asset_type": "desk", …}`),
   **not ids**. The same `Resolver` methods (`space_ids`, `floor_id`, `room_type`, `asset_type`, `connector_id`)
   then turn them into ids. Resolution errors go back to the LLM as tool errors so it can retry. The LLM never
   sees or invents ids, so a hallucinated room fails loudly instead of answering wrongly.
3. **Don't send the kind label to the parser as truth.** Test files include `kind`, but the Sunday input may
   not (PDF: "id, text, optional constraints"). Use it only as a cross-check.

Why not LLM-only: it costs money and latency on every question and adds non-determinism. It also gains nothing
on the current data, because the regex already reaches 100% and the remaining errors are ambiguous text that an
LLM cannot resolve either.

### LLM fallback cost estimate

Per fallback call: about 1,000 input tokens (instructions + tool schema + the building's floor names and type
vocabulary; space names are not needed because the resolver checks them) and about 150 output tokens. With the
Opus prices in `benchmark/evaluate.py` ($4 / M input, $20 / M output):
1,000 × 4/1M + 150 × 20/1M ≈ **$0.007 per question**, under $1.10 even if all 145 test questions fell back.
A Sonnet- or Haiku-class model would be cheaper (prices UNVERIFIED). This is negligible against the $150 credit
budget ([Q-012](../../memory-bank/open-questions.md#q-012)).

## Risks

- **Sunday paraphrasing:** the templates are exact, so any rewording sends the question to the LLM fallback.
  Keep the fallback tested, for example with a few hand-paraphrased dev questions.
- **New kinds on Sunday:** the regex can't cover them; the LLM can only map them onto kinds we have solvers for.
- **Name normalisation:** exact matching relies on the question text copying `space.name` verbatim. This holds
  in all 800 questions, but unicode such as "Büro" must stay NFC. Add `unicodedata.normalize` if a mismatch shows up.

## Related

- [questions.md](../kit/questions.md): definitions behind each kind
- [solver-plan.md](../architecture/solver-plan.md): what consumes `ParsedQuestion.params`
- [scoring.md](../challenge/scoring.md): how the final `Answer:` line is scored
