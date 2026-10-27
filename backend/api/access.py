"""Access mode (archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md): accounts, public / restricted spaces.

Off unless ACCESS_MODE=on; off = every viewer sees everything, exactly as before. On:

- A viewer is anonymous, a member (Supabase Auth user, invited by the admin, with access groups per building) or
  an admin (an account whose email is listed in ADMIN_EMAIL, comma-separated; rights over every building). The bearer token is checked with
  Supabase `GET /auth/v1/user` (cached for a minute), so no JWT secret lives in our code.
- Per building: a `public` flag (default true) and rules — by room_type and by space id (a space rule wins) — that
  restrict spaces to groups. The reserved group "public" makes a space public again (an exception to a room-type
  rule). No rules = everything public.
- `restricted_for` gives the space ids a viewer may not enter; the session then runs on a filtered copy of the
  building (backend/core/access.py, backend/api/sessions.py ensure_access).

Stores: `MemoryAccess` (one process) or `PostgresAccess` (tables in supabase/migrations/20261025200000_access.sql,
when SUPABASE_DB_URL is set)."""

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


@dataclass
class BuildingAccess:
    public: bool = True
    room_types: dict[str, list[str]] = field(default_factory=dict)  # room_type → groups
    spaces: dict[str, list[str]] = field(default_factory=dict)  # space id → groups (wins over room_type)

    def to_dict(self) -> dict:
        return {"public": self.public, "room_types": self.room_types, "spaces": self.spaces}

    @classmethod
    def from_dict(cls, data: dict) -> "BuildingAccess":
        def clean(rules: dict) -> dict[str, list[str]]:
            return {str(key): sorted({str(group).strip() for group in groups if str(group).strip()})
                    for key, groups in (rules or {}).items()}
        return cls(public=bool(data.get("public", True)), room_types=clean(data.get("room_types")),
                   spaces=clean(data.get("spaces")))

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


class MemoryAccess:
    def __init__(self) -> None:
        self.buildings: dict[str, BuildingAccess] = {}
        self.members: dict[tuple[str, str], Member] = {}
        self.prefs: dict[str, dict] = {}
        self.lock = threading.Lock()

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


class PostgresAccess(PostgresConnection):
    """Tables `access_buildings` (building, public, rules), `access_members` (user, building, groups) and
    `user_preferences` (user, preferences)."""

    def building(self, building: str) -> BuildingAccess:
        rows = self.execute("select public, rules from access_buildings where building = %s", (building,))
        if not rows:
            return BuildingAccess()
        return BuildingAccess.from_dict({"public": rows[0][0], **(rows[0][1] or {})})

    def set_building(self, building: str, access: BuildingAccess) -> None:
        rules = {"room_types": access.room_types, "spaces": access.spaces}
        self.execute(
            "insert into access_buildings (building, public, rules) values (%s, %s, %s) on conflict (building) do "
            "update set public = excluded.public, rules = excluded.rules, updated_at = now()",
            (building, access.public, Jsonb(rules)))

    def all_buildings(self) -> dict[str, BuildingAccess]:
        rows = self.execute("select building, public, rules from access_buildings", ())
        return {row[0]: BuildingAccess.from_dict({"public": row[1], **(row[2] or {})}) for row in rows}

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

    def visible(self, viewer: Viewer, building: str) -> bool:
        if not self.enabled or viewer.admin:
            return True
        if self.store.building(building).public:
            return True
        return bool(viewer.user_id and self.store.groups(viewer.user_id, building))

    def hidden_buildings(self, viewer: Viewer) -> set[str]:
        """Catalogue ids this viewer may not list (non-public buildings without a membership)."""
        if not self.enabled or viewer.admin:
            return set()
        mine = self.store.member_buildings(viewer.user_id) if viewer.user_id else {}
        return {building for building, access in self.store.all_buildings().items()
                if not access.public and not mine.get(building)}

    def restricted_for(self, viewer: Viewer, building: str, data: dict) -> frozenset[str]:
        if not self.enabled or viewer.admin:
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
