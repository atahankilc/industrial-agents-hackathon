"""Access mode (archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md): accounts, public / restricted spaces.

Off unless ACCESS_MODE=on; off = every viewer sees everything, exactly as before. On:

- A viewer is anonymous, a member (Supabase Auth user, invited by the admin, with access groups per building) or
  an admin (an account whose email is listed in ADMIN_EMAIL, comma-separated; rights over every building). The bearer token is checked with
  Supabase `GET /auth/v1/user` (cached for a minute), so no JWT secret lives in our code.
- Per building: a listing — listed (default; on the main map), unlisted (anyone may open it, only its org and
  members find it) or private (only they may open it) — and rules — by room_type and by space id (a space rule
  wins) — that restrict spaces to groups. The reserved group "public" makes a space public again (an exception to a
  room-type rule). No rules = everything public.
- Organisations (docs/product/organizations.md): a building may belong to one; its editors and owners administer
  it like the admin does, its viewers may open its private buildings. An org lists a building on the main map only
  once an admin has verified it. Buildings without an org belong to the platform (the admins).
- `restricted_for` gives the space ids a viewer may not enter; the session then runs on a filtered copy of the
  building (backend/core/access.py, backend/api/sessions.py ensure_access).

Stores: `MemoryAccess` (one process) or `PostgresAccess` (tables in supabase/migrations/20261025200000_access.sql
and 20261028120000_orgs.sql, when SUPABASE_DB_URL is set)."""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from psycopg.types.json import Jsonb

from backend.api.persistence import PostgresConnection, db_url

PUBLIC = "public"  # reserved group: everyone
TOKEN_TTL_S = 60


def admin_emails() -> set[str]:
    """ADMIN_EMAIL: one or more admin emails, comma-separated (Atahan, 2026-10-25: two admins)."""
    return {email.strip().lower() for email in os.environ.get("ADMIN_EMAIL", "").split(",") if email.strip()}


def access_mode() -> bool:
    return os.environ.get("ACCESS_MODE", "off").strip().lower() in ("on", "1", "true", "yes")


@dataclass(frozen=True)
class Viewer:
    user_id: str | None = None
    email: str | None = None
    admin: bool = False

    @property
    def anonymous(self) -> bool:
        return self.user_id is None

    def to_dict(self) -> dict:
        return {"user_id": self.user_id, "email": self.email, "admin": self.admin, "anonymous": self.anonymous}


ANONYMOUS = Viewer()


class AuthError(Exception):
    """A bearer token Supabase doesn't accept (expired, forged)."""


class AuthUnavailable(Exception):
    """Supabase Auth isn't configured or can't be reached."""


