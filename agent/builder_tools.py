"""The Builder agent's tools over an Edit-mode draft (archive/hackathon/superpowers/specs/2026-10-24-builder-edit-mode-design.md §4).

Read-only tools describe the *current* draft building; `propose_edit` dry-runs a list of core/edits.py ops, reports
their effect and the problems they would add (core/validate.py), and parks a `Proposal`. There is no apply tool: a
proposal enters the draft only when the user applies it (backend, `Builder.apply`). Results are compact JSON for
the model; `call` never raises — bad input comes back as `{"error": ...}`."""

from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon

from agent.places import candidates, describe, nearest_names, problem
from backend.drafts import Draft, DraftStore
from core.building_map import BuildingMap
from core.edits import EditError, apply_op, edge_sides
from core.solvers.walls import WALL_TOLERANCE_M, shared_wall_neighbours
from core.validate import validate

MAX_MATCHES = 8


@dataclass
class Proposal:
    id: str
    summary: str
    ops: list[dict]
    draft_version: int  # the draft it was made against; applying on a newer version is refused
    new_problems: list[dict] = field(default_factory=list)
    effect: dict = field(default_factory=dict)
    preview: dict | None = None  # the draft after the ops, as dry-run (the plan's ghost); not sent to the model


def shared_length(edge: dict, near: Polygon) -> float:
    """How much of an edge runs along a (buffered) neighbour — which side of the room the neighbour is on."""
    return near.intersection(LineString([edge["from"], edge["to"]])).length


def r2(xy: list[float]) -> list[float]:
    return [round(xy[0], 2), round(xy[1], 2)]


def bbox(polygon: list[list[float]]) -> list[float]:
    xs, ys = [x for x, _ in polygon], [y for _, y in polygon]
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]


class BuilderTools:
    def __init__(self, store: DraftStore, draft: Draft) -> None:
        self.store = store
        self.draft = draft
        self.pending: dict[str, Proposal] = {}
        self.next_id = 1  # proposal numbers P1, P2, … (stored with the Builder, so they never repeat)

    def building(self) -> dict:
        return self.store.building(self.draft)

    def call(self, name: str, arguments: dict) -> dict:
        method = getattr(self, f"tool_{name}", None)
        if method is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return method(**arguments)
        except TypeError as error:
            return {"error": f"{name}: bad arguments ({error})"}
        except (EditError, KeyError, ValueError) as error:
            return {"error": str(error)}
        except Exception as error:  # a tool must answer, never end the agent's turn with a crash
            return {"error": f"{name} failed: {type(error).__name__}: {error}"}

    # ---------- read-only ----------

    def tool_overview(self) -> dict:
        building = self.building()
        floors = sorted(building["floors"], key=lambda floor: floor["level"])
        errors = [issue for issue in self.store.issues(self.draft) if issue["severity"] == "error"]
        return {
            "name": building["building"]["name"],
            "floors": [{"id": floor["id"], "level": floor["level"], "name": floor["name"],
                        "spaces": sum(space["floor_id"] == floor["id"] for space in building["spaces"])}
                       for floor in floors],
            "spaces": len(building["spaces"]), "openings": len(building["openings"]),
            "assets": len(building["assets"]), "problems": len(errors),
        }

    def tool_find(self, query: str, floor_level: int | None = None) -> dict:
        if query is None or str(query).strip() == "":
            return {"error": "find needs a query (a name, ref like '0.21', type or word)"}
        query = str(query)  # models send refs like 0.21 as numbers
        bmap = BuildingMap(self.building())
        found = candidates(bmap, query)
        if floor_level is not None:
            found = [space_id for space_id in found if bmap.floors[bmap.spaces[space_id]["floor_id"]]["level"] == floor_level]
        assets = [{"id": hit["id"], "name": hit["name"], "in": hit["in"]}
                  for hit in bmap.search(query, floor_level) if hit["kind"] == "asset"][:MAX_MATCHES]
        result: dict = {"matches": [describe(bmap, space_id) for space_id in found[:MAX_MATCHES]], "assets": assets}
        if len(found) > MAX_MATCHES:
            result["more"] = len(found) - MAX_MATCHES
        if not found and not assets:
            result["did_you_mean"] = nearest_names(bmap, query)
        return result

    def resolve(self, bmap: BuildingMap, reference: str) -> str:
        found = candidates(bmap, reference)
        if len(found) != 1:
            raise EditError(problem(bmap, reference, found))
        return found[0]

    def tool_space_info(self, space: str) -> dict:
        building = self.building()
        bmap = BuildingMap(building)
        space_id = self.resolve(bmap, str(space))
        item = bmap.spaces[space_id]
        shape = Polygon(item["polygon"])
        edges = edge_sides(item["polygon"])
        neighbours = []
        for other in shared_wall_neighbours(bmap, space_id, min_length=0.5):
            near = Polygon(bmap.spaces[other["id"]]["polygon"]).buffer(WALL_TOLERANCE_M)
            side = max(edges, key=lambda edge: shared_length(edge, near))["side"]
            neighbours.append({"id": other["id"], "name": other["name"], "shared_m": other["shared_m"], "side": side})
        return {
            "id": space_id, "name": item["name"], "type": item["type"], "room_type": item["room_type"],
            "floor_id": item["floor_id"], "area_m2": round(shape.area, 2), "bbox": bbox(item["polygon"]),
            "edges": [{**edge, "from": r2(edge["from"]), "to": r2(edge["to"])} for edge in edges],
            "neighbours": neighbours,
            "openings": [{"id": opening["id"], "kind": opening["kind"],
                          "to": next((s for s in opening["space_ids"] if s != space_id), space_id),
                          "position": r2(opening["position"]), "width_m": opening["width_m"]}
                         for opening in building["openings"] if space_id in opening["space_ids"]],
            "assets": [{"id": asset["id"], "name": asset["name"], "position": r2(asset["position"])}
                       for asset in building["assets"] if asset["space_id"] == space_id],
        }

    def tool_floor_plan(self, floor_id: str) -> dict:
        building = self.building()
        if floor_id not in {floor["id"] for floor in building["floors"]}:
            return {"error": f"no floor {floor_id!r}; floors: {[floor['id'] for floor in building['floors']]}"}
        return {"floor_id": floor_id, "spaces": [
            {"id": space["id"], "name": space["name"], "type": space["type"], "bbox": bbox(space["polygon"])}
            for space in building["spaces"] if space["floor_id"] == floor_id]}

    # ---------- proposals ----------

    def tool_propose_edit(self, ops: list[dict], summary: str) -> dict:
        if not isinstance(ops, list) or not ops or not all(isinstance(operation, dict) for operation in ops):
            return {"error": "ops must be a non-empty list of {\"op\": name, ...arguments} objects"}
        current = self.building()
        after = current
        for operation in ops:
            after = apply_op(after, operation)
        new_problems = [issue for issue in validate(after, base=current) if issue["severity"] == "error"]
        proposal = Proposal(f"P{self.next_id}", summary, ops, self.draft.version, new_problems,
                            effect(current, after), preview=after)
        self.next_id += 1
        self.pending = {proposal.id: proposal}  # only the newest proposal stays open
        return {"proposal_id": proposal.id, "summary": summary, "effect": proposal.effect,
                "new_problems": [issue["message"] for issue in new_problems], "needs_confirmation": True}


