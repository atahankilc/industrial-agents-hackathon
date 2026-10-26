---
id: research-stack-options
summary: Researched cloud stack for day-one deploy with realtime collaboration — Lovable vs own frontend, Supabase vs alternatives, Python backend hosting, CI — with a concrete recommendation, topology, secrets, setup checklist and risks.
status: research — zero-cost recommendation (§9) accepted as D-006 in memory-bank/decisions.md (2026-10-24); §3 Railway pick superseded
researched: 2026-10-24
sources:
  - https://docs.lovable.dev/integrations/github
  - https://docs.lovable.dev/integrations/git-sync-overview
  - https://docs.lovable.dev/integrations/cloud
  - https://docs.lovable.dev/integrations/supabase
  - https://lovable.dev/faq/capabilities/tech-stack/lovable-nextjs-support
  - https://supabase.com/pricing
  - https://supabase.com/docs/guides/realtime
  - https://supabase.com/docs/guides/realtime/postgres-changes
  - https://supabase.com/docs/guides/realtime/broadcast
  - https://supabase.com/docs/reference/python/realtime-api
  - https://docs.fly.io/about/pricing
  - https://render.com/docs/free
  - https://docs.railway.com/reference/pricing/plans
  - https://docs.railway.com/guides/monorepo
  - https://docs.railway.com/reference/app-sleeping
  - https://cloud.google.com/run/pricing
  - https://www.convex.dev/pricing
  - https://liveblocks.io/pricing
  - https://vercel.com/docs/monorepos
  - https://vercel.com/docs/plans/hobby
  - https://vercel.com/docs/functions/runtimes/python
  - https://modal.com/pricing
  - https://huggingface.co/docs/hub/en/spaces-overview
  - https://www.koyeb.com/docs/faqs/pricing
related: [../architecture/overview.md, elevenlabs.md]
---

# Cloud stack options

[Docs index](../README.md) · Architecture: [overview.md](../architecture/overview.md) · Voice: [elevenlabs.md](elevenlabs.md)

Researched 2026-10-24 from the official pages in `sources`. Anything not confirmed on a fetched page is
marked **UNVERIFIED**.

## TL;DR recommendation

