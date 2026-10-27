"""The Anthropic tool definitions the Guide is given (BuildingSession.tool_definitions picks per session)."""

from backend.agents.compute import ALLOWED_MODULES
from backend.agents.tools.profile import PRESETS
from backend.core.solvers import SOLVERS

PLACE = {"type": "string", "description": "Space id, room ref, exact room name, or asset name/id; \"here\" = "
         "where the user is (when the app knows it)"}
TOOL_DEFINITIONS: list[dict] = [
    {"name": "building_overview", "description": "Floors, stairs/lifts, entrances, the user's routing profile and "
     "applied changes. Call once at the start.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "search", "description": "Find spaces and assets whose name, ref or type contains every word.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                      "floor_level": {"type": "integer"}}, "required": ["query"]}},
    {"name": "locate", "description": "Where an item is: asset type (plural ok), name or id → rooms and floors.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"},
                      "floor_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "count_assets", "description": "How many assets of a type, on one floor or the whole building.",
     "input_schema": {"type": "object", "properties": {"asset_type": {"type": "string"},
                      "floor_id": {"type": "string"}}, "required": ["asset_type"]}},
    {"name": "room_facts", "description": "Area, centre, shared walls, doors with widths, rooms above/below "
     "(omitted where floors aren't aligned), items in a room.",
     "input_schema": {"type": "object", "properties": {"space": PLACE}, "required": ["space"]}},
    {"name": "find_route", "description": "Shortest walk under the user's profile and current closures: metres, "
     "rooms passed, followable steps (turns, landmarks, rounded metres) and about_m (the rounded total). Routes never pass through production bays (destinations only) or outside "
     "the building; reachable=false + reason means no route under these rules — tell the user so.", "input_schema": {"type": "object", "properties": {
         "start": PLACE, "destination": PLACE, "via": {"type": "array", "items": PLACE}},
         "required": ["start", "destination"]}},
    {"name": "find_nearest", "description": "The nearest place with something (\"nearest toilet\", \"closest "
     "kitchen\", \"a meeting room near me\"): ranks every room holding that item kind (or of that room kind/name) by "
     "walking distance under the user's profile, routes to the nearest (the map shows that route only; the result "
     "is a find_route result) and lists the next two with about_m. Use it instead of several find_route calls. "
     "closed: lifts, stairs, rooms, corridors or doors closed for THIS question only (\"the lift is out of order\"); "
     "use propose_change for lasting closures.",
     "input_schema": {"type": "object", "properties": {
         "start": PLACE, "query": {"type": "string", "description": "item or room kind, e.g. toilet, kitchen"},
         "floor_id": {"type": "string", "description": "only when the user restricts the floor"},
         "closed": {"type": "array", "items": {"type": "string"}}},
         "required": ["start", "query"]}},
    {"name": "compute", "description": "Exact building analytics no other tool covers (the smallest / second-largest "
     "room, how many rooms of a kind, the narrowest door on a route, lists by any criterion). Runs Python over a copy "
     "of the building and returns what it prints. In scope: b (the BuildingMap: b.spaces, b.floors, b.openings, "
     "b.connectors, b.assets, dicts by id), spaces(floor=None, room_type=None, type=None), floor_id(name_or_level), "
     "area(space_id) m², polygon(space_id), place(phrase, floor=None, item=False), route(start, destination, "
     "stops=(), step_free=None, forklift=None, min_width=None, closed=()) — routes exactly as find_route (your route "
     "rules, the user's profile) —, solve(kind, **inputs) (kinds and inputs as the solve tool), describe(space_id), "
     "math, Counter, Polygon, Point, nx; importable: " + ", ".join(sorted(ALLOWED_MODULES)) + ". \"Rooms\" = spaces "
     "with type room. Print only what you need; state only numbers it printed.", "input_schema": {
         "type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "tour", "description": "Visit several places in the given order.", "input_schema": {
        "type": "object", "properties": {"stops": {"type": "array", "items": PLACE}}, "required": ["stops"]}},
    {"name": "reachable_rooms", "description": "Rooms the user can reach from a place under their profile.",
     "input_schema": {"type": "object", "properties": {"start": PLACE, "floor_id": {"type": "string"}},
                      "required": ["start"]}},
    {"name": "solve", "description": "Exact building analytics. kind ∈ " + ", ".join(sorted(SOLVERS)) + ". params "
     "use ids: floor_area_total/largest_room {floor_id, room_type}; shared_walls_count {start}; room_stacked "
     "{start, direction: above|below}; straight_line_3d {first, second}; wide_delivery_count {start, floor_id, "
     "min_width}; errand {start, asset_type, floor_id, room_type}; what_if_door {first, second, floor_id}; "
     "step_free_reachable_count {closed, start, floor_id}.", "input_schema": {"type": "object", "properties": {
         "kind": {"type": "string", "enum": sorted(SOLVERS)}, "params": {"type": "object"}},
         "required": ["kind", "params"]}},
    {"name": "set_profile", "description": "Remember the user's mobility constraints for every later route. "
     "preset: wheelchair or pram = step-free + doors ≥ 0.8 m (assumed); trolley = step-free, also give "
     "min_door_width_m (ask if unknown); no_lifts; forklift = openings ≥ 3 m, no stairs, no pedestrian walkways; "
     "default = clear all constraints. A preset changes only its own "
     "fields; explicit fields override it. The result lists assumed values: name them to the user. When the user "
     "no longer has a constraint, set just that field back (e.g. they can take stairs again: step_free false) in "
     "one call; don't re-set fields they didn't mention.",
     "input_schema": {"type": "object", "properties": {
         "preset": {"type": "string", "enum": list(PRESETS)},
         "step_free": {"type": "boolean", "description": "true = routes must avoid steps and stairs; "
                       "false = stairs are fine"},
         "min_door_width_m": {"type": "number", "description": "narrowest door the user fits through; 0 clears it"},
         "avoid_lifts": {"type": "boolean", "description": "true = never use lifts; false = lifts are fine"},
         "forklift": {"type": "boolean"}}}},
    {"name": "propose_change", "description": "Prepare (not apply) a building change and predict its effect: the "
     "last route before/after and, from that route's start, rooms that lose access and routes that get longer. "
     "Show the summary to the user and apply only after they confirm.", "input_schema": {
         "type": "object", "properties": {"action": {"type": "string", "enum": ["close", "reopen", "add_door"]},
                                          "targets": {"type": "array", "items": {"type": "string"}}},
         "required": ["action", "targets"]}},
    {"name": "apply_change", "description": "Apply a proposed change the user confirmed.", "input_schema": {
        "type": "object", "properties": {"change_id": {"type": "string"}}, "required": ["change_id"]}},
    {"name": "compare_routes", "description": "Before → after a pending or applied change, from a start place "
     "(default: the last route's start, else the main entrance) under the user's profile: rooms that lost access, "
     "routes that got longer and by how many metres.", "input_schema": {"type": "object", "properties": {
         "change_id": {"type": "string"}, "start": PLACE}, "required": ["change_id"]}},
    {"name": "show_on_map", "description": "Highlight rooms and items in the user's map view: the map zooms to "
     "them. search, locate and room_facts already show what they found; call this to show the one(s) you mean.",
     "input_schema": {"type": "object", "properties": {"space_ids": {"type": "array", "items": PLACE},
                                                       "asset_ids": {"type": "array", "items": PLACE}}}},
    {"name": "set_my_location", "description": "The user says where they are now (\"I'm in the lobby\", \"I'm at "
     "Lab 2.17\"): it becomes \"here\" for later routes, and the app puts its you-are-here figure there and zooms to "
     "it.", "input_schema": {"type": "object", "properties": {"place": PLACE}, "required": ["place"]}},
    {"name": "suggest_my_location", "description": "The user's position is needed (e.g. for a route) but not known: "
     "the app marks where they might be after your answer, and they can tap the right one. Give up to 3 rooms they "
     "could be in when their words or a photo point to some; with none, the app marks the entrances. Then ask "
     "where they are.", "input_schema": {"type": "object", "properties": {
         "rooms": {"type": "array", "items": PLACE, "maxItems": 3}}}},
    {"name": "show_route_step", "description": "Move the app's step card to a step of the route the user is "
     "following, numbered as in the [route note]: call it whenever your reply is about a different step than the "
     "one the user is at (they moved on, ask what's next, or ask about a later or earlier step).",
     "input_schema": {"type": "object", "properties": {"step": {"type": "integer", "minimum": 1}},
                      "required": ["step"]}},
    {"name": "end_route", "description": "End the route on the user's map and its step guide: call it when "
     "the user has arrived at the destination (arrived true; that room becomes their position) or wants to stop, "
     "cancel or close the directions (arrived false). place: where they say they are now, if they say it.",
     "input_schema": {"type": "object", "properties": {"arrived": {"type": "boolean"}, "place": PLACE}}},
    {"name": "open_edit_mode", "description": "Switch the app to its Edit mode, where the Builder changes the "
     "building itself on a copy: rename or re-purpose rooms, move or reshape walls, move or widen doors, add, "
     "move or remove items, save as a new building. Pass the user's request in their words (or nothing when they "
     "just want to edit). Not for closing, reopening or adding a door for routing: that is propose_change.",
     "input_schema": {"type": "object", "properties": {"request": {"type": "string"}}}},
    {"name": "open_building_settings", "description": "Open the app's Building settings (admin only): Access (who "
     "may enter which rooms), Members and Objects. Use it when the user asks to see or change the building's "
     "settings, access or members. Only the building's admin can use them; the app says so to anyone else. Not for "
     "the user's personal preferences: use set_preference, or point them to the app's Preferences sheet.",
     "input_schema": {"type": "object", "properties": {}}},
]
# Only for buildings with neighbours (BuildingSession.campus).
CAMPUS_TOOLS = [
    {"name": "search_nearby_buildings", "description": "Search the buildings next to this one (nearest first, with "
     "distances). Use it when something is not in this building before saying it isn't there.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "route_to_building", "description": "Route from a place here to a place in a nearby building: inside "
     "here to the best exit, outside (straight line, rounded), inside there. The app shows the first part and a "
     "Continue button; give the totals and the floors as an overview (no steps). When the user is at the exit or asks to go on / go in, "
     "call open_nearby_building.", "input_schema": {"type": "object", "properties": {
         "start": PLACE, "building": {"type": "string", "description": "nearby building id or name"},
         "destination": {"type": "string", "description": "place in that building"}},
         "required": ["start", "building", "destination"]}},
    {"name": "open_nearby_building", "description": "Open a nearby building in the app. Use it when the user wants "
     "to go into, open, switch to or look at a nearby building, or to go on with a route_to_building route (they are "
     "at the exit, \"continue\", \"let's go in\"): the app then continues that route inside it. Never tell the "
     "user to tap Continue or that you can't open it.",
     "input_schema": {"type": "object", "properties": {
         "building": {"type": "string", "description": "nearby building id or name"}}, "required": ["building"]}},
]