def effect(before: dict, after: dict) -> dict:
    """Area changes of spaces whose outline changed, and element counts added / removed."""
    old = {space["id"]: space for space in before["spaces"]}
    changed = []
    for space in after["spaces"]:
        previous = old.get(space["id"])
        if previous is not None and previous["polygon"] != space["polygon"]:
            changed.append({"id": space["id"], "name": space["name"],
                            "area_before": round(Polygon(previous["polygon"]).area, 2),
                            "area_after": round(Polygon(space["polygon"]).area, 2)})
    added, removed = {}, {}
    for key in ("spaces", "openings", "assets"):
        ids_before = {item["id"] for item in before[key]}
        ids_after = {item["id"] for item in after[key]}
        if ids_after - ids_before:
            added[key] = len(ids_after - ids_before)
        if ids_before - ids_after:
            removed[key] = len(ids_before - ids_after)
    return {"changed_spaces": changed, "added": added, "removed": removed}


BUILDER_TOOLS: list[dict] = [
    {"name": "overview", "description": "The draft building: floors (id, level, name, space count), element counts and "
     "how many validator problems it has now.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "find", "description": "Find rooms and things by name, ref (e.g. '0.21'), type or word. Returns matching "
     "spaces as 'id (name, ref, type, floor)' and matching assets. Several matches → ask the user which one.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "floor_level": {"type": "integer"}}, "required": ["query"]}},
    {"name": "space_info", "description": "One space in detail: area, bbox, its edges (walls) with the compass side "
     "each faces and exact corner coordinates (use these for move_edge), neighbours with the side they are on, doors "
     "and things inside. Accepts an id or a name/ref; ambiguous → error listing the candidates.",
     "input_schema": {"type": "object", "properties": {"space": {"type": "string"}}, "required": ["space"]}},
    {"name": "floor_plan", "description": "Every space on one floor as id, name, type and bbox [minx, miny, maxx, "
     "maxy] — to see the layout.", "input_schema": {"type": "object", "properties": {
         "floor_id": {"type": "string"}}, "required": ["floor_id"]}},
    {"name": "propose_edit", "description": "Dry-run a list of edit ops as ONE change and park it for the user. "
     "Returns the effect (area before/after of changed spaces, elements added/removed) and the new problems it would "
     "add. Does NOT change the draft: the user applies it. A new proposal replaces the previous one.",
     "input_schema": {"type": "object", "properties": {
         "ops": {"type": "array", "items": {"type": "object"}, "description": "ops as {\"op\": name, ...arguments}"},
         "summary": {"type": "string", "description": "one short line the user sees on the Apply card"}},
         "required": ["ops", "summary"]}},
]
