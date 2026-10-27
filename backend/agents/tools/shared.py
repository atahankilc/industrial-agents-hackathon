"""Limits and phrases several tool groups use."""

MAX_RESULTS = 15
MAX_GUESSES = 3  # rooms the Guide may name as where the user might be (suggest_my_location)
MAX_MAYBE_HERE = 8  # rooms the app marks as where the user might be (entrances of a big building: the first 8)
# Kit README: some Swiss Dwellings floors are centred per floor rather than aligned (84 of 108 multi-floor Swiss
# buildings have every floor's space-bbox centre within 2 m of the origin on each axis; 82 with a Euclidean 2 m
# radius), so "directly above/below" is meaningless there.
UNALIGNED_SOURCES = {"swiss_dwellings"}
# What propose_change adds from compare_routes, so a proposal already says who loses access and how much longer.
IMPACT_KEYS = ("from", "reachable_rooms_before", "reachable_rooms_after", "lost_access_count",
               "lost_access_by_floor", "longer_routes_count", "max_extra_m")
HERE = {"here", "me", "my location", "my position", "current location", "where i am", "where i am now"}
