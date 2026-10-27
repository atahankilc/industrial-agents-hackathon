"""BuildingSession: one conversation's building and state; its tools come from the mixins next to this module."""

import copy
import itertools
from pathlib import Path

from shapely.geometry import Point

from backend.agents import places
from backend.core.building_map import OUTSIDE, BuildingMap, MapError
from backend.core.route_models import KIT
from backend.core.solvers.geometry import polygon

from backend.agents.tools.changes import ChangeTools
from backend.agents.tools.definitions import (CAMPUS_TOOLS, LIVE_STATUS, PREFERENCE_SET_PROFILE, SEND_OBJECT,
                                              SET_PREFERENCE, TOOL_DEFINITIONS)
from backend.agents.tools.live import LiveTools
from backend.agents.tools.lookup import LookupTools
from backend.agents.tools.map import MapTools
from backend.agents.tools.nearby import NearbyTools
from backend.agents.tools.changes import Change
from backend.agents.tools.profile import ProfileTools, RoutingProfile
from backend.agents.tools.routing import RoutingTools
from backend.agents.tools.shared import HERE, MAX_RESULTS


class BuildingSession(LookupTools, RoutingTools, ProfileTools, LiveTools, ChangeTools, MapTools, NearbyTools):
    def __init__(self, building: BuildingMap) -> None:
        # The session owns a private copy: applied changes never leak into other sessions or cached maps.
        self.building = BuildingMap(copy.deepcopy(building.data))
        self.profile = RoutingProfile()
        self.pending: dict[str, Change] = {}
        self.applied: list[Change] = []
        self.snapshots: dict[str, tuple[BuildingMap, BuildingMap]] = {}  # applied change id → (before, after)
        self.events: list[dict] = []
        self.emitting = True  # off while predicting, so hypothetical routes never reach the UI
        self.last_route: dict | None = None
        self.route_model = KIT  # kit 1.1.0 route model ("geodesic" is an alias since 1.1.0)
        self._ids = itertools.count(1)
        # Access mode only (backend/api/access.py): names of spaces/assets this viewer may not see; the building above
        # is already a copy without them (backend/core/access.py). Empty everywhere else, so nothing changes.
        self.restricted_names: set[str] = set()
        # Access mode only: remembered preferences. Off = the tool list and every route exactly as before.
        self.preferences_enabled = False
        self.auto_capture = True  # the user lets the Guide remember what they say (settings switch)
        self.guide_preferences: dict = {}  # GUIDE_PREFERENCES values (language, reply_style, voice)
        # Access mode, admin only: (object name or id, destination) → dispatch result (backend/api/fleet.py).
        self.object_dispatch = None
        # Where the user is, from the app's "you are here" figure: {"space_id", "name", "floor"} (+ "point", where
        # in the room it stands) or None. "here" as a place means this space (HERE), so the Guide never has to ask.
        self.user_location: dict | None = None
        # Buildings nearby (backend/agents/campus.py), set by the backend for buildings with a real position; None = none.
        self.campus = None
        # The living building (backend/api/live/): what connected things report right now (`state()` → obstacles,
        # hazards; `devices()` → their list), set by the backend while the building's live world runs; None = none,
        # and every route is the plain route model.
        self.live = None

    @classmethod
    def load(cls, directory: Path) -> "BuildingSession":
        return cls(BuildingMap.load(directory))

    def call(self, name: str, arguments: dict) -> dict:
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool '{name}'"}
        try:
            result = handler(**arguments)
        except KeyError as error:
            result = {"error": str(error.args[0]) if error.args else "Unknown id"}
        except (MapError, ValueError, TypeError) as error:
            result = {"error": str(error)}
        if self.restricted_names and ("error" in result or result.get("total") == 0):
            named = self.restricted_hit(arguments)
            if named:
                return {"error": "restricted", "restricted": named,
                        "message": f"'{named}' is in a restricted area this user may not enter or see. Say so "
                                   "without any detail about it and offer a public place instead."}
        return result

    def restricted_hit(self, arguments: dict) -> str | None:
        """The first argument phrase that names a restricted space or asset (whole name, or a word run of ≥ 3
        letters inside one)."""
        phrases = []
        for value in arguments.values():
            phrases += value if isinstance(value, list) else [value]
        for phrase in phrases:
            if not isinstance(phrase, str) or len(phrase.strip()) < 3:
                continue
            lowered = phrase.strip().lower()
            if any(lowered == name or lowered in name or name in lowered for name in self.restricted_names):
                return phrase
        return None

    def space_summary(self, space_id: str) -> dict:
        space = self.building.spaces[space_id]
        return {
            "id": space_id,
            "name": space["name"],
            "ref": space.get("ref"),
            "room_type": space["room_type"],
            "floor": self.building.floor_name(space["floor_id"]),
        }

    def stop(self, reference: str) -> str:
        return OUTSIDE if reference == OUTSIDE else self.resolve(reference)

    def resolve(self, reference: str) -> str:
        """One space id for a phrase, else MapError listing the candidates or near-miss names (backend/agents/places.py).
        "here" / "my location" is the space of the app's "you are here" figure."""
        if reference.strip().lower() in HERE:
            if self.user_location is None:
                # every time (the app reads only this turn's events, and takes the last of them)
                entrances = self.entrance_rooms()
                self.maybe_here(entrances, "entrances")
                marked = " (the app marks the entrances as places they might be)" if entrances and self.emitting else ""
                raise MapError(f"The user's position is not known; ask where they are{marked}.")
            return self.user_location["space_id"]
        found = places.candidates(self.building, reference)
        if len(found) != 1:
            raise MapError(places.problem(self.building, reference, found))
        return found[0]

    def set_location(self, space_id: str | None, point: list[float] | None = None) -> dict | None:
        """The app's "you are here" figure was put down in `space_id` (None = taken away), at `point` (plan metres;
        kept only if it lies in that space). Routes are measured from the space's anchor as always; the point only
        moves where the drawn line starts (`start_point` of a route event, backend/core/routeline.py)."""
        if space_id is None:
            self.user_location = None
            return None
        space = self.building.spaces[space_id]
        self.user_location = {"space_id": space_id, "name": space["name"], "ref": space.get("ref"),
                              "floor": self.building.floor_name(space["floor_id"])}
        if point is not None and polygon(space).buffer(0.05).contains(Point(point[0], point[1])):
            self.user_location["point"] = [round(point[0], 3), round(point[1], 3)]
        return self.user_location

    def start_point(self, space_id: str) -> dict:
        """For a route event starting in `space_id`: {"start_point": the figure's point} when the figure stands
        there, else nothing (the drawn line starts at the anchor)."""
        location = self.user_location or {}
        return {"start_point": location["point"]} if location.get("space_id") == space_id and "point" in location else {}

    def highlight(self, space_ids: list[str], asset_ids: list[str] = ()) -> None:
        """Show these rooms (and items in them) on the user's map, as the answer."""
        if self.emitting and (space_ids or asset_ids):
            spaces = list(dict.fromkeys([*space_ids, *(self.building.assets[a]["space_id"] for a in asset_ids)]))
            self.events.append({"type": "highlight", "space_ids": spaces[:MAX_RESULTS * 2],
                                "asset_ids": list(asset_ids)[:MAX_RESULTS * 2]})

    def tool_definitions(self) -> list[dict]:
        """TOOL_DEFINITIONS, with the preference fields and set_preference only when preferences are on,
        send_object for the building admin, the campus tools for a building with neighbours, and live_status while
        the building is live."""
        campus = CAMPUS_TOOLS if self.campus is not None and self.campus.neighbours() else []
        if self.live is not None:
            campus = [*campus, LIVE_STATUS]
        if not self.preferences_enabled:
            return TOOL_DEFINITIONS + campus if campus else TOOL_DEFINITIONS
        tools = [PREFERENCE_SET_PROFILE if tool["name"] == "set_profile" else tool
                 for tool in TOOL_DEFINITIONS] + [SET_PREFERENCE]
        return (tools + [SEND_OBJECT] if self.object_dispatch is not None else tools) + campus
