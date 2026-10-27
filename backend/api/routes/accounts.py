"""Access mode (backend/api/access.py): the frontend's start config, a session's remembered preferences, the signed-in
user, and the admin's building rules and members."""

import json
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api import deps
from backend.api.access import AuthError, AuthUnavailable, BuildingAccess, Member
from backend.api.deps import admin_or_403, conversation_or_404, known_or_422, save_or_409, viewer_or_401
from backend.api.sessions import summary

router = APIRouter()


class SessionPreferences(BaseModel):
    values: dict = {}  # effective preferences for this building (global ← building), see backend/agents/tools/
    auto_capture: bool = True


class AccessUpdate(BaseModel):
    building: str
    public: bool = True
    room_types: dict[str, list[str]] = {}
    spaces: dict[str, list[str]] = {}


class Invite(BaseModel):
    email: str
    building: str
    groups: list[str]
    redirect_to: str | None = None


class MemberUpdate(BaseModel):
    user_id: str
    email: str
    building: str
    groups: list[str]


@router.get("/config")
def config() -> dict:
    """What the frontend needs to know at start: whether access mode is on and how to sign in (public values)."""
    if not deps.access.enabled:
        return {"access_mode": False}
    return {"access_mode": True, "supabase_url": os.environ.get("SUPABASE_URL", ""),
            "supabase_anon_key": os.environ.get("SUPABASE_ANON_KEY", "")}


@router.put("/sessions/{session_id}/preferences")
def session_preferences(session_id: str, body: SessionPreferences, authorization: str | None = Header(None)) -> dict:
    """The app's remembered preferences for this conversation (access mode): set on the session's profile without
    events; the Guide's system prompt gets the talking preferences."""
    if not deps.access.enabled:
        raise HTTPException(404, "access mode is off")
    conversation = conversation_or_404(session_id, authorization)
    with conversation.lock:
        session = conversation.session
        try:
            session.apply_preferences(body.values)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, f"bad preferences: {error}") from None
        session.auto_capture = body.auto_capture
        conversation.guide.refresh_system()
        save_or_409(conversation)
    return summary(conversation)


@router.get("/me/preferences")
def my_preferences(authorization: str | None = Header(None)) -> dict:
    """A signed-in user's stored preferences ({} until saved); anonymous users keep theirs in the browser."""
    viewer = viewer_or_401(authorization)
    if not deps.access.enabled or viewer.anonymous:
        raise HTTPException(404, "sign in to store preferences on the server")
    return deps.access.store.preferences(viewer.user_id)


@router.put("/me/preferences")
def put_my_preferences(body: dict, authorization: str | None = Header(None)) -> dict:
    viewer = viewer_or_401(authorization)
    if not deps.access.enabled or viewer.anonymous:
        raise HTTPException(404, "sign in to store preferences on the server")
    if len(json.dumps(body)) > 50_000:
        raise HTTPException(413, "preferences too large")
    deps.access.store.set_preferences(viewer.user_id, body)
    return body


@router.get("/me")
def me(authorization: str | None = Header(None)) -> dict:
    viewer = viewer_or_401(authorization)
    groups = deps.access.store.member_buildings(viewer.user_id) if deps.access.enabled and viewer.user_id else {}
    return {**viewer.to_dict(), "buildings": groups}


@router.get("/access/building")
def get_access(building: str, authorization: str | None = Header(None)) -> dict:
    """The building's access settings plus what the editor needs: its room types and spaces."""
    admin_or_403(authorization)
    known_or_422(building)
    data = deps.store.base_data(building)
    spaces = [{"id": space["id"], "name": space["name"], "ref": space.get("ref") or "",
               "room_type": space.get("room_type") or "", "floor_id": space["floor_id"]} for space in data["spaces"]]
    room_types = sorted({space["room_type"] for space in spaces if space["room_type"]})
    return {"building": building, **deps.access.store.building(building).to_dict(), "room_type_options": room_types,
            "space_options": spaces}


@router.put("/access/building")
def put_access(body: AccessUpdate, authorization: str | None = Header(None)) -> dict:
    admin_or_403(authorization)
    known_or_422(body.building)
    space_ids = {space["id"] for space in deps.store.base_data(body.building)["spaces"]}
    unknown = sorted(set(body.spaces) - space_ids)
    if unknown:
        raise HTTPException(422, f"unknown space ids: {', '.join(unknown[:5])}")
    rules = BuildingAccess.from_dict(body.model_dump())
    deps.access.store.set_building(body.building, rules)
    return {"building": body.building, **rules.to_dict()}


@router.get("/access/members")
def get_members(building: str, authorization: str | None = Header(None)) -> list[dict]:
    admin_or_403(authorization)
    return [member.to_dict() for member in deps.access.store.list_members(building)]


@router.post("/access/invite")
def invite(body: Invite, authorization: str | None = Header(None)) -> dict:
    """Create (or find) the account and return a sign-in link for the admin to pass on; no email is sent."""
    admin_or_403(authorization)
    known_or_422(body.building)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "enter an email address")
    try:
        user_id, link = deps.access.auth.invite(email, body.redirect_to)
    except (AuthError, AuthUnavailable) as error:
        raise HTTPException(503, f"could not create the invite ({error})") from None
    member = Member(user_id, email, body.building, sorted({g.strip() for g in body.groups if g.strip()}))
    deps.access.store.set_member(member)
    return {**member.to_dict(), "link": link}


@router.put("/access/members")
def put_member(body: MemberUpdate, authorization: str | None = Header(None)) -> dict:
    """Change a member's groups in a building; no groups removes the membership."""
    admin_or_403(authorization)
    member = Member(body.user_id, body.email.strip().lower(), body.building,
                    sorted({g.strip() for g in body.groups if g.strip()}))
    deps.access.store.set_member(member)
    return member.to_dict()