class SupabaseAuth:
    """Bearer token → Viewer, and the admin's invite links. Reads SUPABASE_URL, SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY and ADMIN_EMAIL when first used."""

    def __init__(self) -> None:
        self.cache: dict[str, tuple[float, Viewer]] = {}
        self.lock = threading.Lock()

    @staticmethod
    def settings() -> tuple[str, str, str]:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        anon = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not anon:
            raise AuthUnavailable("SUPABASE_URL / SUPABASE_ANON_KEY are not set")
        return url, anon, os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    def request(self, method: str, path: str, headers: dict, body: dict | None = None) -> dict:
        url, _, _ = self.settings()
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url + path, data=data, method=method,
                                         headers={**headers, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            if error.code in (401, 403):
                raise AuthError(detail) from None
            raise AuthUnavailable(f"{error.code} {detail}") from None
        except urllib.error.URLError as error:
            raise AuthUnavailable(str(error.reason)) from None

    def viewer(self, authorization: str | None) -> Viewer:
        if not authorization or not authorization.lower().startswith("bearer "):
            return ANONYMOUS
        token = authorization[7:].strip()
        now = time.monotonic()
        with self.lock:
            hit = self.cache.get(token)
            if hit and hit[0] > now:
                return hit[1]
        _, anon, _ = self.settings()
        user = self.request("GET", "/auth/v1/user", {"apikey": anon, "Authorization": f"Bearer {token}"})
        email = (user.get("email") or "").lower()
        viewer = Viewer(user_id=user["id"], email=email, admin=bool(email) and email in admin_emails())
        with self.lock:
            self.cache[token] = (now + TOKEN_TTL_S, viewer)
        return viewer

    def invite(self, email: str, redirect_to: str | None = None) -> tuple[str, str]:
        """(user id, sign-in link) for `email` without sending mail: an invite for a new account, a magic link
        for an existing one. Needs the service-role key."""
        _, _, service = self.settings()
        if not service:
            raise AuthUnavailable("SUPABASE_SERVICE_ROLE_KEY is not set")
        headers = {"apikey": service, "Authorization": f"Bearer {service}"}
        body = {"email": email, **({"redirect_to": redirect_to} if redirect_to else {})}
        try:
            user = self.request("POST", "/auth/v1/admin/generate_link", headers, {"type": "invite", **body})
        except AuthUnavailable as error:
            if "422" not in str(error) and "exists" not in str(error):
                raise
            user = self.request("POST", "/auth/v1/admin/generate_link", headers, {"type": "magiclink", **body})
        link = user.get("action_link") or (user.get("properties") or {}).get("action_link")
        user_id = user.get("id") or (user.get("user") or {}).get("id")
        if not link or not user_id:
            raise AuthUnavailable("Supabase returned no link")
        return user_id, link


# ---------- rules ----------


LISTINGS = ("listed", "unlisted", "private")  # on the main map / opened by link or the org's map / members only


@dataclass
class BuildingAccess:
    listing: str = "listed"
    room_types: dict[str, list[str]] = field(default_factory=dict)  # room_type → groups
    spaces: dict[str, list[str]] = field(default_factory=dict)  # space id → groups (wins over room_type)
    org: str | None = None  # the owning organisation's slug; None = the platform (the admins)

    @property
    def public(self) -> bool:
        """Anyone may open it (listed or unlisted)."""
        return self.listing != "private"

    def to_dict(self) -> dict:
        return {"public": self.public, "listing": self.listing, "org": self.org, "room_types": self.room_types,
                "spaces": self.spaces}

    @classmethod
    def from_dict(cls, data: dict) -> "BuildingAccess":
        """`listing` wins; without it the older `public` flag (true → listed, false → private)."""
        def clean(rules: dict) -> dict[str, list[str]]:
            return {str(key): sorted({str(group).strip() for group in groups if str(group).strip()})
                    for key, groups in (rules or {}).items()}
        listing = data.get("listing") or ("listed" if data.get("public", True) else "private")
        if listing not in LISTINGS:
            raise ValueError(f"listing must be one of {', '.join(LISTINGS)}")
        return cls(listing=listing, room_types=clean(data.get("room_types")), spaces=clean(data.get("spaces")),
                   org=data.get("org") or None)

    def groups_for(self, space: dict) -> list[str] | None:
        """The groups that may enter `space`, or None if it is public."""
        groups = self.spaces.get(space["id"])
        if groups is None:
            groups = self.room_types.get(space.get("room_type") or "")
        if groups is None or PUBLIC in groups:
            return None
        return groups


@dataclass
class Member:
    user_id: str
    email: str
    building: str
    groups: list[str]

    def to_dict(self) -> dict:
        return {"user_id": self.user_id, "email": self.email, "building": self.building, "groups": self.groups}


# ---------- organisations (docs/product/organizations.md) ----------

ROLES = ("viewer", "editor", "owner")  # opens its private buildings / also administers them / also its people
ADMIN_ROLES = ("editor", "owner")


@dataclass
class Org:
    slug: str
    name: str
    verified: bool = False  # set by an admin; only a verified org may list a building on the main map
    created_by: str | None = None

    def to_dict(self) -> dict:
        return {"slug": self.slug, "name": self.name, "verified": self.verified}


@dataclass
class OrgMember:
    org: str
    user_id: str
    email: str
    role: str | None  # None removes the membership

    def to_dict(self) -> dict:
        return {"org": self.org, "user_id": self.user_id, "email": self.email, "role": self.role}


class MemoryAccess:
    def __init__(self) -> None:
        self.buildings: dict[str, BuildingAccess] = {}
        self.members: dict[tuple[str, str], Member] = {}
        self.prefs: dict[str, dict] = {}
        self.orgs: dict[str, Org] = {}
        self.org_people: dict[tuple[str, str], OrgMember] = {}
        self.lock = threading.Lock()

    def org(self, slug: str) -> Org | None:
        with self.lock:
            org = self.orgs.get(slug)
            return Org(**vars(org)) if org else None

    def all_orgs(self) -> list[Org]:
        with self.lock:
            return sorted((Org(**vars(org)) for org in self.orgs.values()), key=lambda org: org.slug)

    def insert_org(self, org: Org, owner: OrgMember) -> bool:
        """False = the slug is taken."""
        with self.lock:
            if org.slug in self.orgs:
                return False
            self.orgs[org.slug] = org
            self.org_people[(org.slug, owner.user_id)] = owner
            return True

    def set_org(self, org: Org) -> None:
        with self.lock:
            self.orgs[org.slug] = org

    def org_role(self, user_id: str, slug: str) -> str | None:
        with self.lock:
            member = self.org_people.get((slug, user_id))
            return member.role if member else None

    def user_orgs(self, user_id: str) -> dict[str, str]:
        with self.lock:
            return {m.org: m.role for (_, uid), m in self.org_people.items() if uid == user_id}

    def org_members(self, slug: str) -> list[OrgMember]:
        with self.lock:
            return sorted((m for m in self.org_people.values() if m.org == slug), key=lambda m: m.email)

    def set_org_member(self, member: OrgMember) -> None:
        with self.lock:
            if member.role:
                self.org_people[(member.org, member.user_id)] = member
            else:
                self.org_people.pop((member.org, member.user_id), None)

    def building(self, building: str) -> BuildingAccess:
        with self.lock:
            return BuildingAccess.from_dict(self.buildings.get(building, BuildingAccess()).to_dict())

    def set_building(self, building: str, access: BuildingAccess) -> None:
        with self.lock:
            self.buildings[building] = access

    def all_buildings(self) -> dict[str, BuildingAccess]:
        with self.lock:
            return dict(self.buildings)

    def groups(self, user_id: str, building: str) -> list[str]:
        with self.lock:
            member = self.members.get((user_id, building))
            return list(member.groups) if member else []

    def member_buildings(self, user_id: str) -> dict[str, list[str]]:
        with self.lock:
            return {m.building: list(m.groups) for (uid, _), m in self.members.items() if uid == user_id}

    def list_members(self, building: str) -> list[Member]:
        with self.lock:
            return [m for m in self.members.values() if m.building == building]

    def preferences(self, user_id: str) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.prefs.get(user_id, {})))

    def set_preferences(self, user_id: str, preferences: dict) -> None:
        with self.lock:
            self.prefs[user_id] = json.loads(json.dumps(preferences))

    def set_member(self, member: Member) -> None:
        with self.lock:
            if member.groups:
                self.members[(member.user_id, member.building)] = member
            else:
                self.members.pop((member.user_id, member.building), None)


