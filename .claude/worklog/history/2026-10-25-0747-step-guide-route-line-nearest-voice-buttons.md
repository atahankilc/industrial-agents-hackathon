# Step guide faces the step, route line from the figure, nearest-place tool, calmer voice, round buttons

- **Author:** Claude Code session · **Date:** 2026-10-25
- **Related:** user reports of 2026-10-25 (see `memory-bank/log.md` entries marked "not committed")

## Summary
Several work chunks from 2026-10-25 shipped together on `dev`: the step guide turns the map to each step and the
route band animates; the building is centred on open and the "you are here" figure is placed by drag/tap; the step
card and the Guide stay in sync (`route_step`, `show_route_step`); the route line starts at the figure and skips
doors between overlapping spaces; a `find_nearest` tool; less jumpy voice; map buildings in told-apart tones; one
round-button system across the HUD, access and edit sheets.

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| S1 | step moves pass a heading (step start → end) into `Focus`; Rig turns the camera to it; route band shader draws chevrons, greys walked part, `goal` marker with next TurnIcon | `building/BuildingScreen.tsx`, `plan/PlanView.tsx`, `dev/StoryLayer.tsx`, `dev/story.ts` `StepView`, `building/tracking.ts` `toLine` | read; `npx tsc -b` |
| S2 | whole-building framing mirrors the floor rail (`frameInsets`); figure ghost over the plan, tap-to-arm placing, off-building figure with dashed line to nearest entrance | `plan/PlanView.tsx`, `building/BuildingScreen.tsx`, `building/hud.css` | read |
| S3 | `/chat` and `/chat/stream` accept `route_step`; Guide gets a `[route note]`; `show_route_step` tool emits a `route_step` event; `find_nearest` tool ranks candidates by route length and emits one route | `backend/app.py`, `agent/guide.py` `route_note`, `agent/tools.py` `route_card`, `tool_show_route_step`, `tool_find_nearest` | `tests/test_route_step.py` |
| R1 | `route_line(..., start=)` starts the line at `start`; a door whose landings each lie in the other space is dropped | `core/routeline.py` | `tests/test_routeline.py` |
| R2 | `PUT /sessions/{id}/location` accepts `point` (kept only inside the room); route events get `start_point` | `backend/app.py`, `backend/sessions.py`, `agent/tools.py`, `agent/campus.py`, `agent/guide.py`, `frontend/app/src/api.ts` | `tests/test_voice_location.py` |
| R3 | route lengths unchanged (drawing only) | no change to `core/building_map.py` / `core/navigation.py` | `git diff --stat` |
| V1 | end pause 1700 ms (2800 ms after an open ending), voice gate on the level meter, barge-in grace 1500 ms / ≥4 own words held 700 ms | `voice/useVoice.ts`, `voice/bargeIn.ts` | read |
| M1 | kit buildings within ~4 m get different tones, hover lights pin + block, `model-edges` outline layer | `map/style.ts`, `map/MapLanding.tsx`, `map/bridge.ts` | read |
| B1 | buttons are round with three heights (`--btn-sm/md/lg`), shared press/hover/disabled rules, `--hud-fill` variants; floors popover on phone, rail on wide screens | `building/hud.css`, `access/access.css`, `edit/edit.css` | read |
| D1 | docs and log describe the above (incl. one log entry for `find_nearest` and one for the B1 button restyle) | `docs/product/visualization.md`, `memory-bank/log.md` | read; `python3 scripts/check_links.py` |
| D2 | `memory-bank/project-state.md` header and "What exists" list this chunk (find_nearest, show_route_step, route_step + [route note], figure point / start_point, routeline start=, voice, map tones, round buttons) | `memory-bank/project-state.md` | read |
| D3 | `docs/architecture/ai-agents.md` tool table + implemented list include `find_nearest(start, query, floor_id?)` and `show_route_step(step)`, and describe `route_step` / `[route note]` | `docs/architecture/ai-agents.md` | read against `agent/tools.py` `tool_find_nearest`, `tool_show_route_step`, `agent/guide.py` `route_note` |
| G1 | Guide system prompt: "nearest/closest X" → call `find_nearest` and take them there without asking; `find_nearest` added to `PROFILE_TOOLS` | `agent/guide.py` | read; `git diff --cached agent/guide.py` |
| G2 | `Guide.set_location(space_id, point)`: moving within the same room only updates the point and queues no new location note | `agent/guide.py` `set_location` | read; `tests/test_voice_location.py` |

## Checks I ran
- `uv run pytest -q` → 870 passed, 2 skipped (re-run in fix round 1: `870 passed, 2 skipped in 101.10s`)
- `npx tsc -b` (frontend/app) → clean
- `python3 scripts/check_links.py` → OK: all links resolve in 35 files (re-run in fix round 1: same)
- Fix round 1 smoke run, `BuildingSession.load(Path('data/train/proc-campus-train-000')).call('find_nearest', {'start': 'Main lobby', 'query': 'toilet'})` →
  nearest Toilet 0.14 (F0-S014) length_m 17.99, about_m 20; next_nearest Toilet 1.16 about_m 35, Toilet 0.16 about_m 45; events `['route', 'highlight']`

## Knowledge base updates
- [x] `memory-bank/log.md` entries added (one per chunk)
- [x] `docs/product/visualization.md` step guide, framing, figure, route line
- [x] decisions / open questions: none

## Known gaps / not done
- Voice changes and barge-in not tried with a live mic; `VOICE_LEVEL` may need tuning.
- No dedicated unit test for `find_nearest`.
- Button restyle (B1) not checked visually in this commit pass; light mode of map tones not checked visually.

## Verification rounds
- Round 1: FAIL (project-state, ai-agents.md, log entries)

## Fix round 1
- project-state.md not updated: implemented — header and "What exists" now list this chunk (`memory-bank/project-state.md`).
- ai-agents.md missing new tools: implemented — tool table rows for `find_nearest` and `show_route_step`, implemented list, and a paragraph on `route_step` / `[route note]` (`docs/architecture/ai-agents.md`).
- Missing log entries: implemented — `find_nearest` entry (with smoke run, re-run in this round) and B1 round-button entry marked not checked visually (`memory-bank/log.md`).
- Undeclared changes: claim added — G1 (prompt nearest rule + PROFILE_TOOLS), G2 (same-room move queues no note), plus D2/D3 for the doc updates (`.claude/worklog/PENDING.md`).
- Round 2: PASS

---

# Verification report (round 2)

VERDICT: PASS
TREE: 8f33e1e18d408bd40f2dcf2b7ca30b4e5deb2ec1

All 14 claims (S1, S2, S3, R1, R2, R3, V1, M1, B1, D1, D2, D3, G1, G2) MET.
Standard checks: pytest 870 passed, 2 skipped; `npx tsc -b` clean; check_links OK (35 files); no secrets;
score.py unchanged; no hard-coding of test buildings; find_nearest smoke run reproduced (Toilet 0.14, 17.99 m,
events route+highlight).
Undeclared (minor, within S1/S2 scope): `plan/bands.ts` ribbon emits `across`; ROUTE_PX 7→10, CASING_PX 12→15;
`floor-chip` class; `OutdoorWalk` renamed/exported as `DashedWalk`.
Required fixes: none.
