# Zero-cost cloud stack decision, MIT licence detection fix, session handoff

- **Author:** Claude (main session) · **Date:** 2026-10-24
- **Related:** D-006, D-009, Q-007

## Summary
Records the accepted zero-cost cloud stack (Vercel for frontend + FastAPI backend, Supabase, ElevenLabs, Claude
credits, GitHub Actions), makes GitHub recognise the MIT licence, and adds a "start here" handoff for the next
session (focus: implementing the app; cloud accounts later).

## Claims

| # | Claim | Where | How to verify |
|---|---|---|---|
| C1 | Zero-cost stack research added with sources (Vercel Python runtime, Supabase, Render, Modal, HF Spaces, Koyeb) and the setup checklist rewritten for it; TL;DR backend/hosting rows, §3 Railway verdict ("Was the pick; superseded by §9") and §6 env-var table (Vercel backend env vars, same-origin `VITE_API_BASE_URL`) updated to match | `docs/research/stack-options.md` TL;DR, §3, §6, §7, §9 | read; `grep -n Railway docs/research/stack-options.md` → no hits in TL;DR or §6 table rows (only history wording in TL;DR "Why", §3, §4 note, §6 note, §7, §9); §5 topology box says "FastAPI (Vercel fn)" |
| C2 | D-006 accepted (zero-cost revision) — title and Decision bullet say FastAPI on Vercel's Python runtime in the same Vercel project (fallback Render Free / Modal), Context says "Resolves Q-007"; Q-007 resolved and moved to Resolved; architecture overview marked accepted, backend row = Vercel Python runtime, topology label updated | `memory-bank/decisions.md`, `memory-bank/open-questions.md`, `docs/architecture/overview.md` | read; `grep -n Railway docs/architecture/overview.md` → only the "was Railway" note; `grep -n Railway memory-bank/decisions.md` → only the D-006 Revision bullet (:77) |
| C3 | `LICENSE` is the unmodified MIT text (scope note moved to `NOTICE.md`) so GitHub can detect MIT | `LICENSE`, `NOTICE.md` | `tail -3 LICENSE` ends with `SOFTWARE.`; NOTICE row says MIT covers only our code |
| C4 | `.env.example` lists `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY` (empty) and `PARSER_MODE=hybrid`; `.env` is git-ignored | `.env.example`, `.gitignore` | `cat .env.example`; `git check-ignore -v .env` |
| C5 | Project state has a "Start here" handoff (focus: solvers → answer() → run_benchmark; cloud later; /ship workflow; no API keys) and the log has a zero-cost entry | `memory-bank/project-state.md`, `memory-bank/log.md` | read |

## Checks I ran
- `python3 scripts/check_links.py` → `OK: all links resolve in 26 files` (re-run after fix round 1: same)
- `uv run pytest -q` → `21 passed in 2.70s` (re-run after fix round 1: `21 passed in 2.68s`)
- `grep -n Railway memory-bank/decisions.md` (fix round 1) → `77:- **Revision 2026-10-24 (zero cost):** Atahan wants to pay nothing → backend moves from Railway to **Vercel's Python`
- `git check-ignore -v .env` → `.gitignore:3:.env	.env`
- Fix round 2: `python3 scripts/check_links.py` → `OK: all links resolve in 26 files`
- Fix round 2: `uv run pytest -q` → `21 passed in 2.41s`
- Fix round 2: `grep -n -E "no commits|first commit in progress|PROPOSED" memory-bank/project-state.md docs/architecture/overview.md` → no output (exit 1)

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated (handoff + next priorities)
- [x] `memory-bank/log.md` entry added
- [x] D-006 accepted, Q-007 resolved
- [x] docs: research/stack-options.md, architecture/overview.md

## Known gaps / not done
- No accounts created (Vercel, Supabase) — Atahan, later. Vercel Hobby max function duration and cold start
  with shapely/networkx unverified until first deploy.
- No code changes in this commit.

## Fix round 1
- Fix 1 (D-006 title/Decision/"once accepted"): implemented — `memory-bank/decisions.md` title and Decision bullet
  now FastAPI on Vercel's Python runtime in the same Vercel project as the frontend, fallback Render Free / Modal;
  Context "Resolves Q-007"; Revision bullet kept as history.
