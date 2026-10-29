"""Organisations (docs/product/organizations.md, backend/api/access.py): any signed-in user starts one and is its
owner; owners bring in people with a role; an org's editors set its buildings' listing. Which org owns a building
is the admin's call (a building cannot be claimed by naming an org after its owner), and so is verifying an org, which
lets it list buildings on the main map. Access mode only."""

import re

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api import deps
from backend.api.access import ADMIN_ROLES, ROLES, AuthError, AuthUnavailable, Org, OrgMember, Viewer
from backend.api.deps import known_or_422, viewer_or_401
from backend.api.routes.accounts import listing_or_403

router = APIRouter()

SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")  # also the org's address: ?org=<slug>


class NewOrg(BaseModel):
    slug: str
    name: str


class OrgUpdate(BaseModel):
    name: str | None = None
    verified: bool | None = None  # the admin only


class OrgInvite(BaseModel):
    email: str
    role: str = "viewer"
    redirect_to: str | None = None


class OrgMemberUpdate(BaseModel):
    user_id: str
    email: str
    role: str | None  # None removes them


class OrgBuilding(BaseModel):
    building: str
    listing: str | None = None  # None keeps it
    owned: bool = True  # false: the admin hands the building back to the platform


def signed_in_or_401(authorization: str | None) -> Viewer:
    if not deps.access.enabled:
        raise HTTPException(404, "access mode is off")
    viewer = viewer_or_401(authorization)
    if viewer.anonymous:
        raise HTTPException(401, "sign in first")
    return viewer


def org_or_404(viewer: Viewer, slug: str) -> tuple[Org, str | None]:
    """The org and the viewer's role in it; someone outside it gets a 404, as if it did not exist."""
    org = deps.access.store.org(slug)
    role = deps.access.role(viewer, slug)
    if org is None or not (role or viewer.admin):
        raise HTTPException(404, f"unknown organisation {slug!r}")
    return org, role


def role_or_403(viewer: Viewer, role: str | None, needed: tuple[str, ...]) -> None:
    if not (viewer.admin or role in needed):
        raise HTTPException(403, f"needs the {' or '.join(needed)} role in this organisation")


def role_or_422(role: str | None) -> None:
    if role is not None and role not in ROLES:
        raise HTTPException(422, f"role must be one of {', '.join(ROLES)}")


def keeps_an_owner(slug: str, change: OrgMember) -> bool:
    owners = {m.user_id for m in deps.access.store.org_members(slug) if m.role == "owner"}
    if change.role == "owner":
        owners.add(change.user_id)
    else:
        owners.discard(change.user_id)
    return bool(owners)


def org_payload(org: Org, role: str | None, viewer: Viewer) -> dict:
    buildings = {building: access for building, access in deps.access.store.all_buildings().items()
                 if access.org == org.slug}
    payload = {**org.to_dict(), "role": role,
               "buildings": [{"id": building, "listing": access.listing} for building, access in sorted(buildings.items())]}
    if viewer.admin or role == "owner":
        payload["members"] = [member.to_dict() for member in deps.access.store.org_members(org.slug)]
    return payload


@router.post("/orgs")
def create_org(body: NewOrg, authorization: str | None = Header(None)) -> dict:
    viewer = signed_in_or_401(authorization)
    slug, name = body.slug.strip().lower(), body.name.strip()
    if not SLUG.fullmatch(slug):
        raise HTTPException(422, "the address takes 1–40 lowercase letters, digits and inner hyphens")
    if not name or len(name) > 120:
        raise HTTPException(422, "give the organisation a name (at most 120 characters)")
    org = Org(slug, name, verified=False, created_by=viewer.user_id)
    if not deps.access.store.insert_org(org, OrgMember(slug, viewer.user_id, viewer.email or "", "owner")):
        raise HTTPException(409, f"the address {slug!r} is taken")
    return org_payload(org, "owner", viewer)


