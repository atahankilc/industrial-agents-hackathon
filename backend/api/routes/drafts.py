"""Edit mode: drafts of a building (backend/api/drafts.py) changed by hand or by the Builder agent
(backend/agents/builder.py), saved as `user/<slug>` buildings. A draft change or Builder turn that lost a race to
another instance answers 409."""

import queue
import re
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.builder import Builder
from backend.api import deps, persistence, service_errors
from backend.api.deps import draft_or_404, ndjson_with_pings
from backend.api.drafts import Draft
from backend.core.edits import EditError

router = APIRouter()


class NewDraft(BaseModel):
    base: str


class DraftOps(BaseModel):
    ops: list[dict]


class SaveDraft(BaseModel):
    name: str


class BuilderMessage(BaseModel):
    message: str


@router.delete("/buildings/{split}/{slug}")
def delete_building(split: str, slug: str) -> dict:
    """Delete a building saved from the Edit mode or an import (user/<slug>); dataset buildings cannot be deleted.
    A version it superseded comes back to the map."""
    if split != "user" or not re.fullmatch(r"[a-z0-9-]+", slug) or not deps.drafts.delete(f"user/{slug}"):
        raise HTTPException(404, f"no saved building {split}/{slug}")
    return {"deleted": f"user/{slug}"}


@router.post("/drafts")
def create_draft(body: NewDraft) -> dict:
    try:
        draft = deps.drafts.create(body.base)
    except KeyError:
        raise HTTPException(422, f"unknown building {body.base!r}; see GET /buildings") from None
    return deps.drafts.state(draft)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    return deps.drafts.state(draft_or_404(draft_id))


@router.get("/drafts/{draft_id}/plan")
def draft_plan(draft_id: str) -> dict:
    return deps.drafts.plan(draft_or_404(draft_id))


@router.post("/drafts/{draft_id}/ops")
def draft_ops(draft_id: str, body: DraftOps) -> dict:
    draft = draft_or_404(draft_id)
    try:
        deps.drafts.apply(draft, body.ops)
    except EditError as error:
        raise HTTPException(422, str(error)) from None
    tell_builder(draft, "The user changed the draft by hand (dragging on the plan); look again before proposing.")
    return deps.drafts.state(draft)


@router.post("/drafts/{draft_id}/undo")
def draft_undo(draft_id: str) -> dict:
    draft = draft_or_404(draft_id)
    try:
        deps.drafts.undo(draft)
    except EditError as error:
        raise HTTPException(409, str(error)) from None
    tell_builder(draft, "The user undid the last change to the draft; look again before proposing.")
    return deps.drafts.state(draft)


@router.post("/drafts/{draft_id}/save")
def draft_save(draft_id: str, body: SaveDraft) -> dict:
    draft = draft_or_404(draft_id)
    issues = deps.drafts.issues(draft)
    return {"building": deps.drafts.save(draft, body.name), "issues": issues}


# ---------- Edit mode: the Builder agent (backend/agents/builder.py) — prompt edits ----------
# One Builder per draft behind a per-draft turn lock. The dict is only a cache: the conversation is stored with the
# draft after every turn / apply / cancel / hand-edit note (drafts.backend) and restored when the stored version is
# newer than ours — another instance moved it on, or this one never saw it.

builders: dict[str, Builder] = {}
builder_locks: dict[str, threading.Lock] = {}
builders_guard = threading.Lock()


def builder_lock(draft_id: str) -> threading.Lock:
    with builders_guard:
        return builder_locks.setdefault(draft_id, threading.Lock())


def load_builder(draft: Draft) -> Builder:
    """The draft's Builder as last stored. Hold its builder_lock."""
    cached = builders.get(draft.id)
    if cached is not None and cached.draft is draft and cached.version == deps.drafts.backend.builder_version(draft.id):
        return cached
    state, version = deps.drafts.backend.load_builder(draft.id)
    builder = Builder.restore(deps.drafts, draft, state) if state is not None else Builder(deps.drafts, draft)
    builder.version = version
    builders[draft.id] = builder
    return builder


