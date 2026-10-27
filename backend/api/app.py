"""FastAPI app: the Building Guide over HTTP.

  GUIDE_LLM=offline uv run uvicorn backend.api.app:app --port 8765

This module only assembles the app: middleware, error handlers, /health and the routers. The routes live per area in
backend/api/routes/: guide.py (/buildings, /sessions…, /chat, /chat/stream, /events, plan), voice.py (/tts,
/stt/token), accounts.py (/config, /me, /access/* — access mode), drafts.py (Edit mode /drafts and the Builder),
imports.py (/imports/stream — the Creator — and a draft's place on the map), openai_chat.py (/v1/chat/completions
for ElevenLabs). The living building (/live, backend/api/live.py), moving objects (/objects, backend/api/fleet.py)
and the dev panel (/dev, backend/api/devtools.py) bring their own routers. Shared stores and guards: backend/api/deps.py.

Saved buildings appear in /buildings as `user/<slug>`, stored in Postgres with SUPABASE_DB_URL, else under
GUIDE_USER_DIR (default data/user/). A request that lost a race to another instance answers 409; a database error 503.

On Vercel (vercel.json) the app is the `api` service behind the rewrite `/api/(.*)`, which passes the original path
through, so every route is also reachable under `/api` (StripPrefix). CORS_ORIGINS (comma-separated) restricts
cross-origin callers; the default `*` is for local development, the deployed frontend is same-origin."""

import os

import anthropic
import psycopg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES

from backend.agents.guide import llm_mode
from backend.api import deps, devtools, persistence, service_errors, stt, tts
from backend.api.access import AuthError, AuthUnavailable
from backend.api.deps import admin_or_403, conversation_or_404, known_or_422, save_or_409, viewer_restricted
from backend.api.fleet import router as fleet_router
from backend.api.live import router as live_router
from backend.api.routes import accounts, drafts, guide, imports, openai_chat, voice

API_PREFIX = "/api"


class StripPrefix:
    """ASGI middleware: serve `/api/x` as `/x`, so the same routes work behind the Vercel rewrite and locally."""

    def __init__(self, app: object, prefix: str = API_PREFIX) -> None:
        self.app, self.prefix = app, prefix

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        path = scope.get("path", "")
        if scope["type"] in ("http", "websocket") and (path == self.prefix or path.startswith(self.prefix + "/")):
            scope = {**scope, "path": path[len(self.prefix):] or "/",
                     "raw_path": scope.get("raw_path", b"")[len(self.prefix):] or b"/"}
        await self.app(scope, receive, send)


origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "*").split(",") if origin.strip()]
app = FastAPI(title="Talk to Your Building")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
# the floor plan export is up to ~0.5 MB of JSON; NDJSON streams stay uncompressed: gzip held a Guide turn's lines
# back until the turn ended (browsers ask for gzip), so the app saw no steps and a phone's connection sat idle
app.add_middleware(GZipMiddleware, minimum_size=1000,
                   exclude_content_types=(*DEFAULT_EXCLUDED_CONTENT_TYPES, "application/x-ndjson"))
app.add_middleware(StripPrefix)  # added last = outermost: routes see the path without /api


@app.middleware("http")
async def drafts_admin_only(request: Request, call_next):
    """Access mode: Edit mode (/drafts) hands out a building's full data, and an import (/imports) is a paid Creator
    run that ends in the Edit mode, so only the admin may use them."""
    path = request.url.path.removeprefix(API_PREFIX)
    admin_only = (any(path == root or path.startswith(root + "/") for root in ("/drafts", "/imports"))
                  or (request.method == "DELETE" and path.startswith("/buildings/")))  # deleting a saved building
    if deps.access.enabled and admin_only and request.method != "OPTIONS":
        try:
            viewer = await run_in_threadpool(deps.access.viewer, request.headers.get("authorization"))
        except AuthError:
            return JSONResponse({"detail": "sign-in expired or invalid; sign in again"}, status_code=401)
        except AuthUnavailable as error:
            return JSONResponse({"detail": f"sign-in is unavailable right now ({error})"}, status_code=503)
        if not viewer.admin:
            return JSONResponse({"detail": "only the building admin can edit buildings"}, status_code=403)
    return await call_next(request)


UPDATED_ELSEWHERE = "this draft was updated elsewhere meanwhile; try again"
DB_DOWN = "the database is unavailable right now; try again in a moment"


@app.exception_handler(anthropic.APIError)
def claude_failed(request: Request, error: anthropic.APIError) -> JSONResponse:
    """A Claude call failed on a plain request (/chat, Builder, …): the readable sentence, not a 500 trace."""
    readable = service_errors.friendly(error)
    return JSONResponse({"detail": readable["message"], "code": readable["code"]},
                        status_code=service_errors.STATUS[readable["code"]])


@app.exception_handler(persistence.Conflict)
def conflict_409(request: Request, error: persistence.Conflict) -> JSONResponse:
    return JSONResponse({"detail": UPDATED_ELSEWHERE}, status_code=409)


@app.exception_handler(psycopg.Error)
def database_503(request: Request, error: psycopg.Error) -> JSONResponse:
    return JSONResponse({"detail": DB_DOWN}, status_code=503)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "llm": llm_mode(), "tts": tts.enabled(), "stt": stt.enabled()}


for routes in (guide, voice, accounts, drafts, imports, openai_chat):
    app.include_router(routes.router)
app.include_router(live_router(deps.live, known_or_422, conversation_or_404, save_or_409,
                               lambda authorization, building: deps.live_hidden(authorization, building),
                               lambda: deps.access.enabled, admin_or_403))
app.include_router(fleet_router(deps.fleet, lambda: deps.access.enabled, admin_or_403, viewer_restricted, known_or_422))
app.include_router(devtools.router(deps.store, conversation_or_404, save_or_409))  # the app's dev panel (backend/api/devtools.py)
