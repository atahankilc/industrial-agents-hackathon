# Directions: turns, landmarks and rounded metres in the Guide's route steps

- **Author:** Claude session (Utku) · **Date:** 2026-10-24
- **Related:** docs/architecture/ai-agents.md (directions a person can follow), interaction eval (directions 3.33)

## Summary
The Guide's `find_route`/`tour` steps were the kit's text (no turns, no landmarks, ids on the first/last line). They
now come from `core/directions.py` `guidance_steps`: turn at the door, a landmark next to each door, rounded metres,
one line per staircase/lift ride, no ids; plus `about_m`, the rounded total.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `about_m`: whole metres < 10, steps of 5 < 100, steps of 10 from 100, half up, min 1 | `core/directions.py:about_m` | `test_about_m_rounds_like_a_person` |
| C2 | `landmark`: most recognisable `LANDMARK_TYPES` asset within 4 m of the opening, in one of its spaces; never chairs/desks | `landmark`, `LANDMARK_TYPES`, `LANDMARK_RADIUS_M` | `test_landmark_is_a_recognisable_item_next_to_the_door` |
| C3 | `guidance_steps`: start line, turn phrase from the heading change at the entry door (not the room anchor), rounded metres, "(by the …)" landmark, one line per merged connector ride, arrival line, no ids; `route_legs` unchanged | `guidance_steps` | `test_guidance_steps_have_turns_landmarks_rounded_metres_and_no_ids`; `git diff core/directions.py` only appends |
| C4 | `BuildingSession.find_route` and each `tour` leg get `steps` = guidance steps and `about_m`; `tour` gets `about_m`; `length_m` unchanged; tool description mentions it | `agent/tools.py` `guide_steps`, `tool_find_route`, `tool_tour`, TOOL_DEFINITIONS | `test_tour_legs_get_guidance_steps`, `test_legs_follow_the_route_and_match_kit_steps` (kit length equal) |
| C5 | Guide prompt: use the route's steps, keep distances with their step, total as about_m, never exact length_m | `agent/guide.py` INSTRUCTIONS | read diff |
| C6 | Offline client says about_m instead of round(length_m); test expectations moved accordingly (124→120, 132→130, 27→25) | `agent/offline_llm.py`, `tests/test_guide.py`, `tests/test_speech.py` | `uv run pytest -q` |
| C7 | Memory bank: project-state + log entry with the live numbers; left/right marked UNVERIFIED on site | memory-bank/* | read; check_links |

## Checks I ran
- `uv run pytest tests/test_directions.py tests/test_speech.py -q` → `17 passed`
- `uv run pytest -q` → `315 passed, 1 skipped in 56.15s`
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files`
- Live `scripts/eval_guide.py` (Opus 5.5 medium) → `18/18 turns PASS, 83.0s, total cost ~$0.2193`
- Live `scripts/interaction_eval.py` → `AVERAGE asks_only_needed=4.67 shows_understanding=4.83 followable_directions=4.17 remembers_context=5.00  goal 5/6  errors 0  cost guide $0.27 + eval $0.29` (previous run: directions 3.33)
- Sample (dev campus 001, Main lobby → Lab 2.20): "Walk about 25 m through the door (by the bench) into Corridor 0.01." / "Turn left and walk about 15 m through the door into Staircase 2." / "Take Staircase 2 up two floors to Floor 2."

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none
- [ ] docs: not changed (ai-agents.md already promises "steps with landmarks")

## Known gaps / not done
- Left/right from plan geometry, not checked on site (UNVERIFIED).
- Step distances are straight segments and don't sum to about_m (route cost includes stairs/lift cost); judge flagged it once.
- Camera walk mode (`route_legs`, backend legs) keeps its anchor-based turns.
- Single live runs; judge variance not measured. Factory bay-rule no-route unchanged.

## Verification rounds
- Round 1: VERDICT: PASS (TREE ac0be87db88c6e9a53454e77a796634097e33d9e)

## Verification report (round 1)

VERDICT: PASS
TREE: ac0be87db88c6e9a53454e77a796634097e33d9e

| # | Status | Evidence |
|---|---|---|
| C1 | MET | about_m step 1/5/10, half up, min 1; test passes |
| C2 | MET | landmark filters LANDMARK_TYPES, opening spaces, ≤ 4 m, priority order; no chairs/desks; test passes |
| C3 | MET | guidance_steps start/turn at entry door/about_m/landmark/one ride line/arrival; core/directions.py diff append-only, route_legs unchanged |
| C4 | MET | guide_steps in find_route and each tour leg; tour about_m; length_m untouched; tool description updated; tests pass |
| C5 | MET | INSTRUCTIONS: use route steps, total as about_m, never exact length_m |
| C6 | MET | offline_llm about_m; expectations 124→120, 132→130, 27→25; 315 passed, 1 skipped |
| C7 | MET | log entry with live numbers, left/right UNVERIFIED; project-state bullet; links OK |

Standard checks: pytest 315 passed / 1 skipped; links OK under uv; no secrets; score.py unchanged; no hard-coding; benchmark answers unaffected (agent/answer.py uses solver results). Live evals not re-run (paid). Undeclared changes: none significant.
