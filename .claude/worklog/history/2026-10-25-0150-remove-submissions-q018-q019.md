# Remove old submissions/ folder; record Level 4 and SUBMISSION questions (Q-018, Q-019)

- **Author:** Claude session with Atahan · **Date:** 2026-10-25 01:45
- **Related:** Q-018, Q-019, Q-001; organisers' Discord note on `SUBMISSION/` (pasted by Atahan)

## Summary
The graded benchmark folder is `SUBMISSION/` (already committed in 8537ca0), so the old lowercase `submissions/`
folder is removed. The memory bank records two open questions: Level 4 input/scoring (Q-018) and the scope/schema
of `SUBMISSION/answers.json` (Q-019), plus the submission checklist and a log entry.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | `submissions/team_jaRAG.csv` and `submissions/test_answers.json` deleted; `SUBMISSION/` untouched | `submissions/`, `SUBMISSION/` | `git diff --cached --stat`; `ls SUBMISSION` → `BENCHMARK.md answers.json` |
| C2 | Commands in README/commands.md that write `submissions/team_jaRAG.csv` still work: both runners create the output's parent folder | `agent/run_benchmark_v1.py:48`, `benchmark/evaluate.py:92` | read the `path.parent.mkdir(parents=True, exist_ok=True)` lines |
| C3 | Q-018 and Q-019 added with anchors; next free id = Q-020 | `memory-bank/open-questions.md` | read; `grep -n 'q-018\|q-019\|Q-020' memory-bank/open-questions.md` |
| C4 | Q-019 facts: `SUBMISSION/answers.json` is a list of 145 objects, ids equal `data/test/questions.csv`, 0 errors | `memory-bank/open-questions.md` | `uv run python -c "import json,csv;d=json.load(open('SUBMISSION/answers.json'));i={r['question_id'] for r in csv.DictReader(open('data/test/questions.csv'))};print(len(d),i=={x['question_id'] for x in d},sum(1 for x in d if x['error']))"` → `145 True 0` |
| C5 | Q-018 fact: plan images are Matplotlib renders of `building.json` (floor 0 of osm-way27917482 matches polygons; 15 question kinds, none a build task) | `memory-bank/open-questions.md` | `head -15 data/dev/osm-way27917482/floor_0.svg` (Matplotlib metadata); kinds: count `kind` over `data/*/*/questions*.jsonl` → 15 |
| C6 | Submission checklist in project-state, log entry added | `memory-bank/project-state.md`, `memory-bank/log.md` | read |
| C7 | No kit data changed (`data/` clean) | `data/` | `git status --short data/` → empty |

## Checks I ran
- `python3 scripts/check_links.py` → `OK: all links resolve in 33 files`
- answers.json check (C4) → `test 145 ids match True errors 0 empty answers 0`
- `git status --short data/` → empty (two stray editor keystrokes in `data/train/osm-way52060470/questions*.jsonl` were restored with `git checkout`; both files parse as JSON)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (submission checklist)
- [x] `memory-bank/log.md` entry added
- [x] open questions: Q-018, Q-019 added
- [ ] docs touched: none (README/commands.md still name `submissions/team_jaRAG.csv` as an output path; works since the folder is recreated)

## Known gaps / not done
- Q-019 still needs the organisers' Discord image (scope/schema of answers.json).
- Q-018 question drafted but not sent.
- No tests run: no code changed.

## Verification rounds
- Round 1: FAIL — Q-018 said "280 plain PNG ↔ building.json pairs"; fixed to "797 `floor_*_plain.png` renders across 280 buildings" (`ls data/*/*/floor_*_plain.png | wc -l` → 797, `ls data/*/*/building.json | wc -l` → 280).
- Round 2: PASS

## Verifier report (round 2)

VERDICT: PASS
TREE: 057a0486f76c23ab0fc299386fa2ab08521935df

Claims C1–C7: MET. pytest 753 passed, 2 skipped; links OK (33 files); no secrets; score.py unchanged; no hard-coding;
no significant undeclared changes (README.md:46 and commands.md:50,52 still use `submissions/` as an output path,
declared, works via C2).
