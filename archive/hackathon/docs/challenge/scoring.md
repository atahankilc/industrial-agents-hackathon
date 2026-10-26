---
id: challenge-scoring
summary: Exactly how replies are scored (Answer-line parsing, tolerances per kind), submission CSV format, Sunday benchmark, and known conflicts between PDF and README.
sources:
  - benchmark/score.py
  - benchmark/evaluate.py
  - archive/initial-repo/README-cb51a6f.md §1 (Sunday benchmark; dropped from the 1.1.0 README, Q-017)
  - archive/initial-repo/README.md §6
  - "archive/hackathon/Hackathon Challenge - Talk to Your Building.pdf p.3"
related: [brief.md, ../../../../docs/kit/questions.md, ../../../../docs/architecture/solver-plan.md, ../../../../docs/guides/commands.md]
---

# Scoring and submission

[Docs index](../../../../docs/README.md) · Prev: [brief.md](brief.md) · Question kinds: [questions.md](../../../../docs/kit/questions.md)

`benchmark/score.py` **is the exact scorer the judges use** (README §6). Everything below is
derived from it; if in doubt, read the 68 lines.

## How a reply is parsed

1. Only the **last line matching** `^\W*answer\W*:\s*(.+)$` (case-insensitive, multiline) counts
   (`score.py:14`, `committed_answer`). `**Answer:** …` in Markdown is fine.
2. No `Answer:` line → **wrong**.
3. Numbers are extracted with `NUMBER_PATTERN` (`score.py:15`): integers, decimals, negatives, and
   thousands with commas (`1,234.5`). `**` is stripped first.

### Number answers (`type: "number"`)
Answer line must contain **exactly one number**, within tolerance:
`|value − expected| ≤ max(|expected| × relative_tolerance, absolute_tolerance)` (`score.py:42`).

### Space answers (`type: "space"`)
The answer line must mention one of `accept` labels (room ref or full name; word-boundary match), and that
mention must come **before** any `reject` (runner-up) label (`score.py:48`). For `largest_room` additionally
**some** number in the line must match the area within tolerance.

## Tolerances per kind

| Kind | Answer type | Correct when |
|---|---|---|
| `largest_room` | space + area | expected room named before runner-ups, area (m²) within **±5%** |
| `room_stacked` | space | expected room named before runner-ups |
| `floor_area_total` | number | exactly one number, **±5%** |
| `errand` | number | exactly one number, **±1%, at least ±1 m** |
| `straight_line_3d` | number | exactly one number, **±2%** |
| `wide_delivery_count`, `step_free_reachable_count`, `shared_walls_count`, `what_if_door` | number | exactly one number, **exact** |

Per-question tolerances are stored in each train/dev answer object (`relative_tolerance`,
`absolute_tolerance`) — trust those over this table.

## Formatting pitfalls (cost real points)

Verified by running `numbers_in` / `committed_answer` on 2026-10-24:

| Answer-line text | Numbers extracted | Note |
|---|---|---|
| `214.7 m2`, `214.7 m²`, `61.4m2` | `[214.7]` / `[61.4]` | units are safe (digits glued to letters are skipped) |
| `Office 1.02 has 5` | `[1.02, 5.0]` | ✗ room refs are numbers — never put a ref on a number-answer line |
| `2.03-B 4` | `[2.03, 4.0]` | ✗ same problem with asset names |
| `N0110 3` | `[3.0]` | OSM-style refs glued to letters are skipped |
| `between 92 and 108` | `[92.0, 108.0]` | ✗ ranges fail |
| `1,234.5` | `[1234.5]` | thousands commas OK |
| `**Answer:** 5` | committed text `** 5` → `[5.0]` | Markdown bold OK |

- Number questions: put **only** the number (optionally a unit) on the answer line.
- Ranges ("between 92 and 108") → wrong.
- `largest_room`: name the winner first; don't mention runner-ups before it on the answer line.
- Each question text ends with the exact required template, e.g. `Finish with a line 'Answer: <number>'`.

Recommended: generate the final `Answer:` line **deterministically in code**, not by the LLM →
[D-003](../../../../memory-bank/decisions.md#d-003).

## Submission format

Per README §6 (authoritative for the **test set**): **one CSV**, UTF-8, header row, ≤ 5 MB, columns
`question_id,answer`. `answer` = the agent's **full reply** (multi-line OK, standard CSV quoting).

```csv
question_id,answer
proc-campus-test-000-H01,"The largest seminar room on the ground floor is Seminar room 0.32.
Answer: Seminar room 0.32, 61.4 m²"
```

- Missing ids = wrong; unknown ids ignored; duplicate id → first row counts.
- Score = share of the **145** test questions correct; judges also see per-kind results.
- Template with all ids: `data/test/submission_template.csv`; all questions in one table:
  `data/test/questions.csv` (`question_id,building_id,kind,question`).
- Easiest path: `benchmark.evaluate … --submission-csv team_<name>.csv` → [benchmark-code/README.md](../../benchmark-code/README.md#produce-the-test-submission).

### Test-set weight by kind (145 questions)

| Kind | # | Share |
|---|---|---|
| floor_area_total | 33 | 23% |
| shared_walls_count | 26 | 18% |
| largest_room | 21 | 14% |
| errand | 20 | 14% |
| wide_delivery_count | 18 | 12% |
| straight_line_3d | 15 | 10% |
| room_stacked | 9 | 6% |
| what_if_door | 3 | 2% |

(`step_free_reachable_count` exists in train/dev but not in test — may still appear on Sunday.)

## Sunday benchmark

Shortly before code freeze the organisers release **one unseen building + a question file**.

- **Submission folder (organiser announcement, 2026-10-25):** `SUBMISSION/` with exactly two files, `BENCHMARK.md`
  and `answers.json` (exact spelling and case) — ours: [SUBMISSION/BENCHMARK.md](../../SUBMISSION/BENCHMARK.md).
- **Our run:** a single command, documented in `BENCHMARK.md` in our repo, no manual steps
  (PDF example: `run_benchmark <building_dir> <questions.json> <answers.json>`).
- We run it ourselves and submit the output; they may re-run the command to verify.
- Scored on correct answers, valid routes, and route length vs. best route.
- Release time and exact file format "will be announced with the release" (README).

## ⚠ Conflict: PDF vs README

| Topic | PDF (p.3) | README (§1, §6) |
|---|---|---|
| Sunday output | `answers.json`: per question id → located item/room id, **route as ordered node-id list**, route length (m) | format "announced with the release" |
| Test-set output | not mentioned | CSV `question_id,answer` with full replies |
| Schema / example answer file | "in the data folder (TODO)" | not present in `data/` |

Working assumption: test set = CSV (README, and the kit ships `submission_template.csv`); Sunday format is
unknown and may need structured route output (node ids). Build the core so it can emit **both** prose replies
and structured `{item_id, space_id, route_node_ids, length_m}`. Tracked as
[Q-001](../../../../memory-bank/open-questions.md#q-001).

## Related

- [questions.md](../../../../docs/kit/questions.md) — definitions behind each kind
- [solver-plan.md](../../../../docs/architecture/solver-plan.md) — how we compute each answer
- [commands.md](../../../../docs/guides/commands.md) — running the evaluator and scorer