| Component | Service | Why |
|---|---|---|
| Frontend app | **Own Vite + React + TS + Tailwind + shadcn/ui** in `frontend/`, react-three-fiber for 3D | Same stack Lovable generates, but lives in our monorepo so Claude Code edits it directly |
| Lovable | **Optional side tool**: a separate Lovable project or repo for fast UI mock-ups; copy components into `frontend/` | Git sync always creates a **new** repo and subfolder sync isn't documented ([§1](#1-lovable)) |
| DB + auth + realtime + file storage | **Supabase** (one project we own) | Postgres + Broadcast + Presence + Storage + Auth in one free tier; Python and JS clients |
| Python API (core, solvers, Claude agent, ElevenLabs proxy) | **FastAPI on Vercel's Python runtime** (Hobby, free) — fallback Render Free / Modal ([§9](#9-zero-cost-variant-added-2026-10-24)) | Zero cost; same Vercel project as the frontend. Was Railway Hobby ($5/mo) before the zero-cost revision |
| Frontend hosting | **Vercel** — one project with the Vite frontend and FastAPI backend as *Services* ([§9](#9-zero-cost-variant-added-2026-10-24)), PR previews | One deploy, same origin for frontend and API, a preview URL per PR |
| CI | **GitHub Actions**: lint, tests, link check, deterministic dev benchmark | Guards the 55 benchmark points on every push |
| Benchmark CLI | `run_benchmark` (archived 2026-10-26) in the same Python package, no network needed | Same core, offline, reproducible |

## 1. Lovable

What the official docs confirm:

- **Two-way sync with GitHub**, on one branch at a time (the default branch, usually `main`). Pushes to that
  branch sync back into Lovable. You can't switch branches while Lovable is editing.
  ([github](https://docs.lovable.dev/integrations/github))
- **"Git sync always creates a new repository."** There is no attaching to an existing repo. To start from
  existing code: ZIP → *Upload code* → then connect Git sync, which creates another new repo. Reconnecting
  after a disconnect also creates a new repo.
- **Monorepo subfolder: not documented** (the docs speak of "one GitHub repository"). Assume Lovable owns the
  **repo root**. UNVERIFIED either way; ask Lovable support if it matters.
- Files over 10 MB can't be saved in Lovable, and GitHub rejects files over 100 MB, which **blocks sync**. That
  matters for our 209 MB dataset if it ever sat in a Lovable-synced repo.
- **Stack:** React + Vite + TypeScript (not Next.js), Tailwind, shadcn/ui, Radix
  ([FAQ](https://lovable.dev/faq/capabilities/tech-stack/lovable-nextjs-support)).
- **Lovable Cloud** is its built-in backend, built on Supabase's open-source foundation: DB, auth, storage,
  edge functions, realtime, secrets. **Migrating from Lovable Cloud to your own Supabase is manual** (export
  and restore DB, storage, auth, secrets). ([cloud](https://docs.lovable.dev/integrations/cloud))
- You can connect your **own Supabase project** instead. Lovable then writes migrations to
  `supabase/migrations/`, deploys edge functions, and stores secrets in the Supabase secret store. Lovable
  projects that share one Supabase project **overwrite each other's secrets**.
  ([supabase](https://docs.lovable.dev/integrations/supabase))
- **Calling an external FastAPI backend:** not covered in the docs. It's a normal `fetch` from a React app,
  so it should work with CORS configured. UNVERIFIED as a Lovable-supported flow.

**Verdict:** don't make Lovable the source of truth for `frontend/`. It can't attach to our monorepo, and its
single synced branch would fight Claude Code and teammates. Use it **in a separate throwaway repo** to
generate screens fast (chat panel, floor picker, landing page), then copy the components into `frontend/`.
Both use the same stack, so components transplant cleanly. If the team wants Lovable as the main frontend
tool anyway: give it its **own repo** (`<team>-frontend`), connected to *our* Supabase project (not Lovable
Cloud), and keep the Python API in the monorepo. Claude Code then edits that repo on `main` only while
Lovable is idle.

## 2. Realtime + database

### Supabase (recommended)

Free plan ([pricing](https://supabase.com/pricing)): 500 MB DB, 1 GB file storage, 5 GB egress, **200 peak
realtime connections**, 2M realtime messages/mo, 500k edge function invocations, 50k MAU, **2 active
projects**, **pauses after 1 week of inactivity**. Pro costs from $25/mo. That's plenty for a hackathon demo.

Realtime ([realtime](https://supabase.com/docs/guides/realtime)) has three primitives:

- **Broadcast:** low-latency fan-out of messages. It can be sent from clients, from the REST endpoint
  `POST https://<ref>.supabase.co/realtime/v1/api/broadcast` (with an `apikey` header; batch form takes a
  `messages` array), or **from Postgres** with `realtime.send()` / `realtime.broadcast_changes()` inside a
  trigger. ([broadcast](https://supabase.com/docs/guides/realtime/broadcast))
  - Gotchas: a DB broadcast fails (`WarnSendingBroadcastMessage`) unless a client has connected first, since
    clients create the daily partitions. The `private` flag must match the client channel. Private channels
    need a SELECT policy on `realtime.messages` for `authenticated`.
- **Presence:** who's online and what they're doing (current floor, cursor, selected room). That's our
  "several users" add-in for free.
- **Postgres Changes:** row-change stream. Every event is authorised per subscriber and processed on a
  single thread. The docs recommend Broadcast past about 3k subscribers
  ([postgres-changes](https://supabase.com/docs/guides/realtime/postgres-changes)). That's fine at our scale,
  but needs RLS, a `supabase_realtime` publication, and `replica identity full` to get old rows.
- **Python:** realtime only works on the **async** client (`acreate_client()`). Python can't send REST
  broadcasts through the SDK, so call the REST endpoint with `httpx` instead
  ([python ref](https://supabase.com/docs/reference/python/realtime-api)).

**Pattern:** the FastAPI backend is the **only writer** of building state. It validates an edit against the
core (door must share a wall, connector must exist), inserts a row into `building_edits`, and a trigger calls
`realtime.broadcast_changes()` on topic `building:<id>`. Every client applies the event to its local copy of
the building and re-routes. Presence runs on the same channel.

### Alternatives considered

| Option | Free tier (fetched) | Why not first choice |
|---|---|---|
| Convex | 1M function calls, 0.5 GB DB, 1 GB egress, 1–6 devs ([pricing](https://www.convex.dev/pricing)) | Reactive DB is great, but there's no Python client on the pricing page (UNVERIFIED overall), and our core is Python |
| Liveblocks | 10 connections per room, 3,000 collaboration minutes/mo, 24 h history ([pricing](https://liveblocks.io/pricing)) | Built for document CRDTs; caps hurt during a demo; we still need a DB |
| Firebase | not researched in depth | No Postgres; a second auth/data world next to Python |
| PartyKit / Cloudflare Durable Objects | not researched in depth | Great primitives, but more to build (persistence, auth) in 24 h |

### Data model sketch (Postgres)

```sql
buildings        (id text pk, name, source, base jsonb,          -- original building.json
                  version int, created_by uuid, created_at)
building_edits   (id bigserial pk, building_id fk, seq int,      -- append-only event log = collaboration + undo
                  kind text,       -- close | reopen | add_door | remove_door | move_asset | add_asset | rename_space | import_floor
                  payload jsonb,   -- e.g. {"element_id": "...-V02"} / {"asset_id":..., "space_id":..., "position":[x,y]}
                  author uuid, created_at, undone_by bigint null)
building_snapshots(building_id, version, state jsonb)            -- optional: materialised base + edits, for fast load
plan_uploads     (id, building_id, floor_level, storage_path, status)  -- Level 4: PNG → JSON jobs
conversations    (id, building_id, user_id, created_at)
messages         (id, conversation_id, role, content jsonb, created_at)  -- chat + tool calls, for replay/demo
```

- The building is a **JSON document** (`base`) plus an **event log**, not normalised tables. The core already
  operates on the `building.json` shape. Replaying edits is deterministic and gives undo ("undo the last
  closure") and an audit trail ("who closed lift 2?") for free.
- Floor-plan PNGs for Level 4 go to Supabase Storage (1 GB free).
- Presence is ephemeral (Realtime Presence) and not stored.

## 3. Python backend hosting

| Host | Free / cheapest (fetched) | Sleep / cold start | Verdict |
|---|---|---|---|
| **Railway** | Free $1/mo credit; Trial one-time $5; **Hobby $5/mo incl. $5 usage**; post-paid card required ([plans](https://docs.railway.com/reference/pricing/plans)) | Sleeping ("Serverless") is a per-service opt-in; the first request after sleep may 502 ([app-sleeping](https://docs.railway.com/reference/app-sleeping)) | Was the pick; superseded by [§9](#9-zero-cost-variant-added-2026-10-24) (zero cost). Monorepo `rootDirectory` + watch paths + `railway.toml` ([monorepo](https://docs.railway.com/guides/monorepo)). WebSocket support not stated on the fetched pages (UNVERIFIED, widely used) |
| Fly.io | **No free tier**; trial is 2 h machine time or 7 days; shared-cpu-1x 256 MB $2.19, 512 MB $3.69, 1 GB $6.70 per month ([pricing](https://docs.fly.io/about/pricing)) | Auto-stop/start configurable (UNVERIFIED details) | Out under zero cost (needs card after the trial; [§9](#9-zero-cost-variant-added-2026-10-24)); `fly.toml` per app |
| Render | Free web service **spins down after 15 min idle, ~1 min cold start**, 750 h/mo ([free](https://render.com/docs/free)) | Bad for a live demo or judge re-runs | Free tier is the zero-cost fallback with a keep-warm ping ([§9](#9-zero-cost-variant-added-2026-10-24)); paid plan avoids sleep |
| Google Cloud Run | Free tier and WebSocket/SSE support, 60 min max request (**UNVERIFIED**: the page didn't render, figures from general knowledge) | Cold starts unless `min-instances=1` (paid) | Viable if someone has GCP set up; more setup |
| Modal, HF Spaces | researched later in [§9](#9-zero-cost-variant-added-2026-10-24) | — | Modal = zero-cost fallback; HF Spaces no |

Memory: shapely + networkx + anthropic fit comfortably in 512 MB–1 GB (UNVERIFIED; measure with the largest
OSM building, e.g. `osm-way22744230`, which has 8 floors and 325 spaces).

Streaming: use **SSE** from FastAPI (Vercel functions don't support WebSockets, [§9](#9-zero-cost-variant-added-2026-10-24)) for agent token and tool-progress streaming. Use
**Supabase Realtime**, not our backend, for multi-user fan-out. That keeps the backend stateless and
restartable.

### Frontend hosting

- **Vercel:** one project with the Vite frontend (`frontend/`) and the FastAPI backend as *Services*
  ([§9](#9-zero-cost-variant-added-2026-10-24)); a frontend-only project would set Root Directory to `frontend/`. Every commit deploys and posts preview URLs on PRs.
  Unchanged projects are skipped ([monorepos](https://vercel.com/docs/monorepos)). **Hobby is non-commercial
  personal use only** ([hobby](https://vercel.com/docs/plans/hobby)); a student hackathon demo is probably
  fine, but that's UNVERIFIED.
- Netlify and Cloudflare Pages are equivalent alternatives for a static Vite build (not researched in depth).
- Lovable hosting only applies if Lovable owns the frontend repo ([§1](#1-lovable)).

## 4. CI (GitHub Actions)

```yaml
# .github/workflows/ci.yml (sketch)
on: [push, pull_request]
jobs:
  core:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5          # version tags UNVERIFIED — pin when writing the real file
      - run: uv sync
      - run: uv run pytest -q
      - run: python3 scripts/check_links.py
      - run: uv run python -m <pkg>.oracle_eval data/dev            # warm-up route model, free
      - run: uv run python -m <pkg>.solver_eval data/dev data/train  # deterministic per-kind scores, no LLM
  frontend:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: frontend } }
    steps: [checkout, setup-node, "npm ci", "npm run build", "npm run lint"]
```

- No API keys in CI by default. Live-LLM evals run manually (`workflow_dispatch`) with `ANTHROPIC_API_KEY`
  as a repo secret.
- Vercel gives preview deploys per PR for the whole project (frontend + backend Services); one shared staging
  backend is enough. (The earlier Railway option's PR environments were never confirmed — UNVERIFIED.)
- The 209 MB `data/` checkout is fine for Actions (under GitHub's 100 MB per-file limit; check no single file
  exceeds it).

## 5. Recommended topology

```
                ┌──────────────────────── Browser (team + judges) ────────────────────────┐
                │ React/Vite app (Vercel): 2D plan · r3f stacked floors · chat · voice   │
                └──────┬──────────────────────┬──────────────────────────┬────────────────┘
          REST + SSE   │                      │ Realtime WS              │ voice (WebRTC/WS)
                       ▼                      ▼ (edits, presence)        ▼
        ┌────────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────┐
        │ FastAPI (Vercel fn)    │──▶│ Supabase                 │   │ ElevenLabs           │
        │ core: BuildingMap,     │   │ Postgres: buildings,     │   │ (see elevenlabs.md)  │
        │ solvers, router        │   │ building_edits, convos   │◀──┤ agent tools call our │
        │ Claude agent (tools)   │   │ Realtime: broadcast +    │   │ FastAPI via webhook  │
        │ ElevenLabs token mint  │   │ presence · Storage: PNGs │   └──────────────────────┘
        │ /benchmark endpoint    │   │ Auth (anon/magic link)   │
        └──────────┬─────────────┘   └──────────────────────────┘
                   │ same package
                   ▼
        run_benchmark <building_dir> <questions> <answers>   (offline CLI, no cloud needed; archived 2026-10-26)
```

## 6. Env vars / secrets

Updated for the zero-cost stack ([§9](#9-zero-cost-variant-added-2026-10-24)); previously these lived on Railway.

| Var | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Vercel (backend env vars), local `.env`, GH secret (manual evals only) | never in the frontend |
| `ELEVENLABS_API_KEY` | Vercel (backend env vars) | backend mints short-lived tokens or signed URLs for the browser (see [elevenlabs.md](elevenlabs.md)) |
| `ELEVENLABS_AGENT_ID` | Vercel (backend env vars), frontend (public) | if we use the ElevenLabs Agents platform |
| `SUPABASE_URL` | Vercel (backend env vars), frontend as `VITE_SUPABASE_URL` | public |
| `SUPABASE_ANON_KEY` (publishable key) | frontend as `VITE_SUPABASE_ANON_KEY` | public, protected by RLS |
| `SUPABASE_SERVICE_ROLE_KEY` (secret key) | Vercel (backend env vars) only | server-side writes and broadcast REST |
| `SUPABASE_DB_URL` | Vercel (backend env vars) / CI (migrations) | optional, for direct SQL / migrations |
| `VITE_API_BASE_URL` | frontend | same-origin (empty / relative path) in the one-project Vercel setup; otherwise the Vercel (or fallback) backend URL |
| `CORS_ORIGINS` | Vercel (backend env vars) | Vercel prod + preview domains, localhost (only needed if frontend and API are not same-origin) |

Supabase's newer publishable/secret key naming vs the legacy anon/service_role keys: which one new projects
show is UNVERIFIED; use whatever the dashboard shows.

## 7. Day-one setup checklist (human actions — ask before creating anything)

Zero-cost version (D-006, accepted 2026-10-24); the original Railway variant is superseded.

1. **GitHub:** ✅ done — public repo `atahankilc/industrial-agents-hackathon`, `main` pushed.
2. **Supabase (free):** sign up with GitHub, create one project in an EU region. Copy the project URL,
   publishable/anon key and secret/service-role key. Enable anonymous sign-ins (and/or magic link).
3. **Vercel (Hobby, free):** sign up with GitHub, import the repo. Claude configures the project: Vite frontend +
   FastAPI backend as Services, function `excludeFiles`, env vars. Preview deploy per PR.
4. **ElevenLabs:** API key into local `.env` (`ELEVENLABS_API_KEY`) and into Vercel's env vars → see
   [elevenlabs.md](elevenlabs.md).
5. **Anthropic:** key from the organiser credits into `.env` (`ANTHROPIC_API_KEY`) and Vercel's env vars.
6. **GitHub secrets:** `ANTHROPIC_API_KEY` only for a manual (workflow_dispatch) eval workflow; CI stays key-free.
7. **Lovable (optional):** separate project or repo for UI mock-ups; don't connect it to the monorepo.

Never paste keys into chat; every key lives in `.env` (git-ignored) or the provider's secret settings.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Lovable creates its own repo and owns `main`; conflicts with Claude Code | Keep Lovable out of the monorepo ([§1](#1-lovable)) |
| Supabase free project pauses after 1 week idle | Irrelevant during the weekend; unpause before judging if they re-run later |
| DB-trigger broadcast drops messages before the first client connects | Also broadcast from the backend via REST; clients re-fetch state on (re)connect |
| Realtime/backend outage during the demo | Frontend can run against a local backend; record the demo video early |
| Judges re-run the benchmark command | `run_benchmark` (archived 2026-10-26) is pure local Python and doesn't depend on cloud services |
| Vercel Hobby commercial-use clause | Netlify / Cloudflare Pages for the frontend; Render Free / Modal for the backend |
| Big OSM buildings are slow to route in a request | Cache a `BuildingMap` per building and version in the backend process; invalidate on edit events |
| Secrets leak through `VITE_*` | Only anon/publishable keys go in the frontend; ElevenLabs uses backend-minted tokens |

## Related

- [overview.md](../architecture/overview.md) · [elevenlabs.md](elevenlabs.md) · [scoring.md](../../archive/hackathon/docs/challenge/scoring.md#sunday-benchmark)

## 9. Zero-cost variant (added 2026-10-24)

Constraint from Atahan: **pay nothing for now**. Railway Hobby ($5/mo) is out. Re-checked 2026-10-24:

| Option | Free? | Catch | Source |
|---|---|---|---|
| **Vercel Hobby — Python runtime** | yes | FastAPI runs as Vercel Functions with zero config; streaming responses supported; **500 MB** bundle limit; Python 3.12–3.14; frontend + Python backend in one project via *Services*. No WebSockets (we use Supabase Realtime for push anyway). Hobby = non-commercial use | [python runtime](https://vercel.com/docs/functions/runtimes/python), [hobby](https://vercel.com/docs/plans/hobby) |
| Supabase Free | yes | pauses after 1 week idle; 2 projects | [pricing](https://supabase.com/pricing) |
| Render Free | yes | sleeps after **15 min** without traffic, **~1 min** wake-up; 750 h/mo; free services suspended if over bandwidth without a payment method | [free](https://render.com/docs/free) |
| Modal Starter | yes, **$30/mo credits** | card requirement not stated on the pricing page (UNVERIFIED); CPU $0.0000131/core-s; scale-to-zero cold starts | [pricing](https://modal.com/pricing) |
| Hugging Face Spaces | **no** for us | Docker/Gradio Spaces now need a paid plan (only static Spaces free) | [spaces overview](https://huggingface.co/docs/hub/en/spaces-overview) |
| Koyeb Free | no-go | credit card required ($29 pre-auth hold); scales to zero after 1 h | [pricing FAQ](https://www.koyeb.com/docs/faqs/pricing) |
| Fly.io / Railway Hobby | no | paid after trial | §3 |

**Zero-cost recommendation:** one **Vercel** project (Vite frontend + FastAPI backend as Services) + **Supabase
Free** (DB, Realtime, Auth, Storage) + **ElevenLabs** (existing account) + **Claude** ($150 organiser credits) +
**GitHub Actions** (free for public repos). Fallback backend: Render Free with a keep-warm ping during the demo, or
Modal. Bundle: exclude `archive/`, `tests/`, `docs/`, `frontend/prototypes/` from the function; `data/` (~209 MB)
fits under 500 MB but slows cold starts — move building files to Supabase Storage if cold starts hurt.
Unverified until we deploy: Hobby function max duration (matters for the ElevenLabs Custom LLM stream) and the
cold-start time with shapely + networkx.