def store_builder(builder: Builder) -> None:
    """Persist after a change; raises persistence.Conflict (and forgets our copy) if another instance stored first."""
    try:
        builder.version = deps.drafts.backend.save_builder(builder.draft.id, builder.dump(), builder.version)
    except persistence.Conflict:
        builders.pop(builder.draft.id, None)
        raise


def tell_builder(draft: Draft, note: str) -> None:
    """A hand edit / undo: tell the draft's Builder (if it has talked yet), closing its open proposal."""
    lock = builder_lock(draft.id)
    if not lock.acquire(blocking=False):  # a turn is running here; it stores the note with its own state
        if (builder := builders.get(draft.id)) is not None:
            builder.drafted_by_hand(note)
        return
    try:
        for attempt in range(2):
            if draft.id not in builders and deps.drafts.backend.builder_version(draft.id) == 0:
                return  # no conversation yet: nothing to tell
            builder = load_builder(draft)
            builder.drafted_by_hand(note)
            try:
                store_builder(builder)
                return
            except persistence.Conflict:
                if attempt:  # the edit itself is stored; the Builder just misses one note
                    return
    finally:
        lock.release()


def proposal_payload(draft: Draft, proposal: object | None) -> dict | None:
    """An open proposal for the UI, with the draft as it would look after it (the plan's ghost overlay). None when
    the draft changed while the Builder worked (a hand edit): the reply still goes out, the outdated proposal not."""
    if proposal is None or proposal.draft_version != draft.version:
        return None
    preview = proposal.preview
    return {"id": proposal.id, "summary": proposal.summary, "ops": proposal.ops,
            "new_problems": [issue["message"] for issue in proposal.new_problems], "effect": proposal.effect,
            "building": preview}


@router.post("/drafts/{draft_id}/chat/stream")
def draft_chat_stream(draft_id: str, body: BuilderMessage) -> StreamingResponse:
    """One Builder turn as NDJSON: {"type": "step", …} while it works, then {"type": "reply", "reply", "tool_calls",
    "proposal" (or null), "applied" (summary when a "yes" applied the open proposal), "state"} or {"type": "error"}."""
    draft = draft_or_404(draft_id)
    lines: queue.Queue[dict | None] = queue.Queue()

    def work() -> None:
        try:
            with builder_lock(draft.id):
                builder = load_builder(draft)
                builder.on_step = lambda step: lines.put({"type": "step", **step})
                try:
                    turn = builder.reply(body.message)
                finally:
                    builder.on_step = None
                try:
                    store_builder(builder)
                except persistence.Conflict:
                    lines.put({"type": "error", "code": "conflict",
                               "message": "This conversation was updated elsewhere meanwhile. Send the message again.",
                               "detail": "this conversation was updated elsewhere meanwhile; send the message again"})
                    return
                lines.put({"type": "reply", "reply": turn.text,
                           "tool_calls": [{"name": call["name"], "input": call["input"]} for call in turn.tool_calls],
                           "proposal": proposal_payload(draft, turn.proposal), "applied": turn.applied,
                           "ungrounded": turn.ungrounded, "state": deps.drafts.state(draft)})
        except Exception as error:  # the stream has started: report instead of a status code
            lines.put(service_errors.error_line(error))
        finally:
            lines.put(None)

    def stream():
        threading.Thread(target=work, daemon=True).start()
        yield from ndjson_with_pings(lines)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/drafts/{draft_id}/proposals/{proposal_id}/cancel")
def cancel_proposal(draft_id: str, proposal_id: str) -> dict:
    draft = draft_or_404(draft_id)
    with builder_lock(draft.id):
        builder = load_builder(draft)
        builder.cancel(proposal_id)
        store_builder(builder)
    return {"cancelled": proposal_id}


@router.post("/drafts/{draft_id}/proposals/{proposal_id}/apply")
def apply_proposal(draft_id: str, proposal_id: str) -> dict:
    draft = draft_or_404(draft_id)
    with builder_lock(draft.id):
        builder = load_builder(draft)
        try:
            builder.apply(proposal_id)
        except EditError as error:
            raise HTTPException(409, str(error)) from None
        store_builder(builder)
    return deps.drafts.state(draft)