def building_row(public: bool, listing: str | None, org: str | None, rules: dict | None) -> BuildingAccess:
    """An `access_buildings` row. `public` is still written (code deployed before the orgs migration reads and writes
    only it), so a `listing` that disagrees with it was left behind by such a write and `public` wins."""
    if listing is None or (listing != "private") != public:
        listing = "listed" if public else "private"
    return BuildingAccess.from_dict({**(rules or {}), "listing": listing, "org": org})


class PostgresAccess(PostgresConnection):
    """Tables `access_buildings` (building, public, listing, org, rules), `access_members` (user, building, groups),
    `user_preferences` (user, preferences), `orgs` and `org_members`."""

    def building(self, building: str) -> BuildingAccess:
        rows = self.execute("select public, listing, org, rules from access_buildings where building = %s",
                            (building,))
        return building_row(*rows[0]) if rows else BuildingAccess()

    def set_building(self, building: str, access: BuildingAccess) -> None:
        rules = {"room_types": access.room_types, "spaces": access.spaces}
        self.execute(
            "insert into access_buildings (building, public, listing, org, rules) values (%s, %s, %s, %s, %s) "
            "on conflict (building) do update set public = excluded.public, listing = excluded.listing, "
            "org = excluded.org, rules = excluded.rules, updated_at = now()",
            (building, access.public, access.listing, access.org, Jsonb(rules)))

    def all_buildings(self) -> dict[str, BuildingAccess]:
        rows = self.execute("select building, public, listing, org, rules from access_buildings", ())
        return {row[0]: building_row(*row[1:]) for row in rows}

    def org(self, slug: str) -> Org | None:
        rows = self.execute("select slug, name, verified, created_by from orgs where slug = %s", (slug,))
        return Org(*rows[0]) if rows else None

    def all_orgs(self) -> list[Org]:
        return [Org(*row) for row in self.execute("select slug, name, verified, created_by from orgs order by slug", ())]

    def insert_org(self, org: Org, owner: OrgMember) -> bool:
        rows = self.execute(
            "with made as (insert into orgs (slug, name, verified, created_by) values (%s, %s, %s, %s) "
            "on conflict (slug) do nothing returning slug) "
            "insert into org_members (org, user_id, email, role) select slug, %s, %s, %s from made returning org",
            (org.slug, org.name, org.verified, org.created_by, owner.user_id, owner.email, owner.role))
        return bool(rows)

    def set_org(self, org: Org) -> None:
        self.execute("update orgs set name = %s, verified = %s, updated_at = now() where slug = %s",
                     (org.name, org.verified, org.slug))

    def org_role(self, user_id: str, slug: str) -> str | None:
        rows = self.execute("select role from org_members where user_id = %s and org = %s", (user_id, slug))
        return rows[0][0] if rows else None

    def user_orgs(self, user_id: str) -> dict[str, str]:
        return dict(self.execute("select org, role from org_members where user_id = %s", (user_id,)))

    def org_members(self, slug: str) -> list[OrgMember]:
        rows = self.execute("select org, user_id, email, role from org_members where org = %s order by email", (slug,))
        return [OrgMember(row[0], str(row[1]), row[2], row[3]) for row in rows]

    def set_org_member(self, member: OrgMember) -> None:
        if not member.role:
            self.execute("delete from org_members where org = %s and user_id = %s", (member.org, member.user_id))
            return
        self.execute(
            "insert into org_members (org, user_id, email, role) values (%s, %s, %s, %s) on conflict (org, user_id) "
            "do update set email = excluded.email, role = excluded.role, updated_at = now()",
            (member.org, member.user_id, member.email, member.role))

    def groups(self, user_id: str, building: str) -> list[str]:
        rows = self.execute("select groups from access_members where user_id = %s and building = %s",
                            (user_id, building))
        return list(rows[0][0]) if rows else []

    def member_buildings(self, user_id: str) -> dict[str, list[str]]:
        rows = self.execute("select building, groups from access_members where user_id = %s", (user_id,))
        return {row[0]: list(row[1]) for row in rows}

    def list_members(self, building: str) -> list[Member]:
        rows = self.execute("select user_id, email, building, groups from access_members where building = %s "
                            "order by email", (building,))
        return [Member(str(row[0]), row[1], row[2], list(row[3])) for row in rows]

    def preferences(self, user_id: str) -> dict:
        rows = self.execute("select preferences from user_preferences where user_id = %s", (user_id,))
        return rows[0][0] if rows else {}

    def set_preferences(self, user_id: str, preferences: dict) -> None:
        self.execute(
            "insert into user_preferences (user_id, preferences) values (%s, %s) on conflict (user_id) do update "
            "set preferences = excluded.preferences, updated_at = now()", (user_id, Jsonb(preferences)))

    def set_member(self, member: Member) -> None:
        if not member.groups:
            self.execute("delete from access_members where user_id = %s and building = %s",
                         (member.user_id, member.building))
            return
        self.execute(
            "insert into access_members (user_id, email, building, groups) values (%s, %s, %s, %s) "
            "on conflict (user_id, building) do update set email = excluded.email, groups = excluded.groups, "
            "updated_at = now()", (member.user_id, member.email, member.building, Jsonb(member.groups)))


