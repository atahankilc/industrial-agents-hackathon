"""Edit-mode drafts and saved buildings (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §3).

A draft is a base catalogue building + steps of edit ops (core/edits.py), stored after every change, so it survives
a restart. Saving stores the materialised building as `user/<slug>` and adds it to the shared catalogue, so
sessions, the Guide and the plan view use it like any dataset building. Saved buildings are visible to everyone.

Where it lives (a `DraftBackend`): Postgres (`PostgresDraftBackend`, tables in supabase/migrations/) when
SUPABASE_DB_URL is set and GUIDE_PERSIST is not `off` — the deployed app, where serverless instances share no memory
and the filesystem is read-only; otherwise files under `data/user/` (`FileDraftBackend`): `.drafts/<id>.json`,
`.drafts/<id>.builder.json` and `<slug>/{building.json,draft.json}`. `MemoryDraftBackend` is the Postgres contract in
one process, for tests: several DraftStores on one instance behave like serverless instances on one database.

Every change is *reload if the stored version moved → apply → save if the version is still the one loaded*
(optimistic, like backend/persistence.py); a lost race is redone on the new state up to SAVE_ATTEMPTS times in all,
then raises `Conflict` (HTTP 409). Saved slugs are claimed atomically (`insert_building` returns False when taken → `-2`, `-3`, …). The
catalogue picks up buildings saved by other instances on `refresh` (at most CATALOGUE_TTL_S old, forced when an
unknown id is asked for). Draft ids are uuid4 hex checked against a regex; slugs are built from the name by us; both
are only ever SQL parameters or path parts after those checks. The dataset under `data/train|dev|test` is only read."""

import copy
import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from backend.persistence import Conflict, PostgresConnection, db_url
from core.building_map import BuildingMap
from core.plan_import.reference import strip_references
from core.edits import EditError, apply_op, apply_steps
from core.floorplan import export_plan
from core.validate import validate

DRAFT_ID = re.compile(r"^[0-9a-f]{32}$")
USER_SPLIT = "user"
IMPORT_PREFIX = "import/"  # private base of a draft made by the Creator (plan import), not in the catalogue
SAVE_ATTEMPTS = 3  # tries of one draft change against other instances' saves before Conflict
CATALOGUE_TTL_S = 5.0  # how stale this instance's list of saved buildings may get before /buildings reloads it


@dataclass
class Draft:
    id: str
    base: str
    name: str
    steps: list[list[dict]] = field(default_factory=list)
    version: int = 0  # bumped on every change; cache key (undo + new op keeps the step count)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60].strip("-") or "building"


# ---------- where drafts live ----------


class DraftBackend(Protocol):
    def draft_version(self, draft_id: str) -> int | None: ...
    def load_draft(self, draft_id: str) -> Draft | None: ...
    def insert_draft(self, draft: Draft) -> None: ...
    def save_draft(self, draft: Draft, loaded_version: int) -> None: ...  # raises Conflict
    def builder_version(self, draft_id: str) -> int: ...  # 0 = no Builder stored
    def load_builder(self, draft_id: str) -> tuple[dict | None, int]: ...
    def save_builder(self, draft_id: str, state: dict, loaded_version: int) -> int: ...  # raises Conflict
    def insert_building(self, slug: str, name: str, base: str, building: dict, steps: list) -> bool: ...  # False = taken
    def saved_buildings(self) -> list[dict]: ...  # [{"slug", "name"}]
    def load_building(self, slug: str) -> dict | None: ...
    def building_path(self, slug: str) -> Path | None: ...  # directory of a saved building, if it is a file
    def delete_building(self, slug: str) -> bool: ...  # False = no such building
    def insert_import(self, import_id: str, building: dict) -> None: ...
    def load_import(self, import_id: str) -> dict | None: ...


