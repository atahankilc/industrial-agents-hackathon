# One command to run the app locally; move dev ports to 8390 / 5390

- **Author:** Claude session for Atahan · **Date:** 2026-10-27 04:15
- **Related:** user request (ports clashed with other local projects, e.g. north-star on 5288)

## Summary
Adds `npm run dev` at the repo root (root `package.json` → `scripts/dev.sh`) that starts the FastAPI backend and the
Vite app together and stops both together. Moves the default local ports from 8765 / 5181 (5173 bare) to 8390
(backend) and 5390 (app) and updates every place in the repo that names them.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | Root `package.json` (private, no dependencies) has `"dev": "bash scripts/dev.sh"` | `package.json` | read |
| C2 | `scripts/dev.sh`: ports from `BACKEND_PORT` (default 8390) / `FRONTEND_PORT` (default 5390); exits 1 with a message when either port is busy; `uv sync`; `npm install` in `frontend/` only when `node_modules` is missing; backend with `--env-file .env` if `.env` exists, else `GUIDE_LLM=offline`; Vite gets `BACKEND_URL` and `--strictPort`; Ctrl-C/TERM/either side exiting stops both by killing only its own process trees (no `kill 0`); works with macOS bash 3.2 (no `wait -n`) | `scripts/dev.sh` | read; `bash -n scripts/dev.sh` |
| C3 | `frontend/vite.config.ts`: `server.port: 5390`, `strictPort: true`, proxy default `http://127.0.0.1:8390` | `frontend/vite.config.ts` | read |
| C4 | No remaining 8765 / 5181 / 5173 port references outside archive, worklog history, data and lockfiles | README.md, docs/guides/commands.md, backend/api/app.py, scripts/sim_object.py | `git grep -nwE "8765\|5181\|5173" -- ':!archive' ':!.claude/worklog/history' ':!data' ':!frontend/package-lock.json' ':!uv.lock' ':!backend/api/locations.json'` → only memory-bank/log.md's description of the move |
| C5 | README "Running the app" and commands.md "Frontend app" lead with `npm run dev`, name the ports and the overrides | README.md, docs/guides/commands.md | read |
| C6 | `vercel.json` `excludeFiles` also drops the root `package.json` from the api function bundle; deploy tests pass | `vercel.json` | `uv run pytest tests/test_deploy.py -q` → 8 passed |
| C7 | memory-bank log entry and project-state "What works" line | `memory-bank/log.md`, `memory-bank/project-state.md` | read; `python3 scripts/check_links.py` |

## Checks I ran
- `npm run dev` (root) → prints `app: http://localhost:5390   backend: http://127.0.0.1:8390`, Vite `ready`, uvicorn `running on http://127.0.0.1:8390`; `curl localhost:8390/health` and `curl localhost:5390/api/health` → `{"ok":true,"llm":"anthropic","tts":true,"stt":true}`; `curl localhost:5390/` → 200
- second run while the first is up → `port 8390 is already in use; stop that process or set BACKEND_PORT / FRONTEND_PORT`, exit 1
- second copy on 8391/5391: `kill -TERM <dev.sh>` → 8391 and 5391 down, 8390/5390 still up
- second copy on 8391/5391: killing its uvicorn → 5391 also down within 4 s, first copy still up, calling shell survived (after replacing `kill 0`, which had also killed the caller's process group)
- `bash -n scripts/dev.sh` → ok
- `uv run pytest tests/test_deploy.py -q` → `8 passed`
- `python3 scripts/check_links.py` → `OK: all links resolve in 24 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [ ] decisions / open questions: none (local dev tooling, no architectural choice)
- [x] docs touched: README.md, docs/guides/commands.md

## Known gaps / not done
- A real Ctrl-C in an interactive terminal was not pressed here (the background test shell ignores SIGINT); TERM and one-side-exit were tested, and Ctrl-C in a terminal reaches the whole foreground group anyway.
- `pnpm run dev` should work too (the root script has no dependencies), but the frontend's lockfile is npm's; not tried with pnpm.
- Supabase Auth redirect URLs (if any were set to localhost:5181 in the Supabase dashboard) are outside the repo and not checked.

## Verification rounds
- Round 1: PASS — all claims C1–C7 MET

## Verification report (round 1)

VERDICT: PASS
TREE: 1e977feb943405aed7bec789dc90f74fff6eb39c

C1–C7 MET. dev.sh re-tested on 8392/5392 (health via app, busy port exit 1, TERM and one-side-exit stop only that copy, no leftovers); pytest 955/2; test_deploy 8 passed; links OK; no secrets. Observation: if the backend fails after the pre-check, dev.sh stops both but exits 0.