def store_from_env() -> MemoryAccess | PostgresAccess:
    url = db_url()
    return PostgresAccess(url) if url else MemoryAccess()


# ---------- decisions ----------


class Access:
    """What a viewer may see. With access mode off every answer is "everything"."""

    def __init__(self, store: MemoryAccess | PostgresAccess | None = None, auth: SupabaseAuth | None = None,
                 enabled: bool | None = None) -> None:
        self.store = store if store is not None else store_from_env()
        self.auth = auth if auth is not None else SupabaseAuth()
        self.forced = enabled

    @property
    def enabled(self) -> bool:
        return access_mode() if self.forced is None else self.forced

    def viewer(self, authorization: str | None) -> Viewer:
        if not self.enabled:
            return ANONYMOUS
        return self.auth.viewer(authorization)

    def role(self, viewer: Viewer, org: str | None) -> str | None:
        """The viewer's role in `org` (None: not a member, anonymous, or no org)."""
        if not org or not viewer.user_id:
            return None
        return self.store.org_role(viewer.user_id, org)

    def can_admin(self, viewer: Viewer, building: str) -> bool:
        """Its rules, members and objects: an admin (every building) or an editor / owner of the owning org."""
        if viewer.admin:
            return True
        return self.role(viewer, self.store.building(building).org) in ADMIN_ROLES

    def visible(self, viewer: Viewer, building: str) -> bool:
        """May open it: anyone unless private; then the admins, its org's people and its invited members."""
        if not self.enabled or viewer.admin:
            return True
        access = self.store.building(building)
        if access.public:
            return True
        return bool(viewer.user_id and (self.role(viewer, access.org) or self.store.groups(viewer.user_id, building)))

    def hidden_buildings(self, viewer: Viewer) -> set[str]:
        """Catalogue ids this viewer may not list, nor find from a neighbour: private and unlisted buildings, unless
        the viewer is in the owning org or a member of the building."""
        if not self.enabled or viewer.admin:
            return set()
        mine = self.store.member_buildings(viewer.user_id) if viewer.user_id else {}
        orgs = self.store.user_orgs(viewer.user_id) if viewer.user_id else {}
        return {building for building, access in self.store.all_buildings().items()
                if access.listing != "listed" and not mine.get(building) and access.org not in orgs}

    def restricted_for(self, viewer: Viewer, building: str, data: dict) -> frozenset[str]:
        if not self.enabled or self.can_admin(viewer, building):
            return frozenset()
        access = self.store.building(building)
        if not access.room_types and not access.spaces:
            return frozenset()
        groups = set(self.store.groups(viewer.user_id, building)) if viewer.user_id else set()
        restricted = set()
        for space in data["spaces"]:
            allowed = access.groups_for(space)
            if allowed is not None and not groups & set(allowed):
                restricted.add(space["id"])
        return frozenset(restricted)