class FileDraftBackend:
    """Local directory (default data/user/, gitignored); one process, so a lock makes the version checks atomic."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.lock = threading.Lock()

    def draft_file(self, draft_id: str, suffix: str = "") -> Path:
        return self.root / ".drafts" / f"{draft_id}{suffix}.json"

    def write(self, file: Path, data: object) -> None:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(data), encoding="utf-8")

    def draft_version(self, draft_id: str) -> int | None:
        draft = self.load_draft(draft_id)
        return None if draft is None else draft.version

    def load_draft(self, draft_id: str) -> Draft | None:
        file = self.draft_file(draft_id)
        return Draft(**json.loads(file.read_text(encoding="utf-8"))) if file.exists() else None

    def insert_draft(self, draft: Draft) -> None:
        self.write(self.draft_file(draft.id), asdict(draft))

    def save_draft(self, draft: Draft, loaded_version: int) -> None:
        with self.lock:
            if self.draft_version(draft.id) != loaded_version:
                raise Conflict(draft.id)
            self.write(self.draft_file(draft.id), asdict(draft))

    def builder_version(self, draft_id: str) -> int:
        return self.load_builder(draft_id)[1]

    def load_builder(self, draft_id: str) -> tuple[dict | None, int]:
        file = self.draft_file(draft_id, ".builder")
        if not file.exists():
            return None, 0
        stored = json.loads(file.read_text(encoding="utf-8"))
        return stored["state"], stored["version"]

    def save_builder(self, draft_id: str, state: dict, loaded_version: int) -> int:
        with self.lock:
            if self.builder_version(draft_id) != loaded_version:
                raise Conflict(draft_id)
            self.write(self.draft_file(draft_id, ".builder"), {"state": state, "version": loaded_version + 1})
            return loaded_version + 1

    def insert_building(self, slug: str, name: str, base: str, building: dict, steps: list) -> bool:
        try:
            (self.root / slug).mkdir(parents=True)
        except FileExistsError:
            return False
        (self.root / slug / "building.json").write_text(json.dumps(building, indent=1), encoding="utf-8")
        (self.root / slug / "draft.json").write_text(json.dumps({"base": base, "name": name, "steps": steps}),
                                                     encoding="utf-8")
        return True

    def saved_buildings(self) -> list[dict]:
        return [{"slug": file.parent.name, "name": json.loads(file.read_text(encoding="utf-8"))["building"]["name"]}
                for file in sorted(self.root.glob("*/building.json"))]

    def load_building(self, slug: str) -> dict | None:
        file = self.root / slug / "building.json"
        return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None

    def building_path(self, slug: str) -> Path | None:
        return self.root / slug

    def delete_building(self, slug: str) -> bool:
        folder = self.root / slug
        if not (folder / "building.json").exists():
            return False
        trash = self.root / ".deleted"  # kept out of the listing, not erased: a deleted building can be put back
        trash.mkdir(exist_ok=True)
        folder.rename(trash / f"{slug}-{uuid.uuid4().hex[:8]}")
        return True

    def insert_import(self, import_id: str, building: dict) -> None:
        self.write(self.root / ".imports" / f"{import_id}.json", building)

    def load_import(self, import_id: str) -> dict | None:
        file = self.root / ".imports" / f"{import_id}.json"
        return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


class MemoryDraftBackend:
    """Same contract as PostgresDraftBackend, in one process; rows go through JSON like they would in the DB."""

    def __init__(self) -> None:
        self.drafts: dict[str, str] = {}
        self.builders: dict[str, tuple[str, int]] = {}
        self.buildings: dict[str, tuple[str, str]] = {}  # slug → (name, building JSON)
        self.imports: dict[str, str] = {}  # import id → building JSON
        self.lock = threading.Lock()

    def draft_version(self, draft_id: str) -> int | None:
        draft = self.load_draft(draft_id)
        return None if draft is None else draft.version

    def load_draft(self, draft_id: str) -> Draft | None:
        row = self.drafts.get(draft_id)
        return None if row is None else Draft(**json.loads(row))

    def insert_draft(self, draft: Draft) -> None:
        with self.lock:
            self.drafts[draft.id] = json.dumps(asdict(draft))

    def save_draft(self, draft: Draft, loaded_version: int) -> None:
        with self.lock:
            if self.draft_version(draft.id) != loaded_version:
                raise Conflict(draft.id)
            self.drafts[draft.id] = json.dumps(asdict(draft))

    def builder_version(self, draft_id: str) -> int:
        return self.builders.get(draft_id, (None, 0))[1]

    def load_builder(self, draft_id: str) -> tuple[dict | None, int]:
        state, version = self.builders.get(draft_id, (None, 0))
        return (None if state is None else json.loads(state)), version

    def save_builder(self, draft_id: str, state: dict, loaded_version: int) -> int:
        with self.lock:
            if draft_id not in self.drafts or self.builder_version(draft_id) != loaded_version:
                raise Conflict(draft_id)
            self.builders[draft_id] = (json.dumps(state), loaded_version + 1)
            return loaded_version + 1

    def insert_building(self, slug: str, name: str, base: str, building: dict, steps: list) -> bool:
        with self.lock:
            if slug in self.buildings:
                return False
            self.buildings[slug] = (name, json.dumps(building))
            return True

    def saved_buildings(self) -> list[dict]:
        return [{"slug": slug, "name": name} for slug, (name, _) in list(self.buildings.items())]

    def load_building(self, slug: str) -> dict | None:
        row = self.buildings.get(slug)
        return None if row is None else json.loads(row[1])

    def building_path(self, slug: str) -> Path | None:
        return None

    def delete_building(self, slug: str) -> bool:
        with self.lock:
            return self.buildings.pop(slug, None) is not None

    def insert_import(self, import_id: str, building: dict) -> None:
        with self.lock:
            self.imports[import_id] = json.dumps(building)

    def load_import(self, import_id: str) -> dict | None:
        row = self.imports.get(import_id)
        return None if row is None else json.loads(row)


class PostgresDraftBackend(PostgresConnection):
    """Tables `builder_drafts` and `saved_buildings` (supabase/migrations/20261025120000_builder_drafts.sql) and
    `builder_imports` (20261025180000_builder_imports.sql)."""

    def draft_version(self, draft_id: str) -> int | None:
        rows = self.execute("select version from builder_drafts where id = %s", (draft_id,))
        return rows[0][0] if rows else None

    def load_draft(self, draft_id: str) -> Draft | None:
        rows = self.execute("select id, base, name, steps, version from builder_drafts where id = %s", (draft_id,))
        return Draft(*rows[0]) if rows else None

    def insert_draft(self, draft: Draft) -> None:
        self.execute("insert into builder_drafts (id, base, name, steps, version) values (%s, %s, %s, %s, %s)",
                     (draft.id, draft.base, draft.name, Jsonb(draft.steps), draft.version))

    def save_draft(self, draft: Draft, loaded_version: int) -> None:
        rows = self.execute(
            "update builder_drafts set name = %s, steps = %s, version = %s, updated_at = now() "
            "where id = %s and version = %s returning version",
            (draft.name, Jsonb(draft.steps), draft.version, draft.id, loaded_version))
        if not rows:
            raise Conflict(draft.id)

    def builder_version(self, draft_id: str) -> int:
        rows = self.execute("select builder_version from builder_drafts where id = %s", (draft_id,))
        return rows[0][0] if rows else 0

    def load_builder(self, draft_id: str) -> tuple[dict | None, int]:
        rows = self.execute("select builder, builder_version from builder_drafts where id = %s", (draft_id,))
        return (rows[0][0], rows[0][1]) if rows else (None, 0)

    def save_builder(self, draft_id: str, state: dict, loaded_version: int) -> int:
        rows = self.execute(
            "update builder_drafts set builder = %s, builder_version = builder_version + 1, updated_at = now() "
            "where id = %s and builder_version = %s returning builder_version",
            (Jsonb(state), draft_id, loaded_version))
        if not rows:
            raise Conflict(draft_id)
        return rows[0][0]

    def insert_building(self, slug: str, name: str, base: str, building: dict, steps: list) -> bool:
        rows = self.execute(
            "insert into saved_buildings (slug, name, base, building, steps) values (%s, %s, %s, %s, %s) "
            "on conflict (slug) do nothing returning slug", (slug, name, base, Jsonb(building), Jsonb(steps)))
        return bool(rows)

    def saved_buildings(self) -> list[dict]:
        rows = self.execute("select slug, name from saved_buildings order by created_at, slug", ())
        return [{"slug": slug, "name": name} for slug, name in rows]

    def load_building(self, slug: str) -> dict | None:
        rows = self.execute("select building from saved_buildings where slug = %s", (slug,))
        return rows[0][0] if rows else None

    def building_path(self, slug: str) -> Path | None:
        return None

    def delete_building(self, slug: str) -> bool:
        return bool(self.execute("delete from saved_buildings where slug = %s returning slug", (slug,)))

    def insert_import(self, import_id: str, building: dict) -> None:
        self.execute("insert into builder_imports (id, building) values (%s, %s)", (import_id, Jsonb(building)))

    def load_import(self, import_id: str) -> dict | None:
        rows = self.execute("select building from builder_imports where id = %s", (import_id,))
        return rows[0][0] if rows else None


def backend_from_env(root: Path) -> DraftBackend:
    url = db_url()
    return PostgresDraftBackend(url) if url else FileDraftBackend(root)


# ---------- the store ----------


class DraftStore:
    def __init__(self, source: Path | DraftBackend, catalogue: dict[str, dict]) -> None:
        """`source`: a directory (FileDraftBackend) or any DraftBackend."""
        self.backend: DraftBackend = FileDraftBackend(source) if isinstance(source, (str, Path)) else source
        self.catalogue = catalogue
        self.lock = threading.Lock()  # the dicts and the catalogue
        self.draft_locks: dict[str, threading.Lock] = {}  # one per draft: serialises this instance's changes
        self.drafts: dict[str, Draft] = {}
        self.cache: dict[tuple[str, int], dict] = {}
        self.bases: dict[str, dict] = {}
        self.refreshed = float("-inf")
        self.refresh(quiet=True)  # the database being down must not stop the app from starting

    # ---------- lookup ----------

    def register(self, slug: str, name: str) -> str:
        building_id = f"{USER_SPLIT}/{slug}"
        entry = {"id": building_id, "split": USER_SPLIT, "name": name, "source": "saved", "kind": "saved"}
        if (path := self.backend.building_path(slug)) is not None:
            entry["path"] = path
        location = ((self.backend.load_building(slug) or {}).get("building") or {}).get("location")
        if location:  # a building placed on the map (core/geoplace.py)
            entry["location"] = location
            if location.get("supersedes"):  # re-saved: the older save keeps its entry but leaves the map
                older = self.catalogue.get(f"{USER_SPLIT}/{location['supersedes']}")
                if older is not None:
                    older["superseded"] = True
        self.catalogue[building_id] = entry
        return building_id

    def delete(self, building_id: str) -> bool:
        """Remove a saved building (user/<slug>) from the store and the catalogue; the version it superseded, if
        any, comes back to the map. False when there is no such saved building."""
        if not building_id.startswith(f"{USER_SPLIT}/"):
            return False
        slug = building_id.removeprefix(f"{USER_SPLIT}/")
        location = ((self.backend.load_building(slug) or {}).get("building") or {}).get("location") or {}
        if not self.backend.delete_building(slug):
            return False
        with self.lock:
            self.catalogue.pop(building_id, None)
            self.bases.pop(building_id, None)
            older = self.catalogue.get(f"{USER_SPLIT}/{location.get('supersedes')}")
            if older is not None:
                older.pop("superseded", None)
        return True

    def refresh(self, max_age: float = CATALOGUE_TTL_S, quiet: bool = False) -> None:
        """Add buildings saved since the last refresh (by any instance) to the catalogue. `quiet`: a database error
        leaves the catalogue as it is instead of raising (the dataset buildings keep working)."""
        if time.monotonic() - self.refreshed < max_age:
            return
        try:
            saved = self.backend.saved_buildings()
        except psycopg.Error:
            if quiet:
                return
            raise
        with self.lock:
            for item in saved:
                if f"{USER_SPLIT}/{item['slug']}" not in self.catalogue:
                    self.register(item["slug"], item["name"])
        self.refreshed = time.monotonic()

    @staticmethod
    def import_id(base: str) -> str | None:
        """The import id of a private import base, None if `base` is not one (or not a well-formed one)."""
        if not base.startswith(IMPORT_PREFIX):
            return None
        import_id = base.removeprefix(IMPORT_PREFIX)
        return import_id if DRAFT_ID.match(import_id) else ""

    def known(self, building_id: str) -> bool:
        if (import_id := self.import_id(building_id)) is not None:
            if not import_id:
                return False
            if building_id in self.bases:
                return True
            building = self.backend.load_import(import_id)
            if building is not None:
                self.bases[building_id] = building
            return building is not None
        if building_id not in self.catalogue:
            self.refresh(max_age=0)
        return building_id in self.catalogue

    def base_building(self, base: str) -> dict:
        """A catalogue building's data (cached: dataset files and saved buildings never change)."""
        if base not in self.bases and self.import_id(base):
            if not self.known(base):
                raise KeyError(base)
        if base not in self.bases:
            entry = self.catalogue[base]
            if "path" in entry:
                data = json.loads((Path(entry["path"]) / "building.json").read_text(encoding="utf-8"))
            else:
                data = self.backend.load_building(base.removeprefix(f"{USER_SPLIT}/"))
                if data is None:
                    raise KeyError(base)
            self.bases[base] = data
        return self.bases[base]

    def draft_lock(self, draft_id: str) -> threading.Lock:
        with self.lock:
            return self.draft_locks.setdefault(draft_id, threading.Lock())

    def get(self, draft_id: str) -> Draft | None:
        if not DRAFT_ID.match(draft_id):
            return None
        with self.draft_lock(draft_id):
            cached = self.drafts.get(draft_id)
            if cached is not None:
                self.sync(cached)
                return cached
            draft = self.backend.load_draft(draft_id)
            if draft is None or not self.known(draft.base):
                return None
            with self.lock:
                self.drafts[draft_id] = draft
            return draft

    def sync(self, draft: Draft) -> None:
        """Bring `draft` (in place) to the stored version if another instance changed it. Hold its draft lock."""
        if self.backend.draft_version(draft.id) == draft.version:
            return
        stored = self.backend.load_draft(draft.id)
        if stored is not None:
            adopt(draft, stored)

    # ---------- changes ----------

    def create(self, base: str) -> Draft:
        if not self.known(base):
            raise KeyError(base)
        draft = Draft(uuid.uuid4().hex, base, self.base_building(base)["building"]["name"])
        self.backend.insert_draft(draft)
        with self.lock:
            self.drafts[draft.id] = draft
        return draft

    def create_import(self, building: dict) -> Draft:
        """A draft on a building the Creator made: stored as a private base `import/<id>` (not in the catalogue, not
        listed) until the draft is saved."""
        import_id = uuid.uuid4().hex
        self.backend.insert_import(import_id, building)
        base = IMPORT_PREFIX + import_id
        self.bases[base] = building
        draft = Draft(uuid.uuid4().hex, base, building["building"]["name"])
        self.backend.insert_draft(draft)
        with self.lock:
            self.drafts[draft.id] = draft
        return draft

    def building(self, draft: Draft) -> dict:
        key = (draft.id, draft.version)
        if key not in self.cache:
            self.cache = {k: v for k, v in self.cache.items() if k[0] != draft.id}  # one cached version per draft
            self.cache[key] = apply_steps(self.base_building(draft.base), draft.steps)
        return self.cache[key]

    def plan(self, draft: Draft) -> dict:
        """Vector plan of the draft (core/floorplan.py, what PlanView draws), centred on the *base* building's
        footprint so the preview stays put while outlines change."""
        base = self.base_building(draft.base)
        xs = [x for space in base["spaces"] for x, _ in space["polygon"]]
        ys = [y for space in base["spaces"] for _, y in space["polygon"]]
        center = [round((min(xs) + max(xs)) / 2, 2), round(-(min(ys) + max(ys)) / 2, 2)]
        with self.draft_lock(draft.id):
            return export_plan(BuildingMap(self.building(draft)), center)

    def issues(self, draft: Draft) -> list[dict]:
        if self.import_id(draft.base):  # an imported building's own problems stay errors
            return validate(self.building(draft))
        return validate(self.building(draft), base=self.base_building(draft.base))

    def change(self, draft: Draft, edit) -> Draft:
        """Run `edit(draft) -> (steps, building or None)` on the latest stored draft and store the result as the next
        version. A save that loses a race to another instance is redone on the new state; the last loss raises
        Conflict."""
        with self.draft_lock(draft.id):  # overlapping requests (fast drags) each build on the latest state
            for attempt in range(SAVE_ATTEMPTS):
                self.sync(draft)
                steps, building = edit(draft)
                changed = Draft(draft.id, draft.base, draft.name, steps, draft.version + 1)
                try:
                    self.backend.save_draft(changed, draft.version)
                except Conflict:
                    if attempt == SAVE_ATTEMPTS - 1:
                        raise
                    continue
                adopt(draft, changed)
                if building is not None:
                    self.cache[(draft.id, draft.version)] = building
                return draft
        raise AssertionError("unreachable")

    def apply(self, draft: Draft, ops: list[dict], expected_version: int | None = None) -> Draft:
        """Apply `ops` as one undo step; raises EditError (and stores nothing) if any op fails, or if the draft is no
        longer at `expected_version` (a proposal made against an older draft)."""
        if not ops:
            raise EditError("no ops given")

        def edit(current: Draft) -> tuple[list, dict]:
            if expected_version is not None and current.version != expected_version:
                raise EditError("the draft changed since this proposal; ask again")
            building = self.building(current)
            for operation in ops:
                building = apply_op(building, operation)
            return [*current.steps, copy.deepcopy(ops)], building

        return self.change(draft, edit)

    def undo(self, draft: Draft) -> Draft:
        def edit(current: Draft) -> tuple[list, None]:
            if not current.steps:
                raise EditError("nothing to undo")
            return current.steps[:-1], None

        return self.change(draft, edit)

    def save(self, draft: Draft, name: str) -> str:
        """Store the draft as a new building `user/<slug>` (a free slug: `-2`, `-3`, … if taken) and return its id."""
        name = name.strip() or draft.name
        with self.draft_lock(draft.id):
            self.sync(draft)
            building, steps = copy.deepcopy(self.building(draft)), copy.deepcopy(draft.steps)
        stem = slugify(name)
        slug, n = stem, 1
        while True:
            if f"{USER_SPLIT}/{slug}" not in self.catalogue:
                source_ref = {"base": draft.base}
                # the plans as the draft has them (adjusted trace, scaled, floors added), else the base's import
                kept = (building["building"].get("source_ref") or {}).get("import")
                if kept is None and self.import_id(draft.base):
                    kept = self.base_building(draft.base)["building"]["source_ref"].get("import")
                if kept is not None:
                    source_ref["import"] = kept
                old = draft.base.removeprefix(f"{USER_SPLIT}/") if draft.base.startswith(f"{USER_SPLIT}/") else None
                location = building["building"].get("location")
                if location and old:  # a positioned building saved again: the new save stands where the old one did
                    location["supersedes"] = old
                building["building"].update({"id": slug, "name": name,
                                             "source": "imported" if self.import_id(draft.base) else "edited",
                                             "source_ref": source_ref, "split": USER_SPLIT})
                if self.backend.insert_building(slug, name, draft.base, building, steps):
                    break
            n += 1
            slug = f"{stem}-{n}"
        with self.lock:
            return self.register(slug, name)

    def state(self, draft: Draft) -> dict:
        with self.draft_lock(draft.id):
            return {"draft": {"id": draft.id, "base": draft.base, "name": draft.name, "steps": len(draft.steps)},
                    "building": strip_references(self.building(draft)), "issues": self.issues(draft)}

    def references(self, draft: Draft) -> list[dict]:
        """The import's straightened plan per floor (core/plan_import/reference.py), for Edit mode's reference
        panel: [{"floor_id", "level", "image", "transform"}] by level; [] for buildings that did not come from an
        import. Kept through saves, as the draft has them (save keeps the draft's `source_ref.import`)."""
        with self.draft_lock(draft.id):
            building = self.building(draft)
        floors = ((building["building"].get("source_ref") or {}).get("import") or {}).get("floors") or {}
        by_level = {floor["level"]: floor["id"] for floor in building["floors"]}
        found = []
        for level, notes in floors.items():
            reference = notes.get("reference")
            if reference and int(level) in by_level:
                found.append({"floor_id": by_level[int(level)], "level": int(level), **reference})
        return sorted(found, key=lambda item: item["level"])


def adopt(draft: Draft, other: Draft) -> None:
    """Make `draft` (the object Builders and requests hold) equal to `other`."""
    draft.base, draft.name, draft.steps, draft.version = other.base, other.name, other.steps, other.version
