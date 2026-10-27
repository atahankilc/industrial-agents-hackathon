# Record Steward's GitHub, Vercel and Supabase rename

- **Author:** Claude session 8ec388bb with Atahan · **Date:** 2026-10-27 12:30
- **Related:** D-027

## Summary
Memory-bank only: records what was renamed outside the repo after the Steward commit (GitHub repo, Vercel address,
Supabase), the new deploy URL with its checks, and that voice now works on the deployment.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | project-state "What works" records the deploy URL https://steward-io.vercel.app with the health result `tts`/`stt` true, and the branch note no longer says `main` and `dev` are on the same commit | `memory-bank/project-state.md` | read; `curl -s https://steward-io.vercel.app/api/health` |
| C2 | project-state Next 0 lists what is done (GitHub, Vercel, Supabase by Atahan's report) and what is left (local folder, worktree repair, Claude memory move); the "voice off" / "URL not recorded" gap in Next 5 is gone | `memory-bank/project-state.md` | read |
| C3 | log has a new top entry for GitHub, Vercel, Supabase with the commands' results | `memory-bank/log.md` | read |
| C4 | Only memory-bank files (and this worklog) change | — | `git diff --cached --stat` |
| C5 | The GitHub repo is `atahankilc/steward` with homepage https://steward-io.vercel.app, and `origin` points at it | GitHub | `gh repo view atahankilc/steward --json name,homepageUrl`; `git remote get-url origin` |

## Checks I ran
- `gh repo view atahankilc/steward --json homepageUrl` → `{"homepageUrl":"https://steward-io.vercel.app"}`
- `git push origin dev` → `9251dd8..b33c47c  dev -> dev`
- `curl https://steward-io.vercel.app/api/health` → `{"ok":true,"llm":"anthropic","tts":true,"stt":true}`
- `POST /api/tts` → `200 audio/mpeg 20524 bytes`; `POST /api/stt/token` → `200`
- `curl -sI https://industrial-agents-hackathon.vercel.app/` → `HTTP/2 308`, `location: https://steward-io.vercel.app/`
- `curl -sI https://industrial-agents-hackathon.vercel.app/api/health` → `HTTP/2 308`, `location: https://steward-io.vercel.app/api/health`
  (earlier the same day it answered `404`, `x-vercel-error: DEPLOYMENT_NOT_FOUND`, before the redirect was set up)
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files` (re-run after fix round 1, same output)
- `uv run pytest -q` → `955 passed, 2 skipped in 126.31s`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: none (D-027 already covers the rename)
- [x] docs touched: none

## Known gaps / not done
- The Supabase rename and Auth URLs are Atahan's report; not checked from here (no CLI or browser access).
- Local folder not moved yet.

## Fix round 1
- project-state Next 0 old-URL sentence: claim corrected — now says the old address answers a 308 redirect to https://steward-io.vercel.app/, `/api/*` included (checked 2026-10-27, `curl -sI`); `memory-bank/project-state.md`
- log 2026-10-27 entry: claim corrected — first 404 `DEPLOYMENT_NOT_FOUND`, now a 308 to steward-io; `memory-bank/log.md`
- worklog: old-URL check replaced with the real `curl -sI` output; "not redirected" removed from Known gaps; `.claude/worklog/PENDING.md`
- log: dropped the unverified "after Atahan set up a redirect" attribution (who set it up was not observed); `memory-bank/log.md`

## Verification rounds
- Round 1: VERDICT: FAIL (old-URL statements outdated: it now redirects)
- Round 2: VERDICT: PASS (tree 8f05484c0256a492bcf34932498a87b898befd68)

## Verification report (round 2)

VERDICT: PASS
TREE: 8f05484c0256a492bcf34932498a87b898befd68

C1–C5 MET. pytest 955 passed / 2 skipped; check_links OK (24 files); no secrets; score.py unchanged; only Markdown staged. Not re-run: paid tts/stt POSTs (health shows them enabled) and git push (remote dev = b33c47c). Supabase settings are Atahan's report, flagged in Known gaps.
