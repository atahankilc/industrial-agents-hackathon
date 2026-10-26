"""The Guide's python tool: model code runs against the open building (the BuildingMap, the canonical route and
solver helpers, shapely, networkx) and gets back what it printed (agent/tools.py `compute`).

Moved out of agent/solver_agent.py (archived 2026-10-26 with the benchmark code). The sandbox (restricted builtins, a
module whitelist, a time limit) guards against accidents, not against a hostile model."""

import builtins
import io
import math
import signal
import threading
import traceback
from collections import Counter

from core import solvers_v1
from core.building_map import BuildingMap
from core.route_query import resolve_place, route_query

CODE_TIME_LIMIT_S = 30
MAX_OUTPUT_CHARS = 6000
ALLOWED_MODULES = {"math", "statistics", "collections", "itertools", "functools", "json", "re", "heapq",
                   "shapely", "networkx"}
SAFE_BUILTINS = {name: getattr(builtins, name)
                 for name in ("abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
                              "frozenset", "getattr", "hasattr", "int", "isinstance", "iter", "len", "list", "map",
                              "max", "min", "next", "pow", "range", "repr", "reversed", "round", "set", "slice",
                              "sorted", "str", "sum", "tuple", "type", "zip", "Exception", "ValueError",
                              "KeyError", "TypeError", "IndexError", "ZeroDivisionError", "StopIteration")}


def namespace(bmap: BuildingMap) -> dict:
    """What the model's code can see: the building, helpers over the canonical functions, a few modules."""
    from shapely.geometry import Point, Polygon
    import networkx as nx

    def floor_id(floor: str | int) -> str:
        for identifier, item in bmap.floors.items():
            if floor in (identifier, item["level"]) or str(floor).strip().lower() == item["name"].lower():
                return identifier
        raise KeyError(f"No floor '{floor}'. Floors: {[item['name'] for item in bmap.floors.values()]}")

    def spaces(floor: str | int | None = None, room_type: str | None = None, type: str | None = None) -> list[dict]:
        wanted_floor = floor_id(floor) if floor is not None else None
        return [space for space in bmap.spaces.values()
                if (wanted_floor is None or space["floor_id"] == wanted_floor)
                and (room_type is None or space["room_type"] == room_type)
                and (type is None or space["type"] == type)]

    def place(phrase: str, floor: str | int | None = None, item: bool = False) -> list[str]:
        return resolve_place(bmap, phrase, floor_id(floor) if floor is not None else None, is_item=item)

    def stop(reference: str) -> list[str]:
        found = place(reference)
        if not found:
            raise KeyError(f"No place matches '{reference}'")
        return found

    def route(start: str, destination: str, stops: list[str] | tuple[str, ...] = (), step_free: bool = False,
              forklift: bool = False, min_width: float | None = None, closed: list[str] | tuple[str, ...] = ()) -> dict:
        return route_query(bmap, [stop(start), *[stop(item) for item in stops], stop(destination)],
                           step_free=step_free, forklift=forklift, min_width=min_width, closed=closed,
                           include_steps=False)

    def solve(kind: str, **inputs: object) -> dict:
        return solvers_v1.solve(bmap, kind, inputs)

    def polygon(space_id: str) -> Polygon:
        return Polygon(bmap.spaces[space_id]["polygon"])

    def describe(space_id: str) -> str:
        space = bmap.spaces[space_id]
        return f"{space['name']} ({space['type']}, {space['room_type']}, {bmap.floor_name(space['floor_id'])})"

    def safe_import(name: str, *args: object, **kwargs: object):
        if name.split(".")[0] not in ALLOWED_MODULES:
            raise ImportError(f"Module '{name}' is not available here; allowed: {sorted(ALLOWED_MODULES)}")
        return __import__(name, *args, **kwargs)

    return {
        "__builtins__": {**SAFE_BUILTINS, "__import__": safe_import},
        "b": bmap, "spaces": spaces, "floor_id": floor_id, "area": lambda space_id: polygon(space_id).area,
        "polygon": polygon, "place": place, "route": route, "solve": solve, "describe": describe,
        "math": math, "Counter": Counter, "Polygon": Polygon, "Point": Point, "nx": nx,
    }


def run_code(code: str, scope: dict) -> dict:
    """Execute model code in `scope`; stdout and the error (if any), under a time limit on the main thread."""
    output = io.StringIO()
    scope["print"] = lambda *values, sep=" ", end="\n": output.write(sep.join(str(value) for value in values) + end)
    timed = threading.current_thread() is threading.main_thread()
    previous = None
    if timed:
        def expire(signum, frame):
            raise TimeoutError(f"code ran longer than {CODE_TIME_LIMIT_S} s")

        previous = signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, CODE_TIME_LIMIT_S)
    error = None
    try:
        exec(compile(code, "<python tool>", "exec"), scope)  # noqa: S102 — the sandbox is the point of this tool
    except BaseException as caught:  # noqa: BLE001 — every failure goes back to the model
        if isinstance(caught, KeyboardInterrupt):
            raise
        error = "".join(traceback.format_exception_only(type(caught), caught)).strip()
        frames = [line for line in traceback.format_tb(caught.__traceback__) if "<python tool>" in line]
        if frames:
            error = frames[-1].strip() + "\n" + error
    finally:
        if timed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    text = output.getvalue()
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n… cut ({len(text)} characters in all; print less)"
    return {"output": text, **({"error": error} if error else {})}
