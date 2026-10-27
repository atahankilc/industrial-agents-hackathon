---
id: demo-runbook
summary: Demo video (2 min) and final pitch (3 min + 1 min Q&A) — building, exact lines, expected answers, visitor and admin takes (access, Edit mode), setup, reset, fallbacks.
sources:
  - live run 2026-10-25 against the local backend (real Claude) and the app (headless Chrome)
  - docs/challenge/brief.md (judging, submission)
  - docs/product/personas.md (demo cast)
  - docs/superpowers/specs/2026-10-25-access-profiles-design.md, docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md
  - frontend/app/src/building/BuildingScreen.tsx (Edit mode admin-only in access mode)
related: [../challenge/brief.md, ../challenge/technical-explanation.md, ../product/personas.md, commands.md]
---

# Demo runbook

[Docs index](../../docs/README.md)

## Demo building and the route story (checked 2026-10-25)

**Thierschbau** — `train/osm-way61408163` (TUM Arcisstraße, OSM indoor data, on the map). Floors B1, G, 1; Lift 1 +
Lift 2 (both B1–G–1), Stairs 1–4; lecture hall **Theodor-Fischer-Hörsaal** (G). Start room: **room 1373** (Floor 1,
`osm-way61408163-F1-S001`).

| Step | Say exactly | Guide did (live, 2026-10-25) |
|---|---|---|
| FIND | "Hi, it's my first day. I'm in room 1373 on the first floor. Where's the nearest toilet?" | places user in 1373; **Toilet 0364**, Ground floor, about 45 m, via Stairs 4 |
| ROUTE | "I use a wheelchair. How do I get to the Theodor-Fischer lecture hall?" | saves wheelchair profile (doors ≥ 0.8 m, says it is an assumption); step-free via **Lift 2**, about 90 m (core: 88.0 m) |
| EDIT | "Lift 2 is closed for maintenance." | **proposes**, does not apply: 88 → 224 m, 30 Basement 1 rooms lose step-free access, 48 other routes longer; asks to apply |
| CONFIRM | "Yes, apply it." | applies; route via **Lift 1**, about 220 m (core: 223.8 m) |

Each turn took 6–7 s on the API. Say **"Yes, apply it."** explicitly — "OK, how do I get there now?" was also taken as
a yes, which looks careless on camera.

**Closures are per session**: a reload / new session starts with both lifts open (checked: a fresh session routed
via Lift 2 after the closure). So do **not** say "every visitor's next route already knows" — that is the
`collab-edits` roadmap, not built on `dev`.

## Demo video (strictly 2:00)

Two people: the **visitor** (phone, not signed in) and the **admin** (desktop, signed in with an `ADMIN_EMAIL`
account; backend `ACCESS_MODE=on`). Record the two halves separately and cut.

| Time | Who · screen | Voice-over (EN) |
|---|---|---|
| 0:00–0:08 | map, tap Thierschbau, camera flies in | "Every building gets its own map you can talk to. Every door, stair and lift." |
| 0:08–0:24 | visitor · FIND by **voice** (hold to talk) | (Guide's spoken answer) + "Nearest by walking, not by straight line." |
| 0:24–0:42 | visitor · ROUTE wheelchair, press Start, step card | "Say it once. Step-free, wide-enough doors, never asked again." |
| 0:42–0:58 | visitor · "Lift 2 is closed…" → effect → "Yes, apply it." → route via Lift 1 | "It shows the effect first and waits for a yes." |
| 0:58–1:20 | admin · Building settings → Access: restrict `office` to group `staff`; Members: invite link with `staff` | "It's your building. You decide who sees what." |
| 1:20–1:32 | visitor · offices now darkened; ask for Office 0361 → "that area is restricted", offers a public place | "Restricted rooms vanish from answers and routes, enforced in code." |
| 1:32–1:50 | admin · Edit mode: drag a door, then prompt "Make Office 0361 one metre wider to the east." → dashed proposal → Apply → Save | "Change the building by hand or by saying it. Save, and the Guide routes in it." |
| 1:50–2:00 | architecture card + repo URL | "The model talks, the code counts. Talk to your building." |

Optional instead of 1:32–1:50 if the Creator is the stronger shot: `?view=import`, upload one plan, the Creator
opens the result in Edit mode.

## Final pitch (3 min + 1 min Q&A)

Deck: click-through page (artifact "Talk to Your Building", https://claude.ai/artifact/7wG5j4R5EuXFcJ1Kp3qNis, private to Atahan until shared; 12 slides, `N` = speaker notes, `F` = fullscreen).
Rough timing: 1 title 0:08 · 2 three people 0:20 · 3 today 0:15 · 4 real app 0:07 · 5–7 demo 0:50 · 8 access 0:20 ·
9 edit 0:20 · 10 how 0:20 · 11 proof 0:12 · 12 close 0:08. If a live demo is wanted, replace slides 5–7 by the live app with the same four lines.

Likely Q&A, short answers:
- *How do you stop hallucinations?* The model only picks tools and words; rooms, routes, numbers come from the core.
  The benchmark `Answer:` line is written by code.
- *Unseen building?* Same format → one command; new wording goes to the LLM only to fill slots from the building's
  own vocabulary.
- *Where does the plan come from?* Kit data today (OSM indoor, procedural, Swiss Dwellings, ResPlan); Create from
  floor plans for new ones.
- *Door width 0.8 m?* Our assumption for wheelchairs; the Guide says so and asks to correct it.

- *Can a visitor change the building?* No: in access mode Edit mode is the admin's. A visitor's reported closure
  (e.g. a lift) only changes their own conversation's routes.
- *Restricted rooms?* Filtered in the tool layer before the model sees anything; the plan gets them darkened and
  unnamed.

## Before recording — checklist

- [ ] Backend with the real key: `uv run --env-file .env uvicorn backend.app:app --port 8765`;
      `curl -s localhost:8765/health` → `"llm":"anthropic","tts":true,"stt":true`
- [ ] App: `cd frontend/app && npx vite --port 5181`, open `http://localhost:5181/?building=train/osm-way61408163`
      (or the deployed URL after its smoke test)
- [ ] Fresh session (reload) before each take; phone-size window (390×844) or a real phone
- [ ] Voice with a **live mic** at least once before the take (not yet tried, project-state)
- [ ] Notifications off, browser zoom 100 %, one tab
- [ ] Backend `ACCESS_MODE=on` and an `ADMIN_EMAIL` account that can sign in — **a real Supabase sign-in is not
      yet tried** (project-state); rehearse sign-in, Access, Members (invite link) and Edit mode once
- [ ] After the admin take: remove the `office` restriction again, so the visitor takes start clean
- [ ] Builder prompt rehearsed live once (`scripts/live_builder.py` or in the app); Save creates a new `user/<slug>`
      building — delete test saves you don't want listed
- [ ] Fallback: if a turn fails, the typed version of the same line

## UI glitches seen in the captures (fix or frame around)

- Route HUD at phone width: the text "STEP-FREE, DOORS AT LEAST 0.8 M WIDE" runs under the HUD's icon buttons.
- Lift callouts "Lift 1 to Ground floor" / "From Floor 1" overlap each other at phone width.
- Start room is labelled "Generic room 1373" (kit name); the Guide itself says "room 1373".