- Fix 2 (TL;DR rows): implemented — `docs/research/stack-options.md` Python API row → Vercel Python runtime
  (fallback Render Free / Modal, link §9, "was Railway" as history); frontend hosting row → one-project Services setup.
- Fix 3 (env-var table): implemented — `docs/research/stack-options.md` §6 "Railway" → "Vercel (backend env vars)",
  `VITE_API_BASE_URL` → same-origin / Vercel backend URL, note that the table was updated for §9.
- Fix 4 (§3 Railway verdict): implemented — "**Pick.**" → "Was the pick; superseded by §9 (zero cost)".
- Follow-up (implementer, after fix round 1): §4 CI note and §5 topology box also updated from Railway to Vercel.
- Fix 5: implemented — link check and pytest re-run (outputs above), C1/C2 extended, files re-staged.

## Fix round 2
- Fix 1 (project-state Git bullet + header): implemented — `memory-bank/project-state.md` Git bullet now "first commit
  `3300e6c` pushed to `origin/main`"; "Last updated" header now "(zero-cost stack session, after first commit `3300e6c`)".
- Fix 2 (overview summary "PROPOSED"): implemented — `docs/architecture/overview.md` front-matter summary now "System
  architecture (stack accepted in D-006, zero-cost revision; repo layout and build order proposed) — …".
- Fix 3 (optional, stack-options front matter): implemented — `docs/research/stack-options.md` `sources:` adds
  vercel.com/docs/functions/runtimes/python, modal.com/pricing, huggingface.co/docs/hub/en/spaces-overview,
  www.koyeb.com/docs/faqs/pricing (render.com/docs/free and vercel.com/docs/plans/hobby were already listed);
  `status:` now says the §9 zero-cost recommendation is accepted as D-006 and the §3 Railway pick is superseded.
- Extra scan (same three files, statements contradicting D-006 zero-cost) — implemented, all in
  `docs/research/stack-options.md`:
  - §3 Fly.io verdict "Good fallback" → "Out under zero cost (needs card after the trial; §9)".
  - §3 Render verdict "Only on a paid plan" → Free tier is the zero-cost fallback with keep-warm ping (§9).
  - §3 "Modal, HF Spaces | not researched | Skip" → researched in §9; Modal = zero-cost fallback, HF Spaces no.
  - §3 Streaming "SSE (or a WebSocket)" → SSE only (Vercel functions have no WebSockets, per §9).
  - §3 Frontend hosting "set Root Directory to `frontend/`" → one project with frontend + FastAPI as Services (§9).
  - §8 Risk "Vercel Hobby commercial-use clause" mitigation now also names the backend fallback (Render Free / Modal).
  - No other contradictions found in `memory-bank/project-state.md` or `docs/architecture/overview.md`.
- Fix 4: implemented — link check + pytest re-run (outputs in "Checks I ran"), files re-staged.

## Verification rounds
- Round 1: VERDICT: FAIL — stale Railway text in D-006 and stack-options TL;DR/§3/§6 → fixed in Fix round 1 (+ §4/§5 follow-up)
- Round 2: VERDICT: FAIL — stale Git line in project-state, "PROPOSED" summary in overview → Fix round 2
- Round 3: VERDICT: PASS (fresh verifier)

---

# Verifier report — round 3 (final)

VERDICT: PASS
TREE: 66a00c83e433214d65ca92b002399dacd9ef0ae2

| # | Status | Evidence |
|---|---|---|
| C1 | MET | stack-options §9 with sources + front-matter sources; TL;DR/§3/§5/§6/§7 consistent with zero-cost stack; Railway only in history wording |
| C2 | MET | D-006 title/Decision = Vercel Python runtime, accepted, "Resolves Q-007"; Q-007 resolved; overview accepted, no "PROPOSED" |
| C3 | MET | LICENSE ends with `SOFTWARE.`; NOTICE scopes MIT to our code |
| C4 | MET | `.env.example` keys present and empty; `.env` git-ignored |
| C5 | MET | "Start here" handoff; Git bullet = `3300e6c` pushed; zero-cost log entry |

Standard checks: pytest 21 passed · links OK (26 files) · no secrets · score.py unchanged · no code.
Cosmetic (non-blocking): §9 sits after "## Related" in stack-options.md; double blank line after Q-007.

Round 1 (FAIL): stale Railway text in D-006 / stack-options. Round 2 (FAIL): stale Git line in project-state,
"PROPOSED" summary in overview. Both fixed by commit-fixer.
