"""Tools that drive the app: highlights, the user's location, the route card, Edit mode and settings."""



from backend.agents import places
from backend.core.directions import guidance, maneuvers
from backend.core.building_map import OUTSIDE, MapError

from backend.agents.tools.shared import HERE, MAX_GUESSES, MAX_MAYBE_HERE



class MapTools:
    def tool_show_on_map(self, space_ids: list[str] | None = None, asset_ids: list[str] | None = None) -> dict:
        """Rooms, and items (an asset id or exact name; also accepted among space_ids), shown as the answer."""
        rooms, items = [], []
        for item in [*(space_ids or ()), *(asset_ids or ())]:
            asset = self.asset_ref(item)
            if asset is not None:
                items.append(asset)
            else:
                rooms.append(self.resolve(item))
        self.highlight(rooms, items)
        return {"shown": rooms + items}

    def start_of(self, reference: str, outside: bool = True) -> str:
        """`stop` for where the user is: a phrase that fits several rooms ("I'm in the kitchen") marks them all as
        where they might be (`maybe_here`, drawn apart from the answer), so they can tap theirs. `outside=False`
        (a position, not a route start): "outside" is no space and gets resolve's error."""
        try:
            return self.stop(reference) if outside else self.resolve(reference)
        except MapError as error:
            found = [] if reference.strip().lower() in HERE else places.candidates(self.building, reference)
            if len(found) < 2:
                raise
            self.maybe_here(found, "guide")
            raise MapError(f"{error} The app marks these rooms as where the user might be; they can also tap theirs.") from None

    def tool_set_my_location(self, place: str) -> dict:
        """The user said where they are: that space is "here" from now on, and the app puts its "you are here"
        figure there (event `location`) and zooms to it."""
        space_id = self.start_of(place, outside=False)
        location = self.set_location(space_id)
        if self.emitting:
            self.events.append({"type": "location", "space_id": space_id})
        return {"location": location, "note": "The app now shows the user here; pass \"here\" as the start."}

    def maybe_here(self, space_ids: list[str], source: str) -> None:
        """Mark on the user's map where they might be (event `maybe_here`, `source` "guide" or "entrances"): the app
        shows these rooms after the answer, and a tap on one puts the "you are here" figure there."""
        if self.emitting and space_ids:
            self.events.append({"type": "maybe_here", "space_ids": list(dict.fromkeys(space_ids))[:MAX_MAYBE_HERE],
                                "source": source})

    def entrance_rooms(self) -> list[str]:
        """The rooms the building's entrances open into, once each."""
        return list(dict.fromkeys(self.building.other_side(opening, OUTSIDE) for opening in self.building.openings.values()
                                  if OUTSIDE in opening["space_ids"]))

    def tool_suggest_my_location(self, rooms: list[str] | None = None) -> dict:
        """The user's position is needed but not known: mark where they might be — the rooms the Guide names (from
        their words or a photo), else the entrances — so they can tap the right one."""
        guessed = list(dict.fromkeys(self.resolve(room) for room in rooms or []))[:MAX_GUESSES]
        if guessed:
            self.maybe_here(guessed, "guide")
            return {"shown": [self.space_summary(space_id) for space_id in guessed],
                    "note": "The app marks these rooms; ask which one they are in (they can also tap it)."}
        entrances = self.entrance_rooms()
        if not entrances:
            return {"error": "This building has no entrances in the data; ask where they are."}
        self.maybe_here(entrances, "entrances")
        return {"shown": [self.space_summary(space_id) for space_id in entrances[:MAX_MAYBE_HERE]],
                "note": "The app marks the entrances; ask where they are (they can also tap one)."}

    def shown_route(self) -> dict | None:
        """The last route event, while it is still on the app's map (no `route_end` after it)."""
        for event in reversed(self.events):
            if event["type"] == "route_end":
                return None
            if event["type"] == "route":
                return event
        return None

    def route_card(self) -> list[dict]:
        """The steps of the app's route bar for the last route shown (backend/core/directions.guidance, as
        backend/api/sessions.py sends them with the route event); [] when there is none."""
        route = self.shown_route()
        if route is None:
            return []
        try:
            return maneuvers(guidance(self.building, route.get("space_path") or [], route.get("element_path") or []))
        except (KeyError, StopIteration):  # path no longer valid on this building
            return []

    def tool_show_route_step(self, step: int) -> dict:
        """Move the app's step card (and the map) to step `step` (1-based, the card's numbering) of the route the
        user is following (event `route_step`)."""
        steps = self.route_card()
        if not steps:
            return {"error": "No route is on the map."}
        if not 1 <= int(step) <= len(steps):
            return {"error": f"The route has steps 1 to {len(steps)}."}
        if self.emitting:
            self.events.append({"type": "route_step", "index": int(step) - 1})
        return {"shown": int(step), "of": len(steps), "text": steps[int(step) - 1]["text"]}

    def tool_end_route(self, arrived: bool = False, place: str | None = None) -> dict:
        """Take the route off the app's map and end its step guide (event `route_end`). `arrived`: the user is at
        its destination, which becomes "here"; else `place`, where they say they are, if given."""
        route = self.shown_route()
        if route is None:
            return {"error": "No route is on the map."}
        if place:
            space_id = self.resolve(place)
        else:
            last = (route.get("space_path") or [None])[-1]
            space_id = last if arrived and last in self.building.spaces else None
        location = self.set_location(space_id) if space_id else None
        if self.emitting:
            self.events.append({"type": "route_end", "arrived": bool(arrived),
                                **({"space_id": space_id} if space_id else {})})
        return {"ended": True, "location": location,
                "note": "The route is off the map." + (" The app now shows the user here." if location else "")}

    def tool_open_edit_mode(self, request: str | None = None) -> dict:
        """Switch the app to its Edit mode (frontend/src/edit/), where the Builder (backend/agents/builder.py) takes the
        request on a draft copy; this session's building is not changed."""
        wanted = (request or "").strip() or None
        if self.emitting:
            self.events.append({"type": "edit_mode", "request": wanted})
        return {"opened": True, "request": wanted,
                "note": "The app now shows the Edit mode; its Builder takes the request from here, on a copy."}

    def tool_open_building_settings(self) -> dict:
        """Open the app's Building settings (frontend/src/access/BuildingSettings.tsx, admin only): Access
        (who may enter which rooms), Members and Objects. Personal preferences are not there: they go through
        set_preference or the app's Preferences sheet. The app opens it for the building's admin and says why not
        to anyone else; this session's building is not changed."""
        if self.emitting:
            self.events.append({"type": "settings"})
        return {"opened": True, "note": "The app now shows the Building settings (admins only; it tells anyone "
                                        "else that it needs the admin account)."}

    def asset_ref(self, reference: str) -> str | None:
        if reference in self.building.assets:
            return reference
        wanted = reference.strip().lower()
        named = [a["id"] for a in self.building.assets.values() if a["name"].lower() == wanted]
        return named[0] if len(named) == 1 else None