@router.get("/orgs")
def list_orgs(authorization: str | None = Header(None)) -> list[dict]:
    """The viewer's organisations with their role; every organisation for the admin."""
    viewer = signed_in_or_401(authorization)
    mine = deps.access.store.user_orgs(viewer.user_id)
    return [{**org.to_dict(), "role": mine.get(org.slug)} for org in deps.access.store.all_orgs()
            if viewer.admin or org.slug in mine]


@router.get("/orgs/{slug}")
def get_org(slug: str, authorization: str | None = Header(None)) -> dict:
    viewer = signed_in_or_401(authorization)
    org, role = org_or_404(viewer, slug)
    return org_payload(org, role, viewer)


@router.put("/orgs/{slug}")
def update_org(slug: str, body: OrgUpdate, authorization: str | None = Header(None)) -> dict:
    viewer = signed_in_or_401(authorization)
    org, role = org_or_404(viewer, slug)
    if body.verified is not None and body.verified != org.verified and not viewer.admin:
        raise HTTPException(403, "only the admin verifies an organisation")
    if body.name is not None:
        role_or_403(viewer, role, ("owner",))
        name = body.name.strip()
        if not name or len(name) > 120:
            raise HTTPException(422, "give the organisation a name (at most 120 characters)")
        org.name = name
    if body.verified is not None:
        org.verified = body.verified
    deps.access.store.set_org(org)
    return org_payload(org, role, viewer)


@router.post("/orgs/{slug}/invite")
def invite_to_org(slug: str, body: OrgInvite, authorization: str | None = Header(None)) -> dict:
    """Create (or find) the account and return a sign-in link for the owner to pass on; no email is sent."""
    viewer = signed_in_or_401(authorization)
    _, role = org_or_404(viewer, slug)
    role_or_403(viewer, role, ("owner",))
    role_or_422(body.role)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "enter an email address")
    try:
        user_id, link = deps.access.auth.invite(email, body.redirect_to)
    except (AuthError, AuthUnavailable) as error:
        raise HTTPException(503, f"could not create the invite ({error})") from None
    member = OrgMember(slug, user_id, email, body.role)
    deps.access.store.set_org_member(member)
    return {**member.to_dict(), "link": link}


@router.put("/orgs/{slug}/members")
def update_org_member(slug: str, body: OrgMemberUpdate, authorization: str | None = Header(None)) -> dict:
    """Change someone's role; no role removes them. An org always keeps an owner."""
    viewer = signed_in_or_401(authorization)
    _, role = org_or_404(viewer, slug)
    role_or_403(viewer, role, ("owner",))
    role_or_422(body.role)
    member = OrgMember(slug, body.user_id, body.email.strip().lower(), body.role)
    if not keeps_an_owner(slug, member):
        raise HTTPException(409, "an organisation needs an owner; make someone else owner first")
    deps.access.store.set_org_member(member)
    return member.to_dict()


@router.put("/orgs/{slug}/buildings")
def update_org_building(slug: str, body: OrgBuilding, authorization: str | None = Header(None)) -> dict:
    """Give a building to the org or take it back (the admin), or set its listing (the org's editors)."""
    viewer = signed_in_or_401(authorization)
    _, role = org_or_404(viewer, slug)
    role_or_403(viewer, role, ADMIN_ROLES)
    known_or_422(body.building)
    current = deps.access.store.building(body.building)
    if current.org != slug and not viewer.admin:  # an org's people change only that org's buildings
        raise HTTPException(403, "this organisation does not own that building")
    owner = slug if body.owned else None
    if owner != current.org and not viewer.admin:
        raise HTTPException(403, "only the admin changes which organisation owns a building")
    listing = body.listing or current.listing
    listing_or_403(viewer, owner, listing, current.listing)
    current.org, current.listing = owner, listing
    deps.access.store.set_building(body.building, current)
    return {"building": body.building, **current.to_dict()}