# Access mode only (BuildingSession.preferences_enabled): set_profile with route preferences, and set_preference.
_SET_PROFILE = next(tool for tool in TOOL_DEFINITIONS if tool["name"] == "set_profile")
SCOPE = {"type": "string", "enum": ["global", "building"], "description": "global (default) = everywhere; "
         "building = only in this building, when the user says so (\"here\", \"in this building\")"}
PREFERENCE_SET_PROFILE = {
    "name": "set_profile",
    "description": _SET_PROFILE["description"] + " Route preferences (soft, routes may get a little longer, "
    "say by how much): prefer_lifts, fewer_doors, quiet (avoids noisy rooms like canteens, lobbies, production "
    "halls), avoid_halls (open halls), simple_routes (fewer rooms passed); avoid_room_types = room types never "
    "crossed (start and destination excepted). The app remembers what the user tells you (result `remembered`): "
    "say so in a few words. preset default clears mobility constraints only.",
    "input_schema": {"type": "object", "properties": {
        **_SET_PROFILE["input_schema"]["properties"],
        "avoid_room_types": {"type": "array", "items": {"type": "string"}}, "prefer_lifts": {"type": "boolean"},
        "fewer_doors": {"type": "boolean"}, "quiet": {"type": "boolean"}, "avoid_halls": {"type": "boolean"},
        "simple_routes": {"type": "boolean"}, "scope": SCOPE}},
}
SET_PREFERENCE = {
    "name": "set_preference",
    "description": "Remember how the user wants you to talk (language as an English name, e.g. Turkish; "
    "reply_style brief or detailed; voice true/false) or a favourite place in this building. Call it when the "
    "user states such a wish; the app remembers it (result `remembered`).",
    "input_schema": {"type": "object", "properties": {
        "language": {"type": "string"}, "reply_style": {"type": "string", "enum": ["brief", "detailed"]},
        "voice": {"type": "boolean"}, "favourite": {"type": "string"}, "scope": SCOPE}},
}
LIVE_STATUS = {
    "name": "live_status",
    "description": "Connected things in the building right now (forklifts, AGVs, robots, pallets and carts with tags): "
    "kind, state (moving, loading, left behind…), where, heading to, and `blocking` when it cuts a walkway. Use it for "
    "\"where is the forklift\", \"is anything in the way\", \"what's moving around\". Route results already avoid "
    "what blocks; `simulated: true` means a demo simulation — say so if asked where the data comes from.",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
}
SEND_OBJECT = {
    "name": "send_object",
    "description": "Admin only: send a moving object (robot, forklift, AGV — by name) to a place. The route fits the "
    "object's attributes (width, stairs, lifts); the object receives it as machine steps and the map shows it "
    "moving. reachable=false + reason: tell the admin why. An unknown name lists the building's objects.",
    "input_schema": {"type": "object", "properties": {"object": {"type": "string"}, "destination": PLACE},
                     "required": ["object", "destination"]},
}
