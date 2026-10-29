"""Organisations' maps (backend/api/maps.py, docs/product/organizations.md phase 2): an org's editors make maps of
their buildings (and of anyone's listed ones), choose who opens them, and share a link; the app opens one with
`?map=<slug>` (`&k=<token>` for a link-shared map). A map lists only the buildings its viewer may open: unlisted
ones for everyone who has the map, private ones for the org's people. Access mode only."""

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from backend.api import deps
from backend.api.access import ADMIN_ROLES, Viewer
from backend.api.maps import VISIBILITIES, OrgMap, new_token
from backend.api.routes.guide import listing_item
from backend.api.routes.orgs import SLUG, org_or_404, role_or_403, signed_in_or_401

router = APIRouter()


class NewMap(BaseModel):
    slug: str
    name: str
    visibility: str = "private"


class MapUpdate(BaseModel):
    name: str | None = None
    visibility: str | None = None


class MapBuilding(BaseModel):
    building: str
    on: bool = True  # false takes it off the map


def visibility_or_422(visibility: str) -> None:
    if visibility not in VISIBILITIES:
        raise HTTPException(422, f"visibility must be one of {', '.join(VISIBILITIES)}")


def name_or_422(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 120:
        raise HTTPException(422, "give the map a name (at most 120 characters)")
    return name


def map_or_404(slug: str, viewer: Viewer, token: str | None) -> tuple[OrgMap, str | None]:
    """The map and the viewer's role in its org, if the viewer may open it; else a 404, as if it did not exist."""
    if not deps.access.enabled:
        raise HTTPException(404, "access mode is off")
    row = deps.maps.get(slug)
    role = deps.access.role(viewer, row.org) if row else None
    if row is None or not (viewer.admin or role or row.opens_with(token)):
        raise HTTPException(404, f"unknown map {slug!r}")
    return row, role


def editable_or_403(viewer: Viewer, role: str | None) -> None:
    role_or_403(viewer, role, ADMIN_ROLES)


def map_payload(row: OrgMap, viewer: Viewer, role: str | None) -> dict:
    org = deps.access.store.org(row.org)
    owners = {building: access.org for building, access in deps.access.store.all_buildings().items() if access.org}
    buildings = [listing_item(deps.store.catalogue[building], owners.get(building)) for building in row.buildings
                 if deps.store.known(building) and deps.access.visible(viewer, building)]
    payload = {"slug": row.slug, "name": row.name, "org": org.to_dict() if org else {"slug": row.org},
               "visibility": row.visibility, "buildings": buildings, "layout": row.layout,
               "can_edit": viewer.admin or role in ADMIN_ROLES}
    if payload["can_edit"]:
        payload["token"] = row.token if row.visibility == "link" else None
    return payload


@router.post("/orgs/{org}/maps")
def create_map(org: str, body: NewMap, authorization: str | None = Header(None)) -> dict:
    viewer = signed_in_or_401(authorization)
    _, role = org_or_404(viewer, org)
    editable_or_403(viewer, role)
    slug = body.slug.strip().lower()
    if not SLUG.fullmatch(slug):
        raise HTTPException(422, "the address takes 1–40 lowercase letters, digits and inner hyphens")
    visibility_or_422(body.visibility)
    row = OrgMap(slug, org, name_or_422(body.name), body.visibility,
                 token=new_token() if body.visibility == "link" else None)
    if not deps.maps.insert(row):
        raise HTTPException(409, f"the address {slug!r} is taken")
    return map_payload(row, viewer, role)


@router.get("/orgs/{org}/maps")
def org_maps(org: str, authorization: str | None = Header(None)) -> list[dict]:
    viewer = signed_in_or_401(authorization)
    org_or_404(viewer, org)
    return [{"slug": row.slug, "name": row.name, "visibility": row.visibility, "buildings": len(row.buildings)}
            for row in deps.maps.of_org(org)]


@router.get("/maps/{slug}")
def get_map(slug: str, k: str | None = Query(None), authorization: str | None = Header(None)) -> dict:
    """The map with the buildings this viewer may open; anyone for a public map, `k` for a link-shared one."""
    viewer = deps.viewer_or_401(authorization)
    row, role = map_or_404(slug, viewer, k)
    return map_payload(row, viewer, role)


@router.put("/maps/{slug}")
def update_map(slug: str, body: MapUpdate, authorization: str | None = Header(None)) -> dict:
    viewer = signed_in_or_401(authorization)
    row, role = map_or_404(slug, viewer, None)
    editable_or_403(viewer, role)
    if body.name is not None:
        row.name = name_or_422(body.name)
    if body.visibility is not None:
        visibility_or_422(body.visibility)
        row.visibility = body.visibility
        if row.visibility == "link" and not row.token:
            row.token = new_token()
    deps.maps.put(row)
    return map_payload(row, viewer, role)


@router.post("/maps/{slug}/link")
def renew_link(slug: str, authorization: str | None = Header(None)) -> dict:
    """A new share key: the map becomes link-shared and the old link stops opening it."""
    viewer = signed_in_or_401(authorization)
    row, role = map_or_404(slug, viewer, None)
    editable_or_403(viewer, role)
    row.visibility, row.token = "link", new_token()
    deps.maps.put(row)
    return map_payload(row, viewer, role)


@router.put("/maps/{slug}/buildings")
def map_building(slug: str, body: MapBuilding, authorization: str | None = Header(None)) -> dict:
    """Put a building on the map (one of the org's own, or anyone's listed building) or take it off."""
    viewer = signed_in_or_401(authorization)
    row, role = map_or_404(slug, viewer, None)
    editable_or_403(viewer, role)
    if body.on and body.building not in row.buildings:
        if not deps.store.known(body.building):
            raise HTTPException(422, f"unknown building {body.building}; see GET /buildings")
        access = deps.access.store.building(body.building)
        if not (viewer.admin or access.org == row.org or access.listing == "listed"):
            raise HTTPException(403, "a map takes its organisation's own buildings and listed ones")
        row.buildings.append(body.building)
    elif not body.on:
        row.buildings = [building for building in row.buildings if building != body.building]
    deps.maps.put(row)
    return map_payload(row, viewer, role)


@router.delete("/maps/{slug}")
def delete_map(slug: str, authorization: str | None = Header(None)) -> dict:
    viewer = signed_in_or_401(authorization)
    row, role = map_or_404(slug, viewer, None)
    role_or_403(viewer, role, ("owner",))
    deps.maps.delete(row.slug)
    return {"deleted": row.slug}
