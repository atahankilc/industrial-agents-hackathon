"""Edit-mode drafts and saved buildings, local store (docs/superpowers/specs/2026-10-24-builder-edit-mode-design.md §3).

A draft is a base catalogue building + steps of edit ops (core/edits.py); it is persisted as
`<root>/.drafts/<id>.json` after every change, so it survives a restart. Saving writes the materialised building
to `<root>/<slug>/building.json` (+ `draft.json` with base, name and steps) and adds `user/<slug>` to the shared
catalogue, so sessions, the Guide and the point cloud use it like any dataset building. Saved buildings in `root`
are registered in the catalogue when the store starts. Draft ids are uuid4 hex and checked against a regex before
any path is built from them; slugs are built from the name by us, never taken as a path.

The root defaults to `data/user/` (gitignored). The dataset under `data/train|dev|test` is only ever read."""

import copy
import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.building_map import BuildingMap
from core.edits import EditError, apply_op, apply_steps
from core.floorplan import export_plan
from core.validate import validate

DRAFT_ID = re.compile(r"^[0-9a-f]{32}$")
USER_SPLIT = "user"


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


class DraftStore:
    def __init__(self, root: Path, catalogue: dict[str, dict]) -> None:
        self.root = Path(root)
        self.catalogue = catalogue
        self.lock = threading.Lock()  # the dicts and the catalogue
        self.draft_locks: dict[str, threading.Lock] = {}  # one per draft: a change reads and writes it atomically
        self.drafts: dict[str, Draft] = {}
        self.cache: dict[tuple[str, int], dict] = {}
        self.bases: dict[str, dict] = {}
        for file in sorted(self.root.glob("*/building.json")):
            name = json.loads(file.read_text(encoding="utf-8"))["building"]["name"]
            self.register(file.parent.name, name)

    # ---------- lookup ----------

    def register(self, slug: str, name: str) -> str:
        building_id = f"{USER_SPLIT}/{slug}"
        self.catalogue[building_id] = {"id": building_id, "split": USER_SPLIT, "name": name, "path": self.root / slug}
        return building_id

    def base_building(self, base: str) -> dict:
        if base not in self.bases:
            path = Path(self.catalogue[base]["path"]) / "building.json"
            self.bases[base] = json.loads(path.read_text(encoding="utf-8"))
        return self.bases[base]

    def draft_lock(self, draft_id: str) -> threading.Lock:
        with self.lock:
            return self.draft_locks.setdefault(draft_id, threading.Lock())

    def draft_file(self, draft_id: str) -> Path:
        return self.root / ".drafts" / f"{draft_id}.json"

    def get(self, draft_id: str) -> Draft | None:
        if not DRAFT_ID.match(draft_id):
            return None
        with self.lock:
            if draft_id in self.drafts:
                return self.drafts[draft_id]
            file = self.draft_file(draft_id)
            if not file.exists():
                return None
            draft = Draft(**json.loads(file.read_text(encoding="utf-8")))
            if draft.base not in self.catalogue:
                return None
            self.drafts[draft_id] = draft
            return draft

    # ---------- changes ----------

    def create(self, base: str) -> Draft:
        if base not in self.catalogue:
            raise KeyError(base)
        draft = Draft(uuid.uuid4().hex, base, self.base_building(base)["building"]["name"])
        self.store(draft)
        return draft

    def store(self, draft: Draft) -> None:
        file = self.draft_file(draft.id)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(asdict(draft)), encoding="utf-8")
        with self.lock:
            self.drafts[draft.id] = draft

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
        return validate(self.building(draft), base=self.base_building(draft.base))

    def apply(self, draft: Draft, ops: list[dict], expected_version: int | None = None) -> Draft:
        """Apply `ops` as one undo step; raises EditError (and stores nothing) if any op fails, or if the draft is no
        longer at `expected_version` (a proposal made against an older draft)."""
        if not ops:
            raise EditError("no ops given")
        with self.draft_lock(draft.id):  # overlapping requests (fast drags) each build on the latest state
            if expected_version is not None and draft.version != expected_version:
                raise EditError("the draft changed since this proposal; ask again")
            building = self.building(draft)
            for operation in ops:
                building = apply_op(building, operation)
            draft.steps.append(copy.deepcopy(ops))
            draft.version += 1
            self.cache[(draft.id, draft.version)] = building
            self.store(draft)
        return draft

    def undo(self, draft: Draft) -> Draft:
        with self.draft_lock(draft.id):
            if not draft.steps:
                raise EditError("nothing to undo")
            draft.steps.pop()
            draft.version += 1
            self.store(draft)
        return draft

    def save(self, draft: Draft, name: str) -> str:
        """Write the draft as a new building `user/<slug>` and return its catalogue id."""
        name = name.strip() or draft.name
        with self.lock:
            stem = slugify(name)
            slug, n = stem, 1
            while f"{USER_SPLIT}/{slug}" in self.catalogue or (self.root / slug).exists():
                n += 1
                slug = f"{stem}-{n}"
            (self.root / slug).mkdir(parents=True)
        building = copy.deepcopy(self.building(draft))
        building["building"].update({"id": slug, "name": name, "source": "edited", "source_ref": {"base": draft.base},
                                     "split": USER_SPLIT})
        (self.root / slug / "building.json").write_text(json.dumps(building, indent=1), encoding="utf-8")
        (self.root / slug / "draft.json").write_text(
            json.dumps({"base": draft.base, "name": name, "steps": draft.steps}), encoding="utf-8")
        with self.lock:
            return self.register(slug, name)

    def state(self, draft: Draft) -> dict:
        with self.draft_lock(draft.id):
            return {"draft": {"id": draft.id, "base": draft.base, "name": draft.name, "steps": len(draft.steps)},
                    "building": self.building(draft), "issues": self.issues(draft)}
