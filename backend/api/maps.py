"""An organisation's maps (docs/product/organizations.md, phase 2): a named set of buildings with its own address
(`?map=<slug>`) and visibility — `private` (the org's people), `link` (anyone with the share token: `&k=<token>`) or
`public` (anyone). A building may sit on several maps. The token is stored as is so editors can copy the link again; it
only opens the map, and a new one (POST /maps/{slug}/link) shuts out the old link.

Stores: `MemoryMaps` (one process, tests) or `PostgresMaps` (table `maps` in
supabase/migrations/20261029120000_maps.sql, when SUPABASE_DB_URL is set). Routes: backend/api/routes/maps.py."""

import secrets
import threading
from dataclasses import asdict, dataclass, field

from psycopg.types.json import Jsonb

from backend.api.persistence import PostgresConnection, db_url

VISIBILITIES = ("private", "link", "public")


def new_token() -> str:
    return secrets.token_urlsafe(16)


@dataclass
class OrgMap:
    slug: str
    org: str
    name: str
    visibility: str = "private"
    token: str | None = None  # the share link's key, made with the first `link` visibility
    buildings: list[str] = field(default_factory=list)  # in the order they were added
    layout: dict = field(default_factory=dict)  # phase 3: sites, their areas and places on the board

    def opens_with(self, token: str | None) -> bool:
        if self.visibility == "public":
            return True
        return self.visibility == "link" and bool(token and self.token) and secrets.compare_digest(token, self.token)


class MemoryMaps:
    def __init__(self) -> None:
        self.rows: dict[str, OrgMap] = {}
        self.lock = threading.Lock()

    def get(self, slug: str) -> OrgMap | None:
        with self.lock:
            row = self.rows.get(slug)
            return OrgMap(**{**asdict(row), "buildings": list(row.buildings)}) if row else None

    def of_org(self, org: str) -> list[OrgMap]:
        with self.lock:
            return sorted((m for m in self.rows.values() if m.org == org), key=lambda m: m.slug)

    def insert(self, row: OrgMap) -> bool:
        """False = the slug is taken."""
        with self.lock:
            if row.slug in self.rows:
                return False
            self.rows[row.slug] = row
            return True

    def put(self, row: OrgMap) -> None:
        with self.lock:
            self.rows[row.slug] = row

    def delete(self, slug: str) -> bool:
        with self.lock:
            return self.rows.pop(slug, None) is not None


class PostgresMaps(PostgresConnection):
    COLUMNS = "slug, org, name, visibility, token, buildings, layout"

    def get(self, slug: str) -> OrgMap | None:
        rows = self.execute(f"select {self.COLUMNS} from maps where slug = %s", (slug,))
        return OrgMap(*rows[0]) if rows else None

    def of_org(self, org: str) -> list[OrgMap]:
        return [OrgMap(*row) for row in self.execute(f"select {self.COLUMNS} from maps where org = %s order by slug",
                                                      (org,))]

    def insert(self, row: OrgMap) -> bool:
        rows = self.execute(
            f"insert into maps ({self.COLUMNS}) values (%s, %s, %s, %s, %s, %s, %s) on conflict (slug) do nothing "
            "returning slug", (row.slug, row.org, row.name, row.visibility, row.token, Jsonb(row.buildings),
                               Jsonb(row.layout)))
        return bool(rows)

    def put(self, row: OrgMap) -> None:
        self.execute(
            "update maps set name = %s, visibility = %s, token = %s, buildings = %s, layout = %s, updated_at = now() "
            "where slug = %s", (row.name, row.visibility, row.token, Jsonb(row.buildings), Jsonb(row.layout), row.slug))

    def delete(self, slug: str) -> bool:
        return bool(self.execute("delete from maps where slug = %s returning slug", (slug,)))


def maps_from_env() -> MemoryMaps | PostgresMaps:
    url = db_url()
    return PostgresMaps(url) if url else MemoryMaps()
